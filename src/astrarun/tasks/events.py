"""Observable Task Event Bus decoupling runtime instrumentation from UI and persistence."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from astrarun.core.logging import get_logger
from astrarun.tasks.models import TaskEvent

logger = get_logger("astrarun.tasks.events")


class TaskEventBus:
    """
    Thread-safe event bus for publishing observable TaskEvent records.
    
    CRITICAL INVARIANT (Rule #59):
    This event bus is strictly an informational and observation dispatch mechanism.
    Events NEVER grant execution authority, and subscribers are prohibited from
    triggering arbitrary OS actions in response to events.
    """

    def __init__(self) -> None:
        self._subscribers: dict[int, tuple[Callable[[TaskEvent], None], Optional[str]]] = {}
        self._next_id = 1
        self._lock = threading.Lock()

    def subscribe(self, callback: Callable[[TaskEvent], None], task_id: Optional[str] = None) -> int:
        """
        Register a subscriber callback receiving TaskEvent notifications.
        Optionally filters by task_id.
        Returns a subscription ID for unsubscription.
        """
        with self._lock:
            sub_id = self._next_id
            self._next_id += 1
            self._subscribers[sub_id] = (callback, task_id)
            return sub_id

    def unsubscribe(self, sub_id: int) -> bool:
        """Unregister a subscriber by subscription ID."""
        with self._lock:
            return self._subscribers.pop(sub_id, None) is not None

    def publish(self, event: TaskEvent) -> None:
        """
        Publish an event to all matching subscribers.
        Subscriber exceptions are caught and logged to ensure execution stability.
        """
        with self._lock:
            subs = list(self._subscribers.values())

        for cb, tid in subs:
            if tid is not None and event.task_id != tid:
                continue
            try:
                cb(event)
            except Exception as err:
                logger.error("Error in TaskEvent subscriber callback: %s", err, exc_info=True)

    def clear(self) -> None:
        """Remove all active subscribers."""
        with self._lock:
            self._subscribers.clear()


# Global shared event bus instance
_GLOBAL_EVENT_BUS: Optional[TaskEventBus] = None
_BUS_LOCK = threading.Lock()


def get_global_event_bus() -> TaskEventBus:
    """Retrieve the platform-wide singleton TaskEventBus."""
    global _GLOBAL_EVENT_BUS
    with _BUS_LOCK:
        if _GLOBAL_EVENT_BUS is None:
            _GLOBAL_EVENT_BUS = TaskEventBus()
        return _GLOBAL_EVENT_BUS
