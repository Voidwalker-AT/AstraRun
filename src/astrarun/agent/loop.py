"""Autonomous Closed-Loop Agent Execution Runner for AstraRun agent runtime."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

from astrarun.agent.graph import ExecutionGraph
from astrarun.agent.locking import ResourceLockManager, global_lock_manager
from astrarun.agent.models import (
    AgentTask,
    AgentTaskStatus,
    GoalVerificationStatus,
    Observation,
    Plan,
    PlanRevision,
    PlanStatus,
    PlanStep,
    ProgressMode,
    ReplanEvent,
    StepState,
    Verification,
)
from astrarun.agent.observer import MachineObserver, global_observer
from astrarun.agent.planner import GoalPlanner
from astrarun.agent.validator import PlanQualityValidator
from astrarun.agent.verifier import GoalVerifier, StepVerifier, global_goal_verifier, global_step_verifier
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
      UNDERSTAND GOAL -> VALIDATE PLAN -> ACT -> OBSERVE -> VERIFY -> REPLAN -> VERIFY GOAL -> DONE
    """

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        observer: Optional[MachineObserver] = None,
        verifier: Optional[StepVerifier] = None,
        goal_verifier: Optional[GoalVerifier] = None,
        validator: Optional[PlanQualityValidator] = None,
        lock_manager: Optional[ResourceLockManager] = None,
        listener: Optional[AgentExecutionListener] = None,
        execution_broker: Optional[Any] = None,
        model_service: Optional[Any] = None,
    ):
        from astrarun.capabilities.registry import CapabilityRegistry
        self.registry = registry or CapabilityRegistry()
        if execution_broker is None:
            try:
                from astrarun.security.execution_broker import ExecutionBroker
                self.execution_broker = ExecutionBroker(capability_registry=self.registry)
            except Exception as err:
                raise RuntimeError(f"SECURITY_VIOLATION: AgentExecutionEngine requires an active ExecutionBroker: {err}")
        else:
            self.execution_broker = execution_broker
        if model_service is None:
            try:
                from astrarun.cognition.service import ModelService
                self.model_service = ModelService.get_instance()
            except Exception:
                self.model_service = None
        else:
            self.model_service = model_service
        self.observer = observer or global_observer
        self.verifier = verifier or global_step_verifier
        self.goal_verifier = goal_verifier or global_goal_verifier
        self.validator = validator or PlanQualityValidator(self.registry)
        self.lock_manager = lock_manager or global_lock_manager
        self.planner = GoalPlanner(self.registry, model_service=model_service)
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
        """Entrypoint: parse goal from prompt, construct plan, validate, and execute closed loop."""
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

        # 1. Validate Plan Quality (Quality Gate)
        val_result = self.validator.validate_plan(task.plan)
        if not val_result.is_valid:
            logger.error("Plan validation failed for task %s: %s", task.task_id, val_result.issues)
            task.status = AgentTaskStatus.FAILED
            task.error = f"Invalid plan: {'; '.join(val_result.issues)}"
            self.listener.on_task_failed(task, task.error)
            return task

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
                        # Attempt runtime replanning
                        replan_ok = self._attempt_replan(task, step, graph)
                        if replan_ok:
                            # Re-instantiate execution graph with newly inserted replanned steps
                            graph = ExecutionGraph(task.plan)
                            break
                        else:
                            task.status = AgentTaskStatus.FAILED
                            task.error = f"Step '{step.step_id}' failed: {step.error}"
                            self.listener.on_step_failed(task, step, step.error or "Unknown step failure")
                            break

                task.progress_pct = graph.compute_progress_pct()
                self.listener.on_task_progress(task, task.progress_pct, f"Progress {task.progress_pct}%")

                if task.status == AgentTaskStatus.FAILED:
                    break

            # 2. Final Goal-Level Empirical Verification
            if task.status == AgentTaskStatus.RUNNING:
                if not graph.has_failures():
                    last_step = task.plan.steps[-1] if task.plan.steps else None
                    last_data = last_step.result.data if (last_step and last_step.result) else {}
                    goal_ver = self.goal_verifier.verify_goal(task.goal, task.plan, last_data)
                    task.goal_verification = goal_ver

                    if goal_ver.completed:
                        task.status = AgentTaskStatus.COMPLETED
                        task.progress_pct = 100.0
                        task.completed_at = time.time()
                        self.listener.on_task_completed(task)
                        logger.info("Task %s verified & completed successfully in %.2fs", task.task_id, task.completed_at - (task.started_at or task.completed_at))
                    else:
                        task.status = AgentTaskStatus.FAILED
                        task.error = goal_ver.message
                        self.listener.on_task_failed(task, task.error)
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
        graph.resolve_step_arguments(step, getattr(task, "context", {}))

        lock_key = self.determine_resource_lock(step)
        if lock_key:
            acquired = self.lock_manager.acquire_lock(lock_key, task.task_id, step.step_id, timeout_s=5.0)
            if not acquired:
                step.state = StepState.BLOCKED
                step.error = f"Failed to acquire resource lock '{lock_key}'"
                return False

        try:
            while step.retry_count <= step.max_retries:
                # 1. ACT (mandatorily governed via ExecutionBroker)
                t_act_start = time.perf_counter()
                if not self.execution_broker:
                    raise RuntimeError("SECURITY_VIOLATION: ExecutionBroker is absent; execution prohibited.")

                from astrarun.security.execution_broker import ActionCategory, ActionProposal
                from astrarun.capabilities.models import CapabilityResult
                prop = ActionProposal(
                    category=ActionCategory.ACT,
                    capability_id=step.capability_id,
                    parameters=step.arguments,
                    task_id=task.task_id,
                    source="agent_planner",
                )
                broker_res = self.execution_broker.execute(prop)
                if broker_res.blocked:
                    result = CapabilityResult(
                        capability=step.capability_id,
                        success=False,
                        message=f"ActionGate BLOCKED step '{step.capability_id}': {broker_res.message}",
                        data={"blocked": True, "verdict": "BLOCK"},
                        latency_ms=broker_res.duration_ms,
                    )
                else:
                    result = CapabilityResult(
                        capability=step.capability_id,
                        success=broker_res.success,
                        message=broker_res.message,
                        data=broker_res.data,
                        latency_ms=broker_res.duration_ms,
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

        # 1. Fallback tier degradation (e.g. UIA typing -> SendInput typing)
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

        # 2. Dynamic DAG Replanning via GoalPlanner
        revision = self.planner.replan(task, failed_step, failed_step.observation)
        if revision:
            # Validate updated plan before execution (Safety invariant)
            val_res = self.validator.validate_plan(task.plan)
            if not val_res.is_valid:
                logger.error("Replanned DAG failed quality validation: %s", val_res.issues)
                return False

            replan_event = ReplanEvent(
                trigger_step_id=failed_step.step_id,
                reason=revision.reason,
                old_plan_version=revision.previous_plan_version,
                new_plan_version=revision.new_plan_version,
                modifications={"added_steps": revision.added_steps, "removed_steps": revision.removed_steps},
            )
            task.replans.append(replan_event)
            self.listener.on_replan(task, replan_event)
            logger.info("Dynamic replan successful. Inserted replacement steps: %s", revision.added_steps)
            return True

        return False

    def _cancel_remaining_steps(self, task: AgentTask) -> None:
        """Mark all uncompleted steps as CANCELLED."""
        for step in task.plan.steps:
            if step.state in (StepState.PENDING, StepState.READY, StepState.RUNNING, StepState.WAITING):
                step.state = StepState.CANCELLED
