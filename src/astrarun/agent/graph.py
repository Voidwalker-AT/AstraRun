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
        """Return all steps that are currently in PENDING state whose dependencies are satisfied."""
        ready: list[PlanStep] = []
        for step in self.plan.steps:
            if step.state != StepState.PENDING:
                continue

            deps_satisfied = True
            for dep in step.dependencies:
                dep_step = self._step_map.get(dep.step_id)
                if not dep_step or dep_step.state != dep.required_state:
                    deps_satisfied = False
                    break

            if deps_satisfied:
                step.state = StepState.READY
                self._propagate_data(step)
                ready.append(step)

        return ready

    def _propagate_data(self, step: PlanStep) -> None:
        """Map output data from satisfied dependencies into step arguments."""
        for dep in step.dependencies:
            dep_step = self._step_map.get(dep.step_id)
            if not dep_step or not dep_step.result or not dep_step.result.data:
                continue
            for out_key, in_arg in dep.data_mapping.items():
                if out_key in dep_step.result.data:
                    step.arguments[in_arg] = dep_step.result.data[out_key]

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
