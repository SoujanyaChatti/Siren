"""Replay clock: maps wall time to simulated storm time (speed, pause, jump)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone


class ReplayClock:
    def __init__(self, start: datetime, end: datetime, speed: float = 60.0):
        self.start, self.end = start, end
        self.speed = speed
        self.playing = False
        self._anchor_sim = start
        self._anchor_wall = time.monotonic()

    def now(self) -> datetime:
        if not self.playing:
            return self._anchor_sim
        elapsed = (time.monotonic() - self._anchor_wall) * self.speed
        t = self._anchor_sim + timedelta(seconds=elapsed)
        if t >= self.end:
            self._anchor_sim, self.playing = self.end, False
            return self.end
        return t

    def _reanchor(self) -> None:
        self._anchor_sim = self.now()
        self._anchor_wall = time.monotonic()

    def play(self) -> None:
        self._reanchor()
        self.playing = True

    def pause(self) -> None:
        self._reanchor()
        self.playing = False

    def set_speed(self, speed: float) -> None:
        self._reanchor()
        self.speed = max(0.1, float(speed))

    def jump(self, t: datetime) -> None:
        self._anchor_sim = min(max(t, self.start), self.end)
        self._anchor_wall = time.monotonic()

    def state(self) -> dict:
        return {"now": self.now().astimezone(timezone.utc).isoformat(), "start": self.start.isoformat(),
                "end": self.end.isoformat(), "speed": self.speed, "playing": self.playing}
