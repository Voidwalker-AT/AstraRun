"""Reproduce F0-24A.1 false-completion mechanisms against current source (pre-fix).

Evidence class: SOURCE_TREE_REPRODUCTION
Run: .venv/Scripts/python scripts/repro_f0_24a1_false_completion.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from astrarun.agent.models import (
    AgentTask,
    AgentTaskStatus,
    Goal,
    GoalContract,
    GoalPredicate,
    Plan,
    PlanStep,
    PredicateType,
    StepState,
)
from astrarun.agent.verifier import GoalVerifier, global_step_verifier
from astrarun.capabilities.models import CapabilityResult
from astrarun.capabilities.schema import VerifierStrategy
from astrarun.evaluation.acceptance_model import (
    AcceptanceDimension,
    AcceptancePredicate,
    FormalAcceptanceOracle,
)


def repro_a_editable_surface_typing_failed_but_pass() -> dict:
    """UI_ELEMENT_STATE trusts keystroke dispatch success as text verification."""
    step = PlanStep(
        step_id="s1",
        capability_id="type_into_window",
        description="type hello into editor",
        verifier_strategy=VerifierStrategy.UI_ELEMENT_STATE,
        verifier_params={"text": "hello"},
        arguments={"text": "hello"},
    )
    # Capability claims success with keystroke length, but no physical text was observed.
    result = CapabilityResult(
        capability="type_into_window",
        success=True,
        message="Injected 5 keystrokes",
        data={"length": 5, "hwnd": 12345},
    )
    # Force non-simulated path so we hit the keystroke-fallback branch when UIA finds nothing.
    # On non-win32 the simulated branch already trusts result.success.
    verification = global_step_verifier.verify(step, result)
    return {
        "contradiction": "A_editable_surface_typing_failed_but_pass",
        "verified": verification.verified,
        "message": verification.message,
        "evidence": verification.evidence,
        "mechanism": (
            "StepVerifier.UI_ELEMENT_STATE treats successful keystroke injection "
            "(result.success + length>0) as proof that the editable surface contains the text."
        ),
        "false_completion": bool(verification.verified),
    }


def repro_b_generalization_119_of_120_as_100() -> dict:
    """Pass-rate reporting can invent 100% from 119/120 when only false-completion rate is checked."""
    from astrarun.evaluation.execution_truth import (
        assert_pass_rate_not_fabricated,
        summarize_case_outcomes,
    )

    passed = 119
    total = 120
    false_completions = 0
    # Historical anti-pattern: treat 0 false completions as overall 100% success.
    misleading_overall = 100.0 if false_completions == 0 else 0.0
    summary = summarize_case_outcomes(
        [{"passed": True}] * passed + [{"passed": False}]
    )
    violations = assert_pass_rate_not_fabricated(passed, total, misleading_overall)
    return {
        "contradiction": "B_generalization_119_of_120_as_100",
        "passed_cases": passed,
        "total_cases": total,
        "false_completion_count": false_completions,
        "honest_fraction": summary["fraction"],
        "honest_pass_rate_pct": summary["pass_rate_pct"],
        "misleading_zero_false_completion_as_100pct": misleading_overall,
        "accounting_violations_detected": violations,
        "production_accounting_kills_fabrication": bool(violations),
        "mechanism": (
            "F0_24A_GENERALIZATION_RESULTS.json records passed_cases=119 of total_cases=120 "
            "and false_completion_rate_pct=0.0. Downstream reporting that treats "
            "'0.0% false completion' as overall 100% success misrepresents generalization. "
            "summarize_case_outcomes/assert_pass_rate_not_fabricated now reject that collapse."
        ),
        "false_completion": bool(violations) and misleading_overall == 100.0 and passed < total,
        "killed_by_production_helper": bool(violations),
    }


def repro_c_resource_cleanup_false_pass() -> dict:
    """RESOURCE_CLEANUP dimension passes when resource_delta is empty even if process remained."""
    oracle = FormalAcceptanceOracle()
    # No resource_delta, no cleanup evidence: historical oracle still passes RESOURCE_CLEANUP.
    report = oracle.evaluate(
        case_id="residue",
        prompt="open app and finish",
        contract=GoalContract("gc", "open app", "LAUNCH_APPLICATION"),
        plan=None,
        execution_trace=[],
        resource_delta=None,
    )
    cleanup_dim = report.dimensions.get(AcceptanceDimension.RESOURCE_CLEANUP.value)
    # Contradiction shape from F0_24A_RESOURCE_RESIDUE.json: process_cleaned_up=false + PASS_CLEAN
    process_cleaned_up = False
    pass_clean = process_cleaned_up is False and cleanup_dim and cleanup_dim.passed
    return {
        "contradiction": "C_resource_cleanup_false_pass",
        "cleanup_dimension_passed": bool(cleanup_dim and cleanup_dim.passed),
        "process_cleaned_up": process_cleaned_up,
        "pass_clean_with_uncleaned_process": bool(pass_clean),
        "mechanism": (
            "FormalAcceptanceOracle RESOURCE_CLEANUP treats missing resource_delta as orphans==0. "
            "verify_f0_24a_evidence_closure accepts stage_verdict PASS_CLEAN without checking "
            "process_cleaned_up. F0_24A_RESOURCE_RESIDUE.json literally pairs "
            "process_cleaned_up=false with verdict=PASS_CLEAN."
        ),
        "false_completion": bool(pass_clean),
    }


def repro_d_planning_as_execution_evidence() -> dict:
    """Valid plan with no execution still yields GOAL_COMPLETED when contract is null."""
    verifier = GoalVerifier()
    empty_contract_res = verifier.evaluate(None)
    # Plan validation is not execution.
    plan = Plan(steps=[PlanStep(step_id="s1", capability_id="open_application", description="open")])
    # No steps executed; graph-less path via verify_goal with all PENDING steps.
    goal = Goal(raw_prompt="open calculator", contract=None)
    for s in plan.steps:
        s.state = StepState.PENDING
    goal_res = verifier.verify_goal(goal, plan, None)
    return {
        "contradiction": "D_planning_as_execution_evidence",
        "null_contract_completed": empty_contract_res.completed,
        "null_contract_status": empty_contract_res.status.value,
        "unexecuted_plan_completed": goal_res.completed,
        "unexecuted_plan_status": goal_res.status.value,
        "mechanism": (
            "GoalVerifier.evaluate returns GOAL_COMPLETED when contract is None. "
            "validate_plan success is independent of physical execution; any harness that "
            "counts validation_passed as success treats planning as execution."
        ),
        "false_completion": bool(empty_contract_res.completed or goal_res.completed),
    }


def repro_e_partial_ui_progress_as_completion() -> dict:
    """Opening an editor / returning success is accepted as if typing/save completed."""
    from astrarun.agent.models import SemanticConstraint, ConstraintType

    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "out.txt"
        empty.write_text("", encoding="utf-8")
        verifier = GoalVerifier()
        gc = GoalContract(
            "gc",
            "save hello",
            "PRODUCE_DOCUMENT",
            constraints=[
                SemanticConstraint(
                    constraint_type=ConstraintType.REQUIRED_CONTENT,
                    description="Expected payload",
                    target_key="content",
                    expected_value="hello",
                    is_mandatory=True,
                )
            ],
            acceptance_predicates=[
                GoalPredicate(
                    predicate_type=PredicateType.FILE_EXISTS,
                    parameters={"path": str(empty)},
                    is_mandatory=True,
                )
            ],
        )
        res = verifier.evaluate(gc)
        step = PlanStep(
            step_id="s1",
            capability_id="save_text_file",
            description="save",
            verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
            arguments={"path": str(empty)},
        )
        result = CapabilityResult(capability="save_text_file", success=True, message="dispatched", data={})
        step_ver = global_step_verifier.verify(step, result)
    return {
        "contradiction": "E_partial_ui_progress_as_completion",
        "file_exists_only_completed": res.completed,
        "return_code_only_verified": step_ver.verified,
        "mechanism": (
            "FILE_EXISTS alone + content constraint without content predicate must not complete "
            "a PRODUCE_DOCUMENT goal. RETURN_CODE_ONLY is dispatch evidence only."
        ),
        "false_completion": bool(res.completed or step_ver.verified),
    }


def main() -> int:
    results = [
        repro_a_editable_surface_typing_failed_but_pass(),
        repro_b_generalization_119_of_120_as_100(),
        repro_c_resource_cleanup_false_pass(),
        repro_d_planning_as_execution_evidence(),
        repro_e_partial_ui_progress_as_completion(),
    ]
    payload = {
        "milestone": "F0_24A.1",
        "title": "Pre-fix false-completion mechanism reproduction",
        "evidence_class": "SOURCE_TREE_REPRODUCTION",
        "results": results,
        "any_false_completion": any(r.get("false_completion") for r in results),
    }
    out = Path(__file__).resolve().parents[1] / "docs" / "audit" / "F0_24A1_PRE_FIX_REPRODUCTION.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
