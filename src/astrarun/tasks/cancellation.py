"""Cooperative cancellation token for long-running workstation tasks."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from astrarun.tasks.models import TaskCancelledError


class CancellationToken:
    """
    Thread-safe cooperative cancellation token.
    Allows tasks, capabilities, and workflows to check for cancellation points
    without abruptly terminating worker threads or leaving system state corrupt.
    """

    def __init__(self) -> None:
        self._is_cancelled = False
        self._reason: Optional[str] = None
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[str], None]] = []

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation has been requested."""
        with self._lock:
            return self._is_cancelled

    @property
    def reason(self) -> Optional[str]:
        """Return the reason for cancellation if cancelled."""
        with self._lock:
            return self._reason

    def cancel(self, reason: str = "User cancelled task") -> None:
        """
        Request cancellation of the token.
        Notifies all registered callbacks.
        """
        callbacks_to_run = []
        with self._lock:
            if self._is_cancelled:
                return
            self._is_cancelled = True
            self._reason = reason
            callbacks_to_run = list(self._callbacks)

        for cb in callbacks_to_run:
            try:
                cb(reason)
            except TypeError:
                try:
                    cb()
                except Exception:
                    pass
            except Exception:
                pass

    def check_cancelled(self) -> None:
        """
        Raise TaskCancelledError if cancellation has been requested.
        Call this periodically in cooperative loop checkpoints.
        """
        with self._lock:
            if self._is_cancelled:
                raise TaskCancelledError(self._reason or "Task was cancelled")

    def register_callback(self, callback: Callable[[str], None]) -> None:
        """Register a callback to be called immediately upon cancellation."""
        should_run_now = False
        reason = ""
        with self._lock:
            if self._is_cancelled:
                should_run_now = True
                reason = self._reason or "Task was cancelled"
            else:
                self._callbacks.append(callback)

        if should_run_now:
            try:
                callback(reason)
            except Exception:
                pass
