"""F0-24A.1 adversarial oracle suite.

Designed to fool the acceptance/oracle stack. Every scenario must produce
FAILURE unless complete requested postconditions are genuinely satisfied.

Evidence class: SOURCE_TREE_TEST
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrarun.agent.models import (
    Goal,
    GoalContract,
    GoalPredicate,
    Plan,
    PlanStep,
    PredicateType,
    StepState,
    VerifierStrategy,
)
from astrarun.agent.verifier import GoalVerifier, StepVerifier
from astrarun.capabilities.models import CapabilityResult
from astrarun.evaluation.acceptance_model import (
    AcceptanceDimension,
    AcceptancePredicate,
    FormalAcceptanceOracle,
)
from astrarun.evaluation.execution_truth import (
    ExecutionStage,
    ExecutionTruthOracle,
    assert_pass_rate_not_fabricated,
    evaluate_resource_cleanup,
    resource_cleanup_verdict,
    summarize_case_outcomes,
)
from astrarun.tasks.resource_ledger import AstraResourceLedger, OwnedResource, ResourceLifecycleState


def _file_pred(path: Path, contains: str | None = None, equals: str | None = None) -> list[GoalPredicate]:
    preds = [
        GoalPredicate(predicate_type=PredicateType.FILE_EXISTS, parameters={"path": str(path)}, is_mandatory=True),
        GoalPredicate(predicate_type=PredicateType.FILE_NON_EMPTY, parameters={"path": str(path)}, is_mandatory=True),
    ]
    if contains is not None:
        preds.append(
            GoalPredicate(
                predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
                parameters={"path": str(path), "contains": contains},
                is_mandatory=True,
            )
        )
    if equals is not None:
        preds.append(
            GoalPredicate(
                predicate_type=PredicateType.FILE_CONTENT_EQUALS,
                parameters={"path": str(path), "expected": equals},
                is_mandatory=True,
            )
        )
    return preds


def _clean_delta(**overrides) -> dict:
    base = {
        "resources_owned": True,
        "process_cleanup_required": True,
        "process_residue_measured": True,
        "window_residue_measured": True,
        "ledger_residue_measured": True,
        "cleanup_executed": True,
        "process_cleaned_up": True,
        "orphaned_processes": 0,
        "orphaned_windows": 0,
        "active_ledger_resources": 0,
    }
    base.update(overrides)
    return base


def _completed_step(step_id: str, verified: bool = True) -> PlanStep:
    step = PlanStep(step_id=step_id, capability_id="save_text_file", description="step")
    step.state = StepState.COMPLETED
    step.verification = SimpleNamespace(verified=verified, message="ok")
    return step


def test_correct_app_opened_but_typing_fails():
    verifier = GoalVerifier()
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "doc.txt"
        empty.write_text("", encoding="utf-8")
        gc = GoalContract(
            "gc",
            "type hello and save",
            "PRODUCE_DOCUMENT",
            acceptance_predicates=_file_pred(empty, contains="hello"),
        )
        res = verifier.evaluate(gc)
    assert res.completed is False


def test_typing_succeeds_in_wrong_application_no_postcondition():
    verifier = StepVerifier()
    step = PlanStep(
        step_id="s1",
        capability_id="type_into_window",
        description="type",
        verifier_strategy=VerifierStrategy.UI_ELEMENT_STATE,
        verifier_params={"text": "hello", "app_name": "notepad"},
        arguments={"text": "hello", "app_name": "notepad"},
    )
    # Dispatch success only; UI observation will fail to find text on this headless path.
    result = CapabilityResult(capability="type_into_window", success=True, message="typed", data={"length": 5})
    out = verifier.verify(step, result)
    assert out.verified is False
    assert "not observed" in out.message.lower() or "simulated" in out.message.lower()


def test_correct_filename_exists_but_empty():
    verifier = GoalVerifier()
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "out.txt"
        empty.write_text("", encoding="utf-8")
        gc = GoalContract("gc", "save file", "PRODUCE_DOCUMENT", acceptance_predicates=_file_pred(empty, contains="hello"))
        res = verifier.evaluate(gc)
    assert res.completed is False
    assert any("empty" in m.lower() or "does not contain" in m.lower() for m in res.missing_criteria)


def test_correct_filename_contains_wrong_content():
    verifier = GoalVerifier()
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "out.txt"
        path.write_text("WRONG", encoding="utf-8")
        gc = GoalContract("gc", "save", "PRODUCE_DOCUMENT", acceptance_predicates=_file_pred(path, contains="hello"))
        res = verifier.evaluate(gc)
    assert res.completed is False


def test_save_dialog_opened_but_save_not_completed():
    verifier = StepVerifier()
    step = PlanStep(
        step_id="s1",
        capability_id="save_document_via_ui",
        description="save",
        verifier_strategy=VerifierStrategy.WINDOW_READY,
        verifier_params={},
        arguments={},
    )
    result = CapabilityResult(
        capability="save_document_via_ui",
        success=True,
        message="Save dialog appeared",
        data={},
    )
    out = verifier.verify(step, result)
    # Dialog visibility is not save completion; missing identity must not pass.
    assert out.verified is False


def test_correct_app_launched_but_wrong_app_evaluated():
    oracle = FormalAcceptanceOracle()
    preds = [
        AcceptancePredicate(
            "e1",
            "identity",
            AcceptanceDimension.ENTITY_CORRECTNESS,
            "process",
            "eval",
            "Evaluated wrong application identity",
            is_mandatory=True,
            satisfied=False,
        )
    ]
    report = oracle.evaluate(
        "wrong_app",
        "open calculator",
        GoalContract("gc", "open calculator", "LAUNCH_APPLICATION"),
        plan=None,
        execution_trace=[{"step": "open", "success": True}],
        resource_delta=_clean_delta(),
        custom_predicates=preds,
    )
    assert report.passed is False
    assert report.overall_verdict == "FAIL"


def test_requested_app_remains_open_after_cleanup():
    stage = evaluate_resource_cleanup(
        {
            "process_cleaned_up": False,
            "cleanup_executed": True,
            "orphaned_processes": 1,
            "orphaned_windows": 0,
            "active_ledger_resources": 0,
        }
    )
    assert stage.satisfied is False
    assert resource_cleanup_verdict({"process_cleaned_up": False}) == "FAIL"


def test_unrelated_preexisting_app_accidentally_closed():
    from astrarun.evaluation.side_effect_ledger import MutationType, TaskSideEffectLedger
    from astrarun.evaluation.side_effect_ledger import ResourceOwnership, SideEffectEntry

    ledger = TaskSideEffectLedger("t1")
    ledger.pre_existing_pids = {111}
    ledger.entries.append(
        SideEffectEntry(
            entry_id="proc_111",
            mutation_type=MutationType.PROCESS_TERMINATION,
            target="user-app (PID 111)",
            ownership=ResourceOwnership.USER_OWNED_PREEXISTING,
            is_consequential=True,
            is_requested=False,
            advances_goal=False,
        )
    )
    report = ledger.reconcile_with_contract(
        GoalContract("gc", "save file", "PRODUCE_DOCUMENT")
    )
    assert report["is_clean"] is False
    assert report["verdict"] == "FAIL"
    assert report["user_resource_violations"]


def test_plan_validates_but_no_action_executes():
    verifier = GoalVerifier()
    plan = Plan(steps=[PlanStep(step_id="s1", capability_id="open_application", description="open")])
    plan.steps[0].state = StepState.PENDING
    goal = Goal(raw_prompt="open calculator", contract=GoalContract("gc", "open calculator", "LAUNCH_APPLICATION"))
    res = verifier.verify_goal(goal, plan, None)
    assert res.completed is False


def test_first_step_succeeds_later_required_step_fails():
    verifier = GoalVerifier()
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "late_fail.txt"
        # first artifact missing after later step failed
        gc = GoalContract(
            "gc",
            "type then save",
            "PRODUCE_DOCUMENT",
            acceptance_predicates=_file_pred(path, contains="payload"),
        )
        plan = Plan(
            steps=[
                _completed_step("s1", verified=True),
                PlanStep(step_id="s2", capability_id="save_text_file", description="save"),
            ]
        )
        plan.steps[1].state = StepState.FAILED
        goal = Goal(raw_prompt="type then save", contract=gc)
        res = verifier.verify_goal(goal, plan, None)
    assert res.completed is False


def test_action_returns_success_but_observed_state_disagrees():
    verifier = StepVerifier()
    step = PlanStep(
        step_id="s1",
        capability_id="type_into_window",
        description="type",
        verifier_strategy=VerifierStrategy.UI_ELEMENT_STATE,
        verifier_params={"text": "observable_payload"},
        arguments={"text": "observable_payload"},
    )
    result = CapabilityResult(success=True, capability="type_into_window", message="ok", data={"length": 5})
    out = verifier.verify(step, result)
    assert out.verified is False
    assert out.evidence.get("keystroke_dispatched_chars") == 5


def test_artifact_exists_from_previous_run_wrong_content():
    verifier = GoalVerifier()
    with tempfile.TemporaryDirectory() as td:
        stale = Path(td) / "artifact.txt"
        stale.write_text("STALE_FROM_PREVIOUS_RUN", encoding="utf-8")
        gc = GoalContract(
            "gc",
            "save FRESH",
            "PRODUCE_DOCUMENT",
            acceptance_predicates=_file_pred(stale, contains="FRESH"),
        )
        res = verifier.evaluate(gc)
    assert res.completed is False


def test_stale_observation_is_not_fresh_enough_for_completion():
    from astrarun.agent.models import Observation, InteractionTier
    obs = Observation(step_id="s1", tier=InteractionTier.TIER_A_NATIVE)
    obs.timestamp = 0.0
    obs.freshness_ttl_s = 0.5
    assert obs.is_fresh() is False


def test_unexpected_side_effect_despite_goal_success():
    oracle = FormalAcceptanceOracle()
    report = oracle.evaluate(
        "side_effect",
        "save file",
        GoalContract("gc", "save file", "PRODUCE_DOCUMENT"),
        plan=None,
        execution_trace=[{"step": "s1", "success": True}],
        side_effects=[{"action": "open_folder", "is_unexpected": True, "category": "UNREQUESTED_CONSEQUENTIAL"}],
        resource_delta=_clean_delta(),
    )
    assert report.passed is False


def test_execution_truth_blocks_goal_without_postcondition():
    truth = ExecutionTruthOracle().evaluate(
        case_id="partial",
        plan_valid=True,
        action_dispatched=True,
        action_succeeded=True,
        state_observed=False,
        postcondition_satisfied=False,
        resource_cleanup_verified=True,
    )
    assert truth.goal_completed is False
    assert truth.highest_stage != ExecutionStage.GOAL_COMPLETED
    assert any(s.stage == ExecutionStage.GOAL_COMPLETED and not s.satisfied for s in truth.stages)


def test_cleanup_exception_blocks_pass_clean():
    assert resource_cleanup_verdict({"cleanup_exception": "boom", "process_cleaned_up": True}) == "FAIL"
    assert resource_cleanup_verdict(None) == "FAIL"
    assert resource_cleanup_verdict(_clean_delta(cleanup_exception="boom")) == "FAIL"
    assert resource_cleanup_verdict(_clean_delta()) == "PASS_CLEAN"


@pytest.mark.parametrize(
    "delta",
    [
        {},
        {"cleanup_executed": True},
        {"orphaned_processes": 0},
        {"process_cleaned_up": True},
        {"cleanup_executed": True, "orphaned_processes": 0},
        {"process_cleaned_up": True, "cleanup_executed": True},
        {"resources_owned": True},
        {"resources_owned": False},
        _clean_delta(process_residue_measured=False),
        _clean_delta(orphaned_processes=None),
        _clean_delta(orphaned_windows=None),
        _clean_delta(active_ledger_resources=None),
        _clean_delta(process_cleanup_required=None),
    ],
)
def test_incomplete_cleanup_evidence_cannot_pass(delta):
    """Vacuous/incomplete resource_delta must never establish RESOURCE_CLEANUP_VERIFIED."""
    stage = evaluate_resource_cleanup(delta)
    assert stage.satisfied is False
    assert resource_cleanup_verdict(delta) == "FAIL"
    assert stage.evidence.get("provided") is True or delta == {}


def test_complete_valid_cleanup_record_passes():
    stage = evaluate_resource_cleanup(_clean_delta())
    assert stage.satisfied is True
    assert resource_cleanup_verdict(_clean_delta()) == "PASS_CLEAN"


def test_legitimate_zero_resource_task_via_explicit_ownership():
    """Zero-resource tasks complete only with explicit resources_owned=false + measured zeros."""
    zero_resource = {
        "resources_owned": False,
        "process_cleanup_required": False,
        "process_residue_measured": True,
        "window_residue_measured": True,
        "ledger_residue_measured": True,
        "cleanup_executed": True,
        "orphaned_processes": 0,
        "orphaned_windows": 0,
        "active_ledger_resources": 0,
    }
    stage = evaluate_resource_cleanup(zero_resource)
    assert stage.satisfied is True
    assert resource_cleanup_verdict(zero_resource) == "PASS_CLEAN"
    # Missing resources_owned cannot invent zero-resource cleanliness.
    assert evaluate_resource_cleanup(
        {
            "process_cleanup_required": False,
            "cleanup_executed": True,
            "process_residue_measured": True,
            "window_residue_measured": True,
            "ledger_residue_measured": True,
            "orphaned_processes": 0,
            "orphaned_windows": 0,
            "active_ledger_resources": 0,
        }
    ).satisfied is False


def test_close_owned_resource_returns_false_when_process_remains(tmp_path):
    ledger = AstraResourceLedger(db_path=str(tmp_path / "ledger.db"))
    # Simulate residual process by monkeypatching pid_exists checks via resource that is closed only if process dies.
    res = OwnedResource(
        resource_id="res_live",
        task_id="task_live",
        resource_type=None,
        pid=None,
        hwnd=None,
        astra_created=True,
        lifecycle_state=ResourceLifecycleState.ACTIVE,
    )
    ok = ledger.close_owned_resource(res)
    assert ok is False


def test_null_contract_cannot_complete():
    res = GoalVerifier().evaluate(None)
    assert res.completed is False
    assert res.status.value == "GOAL_INCOMPLETE"


def test_return_code_only_is_not_completion():
    out = StepVerifier().verify(
        PlanStep(step_id="s1", capability_id="save_text_file", description="save", verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY),
        CapabilityResult(success=True, capability="save_text_file", message="dispatched", data={}),
    )
    assert out.verified is False


def test_generalization_119_of_120_not_reported_as_100():
    outcomes = [{"passed": True, "planning": True, "execution": True, "verification": True, "cleanup": True}] * 119
    outcomes.append({"passed": False, "planning": True, "execution": False, "verification": False, "cleanup": True, "false_completion": False})
    summary = summarize_case_outcomes(outcomes)
    assert summary["fraction"] == "119/120"
    assert summary["pass_rate_pct"] == pytest.approx(99.1667, abs=0.01)
    assert summary["combined_fake_100pct"] is False
    violations = assert_pass_rate_not_fabricated(119, 120, 100.0)
    assert violations
    assert assert_pass_rate_not_fabricated(119, 120, summary["pass_rate_pct"]) == []


def test_evidence_class_cannot_self_promote():
    from pydantic import ValidationError

    from astrarun.core.evidence import (
        EvidenceClass,
        EvidencePromotionError,
        EvidenceRecord,
        assert_evidence_class_allowed,
    )

    with pytest.raises(EvidencePromotionError):
        assert_evidence_class_allowed(EvidenceClass.REAL_COMPUTER_USE, {})
    with pytest.raises(EvidencePromotionError):
        assert_evidence_class_allowed(EvidenceClass.FROZEN_EXE, {})
    # Proper provenance allows the class.
    assert_evidence_class_allowed(
        EvidenceClass.REAL_COMPUTER_USE,
        {"physically_executed": True, "runtime_artifact": "trace.json"},
    )
    # Low-tier record construction must reject physical claims (pydantic wraps the error).
    with pytest.raises((EvidencePromotionError, ValidationError)) as excinfo:
        EvidenceRecord(
            evidence_class=EvidenceClass.REAL_COMPUTER_USE,
            claim="typed in notepad",
            target_component="computer_use",
            verified=True,
        )
    assert "self-promot" in str(excinfo.value).lower() or "self-promotion" in str(excinfo.value).lower()
