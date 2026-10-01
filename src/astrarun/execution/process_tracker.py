"""Process ownership tracking and safety boundary enforcement for AstraRun 1.0."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import psutil

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.execution.process_tracker")


@dataclass
class AstraProcessRecord:
    """Record of a process explicitly created by AstraRun."""
    pid: int
    task_id: str
    create_time: float
    command: str
    handle: Optional[int] = None
    registered_at: float = field(default_factory=time.time)


class ProcessTracker:
    """
    Authoritative ledger of AstraRun-owned processes.
    Enforces the strict ownership invariant:
      - Only Astra-created process trees may be assigned to Astra Job Objects or killed.
      - Arbitrary pre-existing user applications are strictly protected.
    """

    _instance: Optional[ProcessTracker] = None

    def __init__(self) -> None:
        self._owned_processes: Dict[int, AstraProcessRecord] = {}
        self._task_processes: Dict[str, Set[int]] = {}

    @classmethod
    def get_instance(cls) -> ProcessTracker:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_process(
        self,
        pid: int,
        task_id: str,
        command: str = "",
        handle: Optional[int] = None,
    ) -> AstraProcessRecord:
        """
        Register a newly spawned child process as Astra-owned.
        """
        create_time = 0.0
        try:
            if psutil.pid_exists(pid):
                proc = psutil.Process(pid)
                create_time = proc.create_time()
        except Exception:
            create_time = time.time()

        record = AstraProcessRecord(
            pid=pid,
            task_id=task_id,
            create_time=create_time,
            command=command,
            handle=handle,
        )
        self._owned_processes[pid] = record

        if task_id not in self._task_processes:
            self._task_processes[task_id] = set()
        self._task_processes[task_id].add(pid)

        logger.debug("Registered Astra-owned process [PID=%d, task_id=%s]", pid, task_id)
        return record

    def unregister_process(self, pid: int) -> None:
        """Unregister a process upon normal termination."""
        record = self._owned_processes.pop(pid, None)
        if record and record.task_id in self._task_processes:
            self._task_processes[record.task_id].discard(pid)
            if not self._task_processes[record.task_id]:
                self._task_processes.pop(record.task_id, None)

    def is_astra_owned(self, pid: int) -> bool:
        """
        Verify if a PID is an active Astra-created process with matching create_time
        to prevent TOCTOU PID reuse attacks.
        """
        record = self._owned_processes.get(pid)
        if not record:
            return False

        if not psutil.pid_exists(pid):
            self.unregister_process(pid)
            return False

        try:
            proc = psutil.Process(pid)
            # Verify create_time hasn't changed (PID recycling)
            if record.create_time > 0 and abs(proc.create_time() - record.create_time) > 1.0:
                self.unregister_process(pid)
                return False
            return True
        except Exception:
            self.unregister_process(pid)
            return False

    def get_task_processes(self, task_id: str) -> List[int]:
        """Return all active Astra PIDs associated with a task."""
        pids = list(self._task_processes.get(task_id, set()))
        return [p for p in pids if self.is_astra_owned(p)]

    def get_descendants(self, pid: int) -> List[int]:
        """
        Retrieve all descendant PIDs under an Astra-owned process.
        """
        if not psutil.pid_exists(pid):
            return []
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            return [c.pid for c in children]
        except Exception:
            return []

    def kill_process_tree(self, pid: int, timeout: float = 3.0) -> bool:
        """
        Kill an Astra-owned process and all its descendants.
        PROTECTION: If PID is NOT owned by Astra, raises PermissionError.
        """
        if not self.is_astra_owned(pid):
            logger.error("Attempted to terminate non-Astra process PID %d! REJECTED.", pid)
            raise PermissionError(f"Safety violation: PID {pid} is not owned by AstraRun.")

        if not psutil.pid_exists(pid):
            self.unregister_process(pid)
            return True

        try:
            parent = psutil.Process(pid)
            descendants = parent.children(recursive=True)
            
            # Send terminate to descendants
            for child in descendants:
                try:
                    child.terminate()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            parent.terminate()

            # Wait for exit
            gone, alive = psutil.wait_procs([parent] + descendants, timeout=timeout)
            
            # Force kill if still alive
            for p in alive:
                try:
                    p.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            self.unregister_process(pid)
        except psutil.NoSuchProcess:
            self.unregister_process(pid)
            return True
        except Exception as e:
            logger.warning("Error killing Astra process tree for PID %d: %s", pid, e)
            return False

    def clear(self) -> None:
        """Clear tracking ledger (for test cleanup)."""
        self._owned_processes.clear()
        self._task_processes.clear()
