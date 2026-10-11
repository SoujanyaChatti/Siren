"""SIREN pipeline: ingest -> evaluate -> prioritize -> communicate -> record.

A replay clock drives ingestion in demo mode. Rules decide every alert before any AI is called.
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import statistics
from datetime import datetime, timedelta, timezone

from . import messages
from .ai import tasks
from .clock import ReplayClock
from .geo import centroid, haversine_m, point_in_geom
from .ingest.fixtures import Fixtures, load, parse_t
from .lifecycle import (ACKNOWLEDGED, CANCELLED, DELIVERED, DRAFTED, GENERATED, SUPERSEDED, TERMINAL,
                        InvalidTransition, Lifecycle)
from .prioritize.routing import route_advice
from .prioritize.zones import exposure
from .rules.engine import SEVERITIES, RulesEngine, ZoneEvaluation, load_rules, sev_rank
from .settings import settings
from .store import ReadingStore
from .voice import elevenlabs

log = logging.getLogger("siren.pipeline")
STEP = timedelta(minutes=15)
OFFICIAL_FLOOD_VTEC = {"FF.W", "FA.W", "FL.W"}


def _stage_of(results: list[dict]) -> float | None:
    """Latest gauge stage quoted in a set of rule results (fresh readings only)."""
    for r in results:
        if r["rule_id"] == "STAGE_ACTION" and isinstance(r["inputs"].get("latest"), dict) and not r["inputs"].get("stale"):
            return r["inputs"]["latest"]["value"]
    return None


def _iso(t: datetime | None) -> str | None:
    return t.astimezone(timezone.utc).isoformat() if t else None


def _now_wall() -> datetime:
    return datetime.now(timezone.utc)


def _result_dict(r, rules: dict) -> dict:
    d = {"rule_id": r.rule_id, "version": r.version, "raw": r.raw, "fired": r.fired, "held": r.held,
         "severity": r.severity, "inputs": r.inputs, "inputs_hash": r.inputs_hash, "missing_data": r.missing_data}
    rule = rules["by_id"][r.rule_id]
    d["description"] = rule["description"]
    d["description_es"] = rule.get("description_es")
    d["official"] = bool(rule.get("official"))
    return d


class Siren:
    def __init__(self, fx: Fixtures | None = None, sink=None, area_id: str | None = None):
        self.fx = fx or load(area_id)
        self.area = self.fx.area
        self.start = parse_t(self.area["replay_start"])
        self.end = parse_t(self.area["replay_end"])
        messages.set_timezone(self.area["tz"])
        self.rules = load_rules()
        self.gauges = {g["station_id"]: g for g in self.fx.stations["gauges"]}
        self.warnings = [dict(w, _issued=parse_t(w["issued_at"]), _expires=parse_t(w["expires_at"]))
                         for w in self.fx.official_warnings]
        self.sink = sink
        self.clock = ReplayClock(self.start, self.end, speed=self.area.get("default_speed", 60))
        self.users = {u["id"]: dict(u) for u in self.fx.users}
        self.audience: dict[str, dict] = {}
        self.demo_run_id = secrets.token_hex(3)
        self.ask_counts: dict[str, int] = {}
        self._pending: set[asyncio.Task] = set()
        self._lead_time_cache: dict | None = None
        self.reset_state()

    # ------------------------------------------------------------ state

    def reset_state(self) -> None:
        self.store = ReadingStore()
        self.store.sink = self.sink
        self.engine = RulesEngine(self.gauges, self.rules)
        self.lifecycle = Lifecycle()
        self.lifecycle.sink = self.sink
        self.released = 0
        self.next_eval = self.start
        self.zone_state: dict[str, dict] = {
            z["properties"]["zone_id"]: {"severity": "Unknown", "changed_at": None, "evaluation": None,
                                         "missing": [], "fired": []}
            for z in self.fx.zones}
        self.evaluations: list[dict] = []
        self.severity_history: list[dict] = []
        self.incidents: dict[str, dict] = {}
        self.alerts: dict[str, dict] = {}
        self.deliveries: dict[str, dict] = {}
        self.photos: dict[str, dict] = {}
        self.injected: list[dict] = []
        self._counter = 0
        if self.sink:
            self.sink.reset_demo()

    def _id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter:04d}"

    def _spawn(self, coro) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return
        t = loop.create_task(coro)
        self._pending.add(t)
        t.add_done_callback(self._pending.discard)

    async def drain(self) -> None:
        """Wait for background generation tasks (used by tests and scripts)."""
        while self._pending:
            await asyncio.gather(*list(self._pending), return_exceptions=True)

    # ------------------------------------------------------------ ingest + evaluate

    def _release(self, upto: datetime) -> None:
        rs = self.fx.readings
        batch = []
        while self.released < len(rs) and rs[self.released]["_t"] <= upto:
            batch.append(rs[self.released])
            self.released += 1
        for r in sorted([x for x in self.injected if not x.get("_released") and x["_t"] <= upto], key=lambda x: x["_t"]):
            r["_released"] = True
            batch.append(r)
        for r in batch:
            self.store.add(r)

    def tick(self) -> None:
        now = self.clock.now()
        while self.next_eval <= now:
            self._release(self.next_eval)
            self.evaluate_all(self.next_eval)
            self.next_eval += STEP
        self._release(now)

    def evaluate_all(self, t: datetime) -> None:
        for zone in self.fx.zones:
            ev = self.engine.evaluate_zone(zone, t, self.store, self.warnings)
            self._record_evaluation(zone, ev)

    def _record_evaluation(self, zone: dict, ev: ZoneEvaluation) -> None:
        zid = zone["properties"]["zone_id"]
        results = [_result_dict(r, self.rules) for r in ev.results]
        for r in results:
            row = {"time": _iso(ev.time), "zone_id": zid, "rule_id": r["rule_id"], "rule_version": r["version"],
                   "fired": r["fired"], "severity": r["severity"], "inputs": r["inputs"],
                   "inputs_hash": r["inputs_hash"], "missing_data": r["missing_data"]}
            self.evaluations.append(row)
            if self.sink:
                self.sink.rule_evaluation(row)
        st = self.zone_state[zid]
        prev = st["severity"]
        fired_ids = [r["rule_id"] for r in results if r["fired"] and r["rule_id"] != "STALE_DATA"]
        st.update(evaluation={"time": _iso(ev.time), "results": results}, missing=ev.missing_data, fired=fired_ids)
        if prev == "Unknown" and st["changed_at"] is None and ev.severity == "Normal":
            st["severity"], st["changed_at"] = ev.severity, _iso(ev.time)  # first evaluation: not a change
        elif ev.severity != prev:
            st["changed_at"] = _iso(ev.time)
            st["severity"] = ev.severity
            self.severity_history.append({"time": _iso(ev.time), "zone_id": zid, "from": prev, "to": ev.severity,
                                          "rules": fired_ids, "missing": ev.missing_data})
            self._on_severity_change(zone, prev, ev.severity, results, ev.time)
        elif sev_rank(ev.severity) >= 1:
            inc = self._open_incident(zid)
            cur = self.alerts.get(inc["active_alert_id"]) if inc else None
            if cur is None:
                return
            if "PHOTO_DEPTH_ROAD" in fired_ids and "PHOTO_DEPTH_ROAD" not in cur["rule_ids"]:
                self._create_alert(zone, inc, ev.severity, results, ev.time)
                return
            now_stage, then_stage = _stage_of(results), _stage_of(cur["results"])
            rise = self.rules.get("update_alert_on_rise_ft")
            if rise and now_stage is not None and then_stage is not None and now_stage - then_stage >= rise:
                self._create_alert(zone, inc, ev.severity, results, ev.time, note=f"update: stage up {now_stage - then_stage:.1f} ft")

    # ------------------------------------------------------------ incidents and alerts

    def _open_incident(self, zid: str) -> dict | None:
        return next((i for i in self.incidents.values() if i["zone_id"] == zid and i["status"] == "open"), None)

    def _on_severity_change(self, zone: dict, prev: str, new: str, results: list[dict], t: datetime) -> None:
        zid = zone["properties"]["zone_id"]
        inc = self._open_incident(zid)
        if sev_rank(new) >= 1:
            if inc is None:
                inc = {"id": self._id(f"INC-{zid}"), "zone_id": zid, "opened_at": _iso(t), "closed_at": None,
                       "peak_severity": new, "status": "open", "active_alert_id": None, "alert_ids": []}
                self.incidents[inc["id"]] = inc
            if sev_rank(new) > sev_rank(inc["peak_severity"]):
                inc["peak_severity"] = new
            self._create_alert(zone, inc, new, results, t)
            if self.sink:
                self.sink.upsert("incidents", {k: inc[k] for k in ("id", "zone_id", "opened_at", "closed_at",
                                                                    "peak_severity", "status")})
        elif new == "Normal" and inc is not None:
            inc["status"], inc["closed_at"] = "closed", _iso(t)
            if inc["active_alert_id"]:
                self._terminate_alert(self.alerts[inc["active_alert_id"]], CANCELLED, "conditions cleared", t)
            if self.sink:
                self.sink.upsert("incidents", {k: inc[k] for k in ("id", "zone_id", "opened_at", "closed_at",
                                                                    "peak_severity", "status")})

    def _create_alert(self, zone: dict, inc: dict, severity: str, results: list[dict], t: datetime,
                      note: str = "") -> dict:
        zid = zone["properties"]["zone_id"]
        rule_ids = [r["rule_id"] for r in results if r["fired"] and r["rule_id"] != "STALE_DATA"]
        msg_en = messages.build_message(lang="en", severity=severity, zone=zone, results=results, at=t)
        alert = {"id": self._id(f"AL-{zid}"), "incident_id": inc["id"], "zone_id": zid, "severity": severity,
                 "rule_ids": rule_ids, "created_at": _iso(t), "text_en": msg_en["text"], "message_en": msg_en,
                 "results": results, "explanation": None, "ai": None, "delivery_ids": [],
                 "exposure": exposure(zone, severity, rule_ids, self.fx.facilities),
                 "photo_ids": sorted({rep.get("photo_id") for r in results if r["rule_id"] == "PHOTO_DEPTH_ROAD"
                                      and r["fired"] for rep in r["inputs"].get("verified_reports", [])} - {None})}
        self.lifecycle.start(alert, alert_id=alert["id"], delivery_id=None, actor="rules-engine",
                             note=f"{', '.join(rule_ids) or 'no rules'} -> {severity}{' (' + note + ')' if note else ''}", at=t)
        if inc.get("active_alert_id") and inc["active_alert_id"] in self.alerts:
            self._terminate_alert(self.alerts[inc["active_alert_id"]], SUPERSEDED, f"superseded by {alert['id']}", t)
        inc["active_alert_id"] = alert["id"]
        inc["alert_ids"].append(alert["id"])
        self.alerts[alert["id"]] = alert
        self._spawn(self._generate_alert(alert["id"]))
        return alert

    def _terminate_alert(self, alert: dict, state: str, note: str, t: datetime) -> None:
        if alert["state"] not in TERMINAL:
            self.lifecycle.transition(alert, state, alert_id=alert["id"], delivery_id=None, actor="rules-engine",
                                      note=note, at=t)
        for did in alert["delivery_ids"]:
            d = self.deliveries[did]
            if d["state"] not in TERMINAL:
                self.lifecycle.transition(d, state, alert_id=alert["id"], delivery_id=did, actor="rules-engine",
                                          note=note, at=t)

    async def _generate_alert(self, alert_id: str) -> None:
        alert = self.alerts.get(alert_id)
        if not alert or alert["state"] != DRAFTED:
            return  # superseded during a fast-forward before generation: no AI call spent
        zone = self.fx.zone(alert["zone_id"])
        facts = tasks.explanation_facts(zone, alert["severity"], alert["results"],
                                        alert["exposure"]["facilities"], self.zone_state[alert["zone_id"]]["missing"],
                                        parse_t(alert["created_at"]))
        res = await tasks.explain(facts)
        if self.alerts.get(alert_id) is not alert or alert["state"] != DRAFTED:
            return
        alert["explanation"], alert["ai"], alert["explanation_facts"] = res.output, res.log(), facts
        self.lifecycle.transition(alert, GENERATED, alert_id=alert_id, delivery_id=None, actor=f"ai:{res.path}",
                                  note=f"explanation by {res.model}", at=self.clock.now())
        if self.sink:
            self.sink.upsert("alerts", {"id": alert_id, "incident_id": alert["incident_id"], "severity": alert["severity"],
                                        "rule_ids": alert["rule_ids"], "text_en": alert["text_en"],
                                        "explanation": json.dumps(res.output), "ai_path": res.path,
                                        "created_at": alert["created_at"]})
        for rec in self._recipients(alert["zone_id"]):
            self._create_delivery(alert, rec)

    def _recipients(self, zid: str) -> list[dict]:
        out = [{"kind": "persona", "id": u["id"], "language": u["language"], "user": u}
               for u in self.users.values() if u["zone_id"] == zid]
        out += [{"kind": "audience", "id": s["id"], "language": s["language"], "user": None}
                for s in self.audience.values() if s["zone_id"] == zid]
        return out

    def _create_delivery(self, alert: dict, rec: dict) -> dict | None:
        if alert["state"] in TERMINAL:
            return None
        if any(self.deliveries[d]["user_id"] == rec["id"] and self.deliveries[d]["state"] not in TERMINAL
               for d in alert["delivery_ids"]):
            return None
        d = {"id": self._id("DL"), "alert_id": alert["id"], "user_id": rec["id"], "kind": rec["kind"],
             "language": rec["language"], "text": None, "card": None, "audio_key": None, "voice": None,
             "translation": None, "times": {}}
        self.lifecycle.start(d, alert_id=alert["id"], delivery_id=d["id"], actor="rules-engine",
                             note=f"recipient {rec['kind']}:{rec['id']} ({rec['language']})", at=self.clock.now())
        d["times"][DRAFTED] = _now_wall().isoformat()
        self.deliveries[d["id"]] = d
        alert["delivery_ids"].append(d["id"])
        self._spawn(self._generate_delivery(d["id"], rec.get("user")))
        return d

    async def _generate_delivery(self, did: str, user: dict | None) -> None:
        d = self.deliveries.get(did)
        if not d or d["state"] != DRAFTED:
            return
        alert = self.alerts[d["alert_id"]]
        zone = self.fx.zone(alert["zone_id"])
        t = parse_t(alert["created_at"])
        msg = messages.build_message(lang=d["language"], severity=alert["severity"], zone=zone,
                                     results=alert["results"], at=t, user=user)
        if d["language"] == "en":
            text, path = msg["text"], "template"
            d["translation"] = None
        else:
            en = messages.build_message(lang="en", severity=alert["severity"], zone=zone, results=alert["results"],
                                        at=t, user=user)
            res = await tasks.translate(en, msg, d["language"])
            text, path = res.output["text"], res.path
            d["translation"] = res.log()
            d["source_text_en"] = en["text"]
        voice = await elevenlabs.synthesize(text, d["language"])
        if self.deliveries.get(did) is not d or d["state"] != DRAFTED:
            return
        d.update(text=text, card=msg, audio_key=voice["audio_key"], voice=voice,
                 reviewed=_translation_reviewed(d["language"], path))
        self.lifecycle.transition(d, GENERATED, alert_id=alert["id"], delivery_id=did,
                                  actor=f"{'ai' if path in ('gemini', 'groq') else 'template'}:{path}",
                                  note=f"text {d['language']} via {path}; voice {voice['provider']}", at=self.clock.now())
        d["times"][GENERATED] = _now_wall().isoformat()
        if self.sink:
            self.sink.upsert("alert_deliveries", {"id": did, "alert_id": alert["id"], "user_id": d["user_id"],
                                                  "language": d["language"], "text": text,
                                                  "audio_path": voice["audio_key"], "state": d["state"],
                                                  "updated_at": _now_wall().isoformat()})

    def mark_rendered(self, did: str, actor: str) -> dict:
        d = self.deliveries[did]
        if d["state"] == GENERATED:
            self.lifecycle.transition(d, DELIVERED, alert_id=d["alert_id"], delivery_id=did, actor=actor,
                                      note="rendered on device (confirmed by client)", at=self.clock.now())
            d["times"][DELIVERED] = _now_wall().isoformat()
            alert = self.alerts[d["alert_id"]]
            if alert["state"] == GENERATED:
                self.lifecycle.transition(alert, DELIVERED, alert_id=alert["id"], delivery_id=None, actor=actor,
                                          note=f"first delivery {did}", at=self.clock.now())
        return d

    def acknowledge(self, did: str, actor: str) -> dict:
        d = self.deliveries[did]
        if d["state"] == GENERATED:  # client acked without a separate render call: record both, in order
            self.mark_rendered(did, actor)
        self.lifecycle.transition(d, ACKNOWLEDGED, alert_id=d["alert_id"], delivery_id=did, actor=actor,
                                  note="I understand", at=self.clock.now())
        d["times"][ACKNOWLEDGED] = _now_wall().isoformat()
        return d

    def deliver_to(self, alert_id: str, user_id: str) -> dict | None:
        alert = self.alerts[alert_id]
        if user_id in self.users:
            u = self.users[user_id]
            rec = {"kind": "persona", "id": u["id"], "language": u["language"], "user": u}
        elif user_id in self.audience:
            s = self.audience[user_id]
            rec = {"kind": "audience", "id": s["id"], "language": s["language"], "user": None}
        else:
            raise KeyError(user_id)
        if alert["state"] == DRAFTED:
            raise InvalidTransition("alert not generated yet")
        return self._create_delivery(alert, rec)

    def change_language(self, rec_id: str, language: str) -> None:
        """Resident switched language: supersede their open deliveries and re-deliver in the new language."""
        rec = self.users.get(rec_id) or self.audience.get(rec_id)
        if not rec or rec["language"] == language:
            return
        rec["language"] = language
        for d in self.deliveries.values():
            if d["user_id"] == rec_id and d["state"] not in TERMINAL:
                self.lifecycle.transition(d, SUPERSEDED, alert_id=d["alert_id"], delivery_id=d["id"],
                                          actor=f"resident:{rec_id}", note=f"language changed to {language}",
                                          at=self.clock.now())
        self._sync_recipient(rec_id)

    def _sync_recipient(self, rec_id: str) -> None:
        """New audience member or persona zone change: deliver the zone's active alert if there is one."""
        rec_zone = (self.users.get(rec_id) or self.audience.get(rec_id) or {}).get("zone_id")
        inc = self._open_incident(rec_zone) if rec_zone else None
        if inc and inc["active_alert_id"]:
            alert = self.alerts[inc["active_alert_id"]]
            if alert["state"] not in (DRAFTED, *TERMINAL):
                try:
                    self.deliver_to(alert["id"], rec_id)
                except (KeyError, InvalidTransition):
                    pass

    # ------------------------------------------------------------ replay controls

    def jump(self, t: datetime) -> None:
        if t < self.clock.now() or t < self.next_eval - STEP:
            playing = self.clock.playing
            self.reset_state()
            self.clock.playing = playing
        self.clock.jump(t)
        self.tick()

    def simulate_surge(self, zone_id: str | None = None, rise_to: str = "moderate") -> dict:
        zone_id = zone_id or self.area.get("audience_default_zone") or self.fx.zones[0]["properties"]["zone_id"]
        zone = self.fx.zone(zone_id)
        g = self.gauges[zone["properties"]["gauge"]]
        now = self.clock.now()
        cur = self.store.latest(g["station_id"], "stage_ft", now)
        start_v = cur["value"] if cur else g["flood_stages_ft"]["action"] - 3
        target = g["flood_stages_ft"][rise_to] + 0.5
        steps = 8
        added = []
        for i in range(1, steps + 1):
            t = now + timedelta(minutes=5 * i)
            v = round(start_v + (target - start_v) * i / steps, 2)
            r = {"time": _iso(t), "_t": t, "source": "simulate", "station_id": g["station_id"], "metric": "stage_ft",
                 "value": v, "quality": "synthetic", "source_url": "siren://simulate (synthetic backup surge)"}
            self.injected.append(r)
            added.append(r)
        return {"station_id": g["station_id"], "readings": [{k: v for k, v in r.items() if k != "_t"} for r in added]}

    # ------------------------------------------------------------ photos

    def nearest_road(self, lat: float, lon: float) -> tuple[dict | None, dict | None]:
        for z in self.fx.zones:
            if point_in_geom(lon, lat, z["geometry"]):
                roads = sorted(z["properties"].get("roads", []),
                               key=lambda r: haversine_m(lat, lon, r["lat"], r["lon"]))
                road = roads[0] if roads and haversine_m(lat, lon, roads[0]["lat"], roads[0]["lon"]) <= 400 else None
                return z, road
        return None, None

    def add_photo_report(self, *, lat: float, lon: float, image_path: str, analysis: dict, check: dict, ai: dict,
                         reporter: str) -> dict:
        t = self.clock.now()
        zone, road = self.nearest_road(lat, lon)
        pid = self._id("PH")
        status = check["status"]
        if status == "verified" and (road is None or "not_on_road" in check["flags"]):
            status = "unverified"
            check = {**check, "reasons": check["reasons"] + ["Not on a known road segment; cannot fire the road rule."]}
        rep = {"id": pid, "time": _iso(t), "lat": lat, "lon": lon, "image_path": image_path, "analysis": analysis,
               "checks": check, "status": status, "ai": ai, "reporter": reporter,
               "zone_id": zone["properties"]["zone_id"] if zone else None, "road": road}
        self.photos[pid] = rep
        if analysis.get("depth_in") is not None and status in ("verified", "unverified"):
            station = road["road_id"] if road else f"photo-{pid}"
            quality = "verified" if status == "verified" else "unverified"
            for metric, val in (("depth_in", analysis["depth_in"]), ("depth_high_in", analysis["depth_high_in"])):
                self.store.add({"time": _iso(t), "_t": t, "source": "photo", "station_id": station, "metric": metric,
                                "value": float(val), "quality": quality, "source_url": f"siren://photos/{pid}",
                                "photo_id": pid, "depth_in": analysis["depth_in"],
                                "depth_low_in": analysis["depth_low_in"]})
        if self.sink:
            self.sink.upsert("photo_reports", {"id": pid, "time": rep["time"], "lat": lat, "lon": lon,
                                               "image_path": image_path, "analysis": json.dumps(analysis),
                                               "status": status})
        self.evaluate_all(t)  # evaluate immediately; the rule decides, not the photo pipeline
        return rep

    # ------------------------------------------------------------ audience

    def audience_join(self, language: str, zone_id: str, run: str | None) -> dict:
        sid = secrets.token_urlsafe(8)
        s = {"id": sid, "demo_run_id": run or self.demo_run_id, "language": "es" if language == "es" else "en",
             "zone_id": zone_id, "joined_at": _now_wall().isoformat(), "last_seen_at": _now_wall().isoformat()}
        self.audience[sid] = s
        if self.sink:
            self.sink.upsert("audience_sessions", s)
        self._sync_recipient(sid)
        return s

    def audience_feed(self, sid: str) -> dict:
        s = self.audience[sid]
        s["last_seen_at"] = _now_wall().isoformat()
        return {"session": s, **self.resident_view(sid)}

    def audience_reset(self) -> None:
        ids = set(self.audience)
        for d in list(self.deliveries.values()):
            if d["user_id"] in ids:
                if d["state"] not in TERMINAL:
                    self.lifecycle.transition(d, CANCELLED, alert_id=d["alert_id"], delivery_id=d["id"],
                                              actor="director", note="audience reset", at=self.clock.now())
        self.audience.clear()
        self.ask_counts.clear()
        self.demo_run_id = secrets.token_hex(3)

    def audience_summary(self) -> dict:
        ids = {s["id"] for s in self.audience.values()}
        ds = [d for d in self.deliveries.values() if d["user_id"] in ids]
        events = [e for e in self.lifecycle.events if e["delivery_id"] and any(e["delivery_id"] == d["id"] for d in ds)]
        delivered = {e["delivery_id"] for e in events if e["to_state"] == DELIVERED}
        acked = {e["delivery_id"] for e in events if e["to_state"] == ACKNOWLEDGED}
        ack_secs = []
        for d in ds:
            if DELIVERED in d["times"] and ACKNOWLEDGED in d["times"]:
                ack_secs.append((parse_t(d["times"][ACKNOWLEDGED]) - parse_t(d["times"][DELIVERED])).total_seconds())
        by_lang = {"en": 0, "es": 0}
        for s in self.audience.values():
            by_lang[s["language"]] = by_lang.get(s["language"], 0) + 1
        by_zone: dict[str, int] = {}
        for s in self.audience.values():
            by_zone[s["zone_id"]] = by_zone.get(s["zone_id"], 0) + 1
        return {"demo_run_id": self.demo_run_id, "joined": len(self.audience), "by_language": by_lang,
                "by_zone": by_zone, "deliveries": len(ds), "delivered": len(delivered), "acknowledged": len(acked),
                "median_seconds_to_ack": round(statistics.median(ack_secs), 1) if ack_secs else None}

    # ------------------------------------------------------------ resident view

    def resident_view(self, rec_id: str) -> dict:
        rec = self.users.get(rec_id) or self.audience.get(rec_id)
        zid = rec["zone_id"]
        zone = self.fx.zone(zid)
        st = self.zone_state[zid]
        mine = [self.deliveries[did] for a in self.alerts.values() if a["zone_id"] == zid
                for did in a["delivery_ids"] if self.deliveries[did]["user_id"] == rec_id]
        visible = [d for d in mine if d["state"] in (GENERATED, DELIVERED, ACKNOWLEDGED)]
        current = visible[-1] if visible else None
        out = {"zone": {"zone_id": zid, "name": zone["properties"]["name"], "name_es": zone["properties"]["name_es"],
                        "severity": st["severity"], "changed_at": st["changed_at"], "missing": st["missing"]},
               "clock": self.clock.state(), "delivery": None, "history": []}
        if current:
            alert = self.alerts[current["alert_id"]]
            out["delivery"] = {**_public_delivery(current), "alert_severity": alert["severity"],
                               "alert_created_at": alert["created_at"], "alert_state": alert["state"]}
        out["history"] = [_public_delivery(d) for d in mine[-6:]]
        if rec_id in self.users and self.users[rec_id].get("needs", {}).get("commute") and self.fx.route:
            out["route"] = self.route_status()
        out["demo_location"] = self.demo_location()
        return out

    def demo_location(self) -> dict | None:
        dp = self.area.get("demo_photo")
        if not dp:
            return None
        road = next(r for r in self.fx.zone(dp["zone_id"])["properties"]["roads"] if r["road_id"] == dp["road_id"])
        return {"lat": road["lat"], "lon": road["lon"], "name": road["name"], "zone_id": dp["zone_id"]}

    def route_status(self) -> dict | None:
        if not self.fx.route:
            return None
        closed = []
        for rep in self.photos.values():
            if rep["status"] == "verified" and rep["road"] and (rep["analysis"].get("depth_high_in") or 0) >= 12:
                closed.append(rep["road"])
        return route_advice(self.fx.route, closed, {z: s["severity"] for z, s in self.zone_state.items()})

    # ------------------------------------------------------------ Q&A facts

    def incident_facts(self, zid: str) -> list[dict]:
        zone = self.fx.zone(zid)
        st = self.zone_state[zid]
        t = self.clock.now()
        facts = []
        sev_en, sev_es = st["severity"], messages.SEVERITY_WORD["es"][st["severity"]]
        since = parse_t(st["changed_at"]) if st["changed_at"] else t  # stable text so cached answers are reusable
        facts.append({"id": "F1", "en": f"{zone['properties']['name']} has been at {sev_en} level since {messages.local_time(since, 'en')}.",
                      "es": f"{zone['properties']['name_es']} está en nivel {sev_es} desde las {messages.local_time(since, 'es')}."})
        g = self.gauges[zone["properties"]["gauge"]]
        latest = self.store.latest(g["station_id"], "stage_ft", t)
        if latest:
            minor = g["flood_stages_ft"]["minor"]
            facts.append({"id": "F2", "en": f"{g['name']} is at {latest['value']:.1f} ft; minor flood stage is {minor:.1f} ft.",
                          "es": f"{g['name']} está a {latest['value']:.1f} pies; el nivel de inundación menor es {minor:.1f} pies."})
        for rep in self.photos.values():
            if rep["zone_id"] == zid and rep["status"] == "verified" and rep["road"]:
                a = rep["analysis"]
                facts.append({"id": "F3", "kind": "photo",
                              "en": f"A verified photo shows about {round(a['depth_in'])} inches of water on {rep['road']['name']}.",
                              "es": f"Una foto verificada muestra unas {round(a['depth_in'])} pulgadas de agua en {rep['road']['name']}."})
                break
        active = [w for w in self.warnings if w["_issued"] <= t < w["_expires"] and w["vtec"] in OFFICIAL_FLOOD_VTEC
                  and point_in_geom(*centroid(zone["geometry"]), w["polygon"])]
        if active:
            facts.append({"id": "F4", "en": f"Official NWS {active[0]['event']} is active for this area.",
                          "es": f"Hay una alerta oficial del NWS activa para esta área ({active[0]['event']})."})
        rs = self.route_status()
        route_zone = next((u["zone_id"] for u in self.users.values() if rs and u["id"] == rs["persona"]), None)
        if rs and rs["recommended"] == "safer" and zid == route_zone:
            facts.append({"id": "F5", "en": f"The usual commute route is blocked at {', '.join(rs['blocked_by'])}; a safer route avoids it.",
                          "es": f"La ruta habitual está bloqueada en {', '.join(rs['blocked_by'])}; una ruta más segura la evita."})
        for f in facts:
            for k in ("en", "es"):
                f[k] = f[k].replace("..", ".")
        return facts

    # ------------------------------------------------------------ lead time

    def lead_time(self) -> dict:
        """Deterministic, independent run over the whole replayed storm with the fixed thresholds.
        SIREN's own first alert excludes the NWS_FFW rule (which simply relays the official warning)."""
        if self._lead_time_cache:
            return self._lead_time_cache
        store, engine = ReadingStore(), RulesEngine(self.gauges, load_rules())
        rs, i = self.fx.readings, 0
        first: dict[str, dict] = {}
        t = self.start
        while t <= self.end:
            while i < len(rs) and rs[i]["_t"] <= t:
                store.add(rs[i])
                i += 1
            for z in self.fx.zones:
                zid = z["properties"]["zone_id"]
                ev = engine.evaluate_zone(z, t, store, [])  # official warnings excluded on purpose
                f = first.setdefault(zid, {})
                if sev_rank(ev.severity) >= 1 and "watch" not in f:
                    f["watch"] = {"time": t, "rules": [r.rule_id for r in ev.fired_rules]}
                if sev_rank(ev.severity) >= 2 and "warning" not in f:
                    f["warning"] = {"time": t, "severity": ev.severity, "rules": [r.rule_id for r in ev.fired_rules]}
            t += STEP
        # Second pass with official warnings included: how fast SIREN relays the official warning to residents
        relay: dict[str, datetime] = {}
        store2, engine2, i2, t = ReadingStore(), RulesEngine(self.gauges, load_rules()), 0, self.start
        while t <= self.end:
            while i2 < len(rs) and rs[i2]["_t"] <= t:
                store2.add(rs[i2])
                i2 += 1
            for z in self.fx.zones:
                zid = z["properties"]["zone_id"]
                if zid not in relay:
                    ev = engine2.evaluate_zone(z, t, store2, self.warnings)
                    if any(r.rule_id == "NWS_FFW" and r.fired for r in ev.results):
                        relay[zid] = t
            t += STEP
        results = []
        for z in self.fx.zones:
            zid = z["properties"]["zone_id"]
            lon, lat = centroid(z["geometry"])
            official = next((w for w in self.warnings if w["vtec"] in OFFICIAL_FLOOD_VTEC
                             and point_in_geom(lon, lat, w["polygon"])), None)
            f = first.get(zid, {})
            sw = f.get("warning")
            lead = None
            if sw and official:
                lead = round((official["_issued"] - sw["time"]).total_seconds() / 60, 1)
            watch_lead = None
            if f.get("watch") and official:
                watch_lead = round((official["_issued"] - f["watch"]["time"]).total_seconds() / 60, 1)
            ffw = next((w for w in self.warnings if w["vtec"] == "FF.W" and point_in_geom(lon, lat, w["polygon"])), None)
            relay_min = round((relay[zid] - ffw["_issued"]).total_seconds() / 60, 1) if ffw and zid in relay else None
            if lead is None:
                note = "No SIREN Warning or no official warning for this zone during the replay."
            elif lead > 0:
                note = f"SIREN flagged {z['properties']['name'].split(' — ')[0]} {lead:.0f} minutes before the official warning."
            else:
                note = (f"The official warning came first, {abs(lead):.0f} minutes before SIREN's own gauge-based Warning. "
                        "SIREN's value here is street-level depth evidence, language access and delivery tracking "
                        "on top of official warnings.")
            row = {"zone_id": zid, "zone_name": z["properties"]["name"],
                   "siren_first_alert_at": _iso(sw["time"]) if sw else None,
                   "siren_severity": sw["severity"] if sw else None, "siren_rules": sw["rules"] if sw else [],
                   "siren_first_watch_at": _iso(f["watch"]["time"]) if f.get("watch") else None,
                   "siren_first_watch_rules": f["watch"]["rules"] if f.get("watch") else [],
                   "official_warning_id": official["id"] if official else None,
                   "official_event": official["event"] if official else None,
                   "official_issued_at": official["issued_at"] if official else None,
                   "official_source_url": official.get("source_url") if official else None,
                   "lead_minutes": lead, "watch_lead_minutes": watch_lead, "relay_minutes": relay_min,
                   "computed_at": _now_wall().isoformat(), "notes": note}
            results.append(row)
            if self.sink:
                self.sink.upsert("lead_time_results", {k: row[k] for k in (
                    "zone_id", "siren_first_alert_at", "siren_severity", "official_warning_id", "official_issued_at",
                    "lead_minutes", "computed_at", "notes")}, key=None)
        self._lead_time_cache = {
            "storm": f"{self.area['storm']}, {self.area['name']}",
            "ruleset_version": self.rules["ruleset_version"],
            "method": ("Lead time = official issue time - SIREN first alert at Warning or above, in minutes "
                       "(positive = SIREN earlier). SIREN's run excludes the NWS_FFW relay rule; thresholds were "
                       "fixed before computing. One storm, not a statistical study."),
            "caveat": ("SIREN's rules use gauge thresholds for specific zones, while official warnings cover larger "
                       "areas and include forecaster judgment, so the comparison shows timing, not which is better overall."),
            "zones": results,
        }
        return self._lead_time_cache

    # ------------------------------------------------------------ views

    def gauge_status(self) -> list[dict]:
        now = self.clock.now()
        out = []
        for g in self.fx.stations["gauges"]:
            latest = self.store.latest(g["station_id"], "stage_ft", now)
            age = None if latest is None else (now - latest["_t"]).total_seconds() / 60
            fresh = "missing" if age is None or age > 45 else "delayed" if age > 20 else "live"
            out.append({**{k: g[k] for k in ("station_id", "usgs_id", "name", "lat", "lon", "flood_stages_ft",
                                              "flood_stages_source")},
                        "latest": _public_reading(latest), "age_minutes": None if age is None else round(age, 1),
                        "freshness": fresh})
        return out

    def series(self) -> dict:
        now = self.clock.now()
        out = {}
        for g in self.fx.stations["gauges"]:
            out[g["station_id"]] = [{"t": r["time"], "v": r["value"], "q": r["quality"]}
                                    for r in self.store.series(g["station_id"], "stage_ft", self.start - STEP * 2, now)]
        for rg in self.fx.stations["rain"]:
            out[rg["station_id"]] = [{"t": r["time"], "v": r["value"]}
                                     for r in self.store.series(rg["station_id"], "rain_in", self.start, now)]
        return out

    def timeline(self, limit: int = 120) -> list[dict]:
        items = [{"time": h["time"], "kind": "severity", "zone_id": h["zone_id"], "from": h["from"], "to": h["to"],
                  "rules": h["rules"], "missing": h["missing"]} for h in self.severity_history]
        for e in self.lifecycle.events:
            if e["delivery_id"] is None:
                a = self.alerts.get(e["alert_id"])
                items.append({"time": e["time"], "wall_time": e["wall_time"], "kind": "alert", "alert_id": e["alert_id"],
                              "zone_id": a["zone_id"] if a else None, "severity": a["severity"] if a else None,
                              "from": e["from_state"], "to": e["to_state"], "actor": e["actor"], "note": e["note"]})
            else:
                d = self.deliveries.get(e["delivery_id"])
                if d and d["kind"] == "persona":
                    items.append({"time": e["time"], "wall_time": e["wall_time"], "kind": "delivery",
                                  "alert_id": e["alert_id"], "delivery_id": e["delivery_id"], "user_id": d["user_id"],
                                  "language": d["language"], "from": e["from_state"], "to": e["to_state"],
                                  "actor": e["actor"]})
        now = self.clock.now()
        for w in self.warnings:
            if w["_issued"] <= now and w["vtec"] in OFFICIAL_FLOOD_VTEC:
                items.append({"time": _iso(w["_issued"]), "kind": "official", "warning_id": w["id"],
                              "event": w["event"], "source_url": w.get("source_url")})
        items.sort(key=lambda x: (x["time"], x.get("wall_time") or ""), reverse=True)
        return items[:limit]

    def state(self) -> dict:
        self.tick()
        now = self.clock.now()
        zones = []
        for z in self.fx.zones:
            zid = z["properties"]["zone_id"]
            st = self.zone_state[zid]
            inc = self._open_incident(zid)
            exp = exposure(z, st["severity"] if st["severity"] in SEVERITIES else "Normal", st["fired"], self.fx.facilities)
            zones.append({"zone_id": zid, "name": z["properties"]["name"], "name_es": z["properties"]["name_es"],
                          "severity": st["severity"], "changed_at": st["changed_at"], "fired": st["fired"],
                          "missing": st["missing"], "gauge": z["properties"]["gauge"], "rain": z["properties"]["rain"],
                          "incident_id": inc["id"] if inc else None,
                          "active_alert_id": inc["active_alert_id"] if inc else None,
                          "exposure": {"label": exp["label"], "verified_by": exp["verified_by"],
                                       "facility_count": len(exp["facilities"])}})
        last_ai = next((a for a in reversed([a for a in self.alerts.values() if a.get("ai")])), None)
        return {
            "clock": self.clock.state(), "offline": settings.demo_offline, "mode": "replay",
            "force_gemini_failure": settings.force_gemini_failure, "demo_run_id": self.demo_run_id,
            "area": self.area["name"], "storm": f"{self.area['storm']} (replay)",
            "area_info": {k: self.area.get(k) for k in ("id", "name", "short_name", "storm", "tz", "description",
                                                         "audience_default_zone", "rain_source")},
            "zones": zones, "gauges": self.gauge_status(),
            "rain": [{**r, "last_hour_in": round(sum(x["value"] for x in self.store.window(
                r["station_id"], "rain_in", now - timedelta(hours=1), now)), 2)} for r in self.fx.stations["rain"]],
            "incidents": [{k: v for k, v in i.items()} for i in self.incidents.values() if i["status"] == "open"],
            "alerts": [_alert_summary(a) for a in sorted(self.alerts.values(), key=lambda a: a["created_at"], reverse=True)[:20]],
            "photos": [_public_photo(p) for p in self.photos.values()],
            "route": self.route_status(),
            "last_ai_path": last_ai["ai"]["path"] if last_ai else None,
            "audience": self.audience_summary(),
            "scenes": self.fx.scenes,
            "pending_generation": len(self._pending),
        }


# ---------------------------------------------------------------- serializers

def _translation_reviewed(language: str, path: str) -> dict:
    try:
        review = json.loads((settings.fixtures_dir / "translation_review.json").read_text())
    except FileNotFoundError:
        review = {}
    r = review.get(language, {})
    return {"template_phrases_reviewed": bool(r.get("reviewed")), "reviewer": r.get("reviewer"),
            "path": path, "note": r.get("note")}


def _public_reading(r: dict | None) -> dict | None:
    if r is None:
        return None
    return {k: v for k, v in r.items() if not k.startswith("_")}


def _public_delivery(d: dict) -> dict:
    return {k: d[k] for k in ("id", "alert_id", "user_id", "kind", "language", "state", "text", "card", "audio_key",
                              "voice", "translation") if k in d} | {"reviewed": d.get("reviewed"),
                                                                     "audio_url": f"/api/audio/{d['audio_key']}" if d.get("audio_key") else None}


def _alert_summary(a: dict) -> dict:
    return {"id": a["id"], "incident_id": a["incident_id"], "zone_id": a["zone_id"], "severity": a["severity"],
            "rule_ids": a["rule_ids"], "created_at": a["created_at"], "state": a["state"], "text_en": a["text_en"],
            "headline": (a.get("explanation") or {}).get("headline") or a["message_en"]["headline"],
            "ai_path": (a.get("ai") or {}).get("path"), "deliveries": len(a["delivery_ids"])}


def _public_photo(p: dict) -> dict:
    return {k: p[k] for k in ("id", "time", "lat", "lon", "analysis", "checks", "status", "zone_id", "road", "reporter")} | {
        "image_url": f"/api/photos/{p['id']}/image", "ai_path": (p.get("ai") or {}).get("path"),
        "model": (p.get("ai") or {}).get("model")}
