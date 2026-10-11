"""Load replay fixtures for an area pack (real historical data, see fixtures/README.md).

An area pack is a folder in fixtures/areas/<id>/ with area.json, stations.json, readings.json, zones.geojson,
official_warnings.json, facilities.json, users.json, scenes.json and optionally route.json.
Adding a new area needs no code changes: see scripts/areas/ and scripts/build_fixtures.py.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache

from ..settings import settings


def parse_t(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@dataclass
class Fixtures:
    area: dict
    stations: dict
    readings: list[dict]
    zones: list[dict]
    facilities: list[dict]
    route: dict | None
    official_warnings: list[dict]
    users: list[dict]
    scenes: list[dict]

    def gauge(self, station_id: str) -> dict:
        return next(g for g in self.stations["gauges"] if g["station_id"] == station_id)

    def zone(self, zone_id: str) -> dict:
        return next(z for z in self.zones if z["properties"]["zone_id"] == zone_id)


def list_areas() -> list[dict]:
    out = []
    for d in sorted((settings.fixtures_dir / "areas").iterdir()):
        if (d / "area.json").exists():
            a = json.loads((d / "area.json").read_text())
            out.append({k: a.get(k) for k in ("id", "name", "short_name", "storm", "tz", "description")})
    return out


@lru_cache(maxsize=8)
def load(area_id: str | None = None) -> Fixtures:
    area_id = area_id or settings.default_area
    d = settings.fixtures_dir / "areas" / area_id
    if not (d / "area.json").exists():
        raise KeyError(f"unknown area {area_id!r}")

    def j(name: str, default=None):
        p = d / name
        return json.loads(p.read_text()) if p.exists() else default

    readings = j("readings.json")
    for r in readings:
        r["_t"] = parse_t(r["time"])
    return Fixtures(
        area=j("area.json"),
        stations=j("stations.json"),
        readings=sorted(readings, key=lambda r: r["_t"]),
        zones=j("zones.geojson")["features"],
        facilities=j("facilities.json", []),
        route=j("route.json"),
        official_warnings=j("official_warnings.json", []),
        users=j("users.json", []),
        scenes=j("scenes.json", []),
    )
