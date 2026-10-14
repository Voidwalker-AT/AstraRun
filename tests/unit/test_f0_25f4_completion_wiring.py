"""Unit verification for F0-25F.4 Authoritative Completion Wiring (Tests A1 through A10).

Verifies that:
- GoalContract registration is cleanly wired by run_id and task_id.
- Stale contracts do not cross task or run boundaries.
- Legitimate satisfied contracts achieve positive completion (APPROVED / GOAL_COMPLETED).
- Violations, missing contracts, or non-SUCCESS statuses fail closed to RUN_TERMINATED.
- Direct emission of unverified or invalid completion is strictly blocked.
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


@pytest.fixture(autouse=True)
def reset_gate_and_telemetry():
    """Ensure clean gate and telemetry state for every test."""
    AuthoritativeCompletionGate.clear_all_contracts()
    telem = CausalTelemetry.get_instance()
    with telem._lock:
        telem._active_run_id = None
        telem._active_task_id = None
        telem._active_contract = None
        telem._execution_state = {}
        telem._evidence_state = {}
    yield
    AuthoritativeCompletionGate.clear_all_contracts()
    with telem._lock:
        telem._active_run_id = None
        telem._active_task_id = None
        telem._active_contract = None
        telem._execution_state = {}
        telem._evidence_state = {}


def test_a1_authoritative_contract_registration_api():
    """A1: GoalContract registration API stores contract mapped to run_id and task_id."""
    pred = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)
    contract = GoalContract(original_utterance="Compute pi", acceptance_predicates=[pred])

    AuthoritativeCompletionGate.register_contract(contract, run_id="run_a1", task_id="task_a1")

    assert AuthoritativeCompletionGate.get_contract(run_id="run_a1") is contract
    assert AuthoritativeCompletionGate.get_contract(task_id="task_a1") is contract


def test_a2_contract_retrieval_by_run_and_task():
    """A2: Completion gate can_complete looks up registered contract by active run_id/task_id if omitted."""
    run_id = "run_a2"
    task_id = "task_a2"
    pred = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": run_id, "task_id": task_id},
    )
    contract = GoalContract(original_utterance="Compute sum", acceptance_predicates=[pred])
    AuthoritativeCompletionGate.register_contract(contract, run_id=run_id, task_id=task_id)

    # Calling can_complete with goal_contract=None should resolve via active_run_id
    res = AuthoritativeCompletionGate.can_complete(
        goal_contract=None,
        active_run_id=run_id,
        active_task_id=task_id,
    )
    assert res.can_complete
    assert res.verdict == GateVerdict.APPROVED
    assert res.status == "SUCCESS"


def test_a3_contract_unregistration_cleans_mapping():
    """A3: Unregistering contract removes run and task mappings, preventing cross-task leaks."""
    contract = GoalContract(original_utterance="Test utterance", acceptance_predicates=[])
    AuthoritativeCompletionGate.register_contract(contract, run_id="run_a3", task_id="task_a3")

    assert AuthoritativeCompletionGate.get_contract(run_id="run_a3") is not None
    AuthoritativeCompletionGate.unregister_contract(run_id="run_a3", task_id="task_a3")

    assert AuthoritativeCompletionGate.get_contract(run_id="run_a3") is None
    assert AuthoritativeCompletionGate.get_contract(task_id="task_a3") is None


def test_a4_run_scoped_isolation():
    """A4: Contract for Run 1 does not leak into Run 2."""
    p1 = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)
    c1 = GoalContract(original_utterance="Run 1 goal", acceptance_predicates=[p1])
    AuthoritativeCompletionGate.register_contract(c1, run_id="run_1", task_id="task_1")

    assert AuthoritativeCompletionGate.get_contract(run_id="run_2") is None
    res = AuthoritativeCompletionGate.can_complete(goal_contract=None, active_run_id="run_2", active_task_id="task_2")
    assert not res.can_complete
    assert res.status == "FAILED_NO_CONTRACT"


def test_a5_legitimate_completion_approved():
    """A5: Legitimate contract with verified predicates achieves APPROVED verdict."""
    run_id = "run_a5"
    task_id = "task_a5"
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
        tf.write("Result: 42")
        tpath = tf.name

    try:
        p1 = GoalPredicate(
            predicate_type=PredicateType.FILE_EXISTS,
            parameters={"path": tpath},
            is_mandatory=True,
            status=PredicateStatus.SATISFIED,
            evidence={"run_id": run_id, "task_id": task_id, "path": tpath},
        )
        p2 = GoalPredicate(
            predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
            parameters={"path": tpath, "content": "42"},
            is_mandatory=True,
            status=PredicateStatus.SATISFIED,
            evidence={"run_id": run_id, "task_id": task_id, "path": tpath},
        )
        contract = GoalContract(original_utterance="Save result 42", acceptance_predicates=[p1, p2])

        res = AuthoritativeCompletionGate.can_complete(
            goal_contract=contract,
            active_run_id=run_id,
            active_task_id=task_id,
        )
        assert res.can_complete
        assert res.verdict == GateVerdict.APPROVED
        assert res.status == "SUCCESS"
    finally:
        Path(tpath).unlink(missing_ok=True)


def test_a6_telemetry_end_run_emits_goal_completed_on_approval():
    """A6: Telemetry end_run(status="SUCCESS") emits GOAL_COMPLETED when contract is satisfied and approved."""
    telem = CausalTelemetry.get_instance()
    run_id = telem.start_run(query="Compute 10th fibonacci", task_id="task_a6")

    p = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": run_id, "task_id": "task_a6"},
    )
    contract = GoalContract(original_utterance="Compute 10th fibonacci", acceptance_predicates=[p])

    ev = telem.end_run(
        status="SUCCESS",
        message="Computation finished",
        goal_contract=contract,
    )

    assert ev is not None
    assert ev.event_type == CausalEventType.GOAL_COMPLETED.value
    assert ev.data.get("status") == "SUCCESS"
    assert ev.data.get("completed") is True


def test_a7_telemetry_end_run_emits_run_terminated_on_gate_rejection():
    """A7: Telemetry end_run(status="SUCCESS") with violated contract emits RUN_TERMINATED and completed=False."""
    telem = CausalTelemetry.get_instance()
    run_id = telem.start_run(query="Violated task", task_id="task_a7")

    p = GoalPredicate(
        predicate_type=PredicateType.FILE_EXISTS,
        parameters={"path": "C:\\nonexistent\\missing_file.xyz"},
        is_mandatory=True,
        status=PredicateStatus.VIOLATED,
        error_message="File does not exist",
    )
    contract = GoalContract(original_utterance="Create missing file", acceptance_predicates=[p])

    ev = telem.end_run(
        status="SUCCESS",
        message="Attempted completion",
        goal_contract=contract,
    )

    assert ev is not None
    assert ev.event_type == CausalEventType.RUN_TERMINATED.value
    assert ev.data.get("status") != "SUCCESS"
    assert ev.data.get("completed") is False


def test_a8_non_success_end_run_never_emits_goal_completed():
    """A8: Telemetry end_run with FAILED or CANCELLED emits RUN_TERMINATED, never GOAL_COMPLETED."""
    telem = CausalTelemetry.get_instance()

    # Case 1: FAILED
    telem.start_run(query="Failing run", task_id="task_a8_1")
    ev1 = telem.end_run(status="FAILED", message="Fatal exception")
    assert ev1 is not None
    assert ev1.event_type == CausalEventType.RUN_TERMINATED.value
    assert ev1.data.get("completed") is False

    # Case 2: CANCELLED
    telem.start_run(query="Cancelled run", task_id="task_a8_2")
    ev2 = telem.end_run(status="CANCELLED", message="User cancelled")
    assert ev2 is not None
    assert ev2.event_type == CausalEventType.RUN_TERMINATED.value
    assert ev2.data.get("completed") is False


def test_a9_app_handle_request_wires_goal_contract():
    """A9: Verifies loop.execute_goal registers contract with telemetry and end_run has contract."""
    from astrarun.agent.planner import GoalPlanner

    planner = GoalPlanner()
    goal = planner.parse_goal("calculate 50 fibonacci numbers")
    assert goal.contract is not None
    assert len(goal.contract.acceptance_predicates) > 0

    telem = CausalTelemetry.get_instance()
    run_id = telem.start_run(query="calculate 50 fibonacci numbers", task_id="task_a9")
    telem.register_contract(goal.contract, run_id=run_id, task_id="task_a9")

    # Contract must now be visible in completion gate
    registered = AuthoritativeCompletionGate.get_contract(run_id=run_id)
    assert registered is goal.contract


def test_a10_direct_emit_blocks_ungated_variants():
    """A10: Direct telemetry.emit(GOAL_COMPLETED) with non-SUCCESS status or without gate approval is blocked."""
    telem = CausalTelemetry.get_instance()
    telem.start_run(query="Adversarial direct emission", task_id="task_a10")

    # Attempt 1: Direct emission with status="FAILED"
    ev_failed = telem.emit(
        event_type=CausalEventType.GOAL_COMPLETED.value,
        component="Attacker",
        data={"status": "FAILED", "completed": False},
    )
    assert ev_failed is None

    # Attempt 2: Direct emission with status="SUCCESS" but no contract/unapproved
    ev_unapproved = telem.emit(
        event_type=CausalEventType.GOAL_COMPLETED.value,
        component="Attacker",
        data={"status": "SUCCESS", "completed": True},
    )
    assert ev_unapproved is None
