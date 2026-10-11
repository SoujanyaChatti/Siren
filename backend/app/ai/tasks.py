"""The four AI tasks, each with a schema, a validator and a deterministic template fallback."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from .. import messages
from . import client, prompts, schemas, validators

LANG_NAME = {"en": "English", "es": "Spanish"}
REFUSAL = {
    "en": "I can only answer from official safety guidance. If you are in danger, call 911. "
          "Follow instructions from local officials.",
    "es": "Solo puedo responder con guías oficiales de seguridad. Si está en peligro, llame al 911. "
          "Siga las instrucciones de las autoridades locales.",
}


# ---------------------------------------------------------------- Task 1: explanation

def explanation_facts(zone: dict, severity: str, evaluation_results: list[dict], facilities: list[dict],
                      missing: list[str], at) -> dict:
    plain = messages.build_message(lang="en", severity=severity, zone=zone, results=evaluation_results, at=at)
    fired = [r for r in evaluation_results if r["fired"] and r["rule_id"] != "STALE_DATA"]
    lines = []
    for r in fired:
        inp = r["inputs"]
        if r["rule_id"].startswith("STAGE_") and not inp.get("latest"):
            lines.append(f"{r['rule_id']}: held by hysteresis; no current reading from {inp['station_name']}")
        elif r["rule_id"].startswith("STAGE_"):
            lt = messages.local_time(messages._parse(inp["latest"]["time"]), "en")
            lines.append(f"{r['rule_id']}: {inp['station_name']} stage {inp['latest']['value']:.1f} ft at {lt}; "
                         f"{inp['flood_category']} threshold {inp['threshold_ft']:.1f} ft")
        elif r["rule_id"] == "RISE_RATE" and not (inp.get("latest") and inp.get("prior")):
            lines.append(f"RISE_RATE: {inp['station_name']} rose fast recently; still held by hysteresis "
                         "(no reading from 30 minutes earlier to recompute)")
        elif r["rule_id"] == "RISE_RATE":
            d = inp["latest"]["value"] - inp["prior"]["value"]
            lines.append(f"RISE_RATE: {inp['station_name']} rose {d:.1f} ft in 30 minutes "
                         f"(from {inp['prior']['value']:.1f} to {inp['latest']['value']:.1f} ft)")
        elif r["rule_id"] == "RAIN_1H":
            lines.append(f"RAIN_1H: {inp['sum_in']:.1f} inches of rain in the last hour at {inp['station_id']}")
        elif r["rule_id"] == "NWS_FFW":
            lines.append("NWS_FFW: National Weather Service Flash Flood Warning active: "
                         + ", ".join(w["id"] for w in inp["active_warnings"]))
        elif r["rule_id"] == "PHOTO_DEPTH_ROAD":
            rep = max(inp["verified_reports"], key=lambda x: x["value"])
            lines.append(f"PHOTO_DEPTH_ROAD: verified photo at {rep['road_name']} shows about "
                         f"{round(rep.get('depth_in') or rep['value'])} in (up to {round(rep['value'])} in)")
    kinds: dict[str, int] = {}
    for f in facilities:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    fac = ", ".join(f"{n} {k.replace('_', ' ')}{'s' if n > 1 else ''}" for k, n in sorted(kinds.items()))
    return {
        "zone": zone["properties"]["name"],
        "severity": severity,
        "decided_at": messages.local_time(at, "en"),
        "fired_rules": [{"rule_id": r["rule_id"], "condition": r.get("description", "")} for r in fired],
        "facts": lines,
        "plain_summary": plain["what"],
        "facilities_in_zone": fac or "none listed",
        "missing_data": missing,
    }


def _explanation_template(facts: dict) -> dict:
    return {
        "headline": f"{facts['severity']} for {facts['zone'].split(' — ')[0]}",
        "what_is_happening": facts.get("plain_summary") or "Rules raised the alert level.",
        "why": [{"rule_id": r["rule_id"], "evidence": r["condition"]} for r in facts["fired_rules"]],
        "who_may_be_affected": f"People in {facts['zone']}. Facilities: {facts['facilities_in_zone']}.",
        "missing_data": facts["missing_data"],
        "confidence_note": "Template explanation built directly from rule outputs (no AI).",
    }


def _trim_words(s: str, n: int) -> str:
    w = s.split()
    return " ".join(w[:n])


async def explain(facts: dict) -> client.AIResult:
    fired_ids = [r["rule_id"] for r in facts["fired_rules"]]
    facts_text = " ".join([*facts["facts"], facts.get("plain_summary", ""), facts["facilities_in_zone"], facts["decided_at"], facts["zone"],
                           *facts["missing_data"], *[r["condition"] for r in facts["fired_rules"]]])

    def template():
        t = _explanation_template(facts)
        t["what_is_happening"] = _trim_words(t["what_is_happening"], 40)
        t["who_may_be_affected"] = _trim_words(t["who_may_be_affected"], 30)
        return t

    return await client.run(
        "explanation", system=prompts.EXPLANATION, payload=facts, schema=schemas.EXPLANATION,
        validate=lambda o: validators.validate_explanation(o, fired_ids, facts_text), template=template)


# ---------------------------------------------------------------- Task 2: translation

async def translate(en_msg: dict, target_msg: dict, language: str) -> client.AIResult:
    """en_msg: deterministic English message. target_msg: deterministic pre-translated template (fallback)."""
    terms = target_msg["protected_terms"]
    payload = {"text": en_msg["text"], "target_language": language}
    system = prompts.TRANSLATION.format(language_name=LANG_NAME[language], language=language, terms=", ".join(terms))
    return await client.run(
        "translation", system=system, payload=payload, schema=schemas.TRANSLATION, language=language,
        validate=lambda o: validators.validate_translation(o, en_msg["text"], language, terms),
        template=lambda: {"language": language, "text": target_msg["text"], "kept_terms": terms})


# ---------------------------------------------------------------- Task 3: grounded Q&A

@lru_cache(maxsize=1)
def guidance() -> dict[str, dict]:
    out = {}
    for line in Path(__file__).with_name("guidance.md").read_text().splitlines():
        m = re.match(r"^(G\d\d) \| (.+?) \| (.+?) \| (\S+)$", line.strip())
        if m:
            out[m.group(1)] = {"id": m.group(1), "en": m.group(2), "es": m.group(3), "source": m.group(4)}
    return out


FAQ = [  # deterministic template tier: keyword -> guidance snippet ids (grounded, cited)
    (r"wheelchair|parent|elder|older|disab|mobility|silla de ruedas|mayor|discapacidad|abuel", ["G13", "G07", "G09"]),
    (r"trapped|stuck|atrapad", ["G09", "G08"]),
    (r"deep|depth|how high|profund|qué tan alt", ["G02", "G05"]),
    (r"drive|driving|car|truck|road|underpass|manej|conduc|carro|coche|camioneta|calle|cruzar", ["G01", "G02", "G05"]),
    (r"walk|kids|child|camin|niñ", ["G04", "G11", "G18"]),
    (r"evacuat|leave|shelter|go where|where should|evacu|refugio|irme|salir", ["G07", "G08"]),
    (r"pack|bring|kit|medicine|mochila|medicin|llevar", ["G14"]),
    (r"what should|what do i do|what now|what can i do|qué hago|qué debo|que hago|que debo|qué puedo", ["G16", "G01", "G08"]),
    (r"warning mean|watch mean|significa", ["G16", "G17"]),
    (r"safe|seguro|peligro|danger", ["G01", "G15"]),
]


def _faq_answer(question: str, language: str, facts: list[dict]) -> dict | None:
    q = question.lower()
    g = guidance()
    for pat, ids in FAQ:
        if re.search(pat, q):
            parts, cites = [], []
            sev = next((f for f in facts if f["id"] == "F1"), None)
            if sev:
                parts.append(sev[language])
                cites.append("F1")
            depth = next((f for f in facts if f.get("kind") == "photo"), None)
            if depth and ("G02" in ids or "G05" in ids):
                parts.append(depth[language])
                cites.append(depth["id"])
            for gid in ids:
                cand = " ".join(parts + [g[gid][language]])
                if validators.words(cand) > 50 and len(cites) > 1:
                    break
                parts.append(g[gid][language])
                cites.append(gid)
            return {"answerable": True, "answer": " ".join(parts), "citations": cites, "language": language}
    return None


async def ask(question: str, language: str, facts: list[dict]) -> client.AIResult:
    g = guidance()
    known = set(g) | {f["id"] for f in facts}
    payload = {
        "question": question,
        "language": language,
        "guidance": [{"id": k, "text": v["en"]} for k, v in g.items()],
        "incident_facts": [{"id": f["id"], "text": f["en"]} for f in facts],
    }
    system = prompts.QA.format(language_name=LANG_NAME[language], language=language)

    def template():
        return _faq_answer(question, language, facts) or {"answerable": False, "answer": REFUSAL[language],
                                                           "citations": [], "language": language}

    res = await client.run("qa", system=system, payload=payload, schema=schemas.QA, language=language,
                           validate=lambda o: validators.validate_qa(o, language, known), template=template)
    if res.path == "template":
        errs = validators.validate_qa(res.output, language, known)
        if errs:  # deterministic FAQ found nothing -> fixed refusal
            res.output = {"answerable": False, "answer": REFUSAL[language], "citations": [], "language": language}
            res.validation_errors = errs
    return res


# ---------------------------------------------------------------- Task 4: photo depth (vision)

async def estimate_depth(image: bytes, mime: str, ref_heights_text: str, fixture_lookup) -> client.AIResult:
    return await client.run(
        "depth", system=prompts.DEPTH.format(refs=ref_heights_text), payload={"task": "depth", "v": 1},
        schema=schemas.DEPTH, image=image, image_mime=mime, allow_groq=False,
        validate=validators.validate_depth, offline_fixture=fixture_lookup,
        template=lambda: {"reference_objects": [], "depth_in": None, "depth_low_in": None, "depth_high_in": None,
                          "confidence": 0.0, "is_road": None,
                          "notes": "Could not analyze photo; report saved as unverified."})
