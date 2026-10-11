from datetime import datetime, timedelta, timezone

import pytest

from app.rules.engine import RulesEngine, condition, load_rules
from app.store import ReadingStore

T0 = datetime(2024, 7, 8, 10, 0, tzinfo=timezone.utc)
GAUGES = {"G1": {"station_id": "G1", "name": "Test gauge",
                 "flood_stages_ft": {"action": 38, "minor": 41, "moderate": 42, "major": 43}}}
ZONE = {"type": "Feature",
        "properties": {"zone_id": "Z", "name": "Zone Z", "gauge": "G1", "rain": "R1",
                       "roads": [{"road_id": "ROAD1", "name": "Low St", "lat": 29.5, "lon": -95.5}]},
        "geometry": {"type": "Polygon", "coordinates": [[[-95.6, 29.4], [-95.4, 29.4], [-95.4, 29.6], [-95.6, 29.6], [-95.6, 29.4]]]}}


def reading(station, metric, t, value, quality="verified", **kw):
    return {"time": t.isoformat(), "_t": t, "station_id": station, "metric": metric, "value": value,
            "quality": quality, "source": "test", "source_url": "http://example", **kw}


def stage_series(store, values, start=T0, step=15):
    for i, v in enumerate(values):
        store.add(reading("G1", "stage_ft", start + timedelta(minutes=step * i), v))
    return start + timedelta(minutes=step * (len(values) - 1))


def run(engine, store, t, warnings=()):
    return engine.evaluate_zone(ZONE, t, store, list(warnings))


@pytest.fixture
def engine():
    return RulesEngine(GAUGES)


def fired(ev):
    return {r.rule_id for r in ev.results if r.fired}


def test_normal_when_below_thresholds(engine):
    s = ReadingStore()
    t = stage_series(s, [30.0, 30.1, 30.2])
    ev = run(engine, s, t)
    assert ev.severity == "Normal"
    assert fired(ev) == set()
    assert len(ev.results) == len(engine.rules["rules"])  # one row per rule, fired or not


@pytest.mark.parametrize("stage,expected", [(38.0, "Watch"), (40.9, "Watch"), (41.0, "Warning"), (42.5, "Emergency")])
def test_threshold_crossing(engine, stage, expected):
    s = ReadingStore()
    t = stage_series(s, [stage, stage, stage])  # flat, so no rise-rate effect
    assert run(engine, s, t).severity == expected


def test_rise_rate_raises_one_level_capped_at_warning(engine):
    s = ReadingStore()
    t = stage_series(s, [30.0, 30.6, 31.2])  # +1.2 ft in 30 min
    ev = run(engine, s, t)
    assert "RISE_RATE" in fired(ev) and ev.severity == "Watch"

    s2 = ReadingStore()
    t2 = stage_series(s2, [37.0, 37.6, 38.2])  # action + rising -> Warning
    assert run(RulesEngine(GAUGES), s2, t2).severity == "Warning"

    s3 = ReadingStore()
    t3 = stage_series(s3, [40.5, 41.2, 41.8])  # minor (Warning) + rising -> stays Warning (cap)
    assert run(RulesEngine(GAUGES), s3, t3).severity == "Warning"


def test_rise_rate_needs_prior_reading(engine):
    s = ReadingStore()
    s.add(reading("G1", "stage_ft", T0, 39.0))
    ev = run(engine, s, T0)
    rise = next(r for r in ev.results if r.rule_id == "RISE_RATE")
    assert rise.raw is None and not rise.fired


def test_hysteresis_no_flapping(engine):
    """Stage oscillating just around the minor threshold must not flap Warning/Watch."""
    s = ReadingStore()
    values = [41.1, 40.95, 41.05, 40.9, 41.02, 40.85]
    sevs = []
    for i, v in enumerate(values):
        t = T0 + timedelta(minutes=15 * i)
        s.add(reading("G1", "stage_ft", t, v))
        sevs.append(run(engine, s, t).severity)
    assert sevs == ["Warning"] * len(values)


def test_hysteresis_clears_after_two_false_and_margin(engine):
    s = ReadingStore()
    seq = [41.5, 40.6, 40.5, 40.4]  # 40.6 is 0.4 below 41 but only 1 false eval; then 2nd false -> clear
    out = []
    for i, v in enumerate(seq):
        t = T0 + timedelta(minutes=15 * i)
        s.add(reading("G1", "stage_ft", t, v))
        ev = run(engine, s, t)
        out.append((ev.severity, next(r for r in ev.results if r.rule_id == "STAGE_MINOR").held))
    assert out[0] == ("Warning", False)
    assert out[1] == ("Warning", True)       # held by hysteresis
    assert out[2][0] == "Watch"              # two false evaluations + 0.3 ft margin -> clears to Watch (action)


def test_hysteresis_requires_margin(engine):
    s = ReadingStore()
    seq = [41.5, 40.9, 40.85, 40.8, 40.75]  # false many times but never 0.3 ft below 41
    sevs = []
    for i, v in enumerate(seq):
        t = T0 + timedelta(minutes=15 * i)
        s.add(reading("G1", "stage_ft", t, v))
        sevs.append(run(engine, s, t).severity)
    assert sevs == ["Warning"] * len(seq)


def test_stale_data_gives_unknown_not_normal(engine):
    s = ReadingStore()
    s.add(reading("G1", "stage_ft", T0, 30.0))
    ev = run(engine, s, T0 + timedelta(minutes=45))
    assert ev.severity == "Unknown"
    assert ev.missing_data and "45" in ev.missing_data[0]


def test_no_readings_at_all_is_unknown(engine):
    assert run(engine, ReadingStore(), T0).severity == "Unknown"


def test_stale_data_keeps_higher_latched_severity(engine):
    s = ReadingStore()
    s.add(reading("G1", "stage_ft", T0, 41.5))
    assert run(engine, s, T0).severity == "Warning"
    ev = run(engine, s, T0 + timedelta(minutes=60))  # gauge goes silent
    assert ev.severity == "Warning"  # silence is never mistaken for safety
    assert ev.missing_data


def test_rain_1h(engine):
    s = ReadingStore()
    t = stage_series(s, [30.0, 30.0, 30.0, 30.0, 30.0])
    for i, v in enumerate([0.5, 0.6, 0.5, 0.5]):
        s.add(reading("R1", "rain_in", t - timedelta(minutes=15 * i), v))
    ev = run(engine, s, t)
    assert "RAIN_1H" in fired(ev) and ev.severity == "Watch"


def test_nws_ffw_containment(engine):
    s = ReadingStore()
    t = stage_series(s, [30.0, 30.0, 30.0])
    poly = {"type": "Polygon", "coordinates": [[[-96, 29], [-95, 29], [-95, 30], [-96, 30], [-96, 29]]]}
    w = {"id": "W1", "vtec": "FF.W", "event": "Flash Flood Warning", "issued_at": "x", "expires_at": "y",
         "_issued": t - timedelta(minutes=5), "_expires": t + timedelta(hours=1), "polygon": poly}
    assert run(engine, s, t, [w]).severity == "Warning"
    far = dict(w, polygon={"type": "Polygon", "coordinates": [[[-90, 29], [-89, 29], [-89, 30], [-90, 30], [-90, 29]]]})
    assert run(RulesEngine(GAUGES), s, t, [far]).severity == "Normal"


def test_photo_depth_only_fires_when_verified(engine):
    s = ReadingStore()
    t = stage_series(s, [30.0, 30.0, 30.0])
    s.add(reading("ROAD1", "depth_high_in", t - timedelta(minutes=5), 22, quality="unverified"))
    assert "PHOTO_DEPTH_ROAD" not in fired(run(engine, s, t))
    s.add(reading("ROAD1", "depth_high_in", t - timedelta(minutes=4), 22, quality="verified"))
    ev = run(engine, s, t)
    assert "PHOTO_DEPTH_ROAD" in fired(ev) and ev.severity == "Emergency"


def test_photo_depth_below_12_does_not_fire(engine):
    s = ReadingStore()
    t = stage_series(s, [30.0, 30.0, 30.0])
    s.add(reading("ROAD1", "depth_high_in", t - timedelta(minutes=5), 10, quality="verified"))
    assert run(engine, s, t).severity == "Normal"


def test_inputs_hash_rerun_is_deterministic(engine):
    """Re-running a rule from its stored inputs gives the same result (evidence 'Re-run rule')."""
    s = ReadingStore()
    t = stage_series(s, [40.0, 40.5, 41.2])
    ev = run(engine, s, t)
    rules = load_rules()
    for r in ev.results:
        assert condition(rules["by_id"][r.rule_id], r.inputs) == r.raw
    ev2 = run(RulesEngine(GAUGES), s, t)
    assert [r.inputs_hash for r in ev.results] == [r.inputs_hash for r in ev2.results]
