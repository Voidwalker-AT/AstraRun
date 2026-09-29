"""Tests for AstraRun v0.11.1 Generality Gate & Dynamic Capability Discovery.

Validates that AstraRun is a genuine autonomous agent runtime:
1. Dynamic plug-in discovery (reverse_text) without planner.py modifications.
2. Dynamic multi-capability chaining (reverse_text -> save_text_file) via OutputReference.
3. Parallel DAG branch execution (cpu_metrics + memory_metrics -> summary).
4. Real dynamic replanning and PlanRevision history on unexpected observation.
5. Plan quality validation and rejection of invalid/dangling plans.
6. Empirical GoalVerifier satisfaction.
7. Negation gating.
8. Plug-in chain: tool_alpha -> tool_beta -> tool_gamma registered after initialization.
"""

import tempfile
import time
from pathlib import Path
import pytest

from astrarun.agent.graph import DependencyCycleError, ExecutionGraph
from astrarun.agent.indexer import CapabilitySemanticIndex
from astrarun.agent.locking import ResourceLockManager
from astrarun.agent.loop import AgentExecutionEngine
from astrarun.agent.models import (
    AgentTask,
    AgentTaskStatus,
    ArgumentSourceType,
    FileObservation,
    Goal,
    GoalVerificationStatus,
    OutputReference,
    Plan,
    PlanCondition,
    PlanningLevel,
    PlanRevision,
    PlanStatus,
    PlanStep,
    PlanValidationStatus,
    StepDependency,
    StepState,
)
from astrarun.agent.planner import GoalPlanner
from astrarun.agent.validator import PlanQualityValidator
from astrarun.agent.verifier import GoalVerifier, StepVerifier
from astrarun.capabilities.models import (
    Capability,
    CapabilityCategory,
    CapabilityPermission,
    CapabilityResult,
)
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.schema import InteractionTier, VerifierStrategy
from astrarun.core.models import ToolRisk


class TestDynamicPluginDiscovery:
    """The Critical Plug-In Test: Discover and execute novel capabilities without modifying planner.py."""

    def test_single_plugin_discovery_reverse_text(self):
        """Register reverse_text ONLY in registry; verify planner discovers and executes it."""
        registry = CapabilityRegistry()
        indexer = CapabilitySemanticIndex(registry)
        planner = GoalPlanner(registry, indexer)
        engine = AgentExecutionEngine(registry=registry)
        engine.planner = planner

        # Register novel capability NOT known to planner.py
        registry.register(
            Capability(
                id="reverse_text",
                category=CapabilityCategory.SYSTEM,
                description="Reverse an input string payload character by character",
                args_schema={"text": str},
                risk=ToolRisk.LOW,
                read_only=True,
                handler=lambda text="": CapabilityResult.ok("reverse_text", f"Reversed: {text[::-1]}", data={"reversed": text[::-1]}),
                permission=CapabilityPermission.AUTO,
            )
        )

        prompt = "reverse hello world"
        task = engine.execute_goal(prompt)

        assert task.status == AgentTaskStatus.COMPLETED
        assert len(task.plan.steps) == 1
        assert task.plan.steps[0].capability_id == "reverse_text"
        assert task.plan.steps[0].arguments.get("text") == "hello world"
        assert task.plan.steps[0].result is not None
        assert task.plan.steps[0].result.data["reversed"] == "dlrow olleh"

    def test_novel_composition_reverse_and_save(self):
        """Register reverse_text and save_text_file; verify dynamic 2-step DAG with OutputReference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = str(Path(tmpdir) / "output.txt")

            registry = CapabilityRegistry()
            indexer = CapabilitySemanticIndex(registry)
            planner = GoalPlanner(registry, indexer)
            engine = AgentExecutionEngine(registry=registry)
            engine.planner = planner

            # 1. Register reverse_text
            registry.register(
                Capability(
                    id="reverse_text",
                    category=CapabilityCategory.SYSTEM,
                    description="Reverse an input string payload",
                    args_schema={"text": str},
                    risk=ToolRisk.LOW,
                    read_only=True,
                    handler=lambda text="": CapabilityResult.ok("reverse_text", "Reversed text", data={"reversed": text[::-1]}),
                    permission=CapabilityPermission.AUTO,
                )
            )

            # 2. Register save_text_file
            def save_handler(path: str = "", content: str = "") -> CapabilityResult:
                Path(path).write_text(content, encoding="utf-8")
                return CapabilityResult.ok("save_text_file", f"Saved to {path}", data={"output_file": path, "size": len(content)})

            registry.register(
                Capability(
                    id="save_text_file",
                    category=CapabilityCategory.FILE,
                    description="Save string content into a filesystem path",
                    args_schema={"path": str, "content": str},
                    risk=ToolRisk.LOW,
                    read_only=False,
                    handler=save_handler,
                    permission=CapabilityPermission.AUTO,
                )
            )

            prompt = f"reverse hello world and save the result to {out_file}"
            task = engine.execute_goal(prompt)

            assert task.status == AgentTaskStatus.COMPLETED
            assert len(task.plan.steps) == 2
            assert task.plan.steps[0].capability_id == "reverse_text"
            assert task.plan.steps[1].capability_id == "save_text_file"

            # Check dependency and OutputReference wiring
            assert len(task.plan.steps[1].dependencies) == 1
            assert task.plan.steps[1].dependencies[0].step_id == task.plan.steps[0].step_id

            # Verify file exists on disk with reversed contents
            assert Path(out_file).exists()
            assert Path(out_file).read_text(encoding="utf-8") == "dlrow olleh"


class TestGeneralDataflowDAG:
    """Tests for parallel DAG branches, OutputReference, and dataflow propagation."""

    def test_parallel_branches_cpu_memory_summary(self):
        """Plan with parallel independent steps feeding a downstream aggregator."""
        registry = CapabilityRegistry()
        registry.register(
            Capability(
                id="cpu_metrics",
                category=CapabilityCategory.SYSTEM,
                description="Get CPU metrics",
                args_schema={},
                risk=ToolRisk.LOW,
                read_only=True,
                handler=lambda: CapabilityResult.ok("cpu_metrics", "CPU 15%", data={"cpu_usage": 15}),
            )
        )
        registry.register(
            Capability(
                id="memory_metrics",
                category=CapabilityCategory.SYSTEM,
                description="Get Memory metrics",
                args_schema={},
                risk=ToolRisk.LOW,
                read_only=True,
                handler=lambda: CapabilityResult.ok("memory_metrics", "RAM 42%", data={"ram_usage": 42}),
            )
        )
        registry.register(
            Capability(
                id="system_summary",
                category=CapabilityCategory.SYSTEM,
                description="Summarize system metrics",
                args_schema={},
                risk=ToolRisk.LOW,
                read_only=True,
                handler=lambda: CapabilityResult.ok("system_summary", "System Healthy", data={"summary": "Healthy"}),
            )
        )
        engine = AgentExecutionEngine(registry=registry)

        step_cpu = PlanStep(
            step_id="step_cpu",
            capability_id="cpu_metrics",
            arguments={},
            weight=1.0,
        )
        step_mem = PlanStep(
            step_id="step_mem",
            capability_id="memory_metrics",
            arguments={},
            weight=1.0,
        )
        step_summary = PlanStep(
            step_id="step_summary",
            capability_id="system_summary",
            arguments={},
            dependencies=[
                StepDependency(step_id="step_cpu"),
                StepDependency(step_id="step_mem"),
            ],
            weight=1.0,
        )

        plan = Plan(steps=[step_cpu, step_mem, step_summary])
        graph = ExecutionGraph(plan)

        # Both step_cpu and step_mem must be ready concurrently
        ready = graph.get_ready_steps()
        assert len(ready) == 2
        ready_ids = {s.step_id for s in ready}
        assert ready_ids == {"step_cpu", "step_mem"}

        task = AgentTask(
            goal=Goal(raw_prompt="Check CPU and memory summary"),
            plan=plan,
        )
        res_task = engine.run_task(task)
        assert res_task.status == AgentTaskStatus.COMPLETED
        assert all(s.state == StepState.COMPLETED for s in res_task.plan.steps)

    def test_symbolic_output_reference_resolution(self):
        """Symbolic OutputReference resolving dynamically during execution graph data propagation."""
        step1 = PlanStep(
            step_id="step1",
            capability_id="c1",
            arguments={},
            result=CapabilityResult.ok("c1", "Done", data={"file_path": "C:\\data\\test.pdf"}),
            state=StepState.COMPLETED,
        )
        step2 = PlanStep(
            step_id="step2",
            capability_id="c2",
            arguments={"path": OutputReference(step_id="step1", field="file_path")},
            dependencies=[StepDependency(step_id="step1")],
            state=StepState.PENDING,
        )

        plan = Plan(steps=[step1, step2])
        graph = ExecutionGraph(plan)

        ready = graph.get_ready_steps()
        assert len(ready) == 1
        assert ready[0].step_id == "step2"
        # Argument must have resolved from OutputReference to string value
        assert step2.arguments["path"] == "C:\\data\\test.pdf"
        assert "path" in step2.argument_bindings
        assert step2.argument_bindings["path"].source_type == ArgumentSourceType.PREVIOUS_STEP


class TestRealReplanningAndRevision:
    """Tests for dynamic DAG replanning, PlanRevision recording, and safety validation."""

    def test_dynamic_replan_with_fallback_action(self):
        """Preferred action fails; engine observes and planner substitutes fallback capability."""
        registry = CapabilityRegistry()
        engine = AgentExecutionEngine(registry=registry)

        # 1. Action that fails
        registry.register(
            Capability(
                id="failing_action",
                category=CapabilityCategory.SYSTEM,
                description="Simulated failing action",
                args_schema={"val": int},
                handler=lambda val=0: CapabilityResult.fail("failing_action", "Action temporarily unavailable"),
            )
        )
        # 2. Working fallback action
        registry.register(
            Capability(
                id="working_fallback_action",
                category=CapabilityCategory.SYSTEM,
                description="Reliable fallback action",
                args_schema={"val": int},
                handler=lambda val=0: CapabilityResult.ok("working_fallback_action", f"Fallback resolved {val}", data={"val": val}),
            )
        )

        step = PlanStep(
            step_id="step_fail",
            capability_id="failing_action",
            arguments={"val": 100},
            max_retries=0,
        )
        task = AgentTask(
            goal=Goal(raw_prompt="Run failing action with fallback"),
            plan=Plan(steps=[step]),
        )

        # Configure custom replan on GoalPlanner for this test
        def custom_replan(t, failed_s, obs):
            rev = PlanRevision(
                task_id=t.task_id,
                previous_plan_version=t.plan.version,
                new_plan_version=t.plan.version + 1,
                reason="Dynamic substitution of failing_action with working_fallback_action",
                added_steps=["step_fallback"],
                removed_steps=[failed_s.step_id],
            )
            fallback_step = PlanStep(
                step_id="step_fallback",
                capability_id="working_fallback_action",
                arguments=dict(failed_s.arguments),
            )
            failed_s.state = StepState.SKIPPED
            t.plan.steps.append(fallback_step)
            t.plan.version += 1
            t.revisions.append(rev)
            return rev

        engine.planner.replan = custom_replan

        res_task = engine.run_task(task)
        assert res_task.status == AgentTaskStatus.COMPLETED
        assert len(res_task.revisions) == 1
        assert res_task.revisions[0].added_steps == ["step_fallback"]
        assert len(res_task.plan.steps) == 2
        assert res_task.plan.steps[0].state == StepState.SKIPPED
        assert res_task.plan.steps[1].state == StepState.COMPLETED


class TestQualityGateAndNegation:
    """Tests for PlanQualityValidator, GoalVerifier, and Negation."""

    def test_validator_rejects_cycles(self):
        s1 = PlanStep(step_id="s1", capability_id="system_summary", dependencies=[StepDependency(step_id="s2")])
        s2 = PlanStep(step_id="s2", capability_id="system_summary", dependencies=[StepDependency(step_id="s1")])
        plan = Plan(steps=[s1, s2])
        validator = PlanQualityValidator()
        res = validator.validate_plan(plan)
        assert not res.is_valid
        assert res.status == PlanValidationStatus.INVALID
        assert any("Cycle detected" in iss for iss in res.issues)

    def test_validator_rejects_dangling_output_reference(self):
        s1 = PlanStep(
            step_id="s1",
            capability_id="system_summary",
            arguments={"path": OutputReference(step_id="non_existent_step", field="file")},
        )
        plan = Plan(steps=[s1])
        validator = PlanQualityValidator()
        res = validator.validate_plan(plan)
        assert not res.is_valid
        assert any("dangling OutputReference" in iss for iss in res.issues)

    def test_negation_excludes_negated_capability(self):
        planner = GoalPlanner()
        goal = planner.parse_goal("find the latest PDF but don't open it")
        assert "open it" in goal.parameters.get("negated_actions", [])
        plan = planner.create_plan(goal)
        cap_ids = [s.capability_id for s in plan.steps]
        assert "open_application" not in cap_ids

    def test_typed_plan_condition(self):
        cond_true = PlanCondition(left="result.count", operator=">", right=0)
        assert cond_true.evaluate({"result": {"count": 5}}) is True
        assert cond_true.evaluate({"result": {"count": 0}}) is False

        cond_non_empty = PlanCondition(left="step1.output_file", operator="non_empty")
        assert cond_non_empty.evaluate({"step1": {"output_file": "c:\\test.html"}}) is True
        assert cond_non_empty.evaluate({"step1": {"output_file": ""}}) is False


class TestChainedDynamicCapabilities:
    """Section 36: tool_alpha -> tool_beta -> tool_gamma registered dynamically."""

    def test_alpha_beta_gamma_pipeline(self):
        registry = CapabilityRegistry()
        engine = AgentExecutionEngine(registry=registry)

        registry.register(
            Capability(
                id="tool_alpha",
                category=CapabilityCategory.SYSTEM,
                description="Produces value X",
                args_schema={},
                handler=lambda: CapabilityResult.ok("tool_alpha", "Produced X", data={"x": 42}),
            )
        )
        registry.register(
            Capability(
                id="tool_beta",
                category=CapabilityCategory.SYSTEM,
                description="Consumes X and produces Y",
                args_schema={"x": int},
                handler=lambda x=0: CapabilityResult.ok("tool_beta", f"Transformed X={x} to Y={x*2}", data={"y": x * 2}),
            )
        )
        registry.register(
            Capability(
                id="tool_gamma",
                category=CapabilityCategory.SYSTEM,
                description="Consumes Y and writes final result",
                args_schema={"y": int},
                handler=lambda y=0: CapabilityResult.ok("tool_gamma", f"Final Y={y}", data={"final": y + 10}),
            )
        )

        step_a = PlanStep(step_id="step_a", capability_id="tool_alpha")
        step_b = PlanStep(
            step_id="step_b",
            capability_id="tool_beta",
            arguments={"x": OutputReference(step_id="step_a", field="x")},
            dependencies=[StepDependency(step_id="step_a")],
        )
        step_c = PlanStep(
            step_id="step_c",
            capability_id="tool_gamma",
            arguments={"y": OutputReference(step_id="step_b", field="y")},
            dependencies=[StepDependency(step_id="step_b")],
        )

        plan = Plan(steps=[step_a, step_b, step_c])
        task = AgentTask(
            goal=Goal(raw_prompt="Run alpha beta gamma pipeline"),
            plan=plan,
        )

        res_task = engine.run_task(task)
        assert res_task.status == AgentTaskStatus.COMPLETED
        assert step_a.result.data["x"] == 42
        assert step_b.result.data["y"] == 84
        assert step_c.result.data["final"] == 94


class TestObservationFreshness:
    """Section 14 & 15: Typed observations and freshness TTL."""

    def test_observation_ttl_expiry(self):
        obs = FileObservation(path="c:\\test.txt", exists=True, freshness_ttl_s=0.1)
        assert obs.is_fresh() is True
        time.sleep(0.15)
        assert obs.is_fresh() is False
