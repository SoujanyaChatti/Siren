"""Affected zones and facility exposure, labelled Estimated exposure vs Verified danger."""
from __future__ import annotations

from ..geo import centroid, haversine_m, point_in_geom
from ..rules.engine import sev_rank

VERIFIED_RULES = {"STAGE_MINOR", "STAGE_MODERATE", "NWS_FFW", "PHOTO_DEPTH_ROAD"}


def facilities_in_zone(zone: dict, facilities: list[dict]) -> list[dict]:
    lon0, lat0 = centroid(zone["geometry"])
    out = []
    for f in facilities:
        if point_in_geom(f["lon"], f["lat"], zone["geometry"]):
            out.append({**f, "distance_m": round(haversine_m(lat0, lon0, f["lat"], f["lon"]))})
    return sorted(out, key=lambda f: f["distance_m"])


def exposure(zone: dict, severity: str, fired_rule_ids: list[str], facilities: list[dict]) -> dict:
    affected = sev_rank(severity) >= 1
    verified = sorted(set(fired_rule_ids) & VERIFIED_RULES)
    label = "verified_danger" if (affected and verified) else "estimated_exposure" if affected else "none"
    return {"zone_id": zone["properties"]["zone_id"], "affected": affected, "label": label,
            "verified_by": verified, "facilities": facilities_in_zone(zone, facilities) if affected else []}
