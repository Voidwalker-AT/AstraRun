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
        from astrarun.hermes.exploration import HermesExplorationEngine
        self.exploration_engine = HermesExplorationEngine(model_service=self.model_service)
        from astrarun.recovery.engine import IntelligentFallbackEngine
        self.fallback_engine = IntelligentFallbackEngine(capability_registry=self.registry)

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
        from astrarun.core.telemetry import CausalTelemetry, CausalEventType, compute_hash
        telem = CausalTelemetry.get_instance()

        goal = self.planner.parse_goal(prompt)
        if goal.contract:
            telem.register_contract(goal.contract)

        telem.emit(
            event_type=CausalEventType.GOAL_INTERPRETED.value,
            component="GoalPlanner",
            data={
                "goal_type": getattr(goal, "goal_type", "CUSTOM"),
                "target": getattr(goal, "target", ""),
                "description": getattr(goal, "description", ""),
            },
            input_hash=compute_hash(prompt),
            output_hash=compute_hash(getattr(goal, "raw_prompt", str(goal))),
        )

        plan = self.planner.create_plan(goal)
        step_caps = [s.capability_id for s in plan.steps] if (plan and plan.steps) else []
        telem.emit(
            event_type=CausalEventType.PLAN_CREATED.value,
            component="GoalPlanner",
            data={"step_count": len(step_caps), "capabilities": step_caps},
            output_hash=compute_hash(step_caps),
        )

        task = AgentTask(
            goal=goal,
            plan=plan,
            status=AgentTaskStatus.PENDING,
            contract=goal.contract,
        )

        return self.run_task(task)

    def run_task(self, task: AgentTask) -> AgentTask:
        """Run execution graph until all steps complete, fail, or task is cancelled."""
        from astrarun.core.telemetry import CausalTelemetry
        telem = CausalTelemetry.get_instance()
        telem.set_task_context(task.task_id)

        task.status = AgentTaskStatus.RUNNING
        task.started_at = time.time()
        if not task.contract and getattr(task.goal, "contract", None):
            task.contract = task.goal.contract
        if not task.contract and task.goal:
            raw_p = getattr(task.goal, "raw_prompt", "") or getattr(task.goal, "intent", "")
            if raw_p:
                try:
                    task.contract = self.planner.extract_goal_contract(raw_p)
                    task.goal.contract = task.contract
                except Exception:
                    pass
        if task.contract:
            telem.register_contract(task.contract, task_id=task.task_id)
        self.listener.on_task_started(task)

        # 0. Pre-Task Ambient Observation Snapshot (Hierarchical Perception)
        try:
            from astrarun.computer_use.observation import DesktopObserver
            initial_state = DesktopObserver.get_instance().observe(task_id=task.task_id)
            task.context["initial_world_state_hash"] = initial_state.compute_state_hash()
            task.context["initial_world_state"] = initial_state.to_dict()
        except Exception as ex:
            logger.debug("Initial world state capture omitted: %s", ex)

        # 1. Validate Plan Quality (Quality Gate & Information Loss Check)
        val_result = self.validator.validate_plan(task.plan, goal_contract=task.contract)
        if not val_result.is_valid:
            logger.error("Plan validation failed for task %s: %s", task.task_id, val_result.issues)
            task.status = AgentTaskStatus.FAILED
            task.error = f"Invalid plan: {'; '.join(val_result.issues)}"
            self.listener.on_task_failed(task, task.error)
            return task

        graph = ExecutionGraph(task.plan)
        task.progress_pct = graph.compute_progress_pct()

        # Epistemic Uncertainty Quantification & Autonomous Exploration (Hermes)
        target_app = None
        for step in task.plan.steps:
            cand = step.arguments.get("app_name") or step.arguments.get("app")
            if not cand and isinstance(step.arguments.get("target"), str):
                cand = step.arguments.get("target")
            if isinstance(cand, str) and cand.strip():
                target_app = cand.strip()
                break
        if not target_app and task.goal and hasattr(task.goal, "raw_prompt"):
            import re
            m = re.search(r"\b(?:open|launch)\s+([a-zA-Z0-9_\-\+]+)\b", task.goal.raw_prompt, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                if cand.lower() not in ('a', 'the', 'an', 'file', 'document', 'url', 'wifi', 'it', 'windows', 'program', 'script', 'code', 'python'):
                    target_app = cand

        if target_app:
            assessment = self.exploration_engine.assess_epistemic_state(target_app)
            task.context["hermes_epistemic_assessment"] = {
                "target_entity": assessment.target_entity_name,
                "decision_mode": assessment.decision_mode.value,
                "confidence_score": assessment.confidence_score,
                "confidence_band": assessment.confidence_band.value,
                "known_affordances": assessment.known_affordances,
                "uncertain_actions": assessment.uncertain_actions,
                "rationale": assessment.rationale,
            }
            logger.info(
                "Task %s Hermes Epistemic Assessment for '%s': mode=%s, confidence=%.2f (%s)",
                task.task_id,
                target_app,
                assessment.decision_mode.value,
                assessment.confidence_score,
                assessment.confidence_band.value,
            )

            # Record DecisionContextSnapshot at task inception
            try:
                from astrarun.computer_use.observation.frame import DecisionContextSnapshot
                dec_snapshot = DecisionContextSnapshot(
                    decision_id=f"dec_init_{int(time.time()*1000)}",
                    frame_id=task.context.get("initial_world_state_hash", "frame_0"),
                    goal=getattr(task.goal, "raw_prompt", str(task.goal)),
                    remaining_postconditions=[p.description for p in getattr(task.contract, "acceptance_predicates", [])] if getattr(task, "contract", None) else [],
                    current_plan=[{"id": s.step_id, "cap": s.capability_id} for s in task.plan.steps],
                    completed_steps=[],
                    failed_attempts=[],
                    bounded_action_history=[],
                    target_identity=target_app,
                    relevant_structural_ui=[],
                    relevant_visual_observations=[],
                    dialog_state={},
                    resource_ownership={},
                    user_takeover_state=False,
                    available_generic_capabilities=[c.id for c in self.registry.list_all()] if hasattr(self.registry, "list_all") else [],
                    hermes_experience={"affordances": assessment.known_affordances},
                    epistemic_uncertainty={"confidence": assessment.confidence_score, "band": assessment.confidence_band.value},
                    decision_mode=assessment.decision_mode.value,
                )
                task.context["initial_decision_snapshot"] = dec_snapshot.to_dict()
            except Exception as dec_ex:
                logger.debug("DecisionContextSnapshot capture exception: %s", dec_ex)

            # If UNCERTAIN or UNKNOWN, formulate and execute bounded diagnostic probe
            if assessment.decision_mode.value == "EXPLORE":
                logger.info(
                    "Entering EXPLORE mode for unfamiliar entity '%s'. Formulating diagnostic experiment...",
                    target_app,
                )
                experiment = self.exploration_engine.formulate_experiment(
                    assessment=assessment,
                    task_context=task.context,
                    goal_prompt=getattr(task.goal, "raw_prompt", str(task.goal)),
                    task_id=task.task_id,
                )
                probe_res = self.exploration_engine.execute_experiment(
                    experiment=experiment,
                    execution_broker=self.execution_broker,
                    task_id=task.task_id,
                )
                task.context["hermes_exploration_outcome"] = probe_res

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
                        # 3. Post-Task Resource & Dialog Cleanliness Check (Requirement 6, 7, 8)
                        # Cleanup failures and unverified residue must block COMPLETED.
                        cleanup_failed = False
                        cleanup_error = ""
                        try:
                            from astrarun.computer_use.observation import DesktopObserver
                            final_state = DesktopObserver.get_instance().observe(task_id=task.task_id)
                            needs_cleanup = True
                            try:
                                needs_cleanup = bool(final_state.has_astra_debris(task_id=task.task_id))
                            except Exception:
                                needs_cleanup = True
                            if needs_cleanup:
                                logger.info(
                                    "Task %s completed goals with residual Astra-owned resources; initiating cleanup...",
                                    task.task_id,
                                )
                            from astrarun.tasks.resource_ledger import AstraResourceLedger
                            from astrarun.tasks.models import TaskStatus
                            try:
                                status_for_cleanup = TaskStatus.COMPLETED
                            except Exception:
                                status_for_cleanup = "COMPLETED"
                            report = AstraResourceLedger.get_instance().cleanup_task_resources(
                                task.task_id, status_for_cleanup
                            )
                            time.sleep(0.3)
                            post_clean = DesktopObserver.get_instance().observe(task_id=task.task_id)
                            debris_remains = bool(post_clean.has_astra_debris(task_id=task.task_id))
                            report_ok = bool(report.get("clean", False)) and not debris_remains
                            task.context["cleanup_report"] = report
                            if not report_ok:
                                cleanup_failed = True
                                cleanup_error = (
                                    f"RESIDUAL_LEAK: cleanup unverified "
                                    f"(process_cleaned_up={report.get('process_cleaned_up')}, "
                                    f"remaining_active={report.get('remaining_active_resources')}, "
                                    f"debris_remains={debris_remains}, "
                                    f"exception={report.get('cleanup_exception')})."
                                )
                        except Exception as ex:
                            # Swallowing cleanup exceptions and still reporting PASS is forbidden.
                            cleanup_failed = True
                            cleanup_error = f"RESIDUAL_LEAK: cleanup verification raised exception: {ex}"

                        if cleanup_failed:
                            task.status = AgentTaskStatus.FAILED
                            task.error = cleanup_error
                            self.listener.on_task_failed(task, task.error)
                            return task

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
            if task.goal_verification is None:
                last_step = task.plan.steps[-1] if task.plan.steps else None
                last_data = last_step.result.data if (last_step and last_step.result) else {}
                task.goal_verification = self.goal_verifier.verify_goal(task.goal, task.plan, last_data)

            # Guaranteed cleanup of transient test/task resources on failure or cancellation (Req 8)
            if task.status in (AgentTaskStatus.FAILED, AgentTaskStatus.CANCELLED):
                try:
                    from astrarun.tasks.resource_ledger import AstraResourceLedger
                    from astrarun.tasks.models import TaskStatus
                    try:
                        status_for_cleanup = TaskStatus.CANCELLED if task.status == AgentTaskStatus.CANCELLED else TaskStatus.FAILED
                    except Exception:
                        status_for_cleanup = "CANCELLED" if task.status == AgentTaskStatus.CANCELLED else "FAILED"
                    report = AstraResourceLedger.get_instance().cleanup_task_resources(
                        task.task_id, status_for_cleanup
                    )
                    task.context.setdefault("cleanup_report", report)
                except Exception as cleanup_err:
                    # Record cleanup failure truthfully; never claim clean on exception.
                    task.context["cleanup_report"] = {
                        "cleanup_exception": str(cleanup_err),
                        "clean": False,
                        "verdict": "FAIL",
                        "resources_owned": True,
                        "process_cleanup_required": True,
                        "process_residue_measured": False,
                        "window_residue_measured": False,
                        "ledger_residue_measured": False,
                        "process_cleaned_up": False,
                        "cleanup_executed": True,
                        "orphaned_processes": None,
                        "orphaned_windows": None,
                        "active_ledger_resources": None,
                    }
            # Always ensure all resource locks are cleanly released
            self.lock_manager.release_all_for_task(task.task_id)

            # Finalize Computer Use trace
            try:
                from astrarun.computer_use.observation.frame import ComputerUseTraceRecorder
                final_rec = ComputerUseTraceRecorder.get_recorder(task.task_id)
                final_status = getattr(task.status, "value", str(task.status))
                final_rec.finalize_trace(verdict=final_status, notes=task.error or "")
            except Exception as final_rec_err:
                logger.debug("Finalize trace failed: %s", final_rec_err)

        return task


    def _execute_step_with_closed_loop(
        self,
        task: AgentTask,
        step: PlanStep,
        graph: Optional[ExecutionGraph] = None,
    ) -> bool:
        """Execute single step through: ACT -> OBSERVE -> VERIFY (with retries)."""
        if graph is None:
            graph = ExecutionGraph(task.plan)
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
                # 1. PRE-OBSERVATION & ADAPTIVE DIVERGENCE CHECK (Req 4, 12)
                t_act_start = time.perf_counter()
                pre_world_state = None
                try:
                    from astrarun.computer_use.observation import DesktopObserver
                    pre_world_state = DesktopObserver.get_instance().observe(task_id=task.task_id)
                except Exception as ex:
                    logger.debug("Pre-observation skipped: %s", ex)

                # Frame-by-frame Computer Use Trace Recorder (F0-24A.2B)
                trace_rec = None
                pre_frame = None
                dec_rec = None
                try:
                    from astrarun.computer_use.observation.frame import (
                        ComputerUseTraceRecorder,
                        DecisionRecord,
                    )
                    trace_rec = ComputerUseTraceRecorder.get_recorder(task.task_id)
                    should_capture_screen = bool(task.context.get("capture_screenshots", False))
                    target_q = step.arguments.get("app_name") or step.arguments.get("window") or step.arguments.get("app")
                    art_q = step.arguments.get("path") or step.arguments.get("output_path") or step.arguments.get("file_path")
                    goal_id_str = getattr(task.goal, "goal_id", getattr(task.goal, "raw_prompt", str(task.goal)))
                    pre_frame = trace_rec.capture_live_frame(
                        step_id=step.step_id,
                        goal_id=goal_id_str,
                        expected_app=target_q,
                        artifact_path=art_q,
                        capture_screenshot=should_capture_screen,
                    )
                    dec_rec = DecisionRecord(
                        decision_id=f"dec_{step.step_id}_{int(time.time() * 1000)}",
                        frame_id=pre_frame.frame_id,
                        task_id=task.task_id,
                        timestamp=time.time(),
                        chosen_capability=step.capability_id,
                        parameters=step.arguments,
                        rationale=f"Execute step {step.step_id}: {step.description}",
                        confidence=0.95,
                    )
                    trace_rec.record_decision(dec_rec)
                except Exception as rec_ex:
                    logger.debug("Trace recorder pre-step exception: %s", rec_ex)

                # Adaptive Check 1: User physical takeover
                if pre_world_state and pre_world_state.user_takeover_active:
                    logger.warning("Physical takeover active; pausing step %s.", step.step_id)
                    step.state = StepState.BLOCKED
                    step.error = "Physical user input detected. Step paused."
                    return False

                # Adaptive Check 2: Target window minimized or lost focus for UI interaction
                target_query = step.arguments.get("app_name") or step.arguments.get("window") or step.arguments.get("app")
                if pre_world_state:
                    w_obs = None
                    # Priority 1: Check task's actively owned resource window from ledger
                    if task and task.task_id:
                        try:
                            from astrarun.tasks.resource_ledger import AstraResourceLedger
                            task_res = AstraResourceLedger.get_instance().list_resources_for_task(task.task_id)
                            for r in reversed(task_res):
                                if r.hwnd:
                                    for w in pre_world_state.visible_windows:
                                        if w.hwnd == r.hwnd:
                                            w_obs = w
                                            break
                                    if w_obs:
                                        break
                        except Exception:
                            pass

                    # Priority 2: Match by target query
                    if not w_obs and target_query:
                        w_obs = pre_world_state.find_window_by_app(target_query)
                        if not w_obs:
                            for w in pre_world_state.visible_windows:
                                title_match = bool(w.title and target_query.lower() in w.title.lower())
                                app_match = bool(getattr(w, "app_name", None) and target_query.lower() in w.app_name.lower())
                                if title_match or app_match:
                                    w_obs = w
                                    break

                    if w_obs and w_obs.is_minimized:
                        logger.info("Target window (HWND %d) is minimized; restoring to foreground...", w_obs.hwnd)
                        try:
                            from astrarun.ui.presentation import force_foreground_activation
                            import ctypes
                            ctypes.windll.user32.ShowWindow(w_obs.hwnd, 9)  # SW_RESTORE
                            force_foreground_activation(w_obs.hwnd)
                            time.sleep(0.3)
                        except Exception as ex:
                            logger.debug("Adaptive window restore error: %s", ex)

                # 2. ACT (mandatorily governed via ExecutionBroker)
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

                # 3. POST-OBSERVATION
                step.state = StepState.VERIFYING
                post_world_state = None
                try:
                    from astrarun.computer_use.observation import DesktopObserver
                    post_world_state = DesktopObserver.get_instance().observe(task_id=task.task_id)
                except Exception as ex:
                    logger.debug("Post-observation skipped: %s", ex)

                observation = self.observer.capture_observation(
                    step_id=step.step_id,
                    raw_output=result.data,
                    tier=step.interaction_tier,
                )
                step.observation = observation
                task.observations.append(observation)

                # 4. VERIFY & RECORD FULL TRACE (Req 4)
                ctx = dict(task.context or {})
                if getattr(task, "contract", None):
                    ctx["contract"] = task.contract
                if getattr(task, "plan", None) and getattr(task.plan, "steps", None):
                    ctx["is_terminal_step"] = (step.step_id == task.plan.steps[-1].step_id)
                verification = self.verifier.verify(step, result, context=ctx)
                step.verification = verification

                # Record execution trace entry with before/after state
                trace_entry = {
                    "step_id": step.step_id,
                    "capability_id": step.capability_id,
                    "arguments": step.arguments,
                    "observation_before": {
                        "state_hash": pre_world_state.compute_state_hash() if pre_world_state else None,
                        "fg_window": pre_world_state.foreground_window.title if (pre_world_state and pre_world_state.foreground_window) else None,
                        "visible_windows": len(pre_world_state.visible_windows) if pre_world_state else 0,
                        "dialogs": [d.title for d in pre_world_state.dialogs] if pre_world_state else [],
                    },
                    "expected_transition": step.description,
                    "selected_action": step.capability_id,
                    "broker_verdict": "BLOCK" if broker_res.blocked else "ALLOW",
                    "execution_result": {
                        "success": result.success,
                        "message": result.message,
                        "data": result.data,
                    },
                    "observation_after": {
                        "state_hash": post_world_state.compute_state_hash() if post_world_state else None,
                        "fg_window": post_world_state.foreground_window.title if (post_world_state and post_world_state.foreground_window) else None,
                        "visible_windows": len(post_world_state.visible_windows) if post_world_state else 0,
                        "dialogs": [d.title for d in post_world_state.dialogs] if post_world_state else [],
                    },
                    "transition_verified": verification.verified,
                }
                task.execution_traces.append(trace_entry)

                if trace_rec:
                    try:
                        from astrarun.computer_use.observation.frame import (
                            ActionRecord,
                            StateTransitionRecord,
                        )
                        should_capture_screen = bool(task.context.get("capture_screenshots", False))
                        target_q = step.arguments.get("app_name") or step.arguments.get("window") or step.arguments.get("app")
                        art_q = step.arguments.get("path") or step.arguments.get("output_path") or step.arguments.get("file_path")
                        goal_id_str = getattr(task.goal, "goal_id", getattr(task.goal, "raw_prompt", str(task.goal)))
                        post_frame = trace_rec.capture_live_frame(
                            step_id=step.step_id,
                            goal_id=goal_id_str,
                            expected_app=target_q,
                            artifact_path=art_q,
                            capture_screenshot=should_capture_screen,
                        )
                        act_id = f"act_{step.step_id}_{int(time.time() * 1000)}"
                        act_rec = ActionRecord(
                            action_id=act_id,
                            decision_id=dec_rec.decision_id if dec_rec else "",
                            pre_frame_id=pre_frame.frame_id if pre_frame else "",
                            capability=step.capability_id,
                            parameters=step.arguments,
                            target_identity=target_q or "",
                            mechanism="ExecutionBroker",
                            dispatch_timestamp=t_act_start,
                            completion_timestamp=time.perf_counter(),
                            broker_verdict="BLOCK" if broker_res.blocked else "ALLOW",
                            os_return_status="SUCCESS" if result.success else "FAILURE",
                            action_result=result.data,
                            post_frame_id=post_frame.frame_id if post_frame else "",
                        )
                        trace_rec.record_action(act_rec)
                        trans_rec = StateTransitionRecord(
                            transition_id=f"trans_{step.step_id}_{int(time.time() * 1000)}",
                            pre_frame_id=pre_frame.frame_id if pre_frame else "",
                            action_id=act_id,
                            post_frame_id=post_frame.frame_id if post_frame else "",
                            expected_transition=step.description,
                            observed_transition=result.message,
                            matched=bool(verification.verified),
                            divergence_notes=None if verification.verified else f"Verification failed: {verification.error}",
                        )
                        trace_rec.record_transition(trans_rec)

                        # Ingest into Hermes experiential memory
                        try:
                            from astrarun.memory.service import MemoryService
                            from astrarun.hermes.models import (
                                EntityNode, EntityType, AffordanceEdge,
                                EpistemicStatus, StateTransitionRecord as HermesTransRec
                            )
                            from astrarun.hermes.provenance import HermesProvenance
                            hermes_store = MemoryService.get_instance().hermes
                            app_identity = target_q or (pre_world_state.foreground_window.title if (pre_world_state and pre_world_state.foreground_window) else None)
                            if app_identity and hermes_store:
                                ent = hermes_store.find_entity_by_name(app_identity)
                                if not ent:
                                    ent = EntityNode.create(
                                        entity_type=EntityType.APPLICATION,
                                        name=app_identity,
                                        class_name=pre_world_state.foreground_window.class_name if (pre_world_state and pre_world_state.foreground_window) else None,
                                        env_hash=HermesProvenance.compute_env_hash(),
                                    )
                                    hermes_store.upsert_entity(ent)
                                aff = hermes_store.find_affordance(ent.entity_id, step.capability_id)
                                if not aff:
                                    aff = AffordanceEdge.create(
                                        entity_id=ent.entity_id,
                                        action_name=step.capability_id,
                                        capability_id=step.capability_id,
                                        confidence=0.20,
                                        status=EpistemicStatus.HYPOTHESIS,
                                    )
                                    hermes_store.upsert_affordance(aff)
                                h_trans = HermesTransRec.create(
                                    affordance_id=aff.affordance_id,
                                    pre_state_hash=pre_world_state.compute_state_hash() if pre_world_state else "pre_state",
                                    action_payload=step.arguments,
                                    post_state_hash=post_world_state.compute_state_hash() if post_world_state else "post_state",
                                    expected_delta={"description": step.description},
                                    observed_delta={"success": result.success, "message": result.message},
                                    transition_verified=bool(verification.verified),
                                    latency_ms=(time.perf_counter() - t_act_start) * 1000.0,
                                    trace_id=task.task_id,
                                    pre_frame_id=pre_frame.frame_id if pre_frame else "pre_frame",
                                    post_frame_id=post_frame.frame_id if post_frame else "post_frame",
                                )
                                hermes_store.record_transition(h_trans)
                        except Exception as h_err:
                            logger.debug("Hermes experiential memory ingestion exception: %s", h_err)
                    except Exception as rec_ex:
                        logger.debug("Trace recorder post-step exception: %s", rec_ex)

                if verification.verified:
                    step.state = StepState.COMPLETED
                    step.completed_at = time.time()
                    step.duration_ms = (time.perf_counter() - t_act_start) * 1000.0

                    # Update contract constraints & predicates
                    if getattr(task, "contract", None):
                        from astrarun.agent.models import ConstraintStatus, PredicateStatus
                        for pred in task.contract.acceptance_predicates:
                            if pred.predicate_type.value in step.satisfies_predicates:
                                pred.status = PredicateStatus.SATISFIED
                        if any(e in ("CREATES_FILE", "WRITES_CONTENT") for e in step.declared_effects):
                            for c in task.contract.constraints:
                                if c.target_key in ("artifact", "location", "content", "text"):
                                    c.status = ConstraintStatus.SATISFIED
                        if "SPAWNS_PROCESS" in step.declared_effects:
                            for c in task.contract.constraints:
                                if c.target_key == "app":
                                    c.status = ConstraintStatus.SATISFIED

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

        # Stage 2 Intelligent Fallback Assessment
        from astrarun.recovery.models import FailureCategory, FailureEvidence, RecoveryAction
        cat = FailureCategory.ACTION_FAILED
        err_str = (failed_step.error or "").lower()
        if "timeout" in err_str:
            cat = FailureCategory.TIMEOUT
        elif "target" in err_str or "not found" in err_str:
            cat = FailureCategory.TARGET_NOT_FOUND
        elif "policy" in err_str or "blocked" in err_str or "denied" in err_str:
            cat = FailureCategory.POLICY_BLOCKED
        elif "verification" in err_str:
            cat = FailureCategory.VERIFICATION_FAILED
        elif "precondition" in err_str:
            cat = FailureCategory.PRECONDITION_FAILED

        evidence = FailureEvidence(
            failure_category=cat,
            what_failed=failed_step.capability_id,
            evidence_summary=failed_step.error or "Step execution failed",
            evidence_data=failed_step.result.data if failed_step.result else {},
            source="AgentLoop._attempt_replan",
            world_state_changed=False,
            original_goal_valid=True,
        )

        decision = self.fallback_engine.evaluate_failure(evidence, task_id=task.task_id)
        task.context.setdefault("fallback_decisions", []).append(decision.to_dict())

        if decision.action in (RecoveryAction.FAIL_CLOSED, RecoveryAction.CLEANUP_AND_FAIL):
            logger.warning("IntelligentFallbackEngine decided %s: %s", decision.action.value, decision.preference_rationale)
            return False

        if decision.action == RecoveryAction.SELECT_ALTERNATIVE_MODEL:
            logger.info("Executing model fallback: Switching to alternative model for task %s", task.task_id)
            current_model_role = task.context.get("active_model_role", "FAST")
            new_role = "DEEP" if current_model_role == "FAST" else "FAST"
            task.context["active_model_role"] = new_role
            task.context["model_fallback_triggered"] = True
            replan_event = ReplanEvent(
                trigger_step_id=failed_step.step_id,
                reason=f"Model fallback: Switched from {current_model_role} to {new_role}",
                old_plan_version=task.plan.version,
                new_plan_version=task.plan.version + 1,
            )
            failed_step.state = StepState.PENDING
            failed_step.retry_count = 0
            task.replans.append(replan_event)
            self.listener.on_replan(task, replan_event)
            return True

        if len(task.replans) >= 3:
            logger.warning("Maximum dynamic replan attempts (3) exceeded for task %s; aborting replan.", task.task_id)
            return False

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
