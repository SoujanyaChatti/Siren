"""Photo depth estimation: Gemini vision -> deterministic checks -> readings row (depth_in)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

from ..ai import tasks
from ..settings import settings

REF = yaml.safe_load(Path(__file__).with_name("reference_heights.yaml").read_text())
REF_TEXT = ", ".join(
    f"{k.replace('_', ' ')} about {v['range_in'][0]}-{v['range_in'][1]} in" if v.get("range_in") and v["range_in"][0] != v["range_in"][1]
    else f"{k.replace('_', ' ')} about {v['typical_in']} in" if v.get("typical_in") else f"{k.replace('_', ' ')} (read the marking)"
    for k, v in REF.items())

MIN_CONFIDENCE = 0.5
LOW_PRECISION_RANGE_IN = 18


def checks(analysis: dict) -> dict:
    """Deterministic checks from the spec. Returns {status, flags, reasons}."""
    flags, reasons = [], []
    refs = analysis.get("reference_objects") or []
    if analysis.get("depth_in") is None:
        return {"status": "unverified", "flags": ["not_analyzed"], "reasons": [analysis.get("notes") or "No analysis"]}
    if not refs:
        return {"status": "rejected", "flags": ["no_reference_object"],
                "reasons": ["No reference object found, so depth cannot be judged."]}
    status = "verified"
    if float(analysis.get("confidence", 0)) < MIN_CONFIDENCE:
        status = "unverified"
        reasons.append(f"Confidence {analysis['confidence']:.2f} is below {MIN_CONFIDENCE}; shown but cannot fire alerts.")
    if analysis.get("depth_high_in") - analysis.get("depth_low_in") > LOW_PRECISION_RANGE_IN:
        flags.append("low_precision")
        reasons.append(f"Range wider than {LOW_PRECISION_RANGE_IN} in: low precision.")
    if analysis.get("is_road") is False:
        flags.append("not_on_road")
        reasons.append("Water does not appear to be on a road; cannot fire the road rule.")
    return {"status": status, "flags": flags, "reasons": reasons}


def fixture_for(image: bytes):
    """Committed analysis for known demo photos (used only when no live/cached model output exists)."""
    digest = hashlib.sha256(image).hexdigest()
    d = settings.fixtures_dir / "photos"

    def lookup():
        for p in d.glob("*.analysis.json"):
            rec = json.loads(p.read_text())
            if rec.get("image_sha256") == digest:
                return {**rec["analysis"], "_model": rec.get("model", "fixture")}
        return None

    return lookup


async def analyze(image: bytes, mime: str) -> tuple[dict, dict, object]:
    res = await tasks.estimate_depth(image, mime, REF_TEXT, fixture_for(image))
    analysis = {k: v for k, v in res.output.items() if not k.startswith("_")}
    return analysis, checks(analysis), res
