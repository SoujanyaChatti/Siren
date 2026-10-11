"""Live status for any US location, right now.

Per request (cached), SIREN:
  1. asks NWS /points for the location's time zone, nearest town and weather stations
  2. finds nearby river gauges with official NOAA flood categories (NWPS) and pulls their last hours of stage
  3. pulls active NWS alerts for the point and the last hour of rain at the nearest NWS station
  4. runs the same versioned rules engine (with hysteresis warm-up over the past 3 hours) per gauge
  5. builds the same deterministic EN/ES message, plus voice when available

Stateless and per person: it never touches the replay demo. Sources are free and keyless.
"""
from __future__ import annotations

import asyncio
import copy
import math
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from . import messages
from .geo import haversine_m
from .rules.engine import RulesEngine, load_rules, sev_rank
from .settings import settings
from .store import ReadingStore

NWPS = "https://api.water.noaa.gov/nwps/v1"
NWS = "https://api.weather.gov"
SEARCH_KM = 50
MAX_GAUGES = 4
HISTORY = timedelta(hours=3)
STEP = timedelta(minutes=15)
VTEC = {"Flash Flood Warning": "FF.W", "Flash Flood Emergency": "FF.W", "Flood Warning": "FL.W",
        "Flood Advisory": "FA.Y", "Flash Flood Watch": "FF.A", "Flood Watch": "FA.A"}
NO_THRESHOLD = 1e9  # categories NOAA hasn't defined for a gauge can never fire

_cache: dict[str, tuple[float, object]] = {}


class LiveError(Exception):
    def __init__(self, msg: str, status: int = 502):
        super().__init__(msg)
        self.status = status


async def _get(c: httpx.AsyncClient, url: str, ttl: float, **params) -> dict:
    key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]  # type: ignore[return-value]
    r = await c.get(url, params=params or None)
    if r.status_code == 404:
        raise LiveError("not found", 404)
    r.raise_for_status()
    data = r.json()
    _cache[key] = (time.monotonic() + ttl, data)
    if len(_cache) > 2000:
        for k in sorted(_cache, key=lambda k: _cache[k][0])[:500]:
            _cache.pop(k, None)
    return data


def _t(s: str | None) -> datetime | None:
    if not s or s.startswith("0001"):
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _square(lon: float, lat: float, km: float) -> dict:
    dlat = km / 111.0
    dlon = km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    ring = [[lon - dlon, lat - dlat], [lon + dlon, lat - dlat], [lon + dlon, lat + dlat], [lon - dlon, lat + dlat],
            [lon - dlon, lat - dlat]]
    return {"type": "Polygon", "coordinates": [ring]}


def _category(v: float, stages: dict) -> str:
    for k in ("major", "moderate", "minor", "action"):
        if v >= stages[k]:
            return k
    return "below_action"


def _outlook(fc, stages: dict) -> dict | None:
    """Official NWS river forecast: peak stage and when, over the forecast horizon (only where NWS issues one)."""
    if isinstance(fc, Exception) or not fc:
        return None
    now = datetime.now(timezone.utc)
    pts = [(_t(p.get("validTime")), p.get("primary")) for p in fc.get("data", [])]
    pts = [(t, float(v)) for t, v in pts if t and t >= now - timedelta(hours=1) and v is not None and v > -900]
    if not pts:
        return None
    peak_t, peak_v = max(pts, key=lambda x: x[1])
    cat = _category(peak_v, stages)
    return {"peak_ft": round(peak_v, 2), "peak_time": peak_t.isoformat(), "category": cat,
            "issued": fc.get("issuedTime"), "horizon_end": pts[-1][0].isoformat(),
            "series": [{"t": t.isoformat(), "v": v} for t, v in pts][:120],
            "source": "NWS river forecast (NWPS)"}


def _stage(v) -> float:
    return float(v) if v is not None and float(v) > -900 else NO_THRESHOLD


async def _gauges_near(c: httpx.AsyncClient, lat: float, lon: float) -> list[dict]:
    dlat = SEARCH_KM / 111.0
    dlon = SEARCH_KM / (111.0 * max(0.2, math.cos(math.radians(lat))))
    d = await _get(c, f"{NWPS}/gauges", 300, **{"bbox.xmin": round(lon - dlon, 3), "bbox.ymin": round(lat - dlat, 3),
                                                  "bbox.xmax": round(lon + dlon, 3), "bbox.ymax": round(lat + dlat, 3),
                                                  "srid": "EPSG_4326"})
    out = []
    now = datetime.now(timezone.utc)
    for g in d.get("gauges", []):
        obs = (g.get("status") or {}).get("observed") or {}
        vt = _t(obs.get("validTime"))
        if obs.get("primaryUnit") != "ft" or vt is None or now - vt > timedelta(hours=12):
            continue  # gauges without a recent stage in feet can't be judged
        dist = haversine_m(lat, lon, g["latitude"], g["longitude"]) / 1000
        if dist <= SEARCH_KM:
            out.append({**g, "distance_km": round(dist, 1)})
    return sorted(out, key=lambda g: g["distance_km"])[:MAX_GAUGES]


async def _gauge_detail(c: httpx.AsyncClient, g: dict) -> dict | None:
    lid = g["lid"]
    detail, obs, fc_series = await asyncio.gather(_get(c, f"{NWPS}/gauges/{lid}", 86400),
                                                  _get(c, f"{NWPS}/gauges/{lid}/stageflow/observed", 300),
                                                  _get(c, f"{NWPS}/gauges/{lid}/stageflow/forecast", 900),
                                                  return_exceptions=True)
    if isinstance(detail, Exception) or isinstance(obs, Exception):
        return None
    cats = (detail.get("flood") or {}).get("categories") or {}
    stages = {k: _stage((cats.get(k) or {}).get("stage")) for k in ("action", "minor", "moderate", "major")}
    cutoff = datetime.now(timezone.utc) - HISTORY - timedelta(hours=3)
    series = []
    for p in obs.get("data", []):
        t = _t(p.get("validTime"))
        v = p.get("primary")
        if t and t >= cutoff and v is not None and v > -900:
            series.append((t, float(v)))
    forecast = _outlook(fc_series, stages)
    name = detail.get("name") or g["name"]
    return {"station_id": lid, "usgs_id": detail.get("usgsId"), "name": name, "short": {"en": name, "es": name},
            "lat": g["latitude"], "lon": g["longitude"], "distance_km": g["distance_km"],
            "flood_stages_ft": stages, "has_categories": any(v < NO_THRESHOLD for v in stages.values()),
            "flood_stages_source": f"https://water.noaa.gov/gauges/{lid.lower()}",
            "nwps_category": ((g.get("status") or {}).get("observed") or {}).get("floodCategory"),
            "forecast": forecast, "series": sorted(series)}


async def _alerts(c: httpx.AsyncClient, lat: float, lon: float) -> list[dict]:
    d = await _get(c, f"{NWS}/alerts/active", 120, point=f"{lat:.4f},{lon:.4f}")
    out = []
    for f in d.get("features", []):
        p = f["properties"]
        out.append({"id": p.get("id"), "event": p.get("event"), "severity": p.get("severity"),
                    "headline": p.get("headline"), "area": p.get("areaDesc"), "sent": p.get("sent"),
                    "expires": p.get("ends") or p.get("expires"), "instruction": p.get("instruction"),
                    "url": p.get("@id") or f.get("id"), "geometry": f.get("geometry"),
                    "flood_related": "Flood" in (p.get("event") or "")})
    return out


async def _rain(c: httpx.AsyncClient, stations_url: str, lat: float, lon: float) -> dict | None:
    try:
        st = await _get(c, stations_url, 86400)
        feats = st.get("features", [])[:3]
        for f in feats:
            sid = f["properties"]["stationIdentifier"]
            obs = await _get(c, f"{NWS}/stations/{sid}/observations", 600, limit=6)
            for o in obs.get("features", []):
                p = o["properties"]
                v = (p.get("precipitationLastHour") or {}).get("value")
                if v is not None:
                    slon, slat = f["geometry"]["coordinates"]
                    return {"station_id": sid, "name": f["properties"].get("name"), "time": p["timestamp"],
                            "last_hour_in": round(v / 25.4, 2),
                            "distance_km": round(haversine_m(lat, lon, slat, slon) / 1000, 1),
                            "source_url": f"{NWS}/stations/{sid}/observations"}
    except Exception:
        return None
    return None


def _live_rules() -> dict:
    rules = copy.deepcopy(load_rules())
    th = rules["by_id"]["STALE_DATA"]["threshold"]
    th["max_age_minutes"] = th.get("live_max_age_minutes", th["max_age_minutes"])
    return rules


async def status(lat: float, lon: float, lang: str = "en") -> dict:
    if not settings.allow_live_data:
        raise LiveError("Live data is disabled (ALLOW_LIVE_DATA=false)", 503)
    lang = "es" if lang == "es" else "en"
    now = datetime.now(timezone.utc)
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": settings.user_agent,
                                                      "Accept": "application/geo+json, application/json"}) as c:
        try:
            pts = await _get(c, f"{NWS}/points/{lat:.4f},{lon:.4f}", 86400)
        except LiveError as e:
            if e.status == 404:
                raise LiveError("Live status covers the United States (NOAA/USGS/NWS data). This location is outside coverage.", 404)
            raise
        except httpx.HTTPError as e:
            raise LiveError(f"Could not reach the National Weather Service: {e.__class__.__name__}", 502)
        props = pts["properties"]
        tz = props.get("timeZone") or "UTC"
        rel = (props.get("relativeLocation") or {}).get("properties") or {}
        place = ", ".join(x for x in (rel.get("city"), rel.get("state")) if x)
        gauges_raw, alerts, rain = await asyncio.gather(
            _gauges_near(c, lat, lon), _alerts(c, lat, lon), _rain(c, props.get("observationStations", ""), lat, lon),
            return_exceptions=True)
        missing: list[str] = []
        if isinstance(gauges_raw, Exception):
            missing.append("River gauge service (NOAA NWPS) unavailable")
            gauges_raw = []
        if isinstance(alerts, Exception):
            missing.append("NWS alerts unavailable")
            alerts = []
        if isinstance(rain, Exception) or rain is None:
            rain = None
        details = [d for d in await asyncio.gather(*[_gauge_detail(c, g) for g in gauges_raw]) if d]

    # Readings store + official warnings in the rules engine's format
    store = ReadingStore()
    for g in details:
        for t, v in g["series"]:
            store.add({"time": t.isoformat(), "_t": t, "source": "nwps", "station_id": g["station_id"], "metric": "stage_ft",
                       "value": v, "quality": "provisional", "source_url": g["flood_stages_source"]})
    rain_id = rain["station_id"] if rain else "NONE"
    if rain:
        rt = _t(rain["time"])
        store.add({"time": rt.isoformat(), "_t": rt, "source": "nws_obs", "station_id": rain_id, "metric": "rain_in",
                   "value": rain["last_hour_in"], "quality": "provisional", "source_url": rain["source_url"]})
    user_area = _square(lon, lat, 1.0)
    warnings = []
    for a in alerts:
        if a["event"] in VTEC:
            issued, expires = _t(a["sent"]) or now, _t(a["expires"]) or now + timedelta(hours=6)
            warnings.append({"id": a["id"], "event": a["event"], "vtec": VTEC[a["event"]], "issued_at": a["sent"],
                             "expires_at": a["expires"], "_issued": issued,
                             "_expires": expires, "source_url": a["url"],
                             # alerts were requested for this exact point, so zone-based alerts (no polygon) apply here
                             "polygon": a["geometry"] or user_area})

    rules = _live_rules()
    engine = RulesEngine({g["station_id"]: g for g in details}, rules)
    evaluations = []
    for g in [g for g in details if g["has_categories"]]:
        zone = {"properties": {"zone_id": g["station_id"],
                               "name": (f"your area — near {g['name']}" if g["distance_km"] < 1
                                        else f"your area — {g['distance_km']:.0f} km from {g['name']}"),
                               "name_es": (f"su zona — cerca de {g['name']}" if g["distance_km"] < 1
                                           else f"su zona — a {g['distance_km']:.0f} km de {g['name']}"),
                               "gauge": g["station_id"], "rain": rain_id, "roads": []},
                "geometry": user_area}
        t = now - HISTORY
        ev = None
        while t <= now:  # warm up hysteresis over the recent past, ending at "now"
            ev = engine.evaluate_zone(zone, min(t, now), store, warnings)
            t += STEP
        ev = engine.evaluate_zone(zone, now, store, warnings)
        evaluations.append((g, zone, ev))

    gauges_out = []
    for g in details:
        latest = store.latest(g["station_id"], "stage_ft", now)
        def ago(m):
            r = store.latest(g["station_id"], "stage_ft", (latest["_t"] if latest else now) - timedelta(minutes=m))
            return round(latest["value"] - r["value"], 2) if latest and r else None
        ev = next((e for gg, _, e in evaluations if gg is g), None)
        gauges_out.append({
            "station_id": g["station_id"], "usgs_id": g["usgs_id"], "name": g["name"], "lat": g["lat"], "lon": g["lon"],
            "distance_km": g["distance_km"],
            "flood_stages_ft": {k: (None if v >= NO_THRESHOLD else v) for k, v in g["flood_stages_ft"].items()},
            "has_categories": g["has_categories"], "nwps_category": g["nwps_category"], "forecast": g["forecast"],
            "latest": {"time": latest["time"], "value": latest["value"]} if latest else None,
            "age_minutes": round((now - latest["_t"]).total_seconds() / 60) if latest else None,
            "change_30m_ft": ago(30), "change_60m_ft": ago(60),
            "severity": ev.severity if ev else None, "source_url": g["flood_stages_source"],
            "series": [{"t": t.isoformat(), "v": v} for t, v in g["series"] if t >= now - timedelta(hours=6)],
        })

    # Primary = nearest gauge with official categories; your status never improves on silence
    primary = evaluations[0] if evaluations else None
    if primary:
        g, zone, ev = primary
        severity = ev.severity
        results = [{"rule_id": r.rule_id, "fired": r.fired, "inputs": r.inputs} for r in ev.results]
        msg = messages.build_message(lang=lang, severity=severity, zone=zone, results=results, at=now, tz=tz, live=True)
        rules_out = [{"rule_id": r.rule_id, "version": r.version, "fired": r.fired, "raw": r.raw, "held": r.held,
                      "inputs_hash": r.inputs_hash, "description": rules["by_id"][r.rule_id]["description"]}
                     for r in ev.results]
        missing += ev.missing_data
    else:
        ffw = [w for w in warnings if w["vtec"] == "FF.W"]
        severity = "Warning" if ffw else "Unknown"
        msg = _no_gauge_message(lang, severity, place, now, tz)
        rules_out = [{"rule_id": "NWS_FFW", "version": rules["by_id"]["NWS_FFW"]["version"], "fired": bool(ffw),
                      "raw": bool(ffw), "held": False, "inputs_hash": None,
                      "description": rules["by_id"]["NWS_FFW"]["description"]}]
        missing.append(f"Sin medidor de río con niveles oficiales de inundación a menos de {SEARCH_KM} km" if lang == "es"
                       else f"No river gauge with official flood categories within {SEARCH_KM} km")
    outlook = None
    fc_g = [x for x in gauges_out if x["forecast"]]
    if fc_g:
        order = {"below_action": 0, "action": 1, "minor": 2, "moderate": 3, "major": 4}
        top = max(fc_g, key=lambda x: (order[x["forecast"]["category"]], -x["distance_km"]))
        f = top["forecast"]
        when = messages.local_time(_t(f["peak_time"]), lang, tz)
        day = _t(f["peak_time"]).astimezone(ZoneInfo(tz)).strftime("%a %b %d")
        cat_en = {"below_action": "below flood levels", "action": "action stage", "minor": "minor flood stage",
                  "moderate": "moderate flood stage", "major": "major flood stage"}[f["category"]]
        cat_es = {"below_action": "por debajo de niveles de inundación", "action": "nivel de acción",
                  "minor": "inundación menor", "moderate": "inundación moderada", "major": "inundación mayor"}[f["category"]]
        end_day = _t(f["horizon_end"]).astimezone(ZoneInfo(tz)).strftime("%a %b %d")
        cur = top["latest"]["value"] if top["latest"] else None
        if f["category"] == "below_action":
            text = (f"NWS forecast: {top['name']} stays below flood levels through {end_day} (highest {f['peak_ft']:.1f} ft)."
                    if lang == "en" else
                    f"Pronóstico del NWS: {top['name']} se mantiene por debajo de niveles de inundación hasta el {end_day} (máximo {f['peak_ft']:.1f} pies).")
        else:
            verb_en = "rises to" if cur is None or f["peak_ft"] > cur else "stays near"
            verb_es = "sube a" if cur is None or f["peak_ft"] > cur else "se mantiene cerca de"
            text = (f"NWS forecast: {top['name']} {verb_en} {f['peak_ft']:.1f} ft ({cat_en}) around {when} {day}."
                    if lang == "en" else
                    f"Pronóstico del NWS: {top['name']} {verb_es} {f['peak_ft']:.1f} pies ({cat_es}) cerca de las {when} del {day}.")
        outlook = {"gauge": top["station_id"], "category": f["category"], **f, "text": text}
    higher = [x for x in gauges_out[1:] if x["severity"] and sev_rank(x["severity"]) > sev_rank(severity)
              and x["distance_km"] <= 15]

    return {
        "location": {"lat": lat, "lon": lon, "place": place, "tz": tz, "nws_office": props.get("cwa")},
        "checked_at": now.isoformat(), "severity": severity, "card": msg, "text": msg["text"], "language": lang,
        "primary_gauge": gauges_out[0]["station_id"] if primary else None,
        "gauges": gauges_out, "nearby_higher": [x["station_id"] for x in higher],
        "alerts": [{k: v for k, v in a.items() if k != "geometry"} for a in alerts],
        "rain": rain, "rules": rules_out, "missing_data": missing, "outlook": outlook,
        "sources": ["NOAA National Water Prediction Service (gauges, flood categories, forecasts)",
                    "National Weather Service API (alerts, observations)"],
        "caveat": ("Live data is provisional and usually 30–60 minutes behind. Gauges measure the river at one point; "
                   "street flooding can happen away from rivers. Not an official warning system."),
    }


def _no_gauge_message(lang: str, severity: str, place: str, now: datetime, tz: str) -> dict:
    t = messages.local_time(now, lang, tz)
    if lang == "es":
        what = ("El NWS tiene una Advertencia de Inundación Repentina activa aquí." if severity == "Warning"
                else "No hay medidores de río con niveles oficiales de inundación cerca, así que SIREN no puede juzgar el riesgo de río aquí.")
        action = "Evite manejar. Nunca maneje sobre agua. Dé la vuelta, no se ahogue." if severity == "Warning" else "Revise las alertas oficiales abajo y manténgase alerta."
        head = "Advertencia: alerta oficial de inundación" if severity == "Warning" else "Sin datos de río cerca"
        where = place or "su ubicación"
        updated = f"Actualizado {t}".rstrip(".") + "."
    else:
        what = ("The NWS has an active Flash Flood Warning here." if severity == "Warning"
                else "There are no river gauges with official flood levels nearby, so SIREN can't judge river flooding here.")
        action = "Avoid driving. Never drive into water. Turn around, don't drown." if severity == "Warning" else "Check the official alerts below and stay alert."
        head = "Warning: official flood alert" if severity == "Warning" else "No river data nearby"
        where = place or "your location"
        updated = f"Updated {t}."
    sev_word = messages.SEVERITY_WORD[lang][severity]
    text = f"{sev_word}. {what} {action} {updated}"
    return {"language": lang, "severity": severity, "severity_word": sev_word, "headline": head, "what": what,
            "where": where, "action": action, "updated": updated, "source": "NWS", "text": text,
            "word_count": messages.word_count(text), "protected_terms": []}


async def geocode(q: str) -> dict:
    """Place or ZIP -> coordinates. OpenStreetMap Nominatim, with Photon (also OSM) as fallback; cached."""
    q = q.strip()[:120]
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": settings.user_agent}) as c:
        try:
            d = await _get(c, "https://nominatim.openstreetmap.org/search", 86400, q=q, format="json", limit=1,
                           countrycodes="us")
            if d:
                return {"lat": float(d[0]["lat"]), "lon": float(d[0]["lon"]), "label": d[0].get("display_name"),
                        "source": "nominatim"}
        except (httpx.HTTPError, LiveError):
            pass  # rate-limited or down: try the fallback
        try:
            d = await _get(c, "https://photon.komoot.io/api/", 86400, q=q, limit=5)
        except (httpx.HTTPError, LiveError) as e:
            raise LiveError(f"Place search unavailable right now ({e.__class__.__name__}); use your location instead", 502)
        for f in d.get("features", []):
            p = f["properties"]
            if p.get("countrycode", "").upper() == "US":
                lon, lat = f["geometry"]["coordinates"]
                label = ", ".join(x for x in (p.get("name"), p.get("state")) if x)
                return {"lat": lat, "lon": lon, "label": label, "source": "photon"}
    raise LiveError("Place not found (US only)", 404)


def qa_facts(st: dict, lang_unused: str = "en") -> list[dict]:
    """Incident facts for grounded Ask SIREN, from a live status."""
    facts = [{"id": "F1", "en": f"Your area is at {st['severity']} level right now (checked {st['card']['updated']})",
              "es": f"Su zona está en nivel {messages.SEVERITY_WORD['es'][st['severity']]} ahora."}]
    g = next((x for x in st["gauges"] if x["station_id"] == st["primary_gauge"]), None)
    if g and g["latest"]:
        minor = g["flood_stages_ft"].get("minor")
        facts.append({"id": "F2", "en": f"{g['name']} is at {g['latest']['value']:.1f} ft" + (f"; minor flood stage is {minor:.1f} ft." if minor else "."),
                      "es": f"{g['name']} está a {g['latest']['value']:.1f} pies" + (f"; el nivel de inundación menor es {minor:.1f} pies." if minor else ".")})
    fl = [a for a in st["alerts"] if a["flood_related"]]
    if fl:
        facts.append({"id": "F4", "en": f"Official NWS {fl[0]['event']} is active for this location.",
                      "es": f"Hay una alerta oficial del NWS activa aquí ({fl[0]['event']})."})
    return facts


async def photo_check(image: bytes, mime: str, lat: float, lon: float, lang: str = "en") -> dict:
    """Photo depth at the person's current location. Same analyzer, checks and PHOTO_DEPTH_ROAD threshold as the
    replay; the result is returned to that person only (not stored, not broadcast)."""
    from .depth import analyzer
    analysis, check, res = await analyzer.analyze(image, mime)
    rule = load_rules()["by_id"]["PHOTO_DEPTH_ROAD"]
    high = analysis.get("depth_high_in")
    fires = (check["status"] == "verified" and analysis.get("is_road") is not False and high is not None
             and high >= rule["threshold"]["depth_high_in"])
    if analysis.get("depth_in") is None:
        msg = ("Could not estimate depth from this photo. Never drive into water you can't see the bottom of."
               if lang == "en" else "No se pudo estimar la profundidad. Nunca maneje en agua cuyo fondo no puede ver.")
    elif fires:
        msg = (f"About {round(analysis['depth_in'])} inches of water ({round(analysis['depth_low_in'])}–{round(high)} in). "
               "Do not drive here: 12 inches can float most cars. Turn around, don't drown." if lang == "en" else
               f"Unas {round(analysis['depth_in'])} pulgadas de agua ({round(analysis['depth_low_in'])}–{round(high)}). "
               "No maneje aquí: 12 pulgadas pueden hacer flotar la mayoría de los carros. Dé la vuelta, no se ahogue.")
    else:
        msg = (f"About {round(analysis['depth_in'])} inches ({round(analysis['depth_low_in'])}–{round(high)} in). "
               "Still avoid driving or walking through floodwater." if lang == "en" else
               f"Unas {round(analysis['depth_in'])} pulgadas ({round(analysis['depth_low_in'])}–{round(high)}). "
               "Aun así evite manejar o caminar en agua de inundación.")
    return {"analysis": analysis, "checks": check, "do_not_drive": bool(fires), "message": msg,
            "rule": {"id": rule["id"], "version": rule["version"], "description": rule["description"]},
            "ai": res.log(), "lat": lat, "lon": lon}
