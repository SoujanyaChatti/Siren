"""Reading storage. In-memory by default; mirrored to TimescaleDB / Tiger Data when DATABASE_URL is set
(see db.py). The rules engine reads through this interface."""
from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import datetime, timedelta


class ReadingStore:
    def __init__(self) -> None:
        self._series: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self._times: dict[tuple[str, str], list[datetime]] = defaultdict(list)
        self.sink = None  # optional db.TimescaleSink

    def add(self, r: dict) -> None:
        key = (r["station_id"], r["metric"])
        i = bisect.bisect_right(self._times[key], r["_t"])
        self._times[key].insert(i, r["_t"])
        self._series[key].insert(i, r)
        if self.sink:
            self.sink.reading(r)

    def latest(self, station: str, metric: str, at: datetime, quality: str | None = None) -> dict | None:
        key = (station, metric)
        i = bisect.bisect_right(self._times[key], at)
        for r in reversed(self._series[key][:i]):
            if quality is None or r.get("quality") == quality:
                return r
        return None

    def window(self, station: str, metric: str, start: datetime, end: datetime) -> list[dict]:
        """Readings with start < time <= end."""
        key = (station, metric)
        lo = bisect.bisect_right(self._times[key], start)
        hi = bisect.bisect_right(self._times[key], end)
        return self._series[key][lo:hi]

    def series(self, station: str, metric: str, start: datetime | None = None, end: datetime | None = None) -> list[dict]:
        rs = self._series[(station, metric)]
        return [r for r in rs if (start is None or r["_t"] >= start) and (end is None or r["_t"] <= end)]

    def rollup_15m(self, station: str, metric: str, end: datetime, buckets: int = 96) -> list[dict]:
        """Same shape as the readings_15m continuous aggregate."""
        out = []
        start = end - timedelta(minutes=15 * buckets)
        grouped: dict[datetime, list[dict]] = defaultdict(list)
        for r in self.window(station, metric, start, end):
            b = r["_t"].replace(minute=(r["_t"].minute // 15) * 15, second=0, microsecond=0)
            grouped[b].append(r)
        for b in sorted(grouped):
            rs = grouped[b]
            out.append({"bucket": b.isoformat(), "max_v": max(x["value"] for x in rs),
                        "last_v": rs[-1]["value"], "n": len(rs)})
        return out
