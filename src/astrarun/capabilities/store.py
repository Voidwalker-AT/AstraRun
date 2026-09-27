"""In-memory observation store for capturing structured OS facts."""

from __future__ import annotations

import time
from typing import Any, List, Optional

from astrarun.capabilities.models import Observation
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.capabilities.store")


class ObservationStore:
    """
    Short-lived in-memory store for structured OS observations.
    Supplies verified machine facts to future reasoning providers without disk clutter.
    """

    def __init__(self, max_items: int = 100, default_ttl_seconds: float = 600.0) -> None:
        self.max_items = max_items
        self.default_ttl_seconds = default_ttl_seconds
        self._observations: list[Observation] = []

    def record(self, obs_type: str, source: str, data: dict[str, Any]) -> Observation:
        """Record a new observation and prune expired/excess entries."""
        now = time.time()
        obs = Observation(
            type=obs_type,
            source=source,
            data=data,
            timestamp=now,
            freshness=0.0,
        )
        self._observations.insert(0, obs)
        self.prune()
        return obs

    def query(self, obs_type: Optional[str] = None, source: Optional[str] = None, limit: int = 10) -> list[Observation]:
        """Query recent non-expired observations."""
        now = time.time()
        results: list[Observation] = []
        for o in self._observations:
            age = now - o.timestamp
            if age > self.default_ttl_seconds:
                continue
            if obs_type and o.type != obs_type:
                continue
            if source and o.source != source:
                continue
            o.freshness = round(age, 2)
            results.append(o)
            if len(results) >= limit:
                break
        return results

    def prune(self) -> None:
        """Prune entries exceeding limit or TTL."""
        now = time.time()
        valid = [
            o for o in self._observations
            if (now - o.timestamp) <= self.default_ttl_seconds
        ]
        self._observations = valid[:self.max_items]

    def clear(self) -> None:
        """Clear all stored observations."""
        self._observations.clear()

    def get_latest(self, obs_type: str) -> Optional[Observation]:
        """Retrieve the most recent observation of a specific type."""
        res = self.query(obs_type=obs_type, limit=1)
        return res[0] if res else None
