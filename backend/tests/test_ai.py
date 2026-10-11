import asyncio

import pytest

from app.ai import client, tasks, validators
from app.settings import settings


def run(coro):
    return asyncio.run(coro)


FACTS = {
    "zone": "Zone B — Meyerland", "severity": "Warning", "decided_at": "9:15 AM",
    "fired_rules": [{"rule_id": "STAGE_MINOR", "condition": "Latest stage is at or above the minor flood stage."}],
    "facts": ["STAGE_MINOR: Brays Bayou at Main St stage 41.2 ft at 9:15 AM; minor threshold 41.0 ft"],
    "plain_summary": "Brays Bayou at Main St is at 41.2 ft, above the minor flood stage of 41.0 ft.",
    "facilities_in_zone": "3 clinics", "missing_data": [],
}
GOOD_EXPL = {"headline": "Brays Bayou is over minor flood stage", "what_is_happening": "The bayou is at 41.2 ft.",
             "why": [{"rule_id": "STAGE_MINOR", "evidence": "41.2 ft is above 41.0 ft"}],
             "who_may_be_affected": "People in Zone B and 3 clinics.", "missing_data": [], "confidence_note": "Based on gauge data."}


@pytest.fixture
def online(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "demo_offline", False)
    monkeypatch.setattr(settings, "gemini_api_key", "test")
    monkeypatch.setattr(settings, "groq_api_key", "test")
    monkeypatch.setattr(settings, "cache_dir", tmp_path)
    monkeypatch.setattr(settings, "force_gemini_failure", False)
    return monkeypatch


def test_explanation_validator_rejects_invented_number():
    bad = dict(GOOD_EXPL, what_is_happening="The bayou is at 45.0 ft and rising.")
    errs = validators.validate_explanation(bad, ["STAGE_MINOR"], "41.2 41.0 9:15 3")
    assert any("numbers not in input" in e for e in errs)


def test_explanation_validator_rejects_unfired_rule():
    bad = dict(GOOD_EXPL, why=[{"rule_id": "STAGE_MODERATE", "evidence": "x"}])
    assert any("did not fire" in e for e in validators.validate_explanation(bad, ["STAGE_MINOR"], "41.2 41.0 3"))


def test_injected_bad_gemini_output_falls_back_to_groq(online):
    async def bad_gemini(*a, **k):
        return dict(GOOD_EXPL, what_is_happening="Water is at 99 ft.")  # invented number

    async def good_groq(*a, **k):
        return GOOD_EXPL

    online.setattr(client, "_gemini", bad_gemini)
    online.setattr(client, "_groq", good_groq)
    res = run(tasks.explain(FACTS))
    assert res.path == "groq"
    assert any("gemini: validation failed" in r for r in res.fallback_reasons)


def test_both_providers_bad_falls_back_to_template(online):
    async def bad(*a, **k):
        return dict(GOOD_EXPL, why=[{"rule_id": "NWS_FFW", "evidence": "made up"}])

    online.setattr(client, "_gemini", bad)
    online.setattr(client, "_groq", bad)
    res = run(tasks.explain(FACTS))
    assert res.path == "template"
    assert not validators.validate_explanation(res.output, ["STAGE_MINOR"], " ".join(FACTS["facts"] + [FACTS["plain_summary"], "3 clinics", "9:15 AM", "Zone B"]))


def test_429_retries_then_falls_back(online):
    calls = {"gemini": 0}

    async def rate_limited(*a, **k):
        calls["gemini"] += 1
        raise client.TransientAIError("gemini HTTP 429")

    async def good_groq(*a, **k):
        return GOOD_EXPL

    online.setattr(client, "_gemini", rate_limited)
    online.setattr(client, "_groq", good_groq)
    real_sleep = asyncio.sleep
    online.setattr(client.asyncio, "sleep", lambda s: real_sleep(0))
    res = run(tasks.explain(FACTS))
    assert calls["gemini"] == 3 and res.path == "groq"


def test_valid_output_is_cached_and_served_offline(online):
    async def good(*a, **k):
        return GOOD_EXPL

    online.setattr(client, "_gemini", good)
    assert run(tasks.explain(FACTS)).path == "gemini"
    online.setattr(settings, "demo_offline", True)
    res = run(tasks.explain(FACTS))
    assert res.path == "gemini" and res.cache_hit


def test_forced_gemini_failure_uses_fallback(online):
    online.setattr(settings, "force_gemini_failure", True)

    async def good_groq(*a, **k):
        return GOOD_EXPL

    online.setattr(client, "_groq", good_groq)
    assert run(tasks.explain(FACTS)).path == "groq"


def test_translation_validator_numbers_and_terms():
    src = "Warning. Brays Bayou at Main St is at 41.2 ft. Where: Zone B — Meyerland. Updated 9:15 AM."
    ok = {"language": "es", "text": "Advertencia. Brays Bayou en Main St está a 41.2 pies. Dónde: Zona B — Meyerland. Actualizado 9:15 a. m.", "kept_terms": []}
    assert validators.validate_translation(ok, src, "es", ["Brays Bayou", "Zona B"]) == []
    wrong_num = dict(ok, text=ok["text"].replace("41.2", "42.1"))
    assert validators.validate_translation(wrong_num, src, "es", ["Brays Bayou", "Zona B"])
    lost_term = dict(ok, text=ok["text"].replace("Zona B", "la zona"))
    assert validators.validate_translation(lost_term, src, "es", ["Brays Bayou", "Zona B"])


def test_qa_missing_citation_replaced_by_refusal(online):
    async def no_cites(*a, **k):
        return {"answerable": True, "answer": "Stay home.", "citations": [], "language": "en"}

    online.setattr(client, "_gemini", no_cites)
    online.setattr(client, "_groq", no_cites)
    res = run(tasks.ask("When will the stock market open?", "en", []))
    assert res.output["answerable"] is False
    assert "911" in res.output["answer"]


def test_qa_unsafe_answer_blocked(online):
    async def unsafe(*a, **k):
        return {"answerable": True, "answer": "It is safe to drive through the water slowly.", "citations": ["G01"], "language": "en"}

    online.setattr(client, "_gemini", unsafe)
    online.setattr(client, "_groq", unsafe)
    res = run(tasks.ask("Can I drive through it?", "en", []))
    assert "safe to drive" not in res.output["answer"].lower()
    assert res.path == "template"


def test_qa_spanish_unsafe_phrase_blocked():
    out = {"answerable": True, "answer": "Sí, es seguro cruzar con cuidado.", "citations": ["G01"], "language": "es"}
    assert any("unsafe" in e for e in validators.validate_qa(out, "es", {"G01"}))


def test_offline_faq_answer_is_grounded_and_cited():
    res = run(tasks.ask("What should I do now?", "es", [{"id": "F1", "en": "Zone B is at Warning.", "es": "Zona B está en Advertencia."}]))
    assert res.output["answerable"] and res.output["citations"]
    known = set(tasks.guidance()) | {"F1"}
    assert not validators.validate_qa(res.output, "es", known)


def test_depth_validator():
    assert validators.validate_depth({"depth_in": 17, "depth_low_in": 14, "depth_high_in": 22, "confidence": 0.7, "reference_objects": []}) == []
    assert validators.validate_depth({"depth_in": 30, "depth_low_in": 14, "depth_high_in": 22, "confidence": 0.7, "reference_objects": []})
    assert validators.validate_depth({"depth_in": 17, "depth_low_in": 14, "depth_high_in": 22, "confidence": 1.7, "reference_objects": []})
