"""Autonomous Closed-Loop Agent Execution Runner for AstraRun v0.11."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from astrarun.agent.graph import ExecutionGraph
from astrarun.agent.locking import ResourceLockManager, global_lock_manager
from astrarun.agent.models import (
    AgentTask,
    AgentTaskStatus,
    Observation,
    Plan,
    PlanStatus,
    PlanStep,
    ProgressMode,
    ReplanEvent,
    StepState,
    Verification,
)
from astrarun.agent.observer import MachineObserver, global_observer
from astrarun.agent.planner import GoalPlanner
from astrarun.agent.verifier import StepVerifier, global_step_verifier
from astrarun.capabilities.models import CapabilityResult
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.schema import InteractionTier, VerifierStrategy
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.agent.loop")


class AgentExecutionListener:
    """Callback interface for observing agent task execution events (used by HUD V2)."""

    def on_task_started(self, task: AgentTask) -> None:
        pass

    def on_task_progress(self, task: AgentTask, progress_pct: float, message: str) -> None:
        pass

    def on_step_started(self, task: AgentTask, step: PlanStep) -> None:
        pass

    def on_step_completed(self, task: AgentTask, step: PlanStep, verification: Verification) -> None:
        pass

    def on_step_failed(self, task: AgentTask, step: PlanStep, error: str) -> None:
        pass

    def on_replan(self, task: AgentTask, event: ReplanEvent) -> None:
        pass

    def on_task_completed(self, task: AgentTask) -> None:
        pass

    def on_task_failed(self, task: AgentTask, error: str) -> None:
        pass

    def on_task_cancelled(self, task: AgentTask) -> None:
        pass


class AgentExecutionEngine:
    """
    Executes the autonomous loop:
      UNDERSTAND GOAL -> PLAN -> ACT -> OBSERVE -> VERIFY -> REPLAN -> DONE
    """

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        observer: Optional[MachineObserver] = None,
        verifier: Optional[StepVerifier] = None,
        lock_manager: Optional[ResourceLockManager] = None,
        listener: Optional[AgentExecutionListener] = None,
    ):
        from astrarun.capabilities.registry import CapabilityRegistry
        self.registry = registry or CapabilityRegistry()
        self.observer = observer or global_observer
        self.verifier = verifier or global_step_verifier
        self.lock_manager = lock_manager or global_lock_manager
        self.planner = GoalPlanner(self.registry)
        self.listener = listener or AgentExecutionListener()

    def determine_resource_lock(self, step: PlanStep) -> Optional[str]:
        """Determine required resource lock for a step to prevent concurrency hazards."""
        cap_id = step.capability_id
        if "wifi" in cap_id:
            return "NETWORK:WIFI"
        if "battery_report" in cap_id or "file" in cap_id:
            path = step.arguments.get("output_path") or step.arguments.get("path")
            if path:
                return f"FILE:{path}"
        if "window" in cap_id or "type" in cap_id:
            hwnd = step.arguments.get("hwnd")
            if hwnd:
                return f"WINDOW:{hwnd}"
        return None

    def execute_goal(self, prompt: str) -> AgentTask:
        """Entrypoint: parse goal from prompt, construct plan, and execute closed loop."""
        goal = self.planner.parse_goal(prompt)
        plan = self.planner.create_plan(goal)

        task = AgentTask(
            goal=goal,
            plan=plan,
            status=AgentTaskStatus.PENDING,
        )

        return self.run_task(task)

    def run_task(self, task: AgentTask) -> AgentTask:
        """Run execution graph until all steps complete, fail, or task is cancelled."""
        task.status = AgentTaskStatus.RUNNING
        task.started_at = time.time()
        self.listener.on_task_started(task)

        graph = ExecutionGraph(task.plan)
        task.progress_pct = graph.compute_progress_pct()

        logger.info("Starting execution of task %s (%d steps)", task.task_id, len(task.plan.steps))

        try:
            while not graph.is_complete():
                if task.cancellation_requested:
                    logger.info("Task %s cancellation requested.", task.task_id)
                    task.status = AgentTaskStatus.CANCELLED
                    self._cancel_remaining_steps(task)
                    self.listener.on_task_cancelled(task)
                    break

                ready_steps = graph.get_ready_steps()
                if not ready_steps:
                    if graph.has_failures():
                        break
                    # If steps still pending but none ready, check for deadlock
                    logger.warning("No ready steps found in plan graph. Deadlock or dependency stall.")
                    task.status = AgentTaskStatus.FAILED
                    task.error = "Unsatisfiable dependencies or deadlock in plan."
                    break

                for step in ready_steps:
                    if task.cancellation_requested:
                        break

                    success = self._execute_step_with_closed_loop(task, step, graph)
                    if not success:
                        # Attempt runtime replanning or fail
                        replan_ok = self._attempt_replan(task, step, graph)
                        if not replan_ok:
                            task.status = AgentTaskStatus.FAILED
                            task.error = f"Step '{step.step_id}' failed: {step.error}"
                            self.listener.on_step_failed(task, step, step.error or "Unknown step failure")
                            break

                task.progress_pct = graph.compute_progress_pct()
                self.listener.on_task_progress(task, task.progress_pct, f"Progress {task.progress_pct}%")

                if task.status == AgentTaskStatus.FAILED:
                    break

            if task.status == AgentTaskStatus.RUNNING:
                if not graph.has_failures():
                    task.status = AgentTaskStatus.COMPLETED
                    task.progress_pct = 100.0
                    task.completed_at = time.time()
                    self.listener.on_task_completed(task)
                    logger.info("Task %s completed successfully in %.2fs", task.task_id, task.completed_at - (task.started_at or task.completed_at))
                else:
                    task.status = AgentTaskStatus.FAILED
                    self.listener.on_task_failed(task, task.error or "Execution graph encountered errors")

        finally:
            # Always ensure all resource locks are cleanly released
            self.lock_manager.release_all_for_task(task.task_id)

        return task

    def _execute_step_with_closed_loop(
        self,
        task: AgentTask,
        step: PlanStep,
        graph: ExecutionGraph,
    ) -> bool:
        """Execute single step through: ACT -> OBSERVE -> VERIFY (with retries)."""
        task.current_step_id = step.step_id
        step.state = StepState.RUNNING
        step.started_at = time.time()
        self.listener.on_step_started(task, step)

        lock_key = self.determine_resource_lock(step)
        if lock_key:
            acquired = self.lock_manager.acquire_lock(lock_key, task.task_id, step.step_id, timeout_s=5.0)
            if not acquired:
                step.state = StepState.BLOCKED
                step.error = f"Failed to acquire resource lock '{lock_key}'"
                return False

        try:
            while step.retry_count <= step.max_retries:
                # 1. ACT
                t_act_start = time.perf_counter()
                result = self.registry.execute(
                    capability_id=step.capability_id,
                    arguments=step.arguments,
                    task_id=task.task_id,
                )
                step.result = result

                # 2. OBSERVE
                step.state = StepState.VERIFYING
                observation = self.observer.capture_observation(
                    step_id=step.step_id,
                    raw_output=result.data,
                    tier=step.interaction_tier,
                )
                step.observation = observation
                task.observations.append(observation)

                # 3. VERIFY
                verification = self.verifier.verify(step, result, context=task.context)
                step.verification = verification

                if verification.verified:
                    step.state = StepState.COMPLETED
                    step.completed_at = time.time()
                    step.duration_ms = (time.perf_counter() - t_act_start) * 1000.0

                    # Update context with any updates emitted by capability
                    for upd in result.context_updates:
                        task.context[upd.get("type", "general")] = upd

                    self.listener.on_step_completed(task, step, verification)
                    return True

                # Step not verified; check for retry
                step.retry_count += 1
                if step.retry_count <= step.max_retries:
                    logger.warning(
                        "Step '%s' verification failed ('%s'). Retrying (%d/%d)...",
                        step.step_id,
                        verification.message,
                        step.retry_count,
                        step.max_retries,
                    )
                    time.sleep(0.3 * step.retry_count)

            # All retries exhausted
            step.state = StepState.FAILED
            step.error = verification.message or "Verification failed after maximum retries"
            return False

        finally:
            if lock_key:
                self.lock_manager.release_lock(lock_key, task.task_id)

    def _attempt_replan(self, task: AgentTask, failed_step: PlanStep, graph: ExecutionGraph) -> bool:
        """Attempt dynamic replanning or graceful degradation for a failed step."""
        logger.info("Evaluating dynamic replan options for failed step: %s", failed_step.step_id)

        # Case 1: Tier C UIA typing failed -> Replan by inserting focus step and degrading to Tier D
        if failed_step.capability_id == "type_into_window" and failed_step.interaction_tier == InteractionTier.TIER_C_UI_AUTOMATION:
            logger.info("Degrading UI automation text injection to Tier D keyboard focus and input.")
            replan_event = ReplanEvent(
                trigger_step_id=failed_step.step_id,
                reason="Tier C UI Automation typing failed; falling back to Tier D SendInput",
                old_plan_version=task.plan.version,
                new_plan_version=task.plan.version + 1,
            )
            failed_step.interaction_tier = InteractionTier.TIER_D_INPUT_EMULATION
            failed_step.state = StepState.PENDING
            failed_step.retry_count = 0
            task.replans.append(replan_event)
            self.listener.on_replan(task, replan_event)
            return True

        return False

    def _cancel_remaining_steps(self, task: AgentTask) -> None:
        """Mark all uncompleted steps as CANCELLED."""
        for step in task.plan.steps:
            if step.state in (StepState.PENDING, StepState.READY, StepState.RUNNING, StepState.WAITING):
                step.state = StepState.CANCELLED
