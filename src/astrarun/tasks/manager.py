"""Central TaskManager coordinating lifecycle, state machine transitions, event emission, and execution."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Optional

from astrarun.capabilities.models import CapabilityResult
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.core.logging import get_logger
from astrarun.tasks.cancellation import CancellationToken
from astrarun.tasks.events import TaskEventBus, get_global_event_bus
from astrarun.tasks.ledger import TaskLedger
from astrarun.tasks.models import (
    Conversation,
    ConversationMessage,
    InvalidStateTransitionError,
    Task,
    TaskCancelledError,
    TaskError,
    TaskEvent,
    TaskEventType,
    TaskResult,
    TaskStatus,
)
from astrarun.tasks.serialization import (
    generate_capability_summary,
    generate_task_title,
    hash_request,
    sanitize_capability_payload,
    sanitize_request,
)

logger = get_logger("astrarun.tasks.manager")


class TaskManager:
    """
    Central lifecycle authority for AstraRun workstation operations.
    
    Responsibilities:
    - Creates and validates finite-state task instances.
    - Manages cooperative cancellation tokens.
    - Publishes observable TaskEvents to the TaskEventBus.
    - Persists audit events and task outcomes to the TaskLedger.
    - Instruments capability and workflow dispatches.
    
    CRITICAL INVARIANT (Rule #10):
    TaskManager orchestrates lifecycle; it does NOT grant execution authority or bypass
    ActionGate, CapabilityRegistry permissions, or hard security policies.
    """

    def __init__(
        self,
        ledger: Optional[TaskLedger] = None,
        event_bus: Optional[TaskEventBus] = None,
    ) -> None:
        self.ledger = ledger or TaskLedger()
        self.event_bus = event_bus or get_global_event_bus()

        self._active_tasks: dict[str, Task] = {}
        self._cancellation_tokens: dict[str, CancellationToken] = {}
        self._lock = threading.Lock()

        # Run startup crash recovery
        self.ledger.recover_interrupted_tasks()

    # -------------------------------------------------------------------------
    # Task Lifecycle Management
    # -------------------------------------------------------------------------

    def create_task(
        self,
        request_text: Optional[str] = None,
        conversation_id: Optional[str] = None,
        source: str = "launcher",
        parent_task_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Task:
        """
        Create and initialize a new Task.
        If conversation_id is omitted, a new conversation is automatically provisioned.
        """
        now = time.time()
        task_id = str(uuid.uuid4())

        # Ensure conversation exists
        if not conversation_id:
            title = generate_task_title(request_text)
            conv = self.ledger.create_conversation(title=title)
            conversation_id = conv.id

        req_hash = hash_request(request_text)

        task = Task(
            id=task_id,
            conversation_id=conversation_id,
            request_text=request_text,
            request_hash=req_hash,
            source=source,
            created_at=now,
            status=TaskStatus.CREATED,
            parent_task_id=parent_task_id,
            metadata=metadata or {},
        )

        with self._lock:
            self._active_tasks[task_id] = task
            self._cancellation_tokens[task_id] = CancellationToken()

        # Persist initial task in ledger
        self.ledger.save_task(task)

        # Emit initial TASK_CREATED event
        self.emit_event(
            task_id=task_id,
            event_type=TaskEventType.TASK_CREATED,
            title="Task Created",
            summary=generate_task_title(request_text),
            data={"request_hash": req_hash, "source": source},
        )

        logger.debug("Task created: %s [conv=%s, source=%s]", task_id, conversation_id, source)
        return task

    def start_task(self, task_id: str) -> None:
        """Mark task as active and running."""
        self.transition_status(task_id, TaskStatus.RUNNING)

    def transition_status(self, task_id: str, new_status: TaskStatus) -> None:
        """
        Safely transition a task to a new state with finite state machine validation.
        """
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        old_status = task.status
        task.transition_to(new_status)

        # Update ledger
        self.ledger.update_task_status(task_id, new_status)

        logger.debug("Task %s transitioned: %s -> %s", task_id, old_status.value, new_status.value)

    def emit_event(
        self,
        task_id: str,
        event_type: TaskEventType,
        title: str,
        summary: Optional[str] = None,
        capability_id: Optional[str] = None,
        entity_ids: Optional[list[str]] = None,
        data: Optional[dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        status: str = "SUCCESS",
    ) -> TaskEvent:
        """
        Emit and persist an immutable TaskEvent.
        Appends to active Task, writes to TaskLedger, and notifies TaskEventBus subscribers.
        """
        task = self.get_task(task_id)
        now = time.time()
        event_id = str(uuid.uuid4())

        event = TaskEvent(
            id=event_id,
            task_id=task_id,
            timestamp=now,
            type=event_type,
            status=status,
            title=title,
            summary=summary,
            capability_id=capability_id,
            entity_ids=entity_ids or [],
            data=data or {},
            duration_ms=duration_ms,
        )

        if task:
            task.events.append(event)

        # Write to ledger
        self.ledger.append_event(event)

        # Publish to event bus (UI, telemetry, diagnostics)
        self.event_bus.publish(event)

        return event

    def complete_task(self, task_id: str, result: TaskResult) -> None:
        """
        Mark a task as successfully COMPLETED with its final result bundle.
        """
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        task.final_result = result
        self.transition_status(task_id, result.status if result.status.is_terminal else TaskStatus.COMPLETED)

        self.emit_event(
            task_id=task_id,
            event_type=TaskEventType.TASK_COMPLETED,
            title="Task Completed",
            summary=result.summary,
            data={"success": result.success, "capabilities": result.capabilities_used},
            duration_ms=result.duration_ms,
            status="SUCCESS",
        )

        self.ledger.update_task_status(task_id, task.status, final_result=result)

        # Record result in conversation messages
        self.ledger.record_message(ConversationMessage(
            id=str(uuid.uuid4()),
            conversation_id=task.conversation_id,
            task_id=task_id,
            sender="ASTRA_RESULT",
            text=result.summary or result.message,
            timestamp=time.time(),
            data=result.data,
        ))

        # Cleanup memory reference from active table
        with self._lock:
            self._active_tasks.pop(task_id, None)
            self._cancellation_tokens.pop(task_id, None)

    def fail_task(self, task_id: str, error: TaskError) -> None:
        """
        Mark a task as FAILED with a structured error payload.
        """
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        result = TaskResult(
            task_id=task_id,
            success=False,
            status=TaskStatus.FAILED,
            message=error.message,
            summary=f"Failed: {error.message}",
            capabilities_used=[error.capability] if error.capability else [],
            duration_ms=task.duration_ms(),
            error=error,
        )
        task.final_result = result

        self.transition_status(task_id, TaskStatus.FAILED)

        self.emit_event(
            task_id=task_id,
            event_type=TaskEventType.TASK_FAILED,
            title="Task Failed",
            summary=error.message,
            capability_id=error.capability,
            data=error.to_dict(),
            status="FAILED",
        )

        self.ledger.update_task_status(task_id, TaskStatus.FAILED, final_result=result)

        with self._lock:
            self._active_tasks.pop(task_id, None)
            self._cancellation_tokens.pop(task_id, None)

    def block_task(self, task_id: str, reason: str, capability_id: Optional[str] = None) -> None:
        """
        Mark a task as BLOCKED due to hard security policy interception.
        """
        task = self.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        err = TaskError(code="POLICY_BLOCKED", message=reason, capability=capability_id)
        result = TaskResult(
            task_id=task_id,
            success=False,
            status=TaskStatus.BLOCKED,
            message=reason,
            summary=f"Blocked: {reason}",
            capabilities_used=[capability_id] if capability_id else [],
            duration_ms=task.duration_ms(),
            error=err,
        )
        task.final_result = result

        self.transition_status(task_id, TaskStatus.BLOCKED)

        self.emit_event(
            task_id=task_id,
            event_type=TaskEventType.TASK_BLOCKED,
            title="Action Blocked by Policy",
            summary=reason,
            capability_id=capability_id,
            status="BLOCKED",
        )

        self.ledger.update_task_status(task_id, TaskStatus.BLOCKED, final_result=result)

        with self._lock:
            self._active_tasks.pop(task_id, None)
            self._cancellation_tokens.pop(task_id, None)

    def cancel_task(self, task_id: str, reason: str = "User cancelled task") -> None:
        """
        Request cooperative cancellation of a task.
        """
        token = self.get_cancellation_token(task_id)
        if token:
            token.cancel(reason)

        task = self.get_task(task_id)
        if not task:
            return

        self.emit_event(
            task_id=task_id,
            event_type=TaskEventType.TASK_CANCEL_REQUESTED,
            title="Cancellation Requested",
            summary=reason,
            status="WARNING",
        )

        try:
            self.transition_status(task_id, TaskStatus.CANCELLED)
        except InvalidStateTransitionError:
            # If already in terminal state, ignore
            return

        result = TaskResult(
            task_id=task_id,
            success=False,
            status=TaskStatus.CANCELLED,
            message=reason,
            summary="Task was cancelled by user.",
            duration_ms=task.duration_ms(),
            error=TaskError(code="CANCELLED", message=reason),
        )
        task.final_result = result

        self.emit_event(
            task_id=task_id,
            event_type=TaskEventType.TASK_CANCELLED,
            title="Task Cancelled",
            summary=reason,
            status="CANCELLED",
        )

        self.ledger.update_task_status(task_id, TaskStatus.CANCELLED, final_result=result)

        with self._lock:
            self._active_tasks.pop(task_id, None)
            self._cancellation_tokens.pop(task_id, None)

    # -------------------------------------------------------------------------
    # Capability Execution Instrumentation
    # -------------------------------------------------------------------------

    def execute_capability(
        self,
        task_id: str,
        capability_id: str,
        arguments: dict[str, Any],
        registry: CapabilityRegistry,
    ) -> CapabilityResult:
        """
        Instrumented capability dispatch within a Task context.
        Verifies cancellation, emits lifecycle events, profiles execution, and records results.
        """
        token = self.get_cancellation_token(task_id)
        if token and token.is_cancelled:
            self.cancel_task(task_id, reason=token.reason or "Task cancelled before capability dispatch.")
            raise TaskCancelledError(token.reason or "Task cancelled")

        # Emit CAPABILITY_STARTED
        cap_meta = registry.get(capability_id)
        title = cap_meta.description if cap_meta else f"Executing {capability_id}"
        self.emit_event(
            task_id=task_id,
            event_type=TaskEventType.CAPABILITY_STARTED,
            title=f"Starting: {capability_id}",
            summary=f"Running {capability_id}",
            capability_id=capability_id,
            data={"args": sanitize_capability_payload(capability_id, arguments)},
            status="RUNNING",
        )

        t0 = time.perf_counter()
        result = registry.execute(capability_id, arguments)
        latency = (time.perf_counter() - t0) * 1000.0

        # Check for mid-execution cancellation
        if token and token.is_cancelled:
            self.cancel_task(task_id, reason="Task cancelled during capability execution.")
            raise TaskCancelledError(token.reason or "Task cancelled")

        if result.success:
            summary = generate_capability_summary(capability_id, result.data, result.message)
            self.emit_event(
                task_id=task_id,
                event_type=TaskEventType.CAPABILITY_COMPLETED,
                title=f"Completed: {capability_id}",
                summary=summary,
                capability_id=capability_id,
                data=sanitize_capability_payload(capability_id, result.data),
                duration_ms=latency,
                status="SUCCESS",
            )
        else:
            self.emit_event(
                task_id=task_id,
                event_type=TaskEventType.CAPABILITY_FAILED,
                title=f"Failed: {capability_id}",
                summary=result.message,
                capability_id=capability_id,
                data={"error_code": result.error_code.value if result.error_code else "UNKNOWN", "message": result.message},
                duration_ms=latency,
                status="FAILED",
            )

        return result

    # -------------------------------------------------------------------------
    # Re-Run Semantic Evaluation (Rule #35, #36)
    # -------------------------------------------------------------------------

    def re_run_task(self, historical_task_id: str) -> Task:
        """
        Re-run a previous task safely.
        
        CRITICAL SAFETY INVARIANT:
        This creates a BRAND NEW task from the original semantic request text.
        It NEVER replays stale resolved arguments (such as yesterday's PID or port).
        The new task must be re-evaluated through the NLP, Entity Resolution, and
        ActionGate pipelines against current real-time machine state.
        """
        old_task = self.ledger.get_task(historical_task_id)
        if not old_task:
            raise KeyError(f"Historical task '{historical_task_id}' not found in ledger.")

        if not old_task.request_text:
            raise ValueError(f"Task '{historical_task_id}' has no recorded semantic request text to re-run.")

        logger.info(
            "Initiating semantic re-run for historical task %s (Request: '%s')",
            historical_task_id,
            old_task.request_text,
        )

        new_task = self.create_task(
            request_text=old_task.request_text,
            conversation_id=old_task.conversation_id,
            source="re_run",
            metadata={"re_run_from": historical_task_id},
        )

        return new_task

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve task from memory if active, or fall back to ledger."""
        with self._lock:
            task = self._active_tasks.get(task_id)
            if task:
                return task
        return self.ledger.get_task(task_id)

    def get_cancellation_token(self, task_id: str) -> Optional[CancellationToken]:
        """Retrieve the cancellation token for an active task."""
        with self._lock:
            return self._cancellation_tokens.get(task_id)
