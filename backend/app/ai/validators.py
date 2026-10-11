"""Deterministic validators. Any AI output that fails is discarded and the next fallback is used."""
from __future__ import annotations

import re

NUM_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")

UNSAFE_PHRASES = {
    "en": [r"safe to (drive|walk|cross|go)", r"(you )?can (drive|walk|cross) (through|across|in)",
           r"(it'?s|it is) (fine|ok|okay|safe)", r"water is (shallow|safe)", r"go ahead and (drive|cross)"],
    "es": [r"es seguro (manejar|conducir|cruzar|caminar)", r"puede (manejar|conducir|cruzar|caminar) (por|sobre|en)",
           r"no hay peligro", r"el agua es (poco profunda|segura)", r"está bien (manejar|cruzar)"],
}


def numbers(text: str) -> set[str]:
    out = set()
    for m in NUM_RE.findall(text or ""):
        v = m.replace(",", ".")
        try:
            f = float(v)
        except ValueError:
            continue
        out.add(f"{f:g}")
    return out


def words(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))


def validate_explanation(out: dict, fired_rule_ids: list[str], facts_text: str) -> list[str]:
    errs = []
    for k, lim in (("headline", 12), ("what_is_happening", 40), ("who_may_be_affected", 30)):
        if not isinstance(out.get(k), str) or not out[k].strip():
            errs.append(f"{k} missing")
        elif words(out[k]) > lim:
            errs.append(f"{k} longer than {lim} words")
    why = out.get("why") or []
    if not why:
        errs.append("why is empty")
    for w in why:
        if w.get("rule_id") not in fired_rule_ids:
            errs.append(f"rule_id {w.get('rule_id')!r} did not fire")
    allowed = numbers(facts_text)
    text = " ".join([out.get("headline", ""), out.get("what_is_happening", ""), out.get("who_may_be_affected", ""),
                     out.get("confidence_note", ""), *[w.get("evidence", "") for w in why],
                     *[m for m in out.get("missing_data", []) if isinstance(m, str)]])
    extra = numbers(text) - allowed
    if extra:
        errs.append(f"numbers not in input facts: {sorted(extra)}")
    return errs


def validate_translation(out: dict, source_text: str, language: str, expected_terms: list[str]) -> list[str]:
    errs = []
    if out.get("language") != language:
        errs.append("wrong language field")
    text = out.get("text") or ""
    if not text.strip():
        errs.append("empty translation")
    missing_nums = numbers(source_text) - numbers(text)
    if missing_nums:
        errs.append(f"numbers changed or missing: {sorted(missing_nums)}")
    for t in expected_terms:
        if t not in text:
            errs.append(f"protected term missing: {t}")
    if words(text) > 80:
        errs.append("translation too long")
    return errs


def validate_qa(out: dict, language: str, known_ids: set[str]) -> list[str]:
    errs = []
    if out.get("answerable") is not True:
        errs.append("not answerable")
    cites = out.get("citations") or []
    if not cites:
        errs.append("no citations")
    unknown = [c for c in cites if c not in known_ids]
    if unknown:
        errs.append(f"unknown citations: {unknown}")
    ans = out.get("answer") or ""
    if not ans.strip():
        errs.append("empty answer")
    if words(ans) > 60:
        errs.append("answer too long")
    for pat in UNSAFE_PHRASES["en"] + UNSAFE_PHRASES.get(language, []):
        if re.search(pat, ans, re.IGNORECASE):
            errs.append(f"unsafe phrase blocked: {pat}")
    return errs


def validate_depth(out: dict) -> list[str]:
    errs = []
    try:
        lo, mid, hi = float(out["depth_low_in"]), float(out["depth_in"]), float(out["depth_high_in"])
        conf = float(out["confidence"])
    except (KeyError, TypeError, ValueError):
        return ["missing numeric fields"]
    if not (0 <= lo <= mid <= hi <= 120):
        errs.append("depth range inconsistent")
    if not (0 <= conf <= 1):
        errs.append("confidence out of range")
    if not isinstance(out.get("reference_objects"), list):
        errs.append("reference_objects not a list")
    return errs
