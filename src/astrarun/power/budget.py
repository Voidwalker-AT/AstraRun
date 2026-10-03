"""Execution Budget Timer for Active Task Execution.

Prevents Windows sleep, standby, or hibernate durations from improperly
expiring task-level execution deadlines. Tracks cumulative active monotonic
work duration separately from wall-clock time.
"""

from __future__ import annotations

import time
from typing import Optional


class ExecutionBudgetTimer:
    """Tracks active task execution duration with suspend-pause awareness."""

    def __init__(self, budget_seconds: float) -> None:
        self.budget_seconds: float = budget_seconds
        self.cumulative_active_sec: float = 0.0
        self._segment_start: Optional[float] = None
        self._is_paused: bool = True

    def start(self) -> None:
        """Start or resume the active work timer."""
        if self._is_paused:
            self._segment_start = time.monotonic()
            self._is_paused = False

    def pause(self) -> None:
        """Pause active work accumulation (e.g., when Windows enters sleep)."""
        if not self._is_paused and self._segment_start is not None:
            now = time.monotonic()
            elapsed_segment = max(0.0, now - self._segment_start)
            self.cumulative_active_sec += elapsed_segment
            self._segment_start = None
            self._is_paused = True

    def resume(self) -> None:
        """Resume active work accumulation (e.g., when Windows wakes from sleep)."""
        self.start()

    @property
    def elapsed_active_seconds(self) -> float:
        """Return total elapsed active monotonic execution seconds (excluding sleep)."""
        if self._is_paused or self._segment_start is None:
            return round(self.cumulative_active_sec, 3)
        now = time.monotonic()
        current_segment = max(0.0, now - self._segment_start)
        return round(self.cumulative_active_sec + current_segment, 3)

    @property
    def remaining_budget_seconds(self) -> float:
        """Return remaining active execution budget seconds."""
        rem = self.budget_seconds - self.elapsed_active_seconds
        return round(max(0.0, rem), 3)

    @property
    def is_expired(self) -> bool:
        """Return True if active execution duration exceeds the allocated budget."""
        return self.remaining_budget_seconds <= 0.0

    @property
    def is_paused(self) -> bool:
        """Return whether the timer is currently paused."""
        return self._is_paused

    def to_dict(self) -> dict:
        """Serialize state for checkpointing."""
        return {
            "budget_seconds": self.budget_seconds,
            "cumulative_active_sec": self.elapsed_active_seconds,
            "remaining_budget_seconds": self.remaining_budget_seconds,
            "is_paused": self._is_paused,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExecutionBudgetTimer:
        """Restore timer from checkpoint data."""
        timer = cls(budget_seconds=data.get("budget_seconds", 1200.0))
        timer.cumulative_active_sec = data.get("cumulative_active_sec", 0.0)
        timer._is_paused = data.get("is_paused", True)
        if not timer._is_paused:
            timer._segment_start = time.monotonic()
        return timer
