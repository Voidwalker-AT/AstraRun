"""Execution graph and dependency resolution engine for AstraRun v0.11 agent runtime."""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Optional

from astrarun.agent.models import Plan, PlanStep, StepState


class DependencyCycleError(ValueError):
    """Raised when an execution plan contains cyclic dependencies."""
    pass


class ExecutionGraph:
    """Manages directed acyclic graph (DAG) of plan steps, data propagation, and readiness."""

    def __init__(self, plan: Plan):
        self.plan = plan
        self._validate_and_build()

    def _validate_and_build(self) -> None:
        """Validate step identifiers and ensure acyclic graph."""
        self._step_map: dict[str, PlanStep] = {s.step_id: s for s in self.plan.steps}
        if len(self._step_map) != len(self.plan.steps):
            raise ValueError("Duplicate step_ids detected in plan.")

        # Build adjacency and in-degree
        self._adj: dict[str, list[str]] = defaultdict(list)
        in_degree: dict[str, int] = {s.step_id: 0 for s in self.plan.steps}

        for step in self.plan.steps:
            for dep in step.dependencies:
                if dep.step_id not in self._step_map:
                    raise ValueError(f"Step '{step.step_id}' references unknown dependency '{dep.step_id}'")
                self._adj[dep.step_id].append(step.step_id)
                in_degree[step.step_id] += 1

        # Check for cycles via Kahn's algorithm
        queue = deque([sid for sid, deg in in_degree.items() if deg == 0])
        visited_count = 0
        while queue:
            node = queue.popleft()
            visited_count += 1
            for nxt in self._adj[node]:
                in_degree[nxt] -= 1
                if in_degree[nxt] == 0:
                    queue.append(nxt)

        if visited_count != len(self.plan.steps):
            raise DependencyCycleError("Plan contains cyclic step dependencies.")

    def get_ready_steps(self) -> list[PlanStep]:
        """Return all steps that are currently in PENDING or READY state whose dependencies are satisfied."""
        ready: list[PlanStep] = []
        for step in self.plan.steps:
            if step.state not in (StepState.PENDING, StepState.READY):
                continue

            deps_satisfied = True
            for dep in step.dependencies:
                dep_step = self._step_map.get(dep.step_id)
                # If dependency was SKIPPED, treat as satisfied if required_state is SKIPPED or COMPLETED
                if not dep_step:
                    deps_satisfied = False
                    break
                if dep_step.state not in (dep.required_state, StepState.SKIPPED if dep.required_state == StepState.COMPLETED else dep.required_state):
                    deps_satisfied = False
                    break

            if deps_satisfied:
                self._propagate_data(step)

                # Evaluate conditional guard if present
                if step.condition:
                    context = self._build_evaluation_context(step)
                    if not step.condition.evaluate(context):
                        step.state = StepState.SKIPPED
                        continue

                step.state = StepState.READY
                ready.append(step)

        return ready

    def _build_evaluation_context(self, step: PlanStep) -> dict[str, Any]:
        """Build execution evaluation context for step condition checks."""
        ctx: dict[str, Any] = {}
        for s in self.plan.steps:
            if s.result and s.result.data:
                ctx[s.step_id] = s.result.data
        if step.dependencies:
            last_dep = self._step_map.get(step.dependencies[-1].step_id)
            if last_dep and last_dep.result and last_dep.result.data:
                ctx["result"] = last_dep.result.data
        return ctx

    def _propagate_data(self, step: PlanStep) -> None:
        """Map output data from satisfied dependencies into step arguments (supporting OutputReference and ${step.field})."""
        import re
        from astrarun.agent.models import ArgumentBinding, ArgumentSourceType, OutputReference

        # 1. Process explicit data_mapping from dependencies
        for dep in step.dependencies:
            dep_step = self._step_map.get(dep.step_id)
            if not dep_step or not dep_step.result or not dep_step.result.data:
                continue
            for out_key, in_arg in dep.data_mapping.items():
                if out_key in dep_step.result.data:
                    val = dep_step.result.data[out_key]
                    step.arguments[in_arg] = val
                    step.argument_bindings[in_arg] = ArgumentBinding(
                        parameter=in_arg,
                        value=val,
                        source_type=ArgumentSourceType.PREVIOUS_STEP,
                        source_reference=f"{dep.step_id}.{out_key}",
                        confidence=1.0,
                    )

        # 2. Process OutputReference and ${step_id.field} within step.arguments
        for arg_name, arg_val in list(step.arguments.items()):
            if isinstance(arg_val, OutputReference):
                ref_step = self._step_map.get(arg_val.step_id)
                if ref_step and ref_step.result and ref_step.result.data and arg_val.field in ref_step.result.data:
                    resolved_val = ref_step.result.data[arg_val.field]
                    step.arguments[arg_name] = resolved_val
                    step.argument_bindings[arg_name] = ArgumentBinding(
                        parameter=arg_name,
                        value=resolved_val,
                        source_type=ArgumentSourceType.PREVIOUS_STEP,
                        source_reference=f"{arg_val.step_id}.{arg_val.field}",
                        confidence=1.0,
                    )
            elif isinstance(arg_val, str) and "${" in arg_val and "}" in arg_val:
                # String template substitution
                def replacer(match):
                    expr = match.group(1).strip()
                    if "." in expr:
                        sid, fld = expr.split(".", 1)
                        ref_step = self._step_map.get(sid)
                        if ref_step and ref_step.result and ref_step.result.data and fld in ref_step.result.data:
                            return str(ref_step.result.data[fld])
                    return match.group(0)

                resolved_str = re.sub(r"\$\{([^}]+)\}", replacer, arg_val)
                step.arguments[arg_name] = resolved_str
                step.argument_bindings[arg_name] = ArgumentBinding(
                    parameter=arg_name,
                    value=resolved_str,
                    source_type=ArgumentSourceType.PREVIOUS_STEP,
                    source_reference=arg_val,
                    confidence=1.0,
                )

    def add_step(self, new_step: PlanStep) -> None:
        """Dynamically append a new step to the plan and revalidate."""
        self.plan.steps.append(new_step)
        self.plan.version += 1
        self._validate_and_build()

    def insert_after(self, predecessor_id: str, new_step: PlanStep) -> None:
        """Insert a step immediately depending on predecessor_id and re-route successors."""
        if predecessor_id not in self._step_map:
            raise ValueError(f"Predecessor '{predecessor_id}' not found in plan.")

        from astrarun.agent.models import StepDependency
        new_step.dependencies.append(StepDependency(step_id=predecessor_id))

        # Re-route any existing successors of predecessor to depend on new_step instead
        for successor_id in self._adj.get(predecessor_id, []):
            succ = self._step_map[successor_id]
            for dep in succ.dependencies:
                if dep.step_id == predecessor_id:
                    dep.step_id = new_step.step_id

        self.plan.steps.append(new_step)
        self.plan.version += 1
        self._validate_and_build()

    def compute_progress_pct(self) -> float:
        """Calculate weighted completion percentage (0.0 to 100.0)."""
        if not self.plan.steps:
            return 100.0
        total_weight = sum(s.weight for s in self.plan.steps)
        if total_weight <= 0:
            return 0.0

        completed_weight = sum(
            s.weight for s in self.plan.steps
            if s.state in (StepState.COMPLETED, StepState.SKIPPED)
        )
        return round((completed_weight / total_weight) * 100.0, 1)

    def is_complete(self) -> bool:
        """Check if all steps in plan have reached terminal states."""
        terminal_states = {
            StepState.COMPLETED,
            StepState.FAILED,
            StepState.CANCELLED,
            StepState.SKIPPED,
        }
        return all(s.state in terminal_states for s in self.plan.steps)

    def has_failures(self) -> bool:
        """Check if any step in plan has failed or is blocked."""
        return any(s.state in (StepState.FAILED, StepState.BLOCKED) for s in self.plan.steps)
