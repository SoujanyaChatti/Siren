"""Deterministic rules engine: readings in, severity per zone out.

Each rule is evaluated in two steps so any evaluation can be re-run from its stored inputs:
  1. gather_inputs(): pick the exact readings the rule needs (with timestamps and sources)
  2. condition():     a pure function of (rule, inputs) -> True / False / None (could not evaluate)
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import yaml

from ..geo import centroid, point_in_geom
from ..store import ReadingStore
from .hysteresis import HysteresisState

RULES_PATH = Path(__file__).with_name("rules.yaml")
SEVERITIES = ["Normal", "Watch", "Warning", "Emergency"]
UNKNOWN = "Unknown"


def sev_rank(s: str) -> int:
    return SEVERITIES.index(s) if s in SEVERITIES else -1


def load_rules(path: Path = RULES_PATH) -> dict:
    cfg = yaml.safe_load(path.read_text())
    cfg["by_id"] = {r["id"]: r for r in cfg["rules"]}
    return cfg


def _reading_view(r: dict | None) -> dict | None:
    if r is None:
        return None
    return {k: r[k] for k in ("time", "station_id", "metric", "value", "quality", "source", "source_url") if k in r}


def inputs_hash(rule: dict, inputs: dict) -> str:
    blob = json.dumps({"rule_id": rule["id"], "version": rule["version"], "inputs": inputs},
                      sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ---------------------------------------------------------------- pure conditions

def _stage_condition(rule: dict, inp: dict) -> bool | None:
    latest = inp.get("latest")
    if latest is None or inp.get("stale"):
        return None
    return latest["value"] >= inp["threshold_ft"]


def _rise_condition(rule: dict, inp: dict) -> bool | None:
    latest, prior = inp.get("latest"), inp.get("prior")
    if latest is None or prior is None or inp.get("stale"):
        return None
    return round(latest["value"] - prior["value"], 3) >= rule["threshold"]["rise_ft"]


def _rain_condition(rule: dict, inp: dict) -> bool | None:
    if not inp.get("readings"):
        return None
    return round(sum(r["value"] for r in inp["readings"]), 3) >= rule["threshold"]["rain_in"]


def _ffw_condition(rule: dict, inp: dict) -> bool | None:
    return len(inp.get("active_warnings", [])) > 0


def _photo_condition(rule: dict, inp: dict) -> bool | None:
    return any(r["value"] >= rule["threshold"]["depth_high_in"] for r in inp.get("verified_reports", []))


def _stale_condition(rule: dict, inp: dict) -> bool | None:
    return bool(inp.get("stale"))


CONDITIONS: dict[str, Callable[[dict, dict], bool | None]] = {
    "STAGE_ACTION": _stage_condition,
    "STAGE_MINOR": _stage_condition,
    "STAGE_MODERATE": _stage_condition,
    "RISE_RATE": _rise_condition,
    "RAIN_1H": _rain_condition,
    "NWS_FFW": _ffw_condition,
    "PHOTO_DEPTH_ROAD": _photo_condition,
    "STALE_DATA": _stale_condition,
}


def condition(rule: dict, inputs: dict) -> bool | None:
    return CONDITIONS[rule["id"]](rule, inputs)


# ---------------------------------------------------------------- engine

@dataclass
class RuleResult:
    rule_id: str
    version: str
    raw: bool | None          # condition right now (None = could not evaluate)
    fired: bool               # effective after hysteresis
    held: bool                # true when hysteresis is holding a rule that is no longer raw-true
    severity: str | None
    inputs: dict
    inputs_hash: str
    missing_data: list[str]


@dataclass
class ZoneEvaluation:
    zone_id: str
    time: datetime
    severity: str
    results: list[RuleResult] = field(default_factory=list)
    missing_data: list[str] = field(default_factory=list)

    @property
    def fired_rules(self) -> list[RuleResult]:
        return [r for r in self.results if r.fired and r.rule_id != "STALE_DATA"]


class RulesEngine:
    def __init__(self, gauges: dict[str, dict], rules: dict | None = None):
        self.rules = rules or load_rules()
        self.gauges = gauges  # station_id -> {flood_stages_ft: {...}, name, ...}
        self.hyst: dict[str, HysteresisState] = {}

    def reset(self) -> None:
        self.hyst.clear()

    def gather_inputs(self, rule: dict, zone: dict, t: datetime, store: ReadingStore,
                      warnings: list[dict]) -> dict[str, Any]:
        p = zone["properties"]
        rid = rule["id"]
        if rid.startswith("STAGE_") or rid in ("RISE_RATE", "STALE_DATA"):
            gauge = self.gauges[p["gauge"]]
            latest = store.latest(p["gauge"], "stage_ft", t)
            age_min = None if latest is None else (t - latest["_t"]).total_seconds() / 60
            stale_limit = self.rules["by_id"]["STALE_DATA"]["threshold"]["max_age_minutes"]
            base = {"station_id": p["gauge"], "station_name": gauge["name"],
                    "station_short": gauge.get("short") or {"en": gauge["name"], "es": gauge["name"]},
                    "evaluated_at": t.isoformat(),
                    "latest": _reading_view(latest), "age_minutes": None if age_min is None else round(age_min, 1),
                    "stale": latest is None or age_min > stale_limit}
            if rid.startswith("STAGE_"):
                cat = rule["threshold"]["flood_category"]
                base["flood_category"] = cat
                base["threshold_ft"] = gauge["flood_stages_ft"][cat]
                base["threshold_source"] = gauge.get("flood_stages_source")
            if rid == "RISE_RATE":
                th = rule["threshold"]
                prior = None
                if latest is not None:
                    target = latest["_t"] - timedelta(minutes=th["window_minutes"])
                    cand = store.latest(p["gauge"], "stage_ft", target)
                    if cand and (target - cand["_t"]) <= timedelta(minutes=th["lookup_tolerance_minutes"]):
                        prior = cand
                base["prior"] = _reading_view(prior)
            return base
        if rid == "RAIN_1H":
            win = rule["threshold"]["window_minutes"]
            rs = store.window(p["rain"], "rain_in", t - timedelta(minutes=win), t)
            return {"station_id": p["rain"], "evaluated_at": t.isoformat(), "window_minutes": win,
                    "readings": [_reading_view(r) for r in rs],
                    "sum_in": round(sum(r["value"] for r in rs), 2)}
        if rid == "NWS_FFW":
            lon, lat = centroid(zone["geometry"])
            active = [
                {"id": w["id"], "event": w["event"], "issued_at": w["issued_at"], "expires_at": w["expires_at"],
                 "source_url": w.get("source_url")}
                for w in warnings
                if w.get("vtec") == rule["threshold"]["vtec"] and w["_issued"] <= t < w["_expires"]
                and point_in_geom(lon, lat, w["polygon"])
            ]
            return {"evaluated_at": t.isoformat(), "zone_centroid": [round(lon, 5), round(lat, 5)],
                    "active_warnings": active}
        if rid == "PHOTO_DEPTH_ROAD":
            th = rule["threshold"]
            reports = []
            for road in p.get("roads", []):
                for r in store.window(road["road_id"], "depth_high_in", t - timedelta(minutes=th["max_age_minutes"]), t):
                    if r.get("quality") == "verified":
                        reports.append({**_reading_view(r), "road_name": road["name"], "photo_id": r.get("photo_id"),
                                        "depth_in": r.get("depth_in"), "depth_low_in": r.get("depth_low_in")})
            return {"evaluated_at": t.isoformat(), "verified_reports": reports}
        raise KeyError(rid)

    def evaluate_zone(self, zone: dict, t: datetime, store: ReadingStore, warnings: list[dict]) -> ZoneEvaluation:
        zid = zone["properties"]["zone_id"]
        hyst = self.hyst.setdefault(zid, HysteresisState(self.rules["hysteresis"]))
        results: list[RuleResult] = []
        missing: list[str] = []
        stale = False
        for rule in self.rules["rules"]:
            inp = self.gather_inputs(rule, zone, t, store, warnings)
            raw = condition(rule, inp)
            rule_missing: list[str] = []
            if rule["id"] == "STALE_DATA":
                stale = bool(raw)
                if stale:
                    age = inp["age_minutes"]
                    msg = (f"No reading from {inp['station_name']} for {age:.0f} min" if age is not None
                           else f"No readings from {inp['station_name']}")
                    rule_missing.append(msg)
                    missing.append(msg)
                fired, held = bool(raw), False
            else:
                if raw is None:
                    rule_missing.append(f"{rule['id']}: inputs unavailable")
                stage_value = inp.get("latest", {}).get("value") if isinstance(inp.get("latest"), dict) else None
                fired, held = hyst.update(rule["id"], raw, stage_value, inp.get("threshold_ft"))
            sev = rule.get("severity")
            results.append(RuleResult(rule["id"], rule["version"], raw, fired, held,
                                      sev if fired else None, inp, inputs_hash(rule, inp), rule_missing))
        severity = self.combine(results, stale)
        return ZoneEvaluation(zid, t, severity, results, missing)

    def combine(self, results: list[RuleResult], stale: bool) -> str:
        by = {r.rule_id: r for r in results}
        base = 0
        for r in results:
            if r.fired and r.rule_id not in ("RISE_RATE", "STALE_DATA") and r.severity:
                base = max(base, sev_rank(r.severity))
        final = base
        rise = by.get("RISE_RATE")
        if rise and rise.fired:
            eff = self.rules["by_id"]["RISE_RATE"]["effect"]
            cap = sev_rank(eff["max"])
            if base < cap:
                final = max(base, min(base + eff["raise_levels"], cap))
        if stale and final == 0:
            return UNKNOWN
        return SEVERITIES[final]
