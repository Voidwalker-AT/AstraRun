"""Adversarial unit tests for AuthoritativeCompletionGate (Tests C1 through C14).

Verifies that:
- Incomplete, missing, UNKNOWN, or failed postconditions fail closed.
- Requested presentation and resource cleanup failures fail closed.
- Stale or wrong-provenance evidence fails closed.
- Early direct manual emission of GOAL_COMPLETED fails closed.
- Only genuinely verified contracts pass.
"""

import tempfile
from pathlib import Path
import pytest

from astrarun.agent.completion_gate import AuthoritativeCompletionGate, GateVerdict
from astrarun.agent.models import (
    GoalContract,
    GoalPredicate,
    PredicateStatus,
    PredicateType,
)
from astrarun.core.telemetry import CausalTelemetry, CausalEventType
from astrarun.tasks.resource_ledger import (
    AstraResourceLedger,
    OwnedResource,
    ResourceType,
    ResourceLifecycleState,
)


def test_c1_no_postconditions():
    """C1: GoalContract with zero acceptance predicates must be rejected."""
    contract = GoalContract(original_utterance="Do something", acceptance_predicates=[])
    res = AuthoritativeCompletionGate.can_complete(goal_contract=contract)
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "FAILED_NO_POSTCONDITIONS" in res.status


def test_c2_one_required_predicate_missing():
    """C2: One required predicate is PENDING (missing/not evaluated) -> rejected."""
    p1 = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.PENDING)
    contract = GoalContract(acceptance_predicates=[p1])
    res = AuthoritativeCompletionGate.can_complete(goal_contract=contract)
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED


def test_c3_one_required_predicate_unknown():
    """C3: One required predicate is UNKNOWN -> rejected."""
    p1 = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.UNKNOWN)
    contract = GoalContract(acceptance_predicates=[p1])
    res = AuthoritativeCompletionGate.can_complete(goal_contract=contract)
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED


def test_c4_action_success_but_postcondition_false():
    """C4: Action succeeded, but postcondition predicate is VIOLATED -> rejected."""
    p1 = GoalPredicate(
        predicate_type=PredicateType.FILE_EXISTS,
        is_mandatory=True,
        status=PredicateStatus.VIOLATED,
        error_message="File does not exist on disk",
    )
    contract = GoalContract(acceptance_predicates=[p1])
    exec_state = {"action_succeeded": True, "exit_code": 0}
    res = AuthoritativeCompletionGate.can_complete(goal_contract=contract, execution_state=exec_state)
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED


def test_c5_presentation_requested_but_not_presented():
    """C5: Presentation was requested, but RESULT_PRESENTED not verified -> rejected."""
    p1 = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)
    contract = GoalContract(
        acceptance_predicates=[p1],
        entities={"reveal_result": True},
    )
    # Evidence contains only RESULT_PRESENTATION_REQUESTED
    ev_state = {
        "events": [{"event_type": "RESULT_PRESENTATION_REQUESTED"}],
    }
    res = AuthoritativeCompletionGate.can_complete(goal_contract=contract, evidence_state=ev_state)
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "Presentation was requested" in res.message


def test_c6_cleanup_attempted_but_failed():
    """C6: Resource cleanup was attempted but failed (FAILED_CLEANUP) -> rejected."""
    task_id = "task_adv_c6"
    ledger = AstraResourceLedger.get_instance()
    res_obj = OwnedResource(
        task_id=task_id,
        resource_type=ResourceType.SANDBOX_DIR,
        launching_capability="SandboxManager",
        document_path="C:\\mock\\nonexistent",
        lifecycle_state=ResourceLifecycleState.FAILED_CLEANUP,
    )
    ledger.register_resource(res_obj)

    p1 = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)
    contract = GoalContract(contract_id=task_id, acceptance_predicates=[p1])
    res = AuthoritativeCompletionGate.can_complete(
        goal_contract=contract, active_task_id=task_id
    )
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "FAILED_CLEANUP" in res.message


def test_c7_artifact_exists_but_wrong_content():
    """C7: Target artifact exists on disk, but does not match required content -> rejected."""
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
        tf.write("Wrong content here")
        tpath = tf.name

    try:
        p1 = GoalPredicate(
            predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
            parameters={"path": tpath, "content": "EXPECTED_TOKEN_SECRET_123"},
            is_mandatory=True,
            status=PredicateStatus.SATISFIED,  # Claimed satisfied by agent
        )
        contract = GoalContract(acceptance_predicates=[p1])
        res = AuthoritativeCompletionGate.can_complete(goal_contract=contract)
        assert not res.can_complete
        assert res.verdict == GateVerdict.REJECTED
        assert "does not contain expected substring" in res.message
    finally:
        Path(tpath).unlink(missing_ok=True)


def test_c8_all_required_predicates_true():
    """C8: All required predicates true with matching run/task provenance -> approved."""
    run_id = "run_c8_valid"
    task_id = "task_c8_valid"
    p1 = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": run_id, "task_id": task_id},
    )
    contract = GoalContract(acceptance_predicates=[p1])
    res = AuthoritativeCompletionGate.can_complete(
        goal_contract=contract, active_run_id=run_id, active_task_id=task_id
    )
    assert res.can_complete
    assert res.verdict == GateVerdict.APPROVED
    assert res.status == "SUCCESS"


def test_c9_deterministic_goal_with_only_its_relevant_predicates():
    """C9: Deterministic calculation needs only computation predicate, not presentation/cleanup."""
    p1 = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        parameters={"result": 4},
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
    )
    contract = GoalContract(
        original_utterance="calculate 2+2",
        acceptance_predicates=[p1],
        entities={"reveal_result": False},
    )
    res = AuthoritativeCompletionGate.can_complete(goal_contract=contract)
    assert res.can_complete
    assert res.verdict == GateVerdict.APPROVED


def test_c10_optional_predicate_missing():
    """C10: Optional predicate missing/PENDING does NOT block completion."""
    p_mand = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)
    p_opt = GoalPredicate(predicate_type=PredicateType.WINDOW_ACTIVE, is_mandatory=False, status=PredicateStatus.PENDING)
    contract = GoalContract(acceptance_predicates=[p_mand, p_opt])
    res = AuthoritativeCompletionGate.can_complete(goal_contract=contract)
    assert res.can_complete
    assert res.verdict == GateVerdict.APPROVED


def test_c11_goal_completed_manually_emitted_early():
    """C11: Direct manual emission of GOAL_COMPLETED before postconditions are verified returns None."""
    telem = CausalTelemetry.get_instance()
    run_id = telem.start_run(query="Goal that has no postconditions", task_id="task_c11")
    # Attempt direct manual emission of GOAL_COMPLETED with status=SUCCESS
    ev = telem.emit(
        event_type=CausalEventType.GOAL_COMPLETED.value,
        component="AdversarialCaller",
        data={"status": "SUCCESS"},
    )
    assert ev is None, "CausalTelemetry.emit allowed early unverified GOAL_COMPLETED emission!"

    # Also test end_run without postconditions verified
    end_ev = telem.end_run(status="SUCCESS")
    assert end_ev is not None
    assert end_ev.data.get("status") != "SUCCESS"
    assert end_ev.data.get("completed") is False


def test_c12_stale_evidence_from_another_run():
    """C12: Evidence marked stale or from prior run -> rejected."""
    run_id = "run_c12_active"
    task_id = "task_c12_active"
    p1 = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": run_id, "task_id": task_id, "stale": True},
    )
    contract = GoalContract(acceptance_predicates=[p1])
    res = AuthoritativeCompletionGate.can_complete(
        goal_contract=contract, active_run_id=run_id, active_task_id=task_id
    )
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "stale" in res.message


def test_c13_correct_evidence_with_wrong_task_id():
    """C13: Evidence has mismatched task_id -> rejected."""
    run_id = "run_c13_active"
    p1 = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": run_id, "task_id": "task_FOREIGN_123"},
    )
    contract = GoalContract(acceptance_predicates=[p1])
    res = AuthoritativeCompletionGate.can_complete(
        goal_contract=contract, active_run_id=run_id, active_task_id="task_c13_active"
    )
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "task_id mismatch" in res.message


def test_c14_correct_evidence_with_wrong_run_id():
    """C14: Evidence has mismatched run_id -> rejected."""
    task_id = "task_c14_active"
    p1 = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": "run_FOREIGN_456", "task_id": task_id},
    )
    contract = GoalContract(acceptance_predicates=[p1])
    res = AuthoritativeCompletionGate.can_complete(
        goal_contract=contract, active_run_id="run_c14_active", active_task_id=task_id
    )
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "run_id mismatch" in res.message
