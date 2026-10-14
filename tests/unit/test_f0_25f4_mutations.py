"""Adversarial Mutations M21 through M30 for F0-25F.4.

Evaluates that mutations against the positive completion, verification,
and reliability invariants are cleanly killed for the intended semantic reason.
"""

from __future__ import annotations

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


@pytest.fixture(autouse=True)
def clean_state():
    AuthoritativeCompletionGate.clear_all_contracts()
    telem = CausalTelemetry.get_instance()
    with telem._lock:
        telem._active_run_id = None
        telem._active_task_id = None
        telem._active_contract = None
    yield
    AuthoritativeCompletionGate.clear_all_contracts()


def test_m21_bypass_gate_via_direct_emit_failed():
    """M21: Attacker calls telemetry.emit(GOAL_COMPLETED) with status='FAILED'."""
    telem = CausalTelemetry.get_instance()
    telem.start_run(query="M21 query", task_id="task_m21")
    ev = telem.emit(
        event_type=CausalEventType.GOAL_COMPLETED.value,
        component="Attacker",
        data={"status": "FAILED", "completed": False},
    )
    # Mutant killed: event dropped (returns None)
    assert ev is None


def test_m22_complete_without_goal_contract():
    """M22: Completion attempt without any registered GoalContract."""
    res = AuthoritativeCompletionGate.can_complete(goal_contract=None, active_run_id="run_m22", active_task_id="task_m22")
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "FAILED_NO_CONTRACT" in res.status


def test_m23_complete_with_pending_predicates():
    """M23: Completion attempt where required predicate is PENDING."""
    p = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.PENDING)
    c = GoalContract(acceptance_predicates=[p])
    res = AuthoritativeCompletionGate.can_complete(goal_contract=c)
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "PENDING" in res.message


def test_m24_complete_with_missing_artifact_file():
    """M24: Completion attempt where required file does not exist on disk."""
    p = GoalPredicate(
        predicate_type=PredicateType.FILE_EXISTS,
        parameters={"path": "C:\\nonexistent\\phantom_file_m24.txt"},
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,  # falsely claimed
    )
    c = GoalContract(acceptance_predicates=[p])
    res = AuthoritativeCompletionGate.can_complete(goal_contract=c)
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "does not exist on disk" in res.message


def test_m25_complete_with_zero_byte_file():
    """M25: Completion attempt where required FILE_NON_EMPTY file is 0 bytes."""
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        p_path = tf.name

    try:
        p = GoalPredicate(
            predicate_type=PredicateType.FILE_NON_EMPTY,
            parameters={"path": p_path},
            is_mandatory=True,
            status=PredicateStatus.SATISFIED,
        )
        c = GoalContract(acceptance_predicates=[p])
        res = AuthoritativeCompletionGate.can_complete(goal_contract=c)
        assert not res.can_complete
        assert res.verdict == GateVerdict.REJECTED
        assert "is empty (0 bytes)" in res.message
    finally:
        Path(p_path).unlink(missing_ok=True)


def test_m26_complete_with_wrong_content():
    """M26: Completion attempt where required FILE_CONTENT_CONTAINS substring is missing."""
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write("Wrong content here")
        p_path = tf.name

    try:
        p = GoalPredicate(
            predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
            parameters={"path": p_path, "content": "SECRET_KEY_M26"},
            is_mandatory=True,
            status=PredicateStatus.SATISFIED,
        )
        c = GoalContract(acceptance_predicates=[p])
        res = AuthoritativeCompletionGate.can_complete(goal_contract=c)
        assert not res.can_complete
        assert res.verdict == GateVerdict.REJECTED
        assert "does not contain expected substring" in res.message
    finally:
        Path(p_path).unlink(missing_ok=True)


def test_m27_complete_with_stale_evidence():
    """M27: Completion attempt with evidence marked stale from prior run."""
    p = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": "run_m27", "task_id": "task_m27", "stale": True},
    )
    c = GoalContract(acceptance_predicates=[p])
    res = AuthoritativeCompletionGate.can_complete(goal_contract=c, active_run_id="run_m27", active_task_id="task_m27")
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "stale from prior run" in res.message


def test_m28_complete_with_mismatched_run_id():
    """M28: Completion attempt with mismatched foreign run_id."""
    p = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": "FOREIGN_RUN_999", "task_id": "task_m28"},
    )
    c = GoalContract(acceptance_predicates=[p])
    res = AuthoritativeCompletionGate.can_complete(goal_contract=c, active_run_id="run_m28", active_task_id="task_m28")
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "run_id mismatch" in res.message


def test_m29_presentation_requested_only():
    """M29: Presentation requested but only RESULT_PRESENTATION_REQUESTED present."""
    p = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)
    c = GoalContract(acceptance_predicates=[p], entities={"reveal_result": True})
    ev_state = {"events": [{"event_type": "RESULT_PRESENTATION_REQUESTED"}]}
    res = AuthoritativeCompletionGate.can_complete(goal_contract=c, evidence_state=ev_state)
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "RESULT_PRESENTED was not verified" in res.message


def test_m30_failed_cleanup_resource_blocks_completion():
    """M30: Task has a resource in FAILED_CLEANUP state."""
    task_id = "task_m30"
    ledger = AstraResourceLedger.get_instance()
    res_obj = OwnedResource(
        task_id=task_id,
        resource_type=ResourceType.SANDBOX_DIR,
        launching_capability="SandboxManager",
        lifecycle_state=ResourceLifecycleState.FAILED_CLEANUP,
    )
    ledger.register_resource(res_obj)

    p = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)
    c = GoalContract(acceptance_predicates=[p], contract_id=task_id)
    res = AuthoritativeCompletionGate.can_complete(goal_contract=c, active_task_id=task_id)
    assert not res.can_complete
    assert res.verdict == GateVerdict.REJECTED
    assert "FAILED_CLEANUP" in res.message
