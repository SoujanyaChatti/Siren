"""End-to-end through the HTTP API, offline (no keys, no network)."""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def c():
    with TestClient(app) as client:
        yield client


def wait_for(fn, timeout=5.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.1)
    raise AssertionError("condition not met")


def test_health_offline(c):
    h = c.get("/api/health").json()
    assert h["offline"] is True and h["deps"]["fixtures"]["readings"] > 100


def test_full_demo_flow(c):
    c.post("/api/director", json={"action": "reset_all"})
    s = c.get("/api/state").json()
    assert {z["severity"] for z in s["zones"]} == {"Normal"}

    # Judge joins in Spanish, Zone B, before the storm
    sid = c.post("/api/audience/join", json={"language": "es", "zone_id": "B"}).json()["id"]
    assert c.get(f"/api/audience/{sid}/feed").json()["delivery"] is None

    # Conditions change -> Warning (rules decide)
    c.post("/api/replay", json={"action": "jump", "time": "2024-07-08T14:20:00Z"})
    feed = wait_for(lambda: (f := c.get(f"/api/audience/{sid}/feed").json())["delivery"] and f)
    d = feed["delivery"]
    assert d["language"] == "es" and d["state"] == "Generated" and "Dé la vuelta" in d["text"]

    # Acknowledged before Delivered is not allowed at the lifecycle level; the phone confirms render first
    assert c.post(f"/api/deliveries/{d['id']}/rendered").json()["state"] == "Delivered"
    assert c.post(f"/api/audience/{sid}/ack", json={"delivery_id": d["id"]}).json()["state"] == "Acknowledged"
    summ = c.get("/api/audience/summary").json()
    assert summ["joined"] == 1 and summ["delivered"] == 1 and summ["acknowledged"] == 1

    # Evidence shows the judge's own delivery with its full lifecycle
    ev = c.get(f"/api/alerts/{d['alert_id']}/evidence").json()
    mine = next(x for x in ev["deliveries"] if x["user_id"] == sid)
    assert [e["to_state"] for e in mine["events"]] == ["Drafted", "Generated", "Delivered", "Acknowledged"]
    assert ev["rules"] and ev["explanation"] and ev["ai"]["path"] == "template"
    assert c.post(f"/api/alerts/{d['alert_id']}/rerun").json()["all_match"]

    # Photo at the Zone B underpass -> verified depth -> PHOTO_DEPTH_ROAD -> Emergency, route changes
    c.post("/api/replay", json={"action": "scene", "scene": "photo"})
    p = c.post("/api/director", json={"action": "photo"}).json()
    assert p["status"] == "verified" and p["analysis"]["depth_high_in"] >= 12
    s = c.get("/api/state").json()
    zb = next(z for z in s["zones"] if z["zone_id"] == "B")
    assert zb["severity"] == "Emergency" and "PHOTO_DEPTH_ROAD" in zb["fired"]
    assert s["route"]["recommended"] == "safer"

    # Ask SIREN, grounded, then the per-phone limit
    a = c.post("/api/ask", json={"question": "¿Qué hago ahora?", "session_id": sid}).json()
    assert a["answerable"] and a["citations"]
    for _ in range(2):
        c.post("/api/ask", json={"question": "x", "session_id": sid})
    assert c.post("/api/ask", json={"question": "again", "session_id": sid}).status_code == 429


def test_lead_time_reported_honestly(c):
    lt = c.get("/api/lead-time").json()
    assert len(lt["zones"]) == 3
    for z in lt["zones"]:
        assert z["official_issued_at"] and z["siren_first_alert_at"]
        assert "NWS_FFW" not in z["siren_rules"]
        assert (z["lead_minutes"] > 0) == ("before the official warning" in z["notes"])


def test_invalid_ack_rejected(c):
    c.post("/api/director", json={"action": "reset_all"})
    c.post("/api/replay", json={"action": "scene", "scene": "warning"})
    s = c.get("/api/state").json()
    aid = next(z for z in s["zones"] if z["zone_id"] == "C")["active_alert_id"]
    ev = wait_for(lambda: (e := c.get(f"/api/alerts/{aid}/evidence").json())["deliveries"] and e)
    did = ev["deliveries"][0]["id"]
    c.post(f"/api/deliveries/{did}/rendered")
    c.post(f"/api/deliveries/{did}/ack")
    assert c.post(f"/api/deliveries/{did}/ack").status_code == 409  # Acknowledged -> Acknowledged is invalid


def test_update_alert_when_stage_keeps_rising():
    """Same severity, but the river rose 2+ ft above the last alert: residents get fresh numbers."""
    import asyncio
    from app.ingest.fixtures import parse_t
    from app.pipeline import Siren

    s = Siren(area_id="asheville-helene")
    s.jump(parse_t("2024-09-27T16:00:00Z"))
    asyncio.run(s.drain())
    inc = s._open_incident("B")
    notes = [e["note"] for e in s.lifecycle.events if e["alert_id"] in inc["alert_ids"] and e["to_state"] == "Drafted"]
    assert any("update: stage up" in n for n in notes)
    assert s.alerts[inc["active_alert_id"]]["severity"] == "Emergency"


def test_area_switch_and_second_area_lead_time(c):
    areas = c.get("/api/areas").json()
    assert {a["id"] for a in areas["areas"]} >= {"houston-brays", "asheville-helene"}
    assert c.post("/api/area", json={"id": "asheville-helene"}).json()["active"] == "asheville-helene"
    s = c.get("/api/state").json()
    assert s["area_info"]["tz"] == "America/New_York" and len(s["zones"]) == 3
    lt = c.get("/api/lead-time").json()
    assert all(z["official_issued_at"] for z in lt["zones"])
    c.post("/api/replay", json={"action": "scene", "scene": "recede"})
    za = next(z for z in c.get("/api/state").json()["zones"] if z["zone_id"] == "A")
    assert za["missing"], "Swannanoa gauge outage must be flagged as missing data"
    assert c.post("/api/area", json={"id": "nowhere"}).status_code == 404
    c.post("/api/area", json={"id": "houston-brays"})


def test_every_area_pack_replays_end_to_end():
    """Each shipped area loads, escalates on real data, and produces a lead-time row per zone."""
    import asyncio
    from app.ingest.fixtures import list_areas
    from app.pipeline import Siren
    from app.rules.engine import sev_rank

    for a in list_areas():
        s = Siren(area_id=a["id"])
        s.jump(s.end)
        asyncio.run(s.drain())
        assert any(sev_rank(h["to"]) >= 2 for h in s.severity_history), a["id"]
        assert len(s.lead_time()["zones"]) == len(s.fx.zones)
        assert s.demo_location() is not None


def test_resident_language_switch_redelivers(c):
    c.post("/api/director", json={"action": "reset_all"})
    c.post("/api/replay", json={"action": "jump", "time": "2024-07-08T14:20:00Z"})
    first = wait_for(lambda: (r := c.get("/api/residents/maria").json())["delivery"] and r["delivery"]["state"] != "Drafted" and r)
    assert first["delivery"]["language"] == "es"
    c.patch("/api/users/maria", json={"language": "en"})
    second = wait_for(lambda: (r := c.get("/api/residents/maria").json())["delivery"] and r["delivery"]["language"] == "en" and r)
    assert "Turn around, don't drown" in second["delivery"]["text"]
    ev = c.get(f"/api/alerts/{second['delivery']['alert_id']}/evidence").json()
    assert any(e["note"] == "language changed to en" for d in ev["deliveries"] for e in d["events"])
    c.patch("/api/users/maria", json={"language": "es"})
