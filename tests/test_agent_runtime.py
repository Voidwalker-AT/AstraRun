"""Unit and integration tests for AstraRun v0.11 Dynamic Agent Runtime."""

import time
import pytest

from astrarun.agent.graph import DependencyCycleError, ExecutionGraph
from astrarun.agent.locking import ResourceLockManager, ResourceLockTimeout
from astrarun.agent.loop import AgentExecutionEngine, AgentExecutionListener
from astrarun.agent.models import (
    AgentTask,
    AgentTaskStatus,
    Goal,
    Plan,
    PlanStep,
    ProgressMode,
    StepDependency,
    StepState,
)
from astrarun.agent.observer import MachineObserver
from astrarun.agent.planner import GoalPlanner
from astrarun.agent.verifier import StepVerifier
from astrarun.capabilities.models import Capability, CapabilityCategory, CapabilityErrorCode, CapabilityResult
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.schema import InteractionTier, VerifierStrategy
from astrarun.core.models import ToolRisk


class TestGoalPlanner:
    """Tests for GoalPlanner and dynamic plan composition."""

    def test_parse_battery_report_goal(self):
        planner = GoalPlanner()
        goal = planner.parse_goal("run a battery report and save it in Downloads as astra-battery.html")
        assert goal.intent == "generate_battery_report"
        assert "astra-battery.html" in goal.parameters.get("filename", "")
        assert goal.parameters.get("folder") == "Downloads"

        plan = planner.create_plan(goal)
        assert len(plan.steps) == 1
        assert plan.steps[0].capability_id == "generate_battery_report"
        assert plan.steps[0].interaction_tier == InteractionTier.TIER_B_STRUCTURED_CLI
        assert plan.steps[0].verifier_strategy == VerifierStrategy.FILE_NON_EMPTY

    def test_parse_wifi_goals(self):
        planner = GoalPlanner()
        # Scan
        goal_scan = planner.parse_goal("scan available wifi networks")
        assert goal_scan.intent == "wifi_scan"
        plan_scan = planner.create_plan(goal_scan)
        assert plan_scan.steps[0].capability_id == "wifi_scan"

        # Status
        goal_status = planner.parse_goal("check wifi status")
        assert goal_status.intent == "wifi_status"
        plan_status = planner.create_plan(goal_status)
        assert plan_status.steps[0].capability_id == "wifi_status"

        # Connect
        goal_conn = planner.parse_goal("connect to wifi OfficeNet")
        assert goal_conn.intent == "wifi_connect"
        assert goal_conn.parameters.get("ssid") == "OfficeNet"
        plan_conn = planner.create_plan(goal_conn)
        assert plan_conn.steps[0].capability_id == "wifi_connect"
        assert plan_conn.steps[0].verifier_strategy == VerifierStrategy.NETWORK_SSID

    def test_parse_compound_open_and_type(self):
        planner = GoalPlanner()
        goal = planner.parse_goal("open testapp and type sample text")
        plan = planner.create_plan(goal)
        assert len(plan.steps) == 2
        assert plan.steps[0].capability_id == "open_application"
        assert plan.steps[1].capability_id == "type_into_window"
        assert plan.steps[1].dependencies[0].step_id == plan.steps[0].step_id


class TestExecutionGraph:
    """Tests for DAG dependency graph resolution and cycle detection."""

    def test_topological_readiness(self):
        step1 = PlanStep(step_id="step1", capability_id="c1", state=StepState.PENDING, weight=1.0)
        step2 = PlanStep(
            step_id="step2",
            capability_id="c2",
            dependencies=[StepDependency(step_id="step1")],
            state=StepState.PENDING,
            weight=1.0,
        )
        plan = Plan(steps=[step1, step2])
        graph = ExecutionGraph(plan)

        # Initially only step1 should be ready
        ready = graph.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "step1"
        assert step1.state == StepState.READY

        # Mark step1 complete
        step1.state = StepState.COMPLETED
        ready = graph.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "step2"

    def test_cycle_detection(self):
        step1 = PlanStep(step_id="s1", capability_id="c1", dependencies=[StepDependency(step_id="s2")])
        step2 = PlanStep(step_id="s2", capability_id="c2", dependencies=[StepDependency(step_id="s1")])
        plan = Plan(steps=[step1, step2])

        with pytest.raises(DependencyCycleError):
            ExecutionGraph(plan)

    def test_progress_calculation(self):
        step1 = PlanStep(step_id="s1", capability_id="c1", state=StepState.COMPLETED, weight=2.0)
        step2 = PlanStep(step_id="s2", capability_id="c2", state=StepState.PENDING, weight=2.0)
        plan = Plan(steps=[step1, step2])
        graph = ExecutionGraph(plan)

        assert graph.compute_progress_pct() == 50.0

        step2.state = StepState.COMPLETED
        assert graph.compute_progress_pct() == 100.0


class TestResourceLocking:
    """Tests for ResourceLockManager concurrency protection."""

    def test_lock_acquire_and_release(self):
        manager = ResourceLockManager()
        assert manager.acquire_lock("NETWORK:WIFI", task_id="task_1", timeout_s=1.0)
        assert manager.is_locked("NETWORK:WIFI")
        assert manager.get_lock_holder("NETWORK:WIFI") == "task_1"

        # Re-entrant by same task
        assert manager.acquire_lock("NETWORK:WIFI", task_id="task_1", timeout_s=1.0)

        # Cannot acquire by another task
        assert not manager.acquire_lock("NETWORK:WIFI", task_id="task_2", timeout_s=0.1)

        # Release
        assert manager.release_lock("NETWORK:WIFI", task_id="task_1")
        assert manager.release_lock("NETWORK:WIFI", task_id="task_1")
        assert not manager.is_locked("NETWORK:WIFI")

    def test_release_all_for_task(self):
        manager = ResourceLockManager()
        manager.acquire_lock("FILE:c:\\test.txt", task_id="task_3")
        manager.acquire_lock("WINDOW:1234", task_id="task_3")
        assert manager.is_locked("FILE:c:\\test.txt")
        assert manager.is_locked("WINDOW:1234")

        count = manager.release_all_for_task("task_3")
        assert count == 2
        assert not manager.is_locked("FILE:c:\\test.txt")
        assert not manager.is_locked("WINDOW:1234")


class TestClosedLoopExecution:
    """Tests for closed-loop execution, retries, and cancellation."""

    def test_successful_closed_loop(self):
        reg = CapabilityRegistry()
        reg.register(
            Capability(
                id="mock_action",
                category=CapabilityCategory.SYSTEM,
                description="Mock action",
                args_schema={"val": int},
                handler=lambda val=0: CapabilityResult.ok("mock_action", f"Handled {val}", data={"val": val}),
            )
        )

        engine = AgentExecutionEngine(registry=reg)
        step = PlanStep(
            step_id="step1",
            capability_id="mock_action",
            arguments={"val": 42},
            verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
        )
        task = AgentTask(
            goal=Goal(raw_prompt="Run mock action"),
            plan=Plan(steps=[step]),
        )

        res_task = engine.run_task(task)
        assert res_task.status == AgentTaskStatus.COMPLETED
        assert step.state == StepState.COMPLETED
        assert step.verification is not None
        assert step.verification.verified is True
        assert len(res_task.observations) == 1

    def test_task_cancellation(self):
        reg = CapabilityRegistry()
        reg.register(
            Capability(
                id="mock_slow",
                category=CapabilityCategory.SYSTEM,
                description="Slow action",
                args_schema={},
                handler=lambda: CapabilityResult.ok("mock_slow", "Done"),
            )
        )

        engine = AgentExecutionEngine(registry=reg)
        step1 = PlanStep(step_id="s1", capability_id="mock_slow")
        step2 = PlanStep(step_id="s2", capability_id="mock_slow", dependencies=[StepDependency(step_id="s1")])
        task = AgentTask(
            goal=Goal(raw_prompt="Slow task"),
            plan=Plan(steps=[step1, step2]),
        )

        # Mark cancellation requested
        task.cancellation_requested = True
        res_task = engine.run_task(task)
        assert res_task.status == AgentTaskStatus.CANCELLED
        assert step2.state == StepState.CANCELLED
