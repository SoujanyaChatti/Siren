"""Live status with canned NOAA/NWS responses (no network)."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app import live

NOW = datetime.now(timezone.utc).replace(second=0, microsecond=0)


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def canned(stages, alerts=(), with_gauge=True, forecast=None):
    """stages: list of stage values, 15 min apart, ending ~20 min ago (typical telemetry lag)."""
    end = NOW - timedelta(minutes=20)
    series = [{"validTime": iso(end - timedelta(minutes=15 * (len(stages) - 1 - i))), "primary": v} for i, v in enumerate(stages)]
    gauge = {"lid": "TSTX1", "name": "Test River at Town", "latitude": 30.0, "longitude": -95.0,
             "status": {"observed": {"primary": stages[-1], "primaryUnit": "ft", "floodCategory": "minor", "validTime": iso(end)},
                        "forecast": {"primary": -999, "floodCategory": "fcst_not_current", "validTime": "0001-01-01T00:00:00Z"}}}
    data = {
        "/points/": {"properties": {"timeZone": "America/Chicago", "cwa": "HGX", "observationStations": "https://api.weather.gov/stations-list",
                                    "relativeLocation": {"properties": {"city": "Town", "state": "TX"}}}},
        "/gauges?": {"gauges": [gauge] if with_gauge else []},
        "/gauges/TSTX1/stageflow/observed": {"data": series},
        "/gauges/TSTX1/stageflow/forecast": {"data": forecast or []},
        "/gauges/TSTX1": {"name": "Test River at Town", "usgsId": "00000000",
                          "flood": {"categories": {"action": {"stage": 10}, "minor": {"stage": 12}, "moderate": {"stage": 14}, "major": {"stage": 16}}}},
        "/alerts/active": {"features": [{"properties": {"id": f"a{i}", "event": e, "severity": "Severe", "headline": e,
                                                        "areaDesc": "Town", "sent": iso(NOW - timedelta(minutes=30)),
                                                        "ends": iso(NOW + timedelta(hours=2)), "@id": "https://nws/a"},
                                         "geometry": None} for i, e in enumerate(alerts)]},
        "stations-list": {"features": []},
    }

    async def fake_get(c, url, ttl, **params):
        full = url + ("?" if params else "")
        for key in sorted(data, key=len, reverse=True):
            if key in full:
                return data[key]
        raise AssertionError(f"unexpected url {url}")
    return fake_get


def run(monkeypatch, fake, lang="en", lat=30.01, lon=-95.01):
    monkeypatch.setattr(live, "_get", fake)
    return asyncio.run(live.status(lat, lon, lang))


def test_rising_river_over_minor_is_warning(monkeypatch):
    st = run(monkeypatch, canned([10.5, 11.0, 11.6, 12.2, 12.5]))
    assert st["severity"] == "Warning"
    fired = {r["rule_id"] for r in st["rules"] if r["fired"]}
    assert "STAGE_MINOR" in fired
    assert "12.5" in st["text"] and st["location"]["place"] == "Town, TX"


def test_normal_live_message(monkeypatch):
    st = run(monkeypatch, canned([5.0, 5.0, 5.0, 5.0]), lang="es")
    assert st["severity"] == "Normal"
    assert "por debajo del nivel de acción" in st["text"]


def test_zone_based_flash_flood_warning_applies_to_point(monkeypatch):
    st = run(monkeypatch, canned([5.0, 5.0, 5.0], alerts=["Flash Flood Warning"]))
    assert st["severity"] == "Warning"
    assert any(r["rule_id"] == "NWS_FFW" and r["fired"] for r in st["rules"])


def test_no_gauge_is_unknown_not_normal(monkeypatch):
    st = run(monkeypatch, canned([5.0], with_gauge=False))
    assert st["severity"] == "Unknown" and st["missing_data"]


def test_telemetry_lag_under_90_min_is_not_stale(monkeypatch):
    st = run(monkeypatch, canned([5.0, 5.0, 5.0]))
    assert not any(r["rule_id"] == "STALE_DATA" and r["fired"] for r in st["rules"])


def test_outside_us(monkeypatch):
    async def nf(c, url, ttl, **p):
        raise live.LiveError("not found", 404)
    monkeypatch.setattr(live, "_get", nf)
    with pytest.raises(live.LiveError) as e:
        asyncio.run(live.status(51.5, -0.12))
    assert e.value.status == 404


def test_official_forecast_outlook(monkeypatch):
    fc = [{"validTime": iso(NOW + timedelta(hours=h)), "primary": v} for h, v in ((3, 9.0), (9, 12.8), (15, 11.0))]
    st = run(monkeypatch, canned([5.0, 5.0, 5.0], forecast=fc))
    assert st["outlook"]["category"] == "minor" and st["outlook"]["peak_ft"] == 12.8
    assert st["severity"] == "Normal"  # a forecast informs; it doesn't change the rule-decided severity
