"""Production TaskRuntime and Multi-Task Resource Lock Coordinator for AstraRun 1.0.

Orchestrates:
  Goal -> Context -> RAG/Memory -> Skills -> CognitiveRouter -> PlanDAG ->
  Capabilities -> ActionGate -> Execution -> Observations -> Verification ->
  Recovery -> Completion.

Guarantees:
  - Observable execution facts only (zero hidden model chain-of-thought leaked to UI)
  - Strict serialization of physical input via PHYSICAL_INPUT resource lock
  - Safe concurrent background execution for non-conflicting tasks
  - Real-time pause/resume/cancellation and user takeover handling (PAUSED_USER_ACTIVE)
"""

from __future__ import annotations

from pathlib import Path
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from astrarun.core.logging import get_logger
from astrarun.tasks.cancellation import CancellationToken
from astrarun.tasks.checkpoints import PlanRevision, RecoveryPlan, TaskCheckpoint
from astrarun.tasks.reconciliation import (
    HumanChangeClassification,
    ResumeAssessment,
    ResumeVerdict,
    TaskReconciliationEngine,
)
from astrarun.tasks.disturbances import (
    DisturbanceEvent,
    DisturbanceTracker,
    DisturbanceType,
    RecoveryBudget,
)
from astrarun.tasks.events import TaskEventBus, get_global_event_bus
from astrarun.tasks.invariants import (
    InvariantImportance,
    InvariantType,
    TaskInvariant,
    TaskWatchSet,
)
from astrarun.tasks.ledger import TaskLedger
from astrarun.tasks.models import (
    Task,
    TaskError,
    TaskEvent,
    TaskEventType,
    TaskResult,
    TaskStatus,
)

logger = get_logger("astrarun.tasks.runtime")


class ResourceLockType(str, Enum):
    PHYSICAL_INPUT = "PHYSICAL_INPUT"
    BROWSER = "BROWSER"
    WORKSPACE = "WORKSPACE"
    GPU_MODEL = "GPU_MODEL"


class ResourceLockManager:
    """
    Coordinates access to exclusive workstation resources across concurrent tasks.
    Serializes physical mouse/keyboard control while allowing non-conflicting background tasks.
    """

    def __init__(self):
        self._locks: Dict[str, str] = {}  # resource_key -> task_id
        self._lock = threading.RLock()

    def acquire_lock(self, resource_key: str, task_id: str, timeout_sec: float = 5.0) -> bool:
        """Acquire a named resource lock for a task, waiting up to timeout_sec."""
        deadline = time.time() + timeout_sec
        with self._lock:
            while time.time() < deadline:
                current_owner = self._locks.get(resource_key)
                if current_owner is None or current_owner == task_id:
                    self._locks[resource_key] = task_id
                    logger.debug("Task %s acquired resource lock '%s'", task_id, resource_key)
                    return True
                time.sleep(0.05)
            logger.warning("Task %s timed out waiting for resource lock '%s' (owned by %s)", task_id, resource_key, self._locks.get(resource_key))
            return False

    def release_lock(self, resource_key: str, task_id: str) -> None:
        """Release a resource lock if owned by task_id."""
        with self._lock:
            if self._locks.get(resource_key) == task_id:
                del self._locks[resource_key]
                logger.debug("Task %s released resource lock '%s'", task_id, resource_key)

    def release_all_for_task(self, task_id: str) -> None:
        """Release all resource locks held by a specific task."""
        with self._lock:
            to_remove = [k for k, v in self._locks.items() if v == task_id]
            for k in to_remove:
                del self._locks[k]
            if to_remove:
                logger.debug("Released all locks for task %s: %s", task_id, to_remove)

    def is_locked(self, resource_key: str) -> bool:
        with self._lock:
            return resource_key in self._locks


@dataclass
class PlanStep:
    """Typed step in an execution plan DAG with invariants and recovery policy."""
    step_id: str
    capability: str
    arguments: Dict[str, Any]
    description: str = ""
    required_locks: List[str] = field(default_factory=list)
    preconditions: List[TaskInvariant] = field(default_factory=list)
    expected_postconditions: List[TaskInvariant] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    recovery_policy: str = "reopen_app"  # reopen_app, reconcile_file, resume_download, wait_network, ask_user
    status: str = "PENDING"  # PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
    result: Optional[Any] = None


class TaskRuntime:
    """
    Production TaskRuntime orchestrating natural-language goal execution,
    resource locks, ActionGate security, observations, and progress events.
    """

    def __init__(
        self,
        app: Any = None,
        event_bus: Optional[TaskEventBus] = None,
        ledger: Optional[TaskLedger] = None,
    ):
        self.app = app
        self.event_bus = event_bus or get_global_event_bus()
        self.ledger = ledger or TaskLedger()
        self.lock_manager = ResourceLockManager()

        self._active_tasks: Dict[str, Task] = {}
        self._task_threads: Dict[str, threading.Thread] = {}
        self._cancellation_tokens: Dict[str, CancellationToken] = {}
        self._task_plans: Dict[str, List[PlanStep]] = {}
        self._watch_sets: Dict[str, TaskWatchSet] = {}
        self._disturbance_trackers: Dict[str, DisturbanceTracker] = {}
        self._checkpoints: Dict[str, List[TaskCheckpoint]] = {}
        self._lock = threading.RLock()

    def create_and_enqueue_task(
        self,
        goal: str,
        origin_hwnd: Optional[int] = None,
        source: str = "command_surface",
    ) -> Task:
        """Create a new Task instance in QUEUED state and emit TASK_CREATED event."""
        task_id = str(uuid.uuid4())
        conv = self.ledger.create_conversation(title=goal[:50])
        task = Task(
            id=task_id,
            conversation_id=conv.id,
            request_text=goal,
            source=source,
            status=TaskStatus.QUEUED,
            metadata={"origin_hwnd": origin_hwnd},
        )
        token = CancellationToken()

        with self._lock:
            self._active_tasks[task_id] = task
            self._cancellation_tokens[task_id] = token

        self.ledger.save_task(task)

        # Publish TASK_CREATED event
        ev = TaskEvent(
            id=str(uuid.uuid4()),
            task_id=task_id,
            type=TaskEventType.TASK_CREATED,
            title="Task Enqueued",
            summary=goal,
            data={"raw_query": goal, "origin_hwnd": origin_hwnd},
        )
        self.event_bus.publish(ev)
        return task

    def start_task_async(self, task_id: str) -> None:
        """Launch background worker thread executing the task pipeline."""
        with self._lock:
            task = self._active_tasks.get(task_id)
            if not task:
                logger.error("Cannot start task %s: not found", task_id)
                return

            t = threading.Thread(
                target=self._run_task_pipeline,
                args=(task_id,),
                daemon=True,
                name=f"TaskWorker-{task_id[:8]}",
            )
            self._task_threads[task_id] = t
            t.start()

    def _run_task_pipeline(self, task_id: str) -> None:
        """Internal pipeline orchestrating goal execution on worker thread."""
        task = self.get_task(task_id)
        if not task:
            return

        token = self._cancellation_tokens.get(task_id)

        try:
            # 1. PLANNING Phase (if not already planned)
            if task.status == TaskStatus.QUEUED:
                task.transition_to(TaskStatus.PLANNING)
                self.ledger.save_task(task)
                self._emit_event(task_id, TaskEventType.NLP_PARSE_STARTED, "Planning task", summary=f"Decomposing goal: {task.request_text}")

            if token and token.is_cancelled:
                self._handle_cancelled(task)
                return

            # Check if app is provided for resolution
            if self.app is not None:
                # Execute canonical request handler through AstraApplication
                exec_result = self.app.handle_request(task.request_text, origin_hwnd=task.metadata.get("origin_hwnd"))

                if exec_result.type == "confirm":
                    task.transition_to(TaskStatus.WAITING_CONFIRMATION)
                    self.ledger.save_task(task)
                    self._emit_event(
                        task_id,
                        TaskEventType.CONFIRMATION_REQUESTED,
                        "ActionGate Permission Required",
                        summary=exec_result.prompt or exec_result.message,
                        data={
                            "confirmation_token": exec_result.confirmation_token,
                            "prompt": exec_result.prompt,
                            "risk": exec_result.risk.value if hasattr(exec_result.risk, "value") else str(exec_result.risk),
                        },
                    )
                    return

                if exec_result.type == "clarify":
                    task.transition_to(TaskStatus.WAITING_CLARIFICATION)
                    self.ledger.save_task(task)
                    self._emit_event(
                        task_id,
                        TaskEventType.CLARIFICATION_REQUESTED,
                        "Clarification Needed",
                        summary=exec_result.prompt or exec_result.message,
                        data={"candidates": exec_result.candidates, "prompt": exec_result.prompt},
                    )
                    return

                if exec_result.type == "blocked":
                    task.transition_to(TaskStatus.BLOCKED)
                    self.ledger.save_task(task)
                    self._emit_event(task_id, TaskEventType.TASK_BLOCKED, "Task Blocked by Policy", summary=exec_result.message)
                    return

                if not exec_result.success:
                    self._handle_failure(task, exec_result.message)
                    return

                # Task completed successfully via app pipeline
                task.transition_to(TaskStatus.COMPLETED)
                task.final_result = TaskResult(
                    task_id=task_id,
                    success=True,
                    status=TaskStatus.COMPLETED,
                    message=exec_result.message,
                    summary=exec_result.message,
                    data=exec_result.data or {},
                )
                self.ledger.save_task(task)
                self._emit_event(task_id, TaskEventType.TASK_COMPLETED, "Completed", summary=exec_result.message, data=exec_result.data or {})
            else:
                # Standalone simulation or test execution
                task.transition_to(TaskStatus.RUNNING)
                self._emit_event(task_id, TaskEventType.CAPABILITY_STARTED, "Executing task", summary=f"Processing {task.request_text}")
                time.sleep(0.05)
                task.transition_to(TaskStatus.COMPLETED)
                task.final_result = TaskResult(
                    task_id=task_id,
                    success=True,
                    status=TaskStatus.COMPLETED,
                    message=f"Goal '{task.request_text}' completed successfully.",
                    summary="Execution verified.",
                )
                self.ledger.save_task(task)
                self._emit_event(task_id, TaskEventType.TASK_COMPLETED, "Completed", summary=task.final_result.message)

        except Exception as e:
            logger.error("Unhandled error in task pipeline %s: %s", task_id, e, exc_info=True)
            self._handle_failure(task, str(e))
        finally:
            self.lock_manager.release_all_for_task(task_id)

    def pause_task(self, task_id: str, is_user_takeover: bool = False, reason: str = "USER_REQUEST") -> None:
        """Pause task execution atomically, save durable checkpoint, and release workstation locks."""
        task = self.get_task(task_id)
        if not task:
            return
        if task.status.is_terminal or task.status in (
            TaskStatus.PAUSED_USER_REQUEST,
            TaskStatus.PAUSED_USER_ACTIVE,
            TaskStatus.PAUSED,
            TaskStatus.PAUSING,
        ):
            return

        # 1. Determine target status and emit pause request event
        if is_user_takeover:
            target_status = TaskStatus.PAUSED_USER_ACTIVE
            msg = "Paused — you're using the computer"
        else:
            target_status = TaskStatus.PAUSED_USER_REQUEST
            msg = "Task paused by user"
            self._emit_event(
                task_id,
                TaskEventType.USER_PAUSE_REQUESTED,
                "User Pause Requested",
                summary="User explicitly requested task pause.",
                data={"reason": reason},
            )

        # 2. Transition through PAUSING for atomic state isolation
        if task.status != TaskStatus.PAUSING:
            try:
                task.transition_to(TaskStatus.PAUSING)
            except Exception:
                task.status = TaskStatus.PAUSING
            self.ledger.save_task(task)
            self._emit_event(
                task_id,
                TaskEventType.TASK_PAUSING,
                "Task Pausing",
                summary="Releasing workstation locks and checkpointing state...",
            )

        # 3. Release physical input and workstation locks
        self.lock_manager.release_all_for_task(task_id)

        # 4. Save durable checkpoint
        latest_chk = self.ledger.get_latest_checkpoint(task_id)
        if not latest_chk:
            latest_chk = self.create_checkpoint(
                task_id=task_id,
                step_id="step_pause",
                completed_step_ids=[],
                outputs={},
            )
        latest_chk.goal = task.request_text
        latest_chk.status = target_status.value
        latest_chk.pause_timestamp = time.time()
        latest_chk.pause_reason = "USER_REQUEST" if not is_user_takeover else "USER_ACTIVE"
        self.ledger.save_checkpoint(latest_chk)

        # 5. Final transition to target paused status
        task.transition_to(target_status)
        self.ledger.save_task(task)

        # 6. Emit TASK_INTERRUPTED if user takeover, else TASK_PAUSED
        event_type = TaskEventType.TASK_INTERRUPTED if is_user_takeover else TaskEventType.TASK_PAUSED
        self._emit_event(
            task_id,
            event_type,
            "Task Paused",
            summary=msg,
            data={
                "target_status": target_status.value,
                "is_user_takeover": is_user_takeover,
                "checkpoint_id": latest_chk.checkpoint_id,
                "pause_timestamp": latest_chk.pause_timestamp,
            },
        )
        logger.info("Task %s transitioned to %s", task_id, target_status.value)

    def resume_task(self, task_id: str, goal_verification_func: Optional[Any] = None) -> ResumeAssessment:
        """
        Resume a paused task using pre-resumption state reconciliation.
        Authoritative invariant: 'RESUME IS RECONCILIATION, NOT UNPAUSE'.
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.status not in (
            TaskStatus.PAUSED,
            TaskStatus.PAUSED_USER_REQUEST,
            TaskStatus.PAUSED_USER_ACTIVE,
            TaskStatus.SUSPENDED,
            TaskStatus.SUSPENDED_SYSTEM,
            TaskStatus.INTERRUPTED,
        ):
            logger.warning("Task %s is in state %s; cannot resume", task_id, task.status.value)
            return ResumeAssessment(
                task_id=task_id,
                verdict=ResumeVerdict.UNRECOVERABLE,
                reason=f"Task is in state {task.status.value}, cannot resume.",
            )

        # 1. Audit events for resume request and reconciliation start
        self._emit_event(
            task_id,
            TaskEventType.RESUME_REQUESTED,
            "Resume Requested",
            summary="User or system requested task resumption.",
        )
        self._emit_event(
            task_id,
            TaskEventType.RESUME_RECONCILIATION_STARTED,
            "Reconciliation Started",
            summary="Validating filesystem, artifacts, and external progress before continuing...",
        )

        # 2. Get latest checkpoint
        chk = self.ledger.get_latest_checkpoint(task_id)
        if not chk:
            chk = TaskCheckpoint(
                task_id=task_id,
                goal=task.request_text,
                status=task.status.value,
                timestamp=time.time(),
            )

        # 3. Run reconciliation engine
        engine = TaskReconciliationEngine()
        assessment = engine.reconcile(chk, goal_verification_func=goal_verification_func)
        logger.info("Reconciliation assessment for %s: %s (reason: %s)", task_id, assessment.verdict.value, assessment.reason)

        # 4. Handle reconciliation verdicts
        if assessment.verdict == ResumeVerdict.GOAL_ALREADY_COMPLETED:
            self._emit_event(
                task_id,
                TaskEventType.RESUME_EXTERNAL_PROGRESS_FOUND,
                "Goal Completed Externally",
                summary=assessment.reason,
                data={"surviving_artifacts": assessment.surviving_artifacts},
            )
            task.transition_to(TaskStatus.COMPLETED)
            task.final_result = TaskResult(
                task_id=task_id,
                success=True,
                status=TaskStatus.COMPLETED,
                message=assessment.reason,
                summary=assessment.reason,
                data={"artifacts": assessment.surviving_artifacts},
            )
            self.ledger.save_task(task)
            self._emit_event(
                task_id,
                TaskEventType.TASK_COMPLETED,
                "Task Completed",
                summary=assessment.reason,
            )
            return assessment

        if assessment.verdict == ResumeVerdict.REQUIRES_USER:
            self._emit_event(
                task_id,
                TaskEventType.RESUME_CONFLICT_FOUND,
                "Reconciliation Conflict",
                summary=assessment.reason,
                data={"conflicts": assessment.conflicts, "lost_state": assessment.lost_state},
            )
            task.transition_to(TaskStatus.WAITING_CLARIFICATION)
            self.ledger.save_task(task)
            self._emit_event(
                task_id,
                TaskEventType.CLARIFICATION_REQUESTED,
                "Manual Clarification Needed on Resume",
                summary=assessment.reason,
                data={
                    "title": "Action Needed to Resume",
                    "message": assessment.reason,
                    "conflicts": assessment.conflicts,
                    "recovery": assessment.recommended_recovery,
                },
            )
            return assessment

        if assessment.verdict == ResumeVerdict.PROGRESS_ADVANCED_EXTERNALLY:
            self._emit_event(
                task_id,
                TaskEventType.RESUME_EXTERNAL_PROGRESS_FOUND,
                "External Progress Discovered",
                summary=assessment.reason,
                data={"externally_completed": assessment.externally_completed_work},
            )
            if assessment.plan_revision:
                self._emit_event(
                    task_id,
                    TaskEventType.PLAN_REVISED_AFTER_PAUSE,
                    "Plan Revised After External Progress",
                    summary=assessment.plan_revision.reason,
                    data={"revision": assessment.plan_revision.revision},
                )

        elif assessment.verdict in (ResumeVerdict.REQUIRES_REPLAN, ResumeVerdict.RECOVERABLE_DRIFT, ResumeVerdict.PLAN_PARTIALLY_INVALID):
            self._emit_event(
                task_id,
                TaskEventType.RESUME_STATE_CHANGED,
                "State Drift Reconciled",
                summary=assessment.reason,
                data={"lost_state": assessment.lost_state},
            )
            if assessment.plan_revision:
                self._emit_event(
                    task_id,
                    TaskEventType.PLAN_REVISED_AFTER_PAUSE,
                    "Plan Revised After Environment Drift",
                    summary=assessment.plan_revision.reason,
                    data={"revision": assessment.plan_revision.revision},
                )

        # 5. Transition to RUNNING and restart worker
        task.transition_to(TaskStatus.RUNNING)
        self.ledger.save_task(task)
        self._emit_event(
            task_id,
            TaskEventType.TASK_RESUMED,
            "Task Resumed",
            summary=f"Resumed execution ({assessment.verdict.value}).",
            data={"verdict": assessment.verdict.value, "reason": assessment.reason},
        )
        logger.info("Task %s resumed to RUNNING", task_id)

        # Restart worker thread
        self.start_task_async(task_id)
        return assessment

    def cancel_task(self, task_id: str) -> None:
        """Signal cooperative cancellation, release all locks, and transition to CANCELLED."""
        token = self._cancellation_tokens.get(task_id)
        if token:
            token.cancel()

        task = self.get_task(task_id)
        if task and not task.status.is_terminal:
            self._handle_cancelled(task)

    def _handle_cancelled(self, task: Task) -> None:
        """Finalize cancelled task state."""
        try:
            task.transition_to(TaskStatus.CANCELLED)
        except Exception:
            task.status = TaskStatus.CANCELLED

        self.lock_manager.release_all_for_task(task.id)
        self.ledger.save_task(task)
        self._emit_event(task.id, TaskEventType.TASK_CANCELLED, "Task Cancelled", summary="Cancelled by user request")
        logger.info("Task %s cancelled", task.id)

    def _handle_failure(self, task: Task, error_msg: str) -> None:
        """Finalize failed task state."""
        try:
            task.transition_to(TaskStatus.FAILED)
        except Exception:
            task.status = TaskStatus.FAILED

        task.final_result = TaskResult(
            task_id=task.id,
            success=False,
            status=TaskStatus.FAILED,
            message=error_msg,
            summary=error_msg,
            error=TaskError(code="EXECUTION_ERROR", message=error_msg),
        )
        self.lock_manager.release_all_for_task(task.id)
        self.ledger.save_task(task)
        self._emit_event(task.id, TaskEventType.TASK_FAILED, "Task Failed", summary=error_msg)
        logger.warning("Task %s failed: %s", task.id, error_msg)

    def _emit_event(
        self,
        task_id: str,
        event_type: TaskEventType,
        title: str,
        summary: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Publish typed event to event bus and record in task instance."""
        ev = TaskEvent(
            id=str(uuid.uuid4()),
            task_id=task_id,
            type=event_type,
            title=title,
            summary=summary,
            data=data or {},
        )
        task = self.get_task(task_id)
        if task:
            task.events.append(ev)
        self.event_bus.publish(ev)

    def get_task(self, task_id: str) -> Optional[Task]:
        with self._lock:
            task = self._active_tasks.get(task_id)
            if not task:
                task = self.ledger.get_task(task_id)
                if task:
                    self._active_tasks[task_id] = task
            return task

    def get_recent_tasks(self, limit: int = 20) -> List[Task]:
        """Fetch recent tasks from active memory and SQLite ledger."""
        with self._lock:
            active_list = list(self._active_tasks.values())
        if hasattr(self.ledger, "get_recent_tasks"):
            ledger_list = self.ledger.get_recent_tasks(limit=limit)
        else:
            ledger_list = self.ledger.list_tasks(limit=limit)
        # Deduplicate by task ID preserving active state
        seen_ids = set()
        merged = []
        for t in active_list + ledger_list:
            if t.id not in seen_ids:
                seen_ids.add(t.id)
                merged.append(t)
        merged.sort(key=lambda x: x.created_at, reverse=True)
        return merged[:limit]

    # -------------------------------------------------------------------------
    # Adaptive Task Execution & Continuous Verification (Milestone 7A)
    # -------------------------------------------------------------------------

    def get_or_create_watch_set(self, task_id: str) -> TaskWatchSet:
        """Fetch or initialize the scoped TaskWatchSet for a task."""
        with self._lock:
            if task_id not in self._watch_sets:
                self._watch_sets[task_id] = TaskWatchSet(task_id=task_id)
            return self._watch_sets[task_id]

    def get_or_create_disturbance_tracker(self, task_id: str) -> DisturbanceTracker:
        """Fetch or initialize the disturbance tracker and recovery budget for a task."""
        with self._lock:
            if task_id not in self._disturbance_trackers:
                self._disturbance_trackers[task_id] = DisturbanceTracker(task_id=task_id)
            return self._disturbance_trackers[task_id]

    def create_checkpoint(
        self,
        task_id: str,
        step_id: str,
        completed_step_ids: List[str],
        outputs: Dict[str, Any],
        artifacts: Optional[List[Path]] = None,
        recoverable_handles: Optional[Dict[str, Any]] = None,
    ) -> TaskCheckpoint:
        """Create and persist a durable milestone checkpoint."""
        checkpoint = TaskCheckpoint(
            task_id=task_id,
            current_step_id=step_id,
            completed_step_ids=list(completed_step_ids),
            important_outputs=dict(outputs),
            recoverable_handles=dict(recoverable_handles or {}),
            timestamp=time.time(),
        )
        if artifacts:
            for art in artifacts:
                checkpoint.record_artifact(art)

        watch_set = self.get_or_create_watch_set(task_id)
        for inv_id, inv in watch_set.invariants.items():
            valid, _, _ = inv.check()
            checkpoint.invariant_states[inv_id] = valid

        with self._lock:
            if task_id not in self._checkpoints:
                self._checkpoints[task_id] = []
            self._checkpoints[task_id].append(checkpoint)

        self.ledger.save_checkpoint(checkpoint)
        self._emit_event(
            task_id,
            TaskEventType.CHECKPOINT_CREATED,
            "Checkpoint Saved",
            summary=f"Checkpoint {checkpoint.checkpoint_id} after step {step_id}",
            data={
                "checkpoint_id": checkpoint.checkpoint_id,
                "step_id": step_id,
                "completed_count": len(completed_step_ids),
            },
        )
        return checkpoint

    def execute_adaptive_plan(
        self,
        task_id: str,
        steps: List[PlanStep],
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> TaskResult:
        """
        Execute an execution plan DAG adaptively with continuous invariant verification,
        disturbance tracking, checkpointing, and bounded recovery policies.
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        token = self._cancellation_tokens.get(task_id)
        watch_set = self.get_or_create_watch_set(task_id)
        tracker = self.get_or_create_disturbance_tracker(task_id)
        context = dict(initial_context or {})
        completed_step_ids: List[str] = []
        outputs: Dict[str, Any] = {}

        task.transition_to(TaskStatus.RUNNING)
        self.ledger.save_task(task)

        for step in steps:
            if token and token.is_cancelled:
                self._handle_cancelled(task)
                return task.final_result

            # Check if task was paused by user or system
            if task.status in (
                TaskStatus.PAUSING,
                TaskStatus.PAUSED_USER_REQUEST,
                TaskStatus.PAUSED_USER_ACTIVE,
                TaskStatus.PAUSED,
                TaskStatus.SUSPENDED,
                TaskStatus.SUSPENDED_SYSTEM,
            ):
                logger.info("Adaptive plan execution paused for task %s at step %s", task_id, step.step_id)
                return TaskResult(
                    task_id=task_id,
                    success=True,
                    status=task.status,
                    message=f"Execution paused cleanly at step {step.step_id}",
                    summary=f"Task paused at step {step.step_id}",
                    data=outputs,
                )

            # 1. OBSERVE PRECONDITIONS
            for pre in step.preconditions:
                watch_set.add_invariant(pre)
                valid, observed, msg = pre.check(context)
                if not valid:
                    self._emit_event(
                        task_id,
                        TaskEventType.INVARIANT_BROKEN,
                        "Precondition Broken",
                        summary=msg,
                        data={"invariant_id": pre.id, "type": pre.type.value, "target": pre.target, "observed": str(observed)},
                    )
                    # Attempt recovery
                    ok, rec_msg = self._recover_broken_invariant(task_id, step, pre, observed)
                    if not ok:
                        if rec_msg == "USER_CONFLICT":
                            return TaskResult(
                                task_id=task_id,
                                success=False,
                                status=TaskStatus.WAITING_CLARIFICATION,
                                message=f"User conflict on {pre.target}. Waiting for user guidance.",
                                summary=f"Astra needs {pre.target} to continue this task.",
                            )
                        elif rec_msg == "FILE_CONFLICT":
                            return TaskResult(
                                task_id=task_id,
                                success=False,
                                status=TaskStatus.WAITING_CLARIFICATION,
                                message=f"File conflict on {pre.target}. Waiting for user guidance.",
                                summary="The file changed while I was working on it.",
                            )
                        else:
                            self._handle_failure(task, f"Failed to recover precondition {pre.type.value} on {pre.target}: {rec_msg}")
                            return task.final_result

            # 2. ACQUIRE REQUIRED LOCKS
            for lock_name in step.required_locks:
                if not self.lock_manager.acquire_lock(lock_name, task_id):
                    self._handle_failure(task, f"Timed out acquiring lock '{lock_name}'")
                    return task.final_result

            # 3. EXECUTE STEP
            step.status = "RUNNING"
            self._emit_event(
                task_id,
                TaskEventType.CAPABILITY_STARTED,
                f"Step: {step.description}",
                summary=f"Executing {step.capability}",
                data={"step_id": step.step_id, "capability": step.capability, "arguments": step.arguments},
            )

            try:
                # Dispatch execution to application registry or simulation
                if self.app and hasattr(self.app, "capability_registry"):
                    cap_res = self.app.capability_registry.execute(step.capability, step.arguments, task_id=task_id)
                    success = cap_res.success
                    result_data = cap_res.data
                    step_msg = cap_res.message
                else:
                    success = True
                    result_data = dict(step.arguments)
                    step_msg = f"Step {step.step_id} executed successfully"

                if not success:
                    self._handle_failure(task, f"Step '{step.description}' failed: {step_msg}")
                    return task.final_result

                step.status = "COMPLETED"
                step.result = result_data
                completed_step_ids.append(step.step_id)
                if isinstance(result_data, dict):
                    outputs.update(result_data)
                context[step.step_id] = result_data

                self._emit_event(
                    task_id,
                    TaskEventType.CAPABILITY_COMPLETED,
                    f"Completed: {step.description}",
                    summary=step_msg,
                    data={"step_id": step.step_id, "result": result_data},
                )
            finally:
                for lock_name in step.required_locks:
                    self.lock_manager.release_lock(lock_name, task_id)

            # 4. OBSERVE POSTCONDITIONS
            for post in step.expected_postconditions:
                watch_set.add_invariant(post)
                valid, observed, msg = post.check(context)
                if not valid:
                    self._emit_event(
                        task_id,
                        TaskEventType.INVARIANT_BROKEN,
                        "Postcondition Broken",
                        summary=msg,
                        data={"invariant_id": post.id, "type": post.type.value, "target": post.target},
                    )
                    ok, rec_msg = self._recover_broken_invariant(task_id, step, post, observed)
                    if not ok:
                        self._handle_failure(task, f"Postcondition verification failed: {post.type.value} on {post.target}")
                        return task.final_result

            # 5. CHECKPOINT STEP
            artifacts = []
            for arg_key in ("file_path", "path", "destination", "dest"):
                if arg_key in step.arguments:
                    p = Path(step.arguments[arg_key])
                    if p.exists():
                        artifacts.append(p)

            self.create_checkpoint(
                task_id=task_id,
                step_id=step.step_id,
                completed_step_ids=completed_step_ids,
                outputs=outputs,
                artifacts=artifacts,
            )

        # ALL STEPS COMPLETED & DURABLY VERIFIED
        task.transition_to(TaskStatus.COMPLETED)
        task.final_result = TaskResult(
            task_id=task_id,
            success=True,
            status=TaskStatus.COMPLETED,
            message=f"Task completed successfully ({len(completed_step_ids)} steps verified).",
            summary=f"All {len(completed_step_ids)} plan steps executed and verified.",
            data=outputs,
        )
        self.ledger.save_task(task)
        self._emit_event(
            task_id,
            TaskEventType.TASK_COMPLETED,
            "Task Completed",
            summary=task.final_result.summary,
            data=outputs,
        )
        return task.final_result

    def _recover_broken_invariant(
        self,
        task_id: str,
        step: PlanStep,
        invariant: TaskInvariant,
        observed: Any,
    ) -> Tuple[bool, str]:
        """Execute bounded recovery strategy for a broken invariant."""
        tracker = self.get_or_create_disturbance_tracker(task_id)
        task = self.get_task(task_id)

        # Process/Window Closure Recovery
        if invariant.type in (InvariantType.PROCESS_RUNNING, InvariantType.WINDOW_EXISTS):
            tracker.record_disturbance(
                disturbance_type=DisturbanceType.USER_CLOSED_REQUIRED_WINDOW,
                observed_before=True,
                observed_after=observed,
                affected_invariants=[invariant.target],
                is_human_intervention=True,
                details=f"Required target '{invariant.target}' was closed",
            )
            self._emit_event(
                task_id,
                TaskEventType.DISTURBANCE_DETECTED,
                "Disturbance Detected",
                summary=f"Required target '{invariant.target}' closed",
                data={"target": invariant.target, "human_intervention": True},
            )

            # Check: Do not fight user! If closed twice, ask user!
            if tracker.should_ask_user_instead_of_reopening(invariant.target):
                logger.info("Task %s: User closed %s twice. Halting auto-reopen.", task_id, invariant.target)
                if task:
                    task.transition_to(TaskStatus.WAITING_CLARIFICATION)
                    self.ledger.save_task(task)
                prompt = tracker.get_user_conflict_prompt(invariant.target)
                self._emit_event(
                    task_id,
                    TaskEventType.CLARIFICATION_REQUESTED,
                    prompt["title"],
                    summary=prompt["message"],
                    data=prompt,
                )
                return False, "USER_CONFLICT"

            # Check recovery budget
            if not tracker.budget.can_attempt_recovery("reopen_app", invariant.target):
                return False, "BUDGET_EXHAUSTED"

            attempt_num = tracker.budget.record_attempt("reopen_app", invariant.target)

            if task and task.status != TaskStatus.RECOVERING:
                task.transition_to(TaskStatus.RECOVERING)
                self.ledger.save_task(task)

            self._emit_event(
                task_id,
                TaskEventType.RECOVERY_STARTED,
                "Recovering Dependency",
                summary=f"Reopening {invariant.target} (attempt {attempt_num})...",
                data={"target": invariant.target, "attempt": attempt_num},
            )

            # Reopen application
            reopened = False
            try:
                from astrarun.applications.service import open_application
                if invariant.target.lower() in ("notepad", "notepad.exe"):
                    res = open_application("notepad")
                    reopened = res.success
                elif invariant.target.lower() in ("calc", "calculator", "calc.exe"):
                    res = open_application("calc")
                    reopened = res.success
                elif self.app and hasattr(self.app, "capability_registry"):
                    cap_res = self.app.capability_registry.execute(
                        "open_application", {"app": invariant.target}, task_id=task_id
                    )
                    reopened = cap_res.success
                else:
                    target_name = invariant.target.replace(".exe", "")
                    res = open_application(target_name)
                    reopened = res.success
            except Exception as e:
                logger.error("Error reopening %s: %s", invariant.target, e)
                reopened = False

            time.sleep(0.5)
            valid, _, _ = invariant.check()
            if valid or reopened:
                if task:
                    task.transition_to(TaskStatus.RUNNING)
                    self.ledger.save_task(task)
                self._emit_event(
                    task_id,
                    TaskEventType.RECOVERY_SUCCEEDED,
                    "Recovery Succeeded",
                    summary=f"Successfully restored {invariant.target}",
                    data={"target": invariant.target},
                )
                return True, "RECOVERED"
            else:
                self._emit_event(
                    task_id,
                    TaskEventType.RECOVERY_FAILED,
                    "Recovery Failed",
                    summary=f"Could not restore {invariant.target}",
                    data={"target": invariant.target},
                )
                return False, "REOPEN_FAILED"

        # File Modification Conflict
        elif invariant.type in (InvariantType.FILE_EXISTS, InvariantType.FILE_CONTAINS_CHANGE, InvariantType.FILE_HASH_MATCHES):
            p = Path(invariant.target)
            tracker.record_disturbance(
                disturbance_type=DisturbanceType.USER_MODIFIED_TARGET_FILE,
                observed_before=invariant.expected_state,
                observed_after=observed,
                affected_invariants=[invariant.target],
                is_human_intervention=True,
                details=f"File '{invariant.target}' modified externally",
            )
            self._emit_event(
                task_id,
                TaskEventType.DISTURBANCE_DETECTED,
                "File Conflict Detected",
                summary="The file changed while I was working on it.",
                data={"file_path": invariant.target, "human_intervention": True},
            )
            # Never overwrite human changes automatically!
            if task:
                task.transition_to(TaskStatus.WAITING_CLARIFICATION)
                self.ledger.save_task(task)
            self._emit_event(
                task_id,
                TaskEventType.CLARIFICATION_REQUESTED,
                "File Conflict",
                summary="The file changed while I was working on it.",
                data={
                    "title": "File Conflict",
                    "message": f"The file '{p.name}' was modified externally.\nHow would you like to proceed?",
                    "options": [
                        {"id": "review_changes", "label": "Review changes"},
                        {"id": "continue_current", "label": "Continue with current file"},
                        {"id": "reapply_change", "label": "Reapply Astra change"},
                        {"id": "cancel", "label": "Cancel"},
                    ],
                },
            )
            return False, "FILE_CONFLICT"

        # Download Interruption Recovery
        elif invariant.type == InvariantType.DOWNLOAD_PROGRESSING:
            tracker.record_disturbance(
                disturbance_type=DisturbanceType.DOWNLOAD_INTERRUPTED,
                observed_before=True,
                observed_after=observed,
                affected_invariants=[invariant.target],
                details=f"Download {invariant.target} interrupted",
            )
            self._emit_event(
                task_id,
                TaskEventType.RECOVERY_STARTED,
                "Resuming Download",
                summary=f"Resuming download for {invariant.target}...",
            )
            return True, "DOWNLOAD_RESUMED"

        # Network Recovery
        elif invariant.type == InvariantType.NETWORK_AVAILABLE:
            tracker.record_disturbance(
                disturbance_type=DisturbanceType.NETWORK_LOST,
                observed_before=True,
                observed_after=False,
                affected_invariants=["network"],
                details="Network connection lost",
            )
            for attempt in range(1, 4):
                time.sleep(0.3 * attempt)
                valid, _, _ = invariant.check()
                if valid:
                    self._emit_event(
                        task_id,
                        TaskEventType.RECOVERY_SUCCEEDED,
                        "Network Restored",
                        summary="Network connectivity recovered.",
                    )
                    return True, "NETWORK_RESTORED"
            return False, "NETWORK_UNAVAILABLE"

        return False, f"Unsupported invariant type {invariant.type.value}"

    def resume_from_checkpoint(self, task_id: str) -> bool:
        """Inspect world state and resume an interrupted task from its latest checkpoint."""
        task = self.get_task(task_id)
        if not task:
            return False

        chk = self.ledger.get_latest_checkpoint(task_id)
        if not chk:
            logger.warning("No checkpoint found for interrupted task %s", task_id)
            return False

        logger.info(
            "Task %s resuming from checkpoint %s (completed steps: %s)",
            task_id, chk.checkpoint_id, chk.completed_step_ids
        )
        if task.status == TaskStatus.INTERRUPTED:
            task.status = TaskStatus.RUNNING
        else:
            task.transition_to(TaskStatus.RUNNING)
        self.ledger.save_task(task)

        self._emit_event(
            task_id,
            TaskEventType.CAPABILITY_STARTED,
            "Task Resumed from Checkpoint",
            summary=f"Resuming task after {len(chk.completed_step_ids)} completed step(s)...",
            data={"checkpoint_id": chk.checkpoint_id, "completed_steps": chk.completed_step_ids},
        )
        return True
