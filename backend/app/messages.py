"""Deterministic alert text. The English (and Spanish template) alert is built from rule outputs,
never written by AI. AI may only translate it (validated) — see ai/tasks.py.

Fixed structure: what is happening, where, what to do now, when updated, source. Max 60 words spoken.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

_TZ = {"tz": ZoneInfo("America/Chicago")}


def set_timezone(name: str) -> None:
    """The active area's local time zone (one area is replayed at a time)."""
    _TZ["tz"] = ZoneInfo(name)
MAX_SPOKEN_WORDS = 60

SEVERITY_WORD = {
    "en": {"Normal": "Normal", "Watch": "Watch", "Warning": "Warning", "Emergency": "Emergency", "Unknown": "Unknown"},
    "es": {"Normal": "Normal", "Watch": "Vigilancia", "Warning": "Advertencia", "Emergency": "Emergencia",
           "Unknown": "Desconocido"},
}

# Pre-translated fixed phrases (Spanish reviewed status lives in fixtures/translation_review.json).
P = {
    "en": {
        "headline": "{sev}: flood risk in {zone}",
        "headline_photo": "{sev}: do not drive on {road}",
        "headline_clear": "Conditions easing in {zone}",
        "headline_unknown": "Data missing for {zone}",
        "stage": "{gauge} is at {value} ft, above the {cat} of {threshold} ft.",
        "cat_action": "action stage", "cat_minor": "minor flood stage", "cat_moderate": "moderate flood stage",
        "rising": "It rose {rise} ft in 30 minutes.",
        "rise_only": "{gauge} rose {rise} ft in 30 minutes, to {value} ft.",
        "rain": "{rain} inches of rain fell in the last hour.",
        "nws": "The National Weather Service issued a Flash Flood Warning for this area.",
        "photo": "A verified photo shows about {depth} inches of water on {road}.",
        "stale": "Gauge data is missing, so conditions are unknown.",
        "act_Watch": "Stay alert. Avoid low roads and underpasses.",
        "act_Warning": "Avoid driving. Never drive into water. Turn around, don't drown.",
        "act_Emergency": "Do not drive. Move to higher ground now. Turn around, don't drown.",
        "act_Unknown": "Check official sources and stay alert.",
        "act_Normal": "Conditions have eased. Stay alert for changes.",
        "act_Normal_live": "No flooding at this gauge right now. Stay alert for changes.",
        "below": "{gauge} is at {value} ft, below the action stage of {threshold} ft.",
        "act_road": "Stay off {road}.",
        "need_mobility": "Plan help now for anyone who cannot move quickly.",
        "need_commute": "Your usual route is affected. Avoid this road.",
        "updated": "Updated {time}.",
        "source": "Source: USGS gauges, NWS, SIREN rules.",
        "where": "Where: {zone}.",
    },
    "es": {
        "headline": "{sev}: riesgo de inundación en {zone}",
        "headline_photo": "{sev}: no maneje en {road}",
        "headline_clear": "Las condiciones mejoran en {zone}",
        "headline_unknown": "Faltan datos para {zone}",
        "stage": "{gauge} está a {value} pies, sobre el {cat} de {threshold} pies.",
        "cat_action": "nivel de acción", "cat_minor": "nivel de inundación menor",
        "cat_moderate": "nivel de inundación moderada",
        "rising": "Subió {rise} pies en 30 minutos.",
        "rise_only": "{gauge} subió {rise} pies en 30 minutos, a {value} pies.",
        "rain": "Cayeron {rain} pulgadas de lluvia en la última hora.",
        "nws": "El Servicio Meteorológico Nacional emitió una Advertencia de Inundación Repentina para esta área.",
        "photo": "Una foto verificada muestra unas {depth} pulgadas de agua en {road}.",
        "stale": "Faltan datos del medidor, así que las condiciones son desconocidas.",
        "act_Watch": "Manténgase alerta. Evite calles bajas y pasos a desnivel.",
        "act_Warning": "Evite manejar. Nunca maneje sobre agua. Dé la vuelta, no se ahogue.",
        "act_Emergency": "No maneje. Vaya a un lugar alto ahora. Dé la vuelta, no se ahogue.",
        "act_Unknown": "Consulte fuentes oficiales y manténgase alerta.",
        "act_Normal": "Las condiciones han mejorado. Manténgase alerta a cambios.",
        "act_Normal_live": "No hay inundación en este medidor ahora. Manténgase alerta a cambios.",
        "below": "{gauge} está a {value} pies, por debajo del nivel de acción de {threshold} pies.",
        "act_road": "No use {road}.",
        "need_mobility": "Planee ayuda ahora para quien no pueda moverse rápido.",
        "need_commute": "Su ruta habitual está afectada. Evite esta calle.",
        "updated": "Actualizado {time}.",
        "source": "Fuente: medidores USGS, NWS, reglas de SIREN.",
        "where": "Dónde: {zone}.",
    },
}

def _short(inp: dict, lang: str) -> str:
    return (inp.get("station_short") or {}).get(lang) or inp["station_name"]


def local_time(t: datetime, lang: str, tz: str | None = None) -> str:
    lt = t.astimezone(ZoneInfo(tz) if tz else _TZ["tz"])
    h = lt.hour % 12 or 12
    suffix = ("AM" if lt.hour < 12 else "PM") if lang == "en" else ("a. m." if lt.hour < 12 else "p. m.")
    return f"{h}:{lt.minute:02d} {suffix}"


def word_count(s: str) -> int:
    return len(re.findall(r"\S+", s))


def _fmt(v: float) -> str:
    return f"{v:.1f}"


def build_message(*, lang: str, severity: str, zone: dict, results: list, at: datetime,
                  user: dict | None = None, tz: str | None = None, live: bool = False) -> dict:
    """results: list of RuleResult-like dicts with rule_id, fired, inputs."""
    p = P[lang]
    props = zone["properties"]
    zone_name = props["name_es"] if lang == "es" else props["name"]
    zone_short = zone_name.split(" — ")[0]
    sev_word = SEVERITY_WORD[lang][severity]
    fired = {r["rule_id"]: r for r in results if r["fired"]}

    what: list[str] = []
    road = None
    if "PHOTO_DEPTH_ROAD" in fired:
        rep = max(fired["PHOTO_DEPTH_ROAD"]["inputs"]["verified_reports"], key=lambda x: x["value"])
        road = rep["road_name"]
        what.append(p["photo"].format(depth=round(rep.get("depth_in") or rep["value"]), road=road))
    stage_rule = next((fired[k] for k in ("STAGE_MODERATE", "STAGE_MINOR", "STAGE_ACTION") if k in fired), None)
    if stage_rule and stage_rule["inputs"].get("latest"):
        inp = stage_rule["inputs"]
        what.append(p["stage"].format(gauge=_short(inp, lang),
                                      value=_fmt(inp["latest"]["value"]), cat=p["cat_" + inp["flood_category"]],
                                      threshold=_fmt(inp["threshold_ft"])))
    rise = fired.get("RISE_RATE")
    if rise and rise["inputs"].get("latest") and rise["inputs"].get("prior"):
        inp = rise["inputs"]
        delta = inp["latest"]["value"] - inp["prior"]["value"]
        if stage_rule:
            what.append(p["rising"].format(rise=_fmt(delta)))
        else:
            what.append(p["rise_only"].format(gauge=_short(inp, lang),
                                              rise=_fmt(delta), value=_fmt(inp["latest"]["value"])))
    if "NWS_FFW" in fired:
        what.append(p["nws"])
    if "RAIN_1H" in fired:
        what.append(p["rain"].format(rain=_fmt(fired["RAIN_1H"]["inputs"]["sum_in"])))
    if severity == "Unknown":
        what.append(p["stale"])
    if live and severity == "Normal":
        act = next((r for r in results if r["rule_id"] == "STAGE_ACTION"), None)
        if act and isinstance(act["inputs"].get("latest"), dict):
            inp = act["inputs"]
            what.append(p["below"].format(gauge=_short(inp, lang), value=_fmt(inp["latest"]["value"]),
                                          threshold=_fmt(inp["threshold_ft"])))
    action = [p["act_road"].format(road=road)] if road else []
    action.append(p["act_Normal_live"] if live and severity == "Normal" else p[f"act_{severity}"])
    needs: list[str] = []
    if user:
        n = user.get("needs") or {}
        if n.get("mobility") and severity in ("Warning", "Emergency"):
            needs.append(p["need_mobility"])
        if n.get("commute") and road:
            needs.append(p["need_commute"])

    if road:
        headline = p["headline_photo"].format(sev=sev_word, road=road)
    elif severity == "Normal" and live:
        headline = "No flooding at nearby gauges" if lang == "en" else "Sin inundación en medidores cercanos"
    elif severity == "Normal":
        headline = p["headline_clear"].format(zone=zone_short)
    elif severity == "Unknown":
        headline = p["headline_unknown"].format(zone=zone_short)
    else:
        headline = p["headline"].format(sev=sev_word, zone=zone_short)

    updated = p["updated"].format(time=local_time(at, lang, tz)).replace("..", ".")
    where = p["where"].format(zone=zone_name)

    # Compose spoken text, trimming optional parts until it fits in 60 words.
    def compose(what_parts, need_parts, with_source=True):
        parts = [f"{sev_word}.", *what_parts, where, *action, *need_parts, updated]
        if with_source:
            parts.append(p["source"])
        return " ".join(parts)

    text = compose(what, needs)
    w, nd = list(what), list(needs)
    while word_count(text) > MAX_SPOKEN_WORDS:
        if len(w) > 1:
            w.pop()
        elif nd:
            nd.pop()
        else:
            text = compose(w, nd, with_source=False)
            break
        text = compose(w, nd)

    return {"language": lang, "severity": severity, "severity_word": sev_word, "headline": headline,
            "what": " ".join(w) or "—", "where": zone_name, "action": " ".join(action + nd),
            "updated": updated, "source": p["source"], "text": text, "word_count": word_count(text),
            "protected_terms": protected_terms(lang, zone_name, road)}


def protected_terms(lang: str, zone_name: str, road: str | None) -> list[str]:
    terms = [zone_name.split(" — ")[0]]
    if road:
        terms.append(road)
    return terms


def _parse(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))
