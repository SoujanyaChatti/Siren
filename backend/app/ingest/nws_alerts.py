"""Live mode: active NWS alerts (no key; NWS requires a descriptive User-Agent)."""
from __future__ import annotations

from datetime import datetime

import httpx

from ..settings import settings

VTEC = {"Flash Flood Warning": "FF.W", "Flood Warning": "FL.W", "Flood Advisory": "FA.Y"}


async def active_flood_alerts(point: tuple[float, float]) -> list[dict]:
    lat, lon = point
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": settings.user_agent, "Accept": "application/geo+json"}) as c:
        r = await c.get("https://api.weather.gov/alerts/active", params={"point": f"{lat},{lon}"})
    r.raise_for_status()
    out = []
    for f in r.json().get("features", []):
        p = f["properties"]
        if p["event"] not in VTEC or not f.get("geometry"):
            continue
        out.append({"id": p["id"], "event": p["event"], "vtec": VTEC[p["event"]], "issued_at": p["sent"],
                    "expires_at": p["expires"], "polygon": f["geometry"], "source_url": p.get("@id"),
                    "_issued": datetime.fromisoformat(p["sent"]), "_expires": datetime.fromisoformat(p["expires"])})
    return out
