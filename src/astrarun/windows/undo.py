"""Window layout undo stack and geometry snapshot management."""

from __future__ import annotations

import threading
from typing import Optional

from astrarun.core.logging import get_logger
from astrarun.windows.models import WindowLayoutSnapshot

logger = get_logger("astrarun.windows.undo")


class WindowRestoreStack:
    """
    Thread-safe, bounded LIFO stack of window geometry snapshots.
    Supports 'undo last window move' within a 10-minute sliding window.
    """

    def __init__(self, max_depth: int = 20, ttl_seconds: float = 600.0) -> None:
        self.max_depth = max_depth
        self.ttl_seconds = ttl_seconds
        self._stack: list[WindowLayoutSnapshot] = []
        self._lock = threading.Lock()

    def push(self, snapshot: WindowLayoutSnapshot) -> None:
        """Record window geometry prior to a layout mutation."""
        with self._lock:
            # Prune expired snapshots first
            self._prune_expired_locked()
            self._stack.append(snapshot)
            if len(self._stack) > self.max_depth:
                self._stack.pop(0)
            logger.debug(
                "Pushed window snapshot for HWND %d ('%s') at %s. Stack depth: %d",
                snapshot.hwnd,
                snapshot.title,
                snapshot.bounds,
                len(self._stack),
            )

    def pop(self) -> Optional[WindowLayoutSnapshot]:
        """Pop the most recent non-expired snapshot."""
        with self._lock:
            self._prune_expired_locked()
            if not self._stack:
                return None
            return self._stack.pop()

    def peek(self) -> Optional[WindowLayoutSnapshot]:
        """Inspect the most recent snapshot without popping."""
        with self._lock:
            self._prune_expired_locked()
            if not self._stack:
                return None
            return self._stack[-1]

    def clear(self) -> None:
        """Clear all recorded undo snapshots."""
        with self._lock:
            self._stack.clear()

    def __len__(self) -> int:
        with self._lock:
            self._prune_expired_locked()
            return len(self._stack)

    def _prune_expired_locked(self) -> None:
        """Remove snapshots that have exceeded TTL."""
        self._stack = [s for s in self._stack if not s.is_expired(self.ttl_seconds)]


# Global singleton instance for application runtime
restore_stack = WindowRestoreStack()
