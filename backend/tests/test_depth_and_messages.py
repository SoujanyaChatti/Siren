from datetime import datetime, timezone

from app import messages
from app.depth.analyzer import checks
from app.ingest.fixtures import load

REF = [{"type": "car_tire", "typical_height_in": 28, "waterline_fraction": 0.6}]


def test_rejects_without_reference_object():
    assert checks({"reference_objects": [], "depth_in": 10, "depth_low_in": 8, "depth_high_in": 12, "confidence": 0.9})["status"] == "rejected"


def test_low_confidence_is_unverified():
    c = checks({"reference_objects": REF, "depth_in": 17, "depth_low_in": 14, "depth_high_in": 22, "confidence": 0.4, "is_road": True})
    assert c["status"] == "unverified"


def test_wide_range_is_low_precision():
    c = checks({"reference_objects": REF, "depth_in": 20, "depth_low_in": 8, "depth_high_in": 30, "confidence": 0.8, "is_road": True})
    assert c["status"] == "verified" and "low_precision" in c["flags"]


def test_not_analyzed_is_unverified():
    assert checks({"reference_objects": [], "depth_in": None, "notes": "x"})["status"] == "unverified"


def _results(stage=41.2):
    return [{"rule_id": "STAGE_MINOR", "fired": True, "inputs": {
        "station_id": "HBMT2", "station_name": "Brays Bayou at Main St (Houston)", "flood_category": "minor",
        "threshold_ft": 41.0, "latest": {"time": "2024-07-08T14:15:00Z", "value": stage}}}]


def test_message_structure_and_word_limit():
    messages.set_timezone("America/Chicago")  # module-global; other tests replay other areas
    fx = load("houston-brays")
    zone = fx.zone("B")
    t = datetime(2024, 7, 8, 14, 15, tzinfo=timezone.utc)
    for lang in ("en", "es"):
        m = messages.build_message(lang=lang, severity="Warning", zone=zone, results=_results(), at=t,
                                   user={"needs": {"mobility": "wheelchair", "commute": "x"}})
        assert m["word_count"] <= messages.MAX_SPOKEN_WORDS
        assert "41.2" in m["text"] and "9:15" in m["text"]
        assert all(m[k] for k in ("what", "where", "action", "updated", "source"))
    es = messages.build_message(lang="es", severity="Warning", zone=zone, results=_results(), at=t)
    assert "Dé la vuelta, no se ahogue" in es["text"] and "Zona B" in es["text"]
