"""Dynamic execution runtime for AstraRun 1.0.

Provides fully sandboxed, stealth, and governed command/process execution:
  - Authorized by ActionGate prior to execution.
  - Isolated within Win32 Job Object (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE).
  - Headless execution with CREATE_NO_WINDOW (0x08000000).
  - Strict Astra process ownership tracking via ProcessTracker.
  - Real-time JIT secret resolution and output stream scrubbing via SecretBroker.
  - Deterministic typed ExecutionObservation output with resource telemetry.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.execution.job_object import Win32JobObject
from astrarun.execution.models import (
    ExecutionObservation,
    ExecutionRequest,
    ExecutionStatus,
    ResourceUsage,
)
from astrarun.execution.process_tracker import ProcessTracker
from astrarun.security.action_gate import ActionGate
from astrarun.security.models import (
    ActionGateVerdict,
    ActionRequest,
    Operation,
    RiskLevel,
)
from astrarun.security.secret_broker import SecretBroker

logger = get_logger("astrarun.execution.runtime")

CREATE_NO_WINDOW = 0x08000000


@dataclass
class _ActiveExecution:
    """Internal tracking record for an active in-flight execution."""
    task_id: str
    popen: subprocess.Popen
    job: Win32JobObject
    cancel_event: threading.Event
    start_time: float


class DynamicExecutionRuntime:
    """
    Sandboxed Dynamic Execution Runtime for AstraRun 1.0.
    Authoritative boundary for all subprocess and OS-level execution.
    """

    def __init__(
        self,
        action_gate: Optional[ActionGate] = None,
        secret_broker: Optional[SecretBroker] = None,
        process_tracker: Optional[ProcessTracker] = None,
        default_timeout: float = 30.0,
        default_memory_limit_bytes: Optional[int] = None,
    ) -> None:
        self.action_gate = action_gate or ActionGate.get_instance()
        self.secret_broker = secret_broker or SecretBroker.get_instance()
        self.process_tracker = process_tracker or ProcessTracker.get_instance()
        self.default_timeout = default_timeout
        self.default_memory_limit_bytes = default_memory_limit_bytes
        self._active_tasks: Dict[str, _ActiveExecution] = {}
        self._lock = threading.Lock()

    def cancel_task(self, task_id: str) -> bool:
        """
        Immediately cancel a running task by task_id.
        Terminates the process tree via Job Object and ProcessTracker.
        """
        with self._lock:
            active = self._active_tasks.get(task_id)
            if not active:
                logger.warning("cancel_task called for unknown or inactive task_id: %s", task_id)
                return False

            active.cancel_event.set()
            logger.info("Cancelling task %s (PID=%s)", task_id, active.popen.pid)

            # Terminate Job Object tree immediately
            try:
                active.job.terminate(exit_code=1)
            except Exception as e:
                logger.warning("Error terminating job for task %s: %s", task_id, e)

            # Fallback to process tracker kill
            try:
                self.process_tracker.kill_process_tree(active.popen.pid)
            except Exception as e:
                logger.warning("Error killing process tree for task %s: %s", task_id, e)

            return True

    def execute_sync(self, request: ExecutionRequest) -> ExecutionObservation:
        """
        Synchronous execution entrypoint.
        """
        return self._execute_internal(request)

    async def execute(self, request: ExecutionRequest) -> ExecutionObservation:
        """
        Asynchronous execution entrypoint complying with AstraRun 1.0 runtime contract.
        """
        return await asyncio.to_thread(self._execute_internal, request)

    def _execute_internal(self, request: ExecutionRequest) -> ExecutionObservation:
        """
        Core execution pipeline implementing the 8-step safety contract.
        """
        start_mono = time.monotonic()
        task_id = request.task_id

        # ---------------------------------------------------------
        # 1. ActionGate Policy Authorization Check
        # ---------------------------------------------------------
        full_cmd_str = f"{request.executable} {' '.join(request.args)}".strip()
        gate_request = ActionRequest(
            operation=Operation.EXECUTE,
            capability="execution_runtime",
            target=request.executable,
            parameters={
                "command": full_cmd_str,
                "executable": request.executable,
                "args": list(request.args),
                "cwd": request.cwd or os.getcwd(),
            },
            task_id=task_id,
            authorization_scope=request.authorization_ref or "",
            metadata={"ownership": request.ownership},
        )
        gate_eval = self.action_gate.evaluate_request(gate_request)

        if gate_eval.verdict == ActionGateVerdict.DENY:
            logger.warning(
                "Execution DENIED by ActionGate for task %s: %s (Risk: %s)",
                task_id,
                gate_eval.reason,
                gate_eval.risk_level.value,
            )
            return ExecutionObservation(
                status=ExecutionStatus.DENIED,
                exit_code=None,
                stdout="",
                stderr=f"Execution DENIED by ActionGate: {gate_eval.reason}",
                duration_ms=(time.monotonic() - start_mono) * 1000.0,
                timeout=False,
                killed=False,
                resource_usage=ResourceUsage(),
                redaction_occurred=False,
                redaction_metadata={},
                task_id=task_id,
                audit_event={
                    "event": "EXECUTION_DENIED",
                    "reason": gate_eval.reason,
                    "risk_level": gate_eval.risk_level.value,
                    "executable": request.executable,
                    "args": request.args,
                },
            )

        if gate_eval.verdict == ActionGateVerdict.REQUIRE_CONFIRMATION:
            # If not authorized by token/explicit confirmation, halt execution
            if not request.authorization_ref:
                logger.warning(
                    "Execution REQUIRES_CONFIRMATION for task %s: %s",
                    task_id,
                    gate_eval.reason,
                )
                return ExecutionObservation(
                    status=ExecutionStatus.DENIED,
                    exit_code=None,
                    stdout="",
                    stderr=f"Execution blocked: User confirmation required. {gate_eval.reason}",
                    duration_ms=(time.monotonic() - start_mono) * 1000.0,
                    timeout=False,
                    killed=False,
                    resource_usage=ResourceUsage(),
                    redaction_occurred=False,
                    redaction_metadata={},
                    task_id=task_id,
                    audit_event={
                        "event": "EXECUTION_CONFIRMATION_REQUIRED",
                        "reason": gate_eval.reason,
                        "risk_level": gate_eval.risk_level.value,
                        "confirmation_token": gate_eval.confirmation_token,
                    },
                )

        # ---------------------------------------------------------
        # 2. SecretBroker JIT Secret Resolution
        # ---------------------------------------------------------
        if request.environment is not None:
            child_env = os.environ.copy()
            child_env.update(self.secret_broker.resolve_environment(request.environment))
        else:
            child_env = None

        resolved_args = [self.secret_broker.resolve_argument(arg) for arg in request.args]
        full_command = [request.executable] + resolved_args

        # ---------------------------------------------------------
        # 3. Process Spawning & Win32 Job Object Containment
        # ---------------------------------------------------------
        mem_limit = request.memory_limit_bytes or self.default_memory_limit_bytes
        job = Win32JobObject(
            name=f"astra_job_{task_id}",
            memory_limit_bytes=mem_limit,
        )

        creationflags = 0
        if os.name == "nt" and request.stealth:
            creationflags |= CREATE_NO_WINDOW

        popen: Optional[subprocess.Popen] = None
        timed_out = False
        killed = False
        peak_memory = 0
        cancel_event = threading.Event()

        try:
            popen = subprocess.Popen(
                full_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=request.cwd,
                env=child_env,
                creationflags=creationflags,
            )

            # Assign to Job Object immediately
            if os.name == "nt" and hasattr(popen, "_handle"):
                job.assign_process(int(popen._handle))

            # Register with ProcessTracker
            cmd_display = f"{request.executable} {' '.join(request.args)}"
            self.process_tracker.register_process(
                pid=popen.pid,
                task_id=task_id,
                command=cmd_display,
                handle=int(popen._handle) if hasattr(popen, "_handle") else None,
            )

            with self._lock:
                self._active_tasks[task_id] = _ActiveExecution(
                    task_id=task_id,
                    popen=popen,
                    job=job,
                    cancel_event=cancel_event,
                    start_time=time.monotonic(),
                )

            # ---------------------------------------------------------
            # 4. Stream Communication with Timeout & Cancellation
            # ---------------------------------------------------------
            timeout_sec = request.timeout if request.timeout > 0 else self.default_timeout
            raw_stdout = b""
            raw_stderr = b""

            try:
                raw_stdout, raw_stderr = popen.communicate(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                timed_out = True
                killed = True
                logger.warning("Task %s timed out after %s seconds. Terminating.", task_id, timeout_sec)
                job.terminate(exit_code=124)
                try:
                    self.process_tracker.kill_process_tree(popen.pid)
                except Exception:
                    pass
                raw_stdout, raw_stderr = popen.communicate()

            # Check if cancelled asynchronously
            if cancel_event.is_set():
                killed = True

            # Query peak hardware metrics before closing Job Object
            peak_memory = job.query_peak_memory()

        except Exception as e:
            logger.error("Execution failure for task %s: %s", task_id, e)
            raw_stdout = b""
            raw_stderr = str(e).encode("utf-8")
            killed = True
        finally:
            # ---------------------------------------------------------
            # 5. Guaranteed Cleanup
            # ---------------------------------------------------------
            with self._lock:
                self._active_tasks.pop(task_id, None)

            if popen is not None:
                self.process_tracker.unregister_process(popen.pid)

            job.close()

        # ---------------------------------------------------------
        # 6. Stream Scrubbing via SecretBroker
        # ---------------------------------------------------------
        stdout_text = raw_stdout.decode("utf-8", errors="replace")
        stderr_text = raw_stderr.decode("utf-8", errors="replace")

        clean_stdout, report_stdout = self.secret_broker.scrub_text(stdout_text)
        clean_stderr, report_stderr = self.secret_broker.scrub_text(stderr_text)

        total_redactions = report_stdout.redaction_count + report_stderr.redaction_count
        redaction_occurred = total_redactions > 0
        all_redacted_types = list(set(report_stdout.redacted_types + report_stderr.redacted_types))

        # ---------------------------------------------------------
        # 7. Status Resolution
        # ---------------------------------------------------------
        duration_ms = (time.monotonic() - start_mono) * 1000.0
        exit_code = popen.returncode if popen is not None else -1

        if cancel_event.is_set():
            status = ExecutionStatus.CANCELLED
        elif timed_out:
            status = ExecutionStatus.TIMEOUT
        elif exit_code == 0:
            status = ExecutionStatus.SUCCESS
        else:
            status = ExecutionStatus.FAILED

        # ---------------------------------------------------------
        # 8. Typed ExecutionObservation Output
        # ---------------------------------------------------------
        return ExecutionObservation(
            status=status,
            exit_code=exit_code,
            stdout=clean_stdout,
            stderr=clean_stderr,
            duration_ms=duration_ms,
            timeout=timed_out,
            killed=killed,
            resource_usage=ResourceUsage(peak_memory_bytes=peak_memory),
            redaction_occurred=redaction_occurred,
            redaction_metadata={
                "total_redactions": total_redactions,
                "redacted_types": all_redacted_types,
            },
            task_id=task_id,
            audit_event={
                "task_id": task_id,
                "executable": request.executable,
                "status": status.value,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "peak_memory_bytes": peak_memory,
                "redactions": total_redactions,
            },
        )
