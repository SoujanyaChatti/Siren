"""NOAA National Water Prediction Service: official flood categories per gauge."""
from __future__ import annotations

import httpx

from ..settings import settings


async def flood_categories(lid: str) -> dict:
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": settings.user_agent}) as c:
        r = await c.get(f"https://api.water.noaa.gov/nwps/v1/gauges/{lid}")
    r.raise_for_status()
    cats = r.json()["flood"]["categories"]
    return {k: cats[k]["stage"] for k in ("action", "minor", "moderate", "major")}
