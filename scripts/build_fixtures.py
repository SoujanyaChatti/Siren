"""Build SIREN replay fixtures from real public data (run once, with network).

Each area is a config file in scripts/areas/ (gauges, rain stations, bounding box, event window, NWS office).

Sources:
  - USGS Water Data OGC API (continuous / instantaneous values), parameter 00065 gage height
  - NOAA National Water Prediction Service gauge metadata (official flood categories)
  - Iowa Environmental Mesonet (IEM) ASOS archive: NWS airport precipitation (HOU, SGR)
  - IEM storm-based warning archive (NWS HGX warnings issued during the event)
  - OpenStreetMap via Overpass API (facilities)
  - OSRM public demo server (precomputed commute routes)

Usage:  python scripts/build_fixtures.py houston-brays        (config: scripts/areas/<id>.json)
Outputs go to fixtures/areas/<id>/. Hand-made files there (zones.geojson, users.json, scenes.json, area.json)
are not touched. Thresholds in backend/app/rules/rules.yaml are NOT touched either.
"""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
UA = "SIREN-hackathon/0.1 (flood alert demo; contact via repo)"

CFG: dict = {}
START = END = datetime.now(timezone.utc)
GAUGES: list[dict] = []
RAIN: list[dict] = []
BBOX: tuple = ()


def configure(area_id: str) -> Path:
    global CFG, START, END, GAUGES, RAIN, BBOX
    CFG = json.loads((ROOT / "scripts" / "areas" / f"{area_id}.json").read_text())
    START = datetime.fromisoformat(CFG["fetch_start"].replace("Z", "+00:00"))
    END = datetime.fromisoformat(CFG["fetch_end"].replace("Z", "+00:00"))
    GAUGES, RAIN, BBOX = CFG["gauges"], CFG["rain"], tuple(CFG["bbox"])
    out = FIX / "areas" / area_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def get(url: str, data: bytes | None = None, timeout: int = 90) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_gauges() -> tuple[list[dict], list[dict]]:
    meta, readings = [], []
    for g in GAUGES:
        info = json.loads(get(f"https://api.water.noaa.gov/nwps/v1/gauges/{g['station_id']}"))
        cats = info["flood"]["categories"]
        meta.append({
            **g,
            "lat": info["latitude"], "lon": info["longitude"],
            "flood_stages_ft": {k: cats[k]["stage"] for k in ("action", "minor", "moderate", "major")},
            "flood_stages_source": f"https://water.noaa.gov/gauges/{g['station_id'].lower()}",
        })
        url = ("https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items?f=json"
               f"&monitoring_location_id=USGS-{g['usgs_id']}&parameter_code=00065"
               f"&datetime={iso(START)}/{iso(END)}&limit=5000")
        feats = json.loads(get(url))["features"]
        src = f"https://waterdata.usgs.gov/monitoring-location/USGS-{g['usgs_id']}/"
        for f in feats:
            p = f["properties"]
            if p["value"] in (None, ""):
                continue
            t = datetime.fromisoformat(p["time"]).astimezone(timezone.utc)
            readings.append({
                "time": iso(t), "source": "usgs", "station_id": g["station_id"], "metric": "stage_ft",
                "value": float(p["value"]),
                "quality": "verified" if p.get("approval_status") == "Approved" else "provisional",
                "source_url": src,
            })
        print(f"  {g['station_id']}: {len(feats)} stage readings, categories {meta[-1]['flood_stages_ft']}")
    return meta, readings


def build_rain() -> tuple[list[dict], list[dict]]:
    """ASOS p01i is cumulative within each METAR hour (resets after the :5x routine report).
    Convert to increments, then bucket into 15-minute totals."""
    q = urllib.parse.urlencode([
        *[("station", r["station_id"]) for r in RAIN],
        ("data", "p01i"), ("tz", "Etc/UTC"), ("format", "onlycomma"), ("latlon", "yes"),
        ("missing", "M"), ("trace", "0.0001"), ("report_type", "3"), ("report_type", "4"),
        ("year1", (START - timedelta(hours=1)).year), ("month1", (START - timedelta(hours=1)).month),
        ("day1", (START - timedelta(hours=1)).day), ("hour1", (START - timedelta(hours=1)).hour),
        ("year2", END.year), ("month2", END.month), ("day2", END.day), ("hour2", END.hour),
    ])
    text = get(f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?{q}").decode()
    rows = list(csv.DictReader(io.StringIO(text)))
    meta, by_station = [], defaultdict(list)
    for r in rows:
        if r["p01i"] == "M":
            continue
        t = datetime.strptime(r["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
        by_station[r["station"]].append((t, float(r["p01i"]), float(r["lat"]), float(r["lon"])))
    readings = []
    for st in RAIN:
        obs = sorted(by_station[st["station_id"]])
        meta.append({**st, "lat": obs[0][2], "lon": obs[0][3],
                     "source_url": f"https://mesonet.agron.iastate.edu/sites/site.php?station={st['station_id']}&network={st['network']}"})
        buckets: dict[datetime, float] = defaultdict(float)
        prev_cum, prev_hour_key = 0.0, None
        for t, cum, _, _ in obs:
            # METAR hour runs from :54 of previous hour to :53 of this hour
            hour_key = (t + timedelta(minutes=6)).replace(minute=0, second=0)
            if hour_key != prev_hour_key:
                prev_cum, prev_hour_key = 0.0, hour_key
            inc = max(0.0, cum - prev_cum)
            prev_cum = max(prev_cum, cum)
            b = t.replace(minute=(t.minute // 15) * 15, second=0) + timedelta(minutes=15)  # bucket end
            buckets[b] += inc if inc >= 0.001 else 0.0
        b = START
        while b <= END:
            readings.append({
                "time": iso(b), "source": "nws_asos", "station_id": st["station_id"], "metric": "rain_in",
                "value": round(buckets.get(b, 0.0), 2), "quality": "verified",
                "source_url": meta[-1]["source_url"],
            })
            b += timedelta(minutes=15)
        total = sum(r["value"] for r in readings if r["station_id"] == st["station_id"])
        print(f"  {st['station_id']}: {total:.2f} in over window")
    return meta, readings


def build_warnings() -> list[dict]:
    q = urllib.parse.urlencode({"sts": iso(START - timedelta(hours=2)), "ets": iso(END), "wfos": CFG["wfo"]})
    d = json.loads(get(f"https://mesonet.agron.iastate.edu/geojson/sbw.geojson?{q}"))
    names = {"FF.W": "Flash Flood Warning", "FA.W": "Flood Warning (areal)", "FL.W": "Flood Warning (river)",
             "FA.Y": "Flood Advisory"}
    out = []
    s, w, n, e = BBOX
    for f in d["features"]:
        p = f["properties"]
        key = f"{p['phenomena']}.{p['significance']}"
        if key not in names or p.get("status") != "NEW":
            continue
        coords = [c for ring in _rings(f["geometry"]) for c in ring]
        if not any(w <= x <= e and s <= y <= n for x, y in coords) and not _bbox_inside(f["geometry"], BBOX):
            continue
        out.append({
            "id": f["id"], "event": names[key], "vtec": key, "eventid": p["eventid"],
            "issued_at": p["issue"], "expires_at": p["expire"], "polygon": f["geometry"],
            "source_url": ("https://mesonet.agron.iastate.edu/vtec/#"
                           f"{p['issue'][:4]}-O-NEW-K{p['wfo']}-{p['phenomena']}-{p['significance']}-{int(p['eventid']):04d}"),
        })
    out.sort(key=lambda x: x["issued_at"])
    print(f"  {len(out)} official warnings touch the area")
    return out


def _rings(geom: dict) -> list:
    if geom["type"] == "Polygon":
        return geom["coordinates"]
    if geom["type"] == "MultiPolygon":
        return [r for poly in geom["coordinates"] for r in poly]
    return []


def _bbox_inside(geom: dict, bbox) -> bool:
    """True if the bbox centre is inside the polygon (polygon fully covers our area)."""
    s, w, n, e = bbox
    x, y = (w + e) / 2, (s + n) / 2
    for ring in _rings(geom):
        inside = False
        for i in range(len(ring)):
            x1, y1 = ring[i - 1]
            x2, y2 = ring[i]
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
        if inside:
            return True
    return False


def build_facilities() -> list[dict]:
    s, w, n, e = BBOX
    bb = f"({s},{w},{n},{e})"
    q = (f'[out:json][timeout:90];(nwr["amenity"~"^(hospital|school|clinic|fire_station)$"]{bb};'
         f'nwr["social_facility"]{bb};);out center tags;')
    body = urllib.parse.urlencode({"data": q}).encode()
    servers = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
               "https://overpass.private.coffee/api/interpreter"] * 3
    for attempt, server in enumerate(servers):
        try:
            d = json.loads(get(server, body, timeout=120))
            break
        except Exception as exc:  # Overpass is often busy; back off and try a mirror
            print(f"  overpass attempt {attempt + 1} failed: {exc}")
            time.sleep(10)
    else:
        raise RuntimeError("Overpass unavailable")
    out, seen = [], set()
    for el in d["elements"]:
        t = el.get("tags", {})
        name = t.get("name")
        if not name or name in seen:
            continue
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        sf = t.get("social_facility", "")
        kind = ("nursing_home" if ("nursing" in sf or "assisted" in sf) else
                "shelter" if ("shelter" in sf or t.get("emergency") == "shelter") else
                t.get("amenity") if t.get("amenity") in ("hospital", "school", "clinic", "fire_station") else
                t.get("healthcare", "clinic"))
        if kind == "social_facility":
            continue
        seen.add(name)
        out.append({"id": f"osm-{el['type']}-{el['id']}", "name": name, "kind": kind, "lat": lat, "lon": lon,
                    "source_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}"})
    print(f"  {len(out)} facilities")
    return out


def build_routes() -> dict | None:
    """Precomputed commute: 'usual' passes the low point, 'safer' detours around the watch zones."""
    rc = CFG.get("route")
    if not rc:
        return None

    def route(*pts):
        coords = ";".join(f"{x},{y}" for x, y in pts)
        d = json.loads(get(f"https://router.project-osrm.org/route/v1/driving/{coords}?overview=full&geometries=geojson"))
        r = d["routes"][0]
        return {"geometry": r["geometry"], "distance_m": r["distance"], "duration_s": r["duration"]}

    usual = route(rc["home"], rc["via_usual"], rc["work"])
    time.sleep(1)
    safer = route(rc["home"], rc["via_safer"], rc["work"])
    print(f"  usual {usual['distance_m']:.0f} m, safer {safer['distance_m']:.0f} m")
    return {"persona": rc["persona"], "home": rc["home"], "work": rc["work"], "usual": usual, "safer": safer,
            "source": "OSRM demo server (router.project-osrm.org), OpenStreetMap data; precomputed"}


def main() -> None:
    import sys
    area_id = sys.argv[1] if len(sys.argv) > 1 else "houston-brays"
    out = configure(area_id)
    print(f"area {area_id} -> {out}")
    print("gauges…")
    gmeta, greadings = build_gauges()
    for g in gmeta:
        cfg = next(x for x in GAUGES if x["station_id"] == g["station_id"])
        g["short"] = {"en": cfg["short_en"], "es": cfg["short_es"]}
    print("rain…")
    rmeta, rreadings = build_rain()
    readings = sorted(greadings + rreadings, key=lambda r: (r["time"], r["station_id"]))
    (out / "stations.json").write_text(json.dumps({"gauges": gmeta, "rain": rmeta}, indent=2))
    (out / "readings.json").write_text(json.dumps(readings, indent=1))
    print("warnings…")
    (out / "official_warnings.json").write_text(json.dumps(build_warnings(), indent=1))
    print("facilities…")
    (out / "facilities.json").write_text(json.dumps(build_facilities(), indent=1))
    print("routes…")
    route = build_routes()
    if route:
        (out / "route.json").write_text(json.dumps(route, indent=1))
    print("done")


if __name__ == "__main__":
    main()
