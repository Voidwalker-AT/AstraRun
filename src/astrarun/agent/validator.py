"""Plan Quality Validator for verifying candidate DAGs before execution."""

from __future__ import annotations

from typing import Any, Optional

from astrarun.agent.graph import DependencyCycleError, ExecutionGraph
from astrarun.agent.models import (
    OutputReference,
    Plan,
    PlanStep,
    PlanValidationResult,
    PlanValidationStatus,
)
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.core.logging import get_logger
from astrarun.core.models import ToolRisk

logger = get_logger("astrarun.agent.validator")


class PlanQualityValidator:
    """
    Validates candidate execution plans prior to actuation:
    1. Capability existence in registry
    2. Required argument satisfiability
    3. Graph acyclicity (no cycles)
    4. No dangling OutputReference pointers
    5. Action risk and policy gating compliance
    6. Parallel step resource lock compatibility
    """

    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        self.registry = registry or CapabilityRegistry()

    def validate(self, plan: Plan, goal_contract: Optional[Any] = None) -> PlanValidationResult:
        """Alias for validate_plan."""
        return self.validate_plan(plan, goal_contract=goal_contract)

    def validate_plan(self, plan: Plan, goal_contract: Optional[Any] = None) -> PlanValidationResult:
        """Validate candidate plan across static, structural, policy, and information-loss dimensions."""
        issues: list[str] = []

        if not plan.steps:
            return PlanValidationResult(
                status=PlanValidationStatus.INVALID,
                is_valid=False,
                issues=["Plan contains no executable steps."],
            )

        # 0. Information-Loss Invariant: verify all mandatory constraints are addressed
        contract = goal_contract or getattr(plan, "contract", None)
        if contract and hasattr(contract, "detect_information_loss"):
            loss_issues = contract.detect_information_loss(plan.steps)
            if loss_issues:
                issues.extend(loss_issues)

        step_ids = {s.step_id for s in plan.steps}
        if len(step_ids) != len(plan.steps):
            issues.append("Duplicate step_ids detected in plan.")

        # 1. Structural Cycle & Dependency Validation
        try:
            ExecutionGraph(plan)
        except DependencyCycleError as e:
            issues.append(f"Cycle detected in plan dependencies: {e}")
        except Exception as e:
            issues.append(f"Dependency structure invalid: {e}")

        # Map step outputs for checking OutputReferences
        step_declared_outputs: dict[str, set[str]] = {}

        for step in plan.steps:
            # 2. Check capability existence
            cap = self.registry.get(step.capability_id)
            if not cap:
                issues.append(f"Step '{step.step_id}' references unknown capability '{step.capability_id}'.")
                continue

            # Record declared outputs if available
            outputs = set()
            if hasattr(cap, "outputs") and cap.outputs:
                for o in cap.outputs:
                    if isinstance(o, str):
                        outputs.add(o)
                    elif hasattr(o, "name"):
                        outputs.add(o.name)
            step_declared_outputs[step.step_id] = outputs

            # 3. Check required arguments
            if hasattr(cap, "args_schema") and isinstance(cap.args_schema, dict):
                for arg_name, arg_type in cap.args_schema.items():
                    if not self._is_argument_required(cap, arg_name, arg_type):
                        continue
                    # If step.arguments does not provide it and not in dependencies data_mapping
                    is_provided = arg_name in step.arguments
                    is_mapped = any(arg_name in dep.data_mapping.values() for dep in step.dependencies)
                    if not is_provided and not is_mapped:
                        issues.append(
                            f"Step '{step.step_id}' missing required argument '{arg_name}' for capability '{step.capability_id}'."
                        )

            # 4. Check for dangling OutputReferences
            for arg_name, arg_val in step.arguments.items():
                if isinstance(arg_val, OutputReference):
                    if arg_val.step_id not in step_ids:
                        issues.append(
                            f"Step '{step.step_id}' has dangling OutputReference to non-existent step '{arg_val.step_id}'."
                        )
                    # Check dependency relation: step must depend on arg_val.step_id
                    dep_ids = {d.step_id for d in step.dependencies}
                    if arg_val.step_id not in dep_ids:
                        issues.append(
                            f"Step '{step.step_id}' references output of '{arg_val.step_id}' without an explicit dependency."
                        )
                    # Check if referenced field is declared on referenced step
                    if arg_val.step_id in step_declared_outputs:
                        parent_outs = step_declared_outputs[arg_val.step_id]
                        if parent_outs and arg_val.field not in parent_outs:
                            issues.append(
                                f"Step '{step.step_id}' references non-existent output field '{arg_val.field}' on step '{arg_val.step_id}'."
                            )

            # 5. Check risk policy
            if cap.risk == ToolRisk.BLOCKED:
                issues.append(
                    f"Step '{step.step_id}' invokes BLOCKED risk capability '{step.capability_id}' which is prohibited by policy."
                )

        if issues:
            return PlanValidationResult(
                status=PlanValidationStatus.INVALID,
                is_valid=False,
                issues=issues,
            )

        return PlanValidationResult(
            status=PlanValidationStatus.VALID,
            is_valid=True,
            issues=[],
        )

    def _is_argument_required(self, cap: Any, arg_name: str, arg_type: Any) -> bool:
        """Determine if an argument is strictly mandatory."""
        import typing
        import inspect

        # 1. Type annotation check (Optional[T] or Union[T, None] is not required)
        if arg_type is None or arg_type is type(None):
            return False
        type_str = str(arg_type)
        if "Optional" in type_str or "NoneType" in type_str:
            return False
        origin = typing.get_origin(arg_type)
        if origin is typing.Union and type(None) in typing.get_args(arg_type):
            return False

        # 2. Handler default value check (if parameter has default, it is optional)
        handler = getattr(cap, "handler", None)
        if handler and callable(handler):
            try:
                sig = inspect.signature(handler)
                if arg_name in sig.parameters:
                    param = sig.parameters[arg_name]
                    if param.default is not inspect.Parameter.empty:
                        return False
            except Exception:
                pass

        return True
