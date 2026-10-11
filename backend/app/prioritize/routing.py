"""Safer route (precomputed with OSRM for the demo; OpenRouteService avoid_polygons in live mode)."""
from __future__ import annotations

from ..geo import haversine_m


def _route_hits(route_geom: dict, lat: float, lon: float, radius_m: float = 120) -> bool:
    return any(haversine_m(lat, lon, y, x) <= radius_m for x, y in route_geom["coordinates"])


def route_advice(route_fx: dict, closed_roads: list[dict], zone_severity: dict[str, str]) -> dict:
    usual = route_fx["usual"]
    blocked_by = [r for r in closed_roads if _route_hits(usual["geometry"], r["lat"], r["lon"])]
    recommend = "safer" if blocked_by else "usual"
    return {"persona": route_fx["persona"], "recommended": recommend,
            "blocked_by": [r["name"] for r in blocked_by],
            "usual": usual, "safer": route_fx["safer"], "source": route_fx["source"]}
