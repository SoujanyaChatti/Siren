"""Live mode: USGS Water Data OGC API (instantaneous gage height). Replay mode uses fixtures instead."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ..settings import settings

URL = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items"


async def fetch_stage(usgs_id: str, station_id: str, hours: int = 3) -> list[dict]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    params = {"f": "json", "monitoring_location_id": f"USGS-{usgs_id}", "parameter_code": "00065",
              "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}", "limit": 500}
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": settings.user_agent}) as c:
        r = await c.get(URL, params=params)
    r.raise_for_status()
    out = []
    for f in r.json()["features"]:
        p = f["properties"]
        if p["value"] in (None, ""):
            continue
        t = datetime.fromisoformat(p["time"])
        out.append({"time": t.isoformat(), "_t": t, "source": "usgs", "station_id": station_id, "metric": "stage_ft",
                    "value": float(p["value"]), "quality": "verified" if p.get("approval_status") == "Approved" else "provisional",
                    "source_url": f"https://waterdata.usgs.gov/monitoring-location/USGS-{usgs_id}/"})
    return out
