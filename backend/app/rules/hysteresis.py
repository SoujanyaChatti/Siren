"""Hysteresis: escalate immediately, de-escalate only when clearly over.

A latched rule clears only after its condition has been false for N consecutive evaluations AND,
for stage-threshold rules, the stage is at least `stage_clear_margin_ft` below the threshold.
An evaluation that could not run (missing data) neither clears nor counts toward clearing.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _RuleLatch:
    latched: bool = False
    false_count: int = 0


@dataclass
class HysteresisState:
    cfg: dict
    latches: dict[str, _RuleLatch] = field(default_factory=dict)

    def update(self, rule_id: str, raw: bool | None, stage: float | None = None,
               threshold: float | None = None) -> tuple[bool, bool]:
        """Returns (fired, held_by_hysteresis)."""
        l = self.latches.setdefault(rule_id, _RuleLatch())
        if raw is True:
            l.latched, l.false_count = True, 0
            return True, False
        if raw is None:
            return l.latched, l.latched
        if not l.latched:
            return False, False
        l.false_count += 1
        margin_ok = threshold is None or (stage is not None and stage <= threshold - self.cfg["stage_clear_margin_ft"])
        if l.false_count >= self.cfg["clear_after_false_evaluations"] and margin_ok:
            l.latched, l.false_count = False, 0
            return False, False
        return True, True
