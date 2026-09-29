"""Workstation resource locking engine for AstraRun v0.11 agent runtime."""

from __future__ import annotations

import contextlib
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Generator, Optional

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.agent.locking")


class ResourceLockTimeout(TimeoutError):
    """Raised when acquiring a resource lock exceeds timeout."""
    pass


@dataclass
class LockEntry:
    """Internal state of an active resource lock."""
    resource_key: str
    task_id: str
    step_id: Optional[str]
    acquired_at: float = field(default_factory=time.time)
    reentrant_count: int = 1


class ResourceLockManager:
    """
    Manages non-conflicting access to shared workstation resources:
      - WINDOW:<hwnd>
      - FILE:<canonical_path>
      - NETWORK:WIFI
      - PROCESS:<pid>
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._active_locks: dict[str, LockEntry] = {}
        self._wait_conditions: dict[str, threading.Condition] = {}

    def _normalize_key(self, resource_key: str) -> str:
        """Canonicalize resource keys."""
        key = resource_key.strip()
        if key.startswith("FILE:"):
            # Normalize file path
            prefix, path = key.split(":", 1)
            import os
            return f"FILE:{os.path.abspath(path).lower()}"
        return key

    def acquire_lock(
        self,
        resource_key: str,
        task_id: str,
        step_id: Optional[str] = None,
        timeout_s: float = 5.0,
    ) -> bool:
        """Acquire a lock for resource_key on behalf of task_id."""
        canon_key = self._normalize_key(resource_key)
        deadline = time.time() + timeout_s

        with self._lock:
            while True:
                existing = self._active_locks.get(canon_key)
                if existing is None:
                    self._active_locks[canon_key] = LockEntry(
                        resource_key=canon_key,
                        task_id=task_id,
                        step_id=step_id,
                        acquired_at=time.time(),
                        reentrant_count=1,
                    )
                    logger.debug("Lock acquired for %s by task %s", canon_key, task_id)
                    return True

                if existing.task_id == task_id:
                    # Re-entrant acquisition by the same task
                    existing.reentrant_count += 1
                    return True

                remaining = deadline - time.time()
                if remaining <= 0:
                    logger.warning(
                        "Timeout acquiring lock for %s by task %s (held by %s)",
                        canon_key,
                        task_id,
                        existing.task_id,
                    )
                    return False

                # Wait on condition
                if canon_key not in self._wait_conditions:
                    self._wait_conditions[canon_key] = threading.Condition(self._lock)
                self._wait_conditions[canon_key].wait(timeout=remaining)

    def release_lock(self, resource_key: str, task_id: str) -> bool:
        """Release lock for resource_key held by task_id."""
        canon_key = self._normalize_key(resource_key)

        with self._lock:
            existing = self._active_locks.get(canon_key)
            if existing is None:
                return False

            if existing.task_id != task_id:
                logger.error(
                    "Task %s attempted to release lock for %s held by %s",
                    task_id,
                    canon_key,
                    existing.task_id,
                )
                return False

            existing.reentrant_count -= 1
            if existing.reentrant_count <= 0:
                del self._active_locks[canon_key]
                logger.debug("Lock released for %s by task %s", canon_key, task_id)
                cond = self._wait_conditions.get(canon_key)
                if cond:
                    cond.notify_all()

            return True

    def release_all_for_task(self, task_id: str) -> int:
        """Release all locks owned by task_id (e.g. upon task completion or cancellation)."""
        count = 0
        with self._lock:
            keys_to_release = [
                k for k, v in self._active_locks.items() if v.task_id == task_id
            ]
            for key in keys_to_release:
                del self._active_locks[key]
                count += 1
                cond = self._wait_conditions.get(key)
                if cond:
                    cond.notify_all()

        if count > 0:
            logger.info("Released %d locks for task %s", count, task_id)
        return count

    def is_locked(self, resource_key: str) -> bool:
        """Check if resource_key is currently locked."""
        canon_key = self._normalize_key(resource_key)
        with self._lock:
            return canon_key in self._active_locks

    def get_lock_holder(self, resource_key: str) -> Optional[str]:
        """Get the task_id currently holding the lock for resource_key."""
        canon_key = self._normalize_key(resource_key)
        with self._lock:
            entry = self._active_locks.get(canon_key)
            return entry.task_id if entry else None

    @contextlib.contextmanager
    def lock_resource(
        self,
        resource_key: str,
        task_id: str,
        step_id: Optional[str] = None,
        timeout_s: float = 5.0,
    ) -> Generator[bool, None, None]:
        """Context manager for acquiring and releasing a resource lock."""
        acquired = self.acquire_lock(resource_key, task_id, step_id, timeout_s)
        if not acquired:
            raise ResourceLockTimeout(f"Failed to acquire lock for '{resource_key}' within {timeout_s}s")
        try:
            yield acquired
        finally:
            self.release_lock(resource_key, task_id)


# Global lock manager instance
global_lock_manager = ResourceLockManager()
