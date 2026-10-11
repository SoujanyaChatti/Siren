"""Alert lifecycle state machine. States are tracked separately and never merged;
every transition writes an alert_events row; invalid transitions raise."""
from __future__ import annotations

from datetime import datetime, timezone

DRAFTED, GENERATED, DELIVERED, ACKNOWLEDGED = "Drafted", "Generated", "Delivered", "Acknowledged"
SUPERSEDED, EXPIRED, CANCELLED = "Superseded", "Expired", "Cancelled"
TERMINAL = {SUPERSEDED, EXPIRED, CANCELLED}
STATES = [DRAFTED, GENERATED, DELIVERED, ACKNOWLEDGED, SUPERSEDED, EXPIRED, CANCELLED]

ALLOWED: dict[str, set[str]] = {
    DRAFTED: {GENERATED} | TERMINAL,
    GENERATED: {DELIVERED} | TERMINAL,
    DELIVERED: {ACKNOWLEDGED} | TERMINAL,
    ACKNOWLEDGED: set(TERMINAL),
    SUPERSEDED: set(),
    EXPIRED: set(),
    CANCELLED: set(),
}


class InvalidTransition(ValueError):
    pass


class Lifecycle:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self.sink = None  # optional db sink

    def start(self, entity: dict, *, alert_id: str, delivery_id: str | None, actor: str, note: str = "",
              at: datetime | None = None) -> None:
        entity["state"] = DRAFTED
        self._record(alert_id, delivery_id, None, DRAFTED, actor, note, at)

    def transition(self, entity: dict, to_state: str, *, alert_id: str, delivery_id: str | None, actor: str,
                   note: str = "", at: datetime | None = None) -> None:
        cur = entity.get("state")
        if to_state not in ALLOWED.get(cur, set()):
            raise InvalidTransition(f"{cur} -> {to_state} is not allowed")
        entity["state"] = to_state
        self._record(alert_id, delivery_id, cur, to_state, actor, note, at)

    def _record(self, alert_id, delivery_id, frm, to, actor, note, at) -> None:
        ev = {"time": (at or datetime.now(timezone.utc)).isoformat(), "wall_time": datetime.now(timezone.utc).isoformat(),
              "alert_id": alert_id, "delivery_id": delivery_id, "from_state": frm, "to_state": to,
              "actor": actor, "note": note}
        self.events.append(ev)
        if self.sink:
            self.sink.alert_event(ev)

    def for_alert(self, alert_id: str) -> list[dict]:
        return [e for e in self.events if e["alert_id"] == alert_id]
