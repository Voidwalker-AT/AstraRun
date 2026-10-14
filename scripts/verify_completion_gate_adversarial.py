"""Runner and evidence generator for F0-25F.3 Stage 1 Authoritative Completion Gate.

Executes tests C1 through C14 and writes docs/audit/F0_25F3_COMPLETION_GATE_RESULTS.json.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
src_dir = REPO_ROOT / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

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


def run_all_cases() -> dict:
    cases = {}

    # C1: no postconditions
    c1_contract = GoalContract(original_utterance="Do something", acceptance_predicates=[])
    c1_res = AuthoritativeCompletionGate.can_complete(goal_contract=c1_contract)
    cases["C1_no_postconditions"] = {
        "description": "GoalContract has zero acceptance predicates",
        "expected": "REJECTED",
        "actual": c1_res.verdict.value,
        "can_complete": c1_res.can_complete,
        "passed": (not c1_res.can_complete and c1_res.verdict == GateVerdict.REJECTED),
        "reason": c1_res.message,
    }

    # C2: one required predicate missing (PENDING)
    p_c2 = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.PENDING)
    c2_contract = GoalContract(acceptance_predicates=[p_c2])
    c2_res = AuthoritativeCompletionGate.can_complete(goal_contract=c2_contract)
    cases["C2_one_required_predicate_missing"] = {
        "description": "One required predicate is PENDING (missing/not evaluated)",
        "expected": "REJECTED",
        "actual": c2_res.verdict.value,
        "can_complete": c2_res.can_complete,
        "passed": (not c2_res.can_complete and c2_res.verdict == GateVerdict.REJECTED),
        "reason": c2_res.message,
    }

    # C3: one required predicate UNKNOWN
    p_c3 = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.UNKNOWN)
    c3_contract = GoalContract(acceptance_predicates=[p_c3])
    c3_res = AuthoritativeCompletionGate.can_complete(goal_contract=c3_contract)
    cases["C3_one_required_predicate_unknown"] = {
        "description": "One required predicate is UNKNOWN",
        "expected": "REJECTED",
        "actual": c3_res.verdict.value,
        "can_complete": c3_res.can_complete,
        "passed": (not c3_res.can_complete and c3_res.verdict == GateVerdict.REJECTED),
        "reason": c3_res.message,
    }

    # C4: action success but postcondition false (VIOLATED)
    p_c4 = GoalPredicate(
        predicate_type=PredicateType.FILE_EXISTS,
        is_mandatory=True,
        status=PredicateStatus.VIOLATED,
        error_message="File does not exist on disk",
    )
    c4_contract = GoalContract(acceptance_predicates=[p_c4])
    c4_res = AuthoritativeCompletionGate.can_complete(goal_contract=c4_contract, execution_state={"action_succeeded": True})
    cases["C4_action_success_but_postcondition_false"] = {
        "description": "Action succeeded, but postcondition predicate is VIOLATED",
        "expected": "REJECTED",
        "actual": c4_res.verdict.value,
        "can_complete": c4_res.can_complete,
        "passed": (not c4_res.can_complete and c4_res.verdict == GateVerdict.REJECTED),
        "reason": c4_res.message,
    }

    # C5: presentation requested but not presented
    p_c5 = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)
    c5_contract = GoalContract(acceptance_predicates=[p_c5], entities={"reveal_result": True})
    c5_ev = {"events": [{"event_type": "RESULT_PRESENTATION_REQUESTED"}]}
    c5_res = AuthoritativeCompletionGate.can_complete(goal_contract=c5_contract, evidence_state=c5_ev)
    cases["C5_presentation_requested_but_not_presented"] = {
        "description": "Presentation was requested, but RESULT_PRESENTED not verified (REQUESTED only)",
        "expected": "REJECTED",
        "actual": c5_res.verdict.value,
        "can_complete": c5_res.can_complete,
        "passed": (not c5_res.can_complete and c5_res.verdict == GateVerdict.REJECTED),
        "reason": c5_res.message,
    }

    # C6: cleanup attempted but failed
    task_id_c6 = "task_verify_c6"
    ledger = AstraResourceLedger.get_instance()
    res_c6 = OwnedResource(
        task_id=task_id_c6,
        resource_type=ResourceType.SANDBOX_DIR,
        launching_capability="SandboxManager",
        document_path="C:\\mock\\nonexistent",
        lifecycle_state=ResourceLifecycleState.FAILED_CLEANUP,
    )
    ledger.register_resource(res_c6)
    p_c6 = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)
    c6_contract = GoalContract(contract_id=task_id_c6, acceptance_predicates=[p_c6])
    c6_res = AuthoritativeCompletionGate.can_complete(goal_contract=c6_contract, active_task_id=task_id_c6)
    cases["C6_cleanup_attempted_but_failed"] = {
        "description": "Resource is in FAILED_CLEANUP",
        "expected": "REJECTED",
        "actual": c6_res.verdict.value,
        "can_complete": c6_res.can_complete,
        "passed": (not c6_res.can_complete and c6_res.verdict == GateVerdict.REJECTED),
        "reason": c6_res.message,
    }

    # C7: artifact exists but wrong content
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt") as tf:
        tf.write("Wrong content here")
        tpath_c7 = tf.name
    try:
        p_c7 = GoalPredicate(
            predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
            parameters={"path": tpath_c7, "content": "EXPECTED_TOKEN_SECRET_123"},
            is_mandatory=True,
            status=PredicateStatus.SATISFIED,
        )
        c7_contract = GoalContract(acceptance_predicates=[p_c7])
        c7_res = AuthoritativeCompletionGate.can_complete(goal_contract=c7_contract)
        cases["C7_artifact_exists_but_wrong_content"] = {
            "description": "Target artifact exists on disk, but does not match required content",
            "expected": "REJECTED",
            "actual": c7_res.verdict.value,
            "can_complete": c7_res.can_complete,
            "passed": (not c7_res.can_complete and c7_res.verdict == GateVerdict.REJECTED),
            "reason": c7_res.message,
        }
    finally:
        Path(tpath_c7).unlink(missing_ok=True)

    # C8: all required predicates true
    run_id_c8 = "run_c8_valid"
    task_id_c8 = "task_c8_valid"
    p_c8 = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": run_id_c8, "task_id": task_id_c8},
    )
    c8_contract = GoalContract(acceptance_predicates=[p_c8])
    c8_res = AuthoritativeCompletionGate.can_complete(
        goal_contract=c8_contract, active_run_id=run_id_c8, active_task_id=task_id_c8
    )
    cases["C8_all_required_predicates_true"] = {
        "description": "All required predicates true with matching run/task provenance",
        "expected": "APPROVED",
        "actual": c8_res.verdict.value,
        "can_complete": c8_res.can_complete,
        "passed": (c8_res.can_complete and c8_res.verdict == GateVerdict.APPROVED),
        "reason": c8_res.message,
    }

    # C9: deterministic goal with only its relevant predicates
    p_c9 = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        parameters={"result": 4},
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
    )
    c9_contract = GoalContract(
        original_utterance="calculate 2+2",
        acceptance_predicates=[p_c9],
        entities={"reveal_result": False},
    )
    c9_res = AuthoritativeCompletionGate.can_complete(goal_contract=c9_contract)
    cases["C9_deterministic_goal_with_only_its_relevant_predicates"] = {
        "description": "Deterministic calculation needs only computation predicate, not presentation/cleanup",
        "expected": "APPROVED",
        "actual": c9_res.verdict.value,
        "can_complete": c9_res.can_complete,
        "passed": (c9_res.can_complete and c9_res.verdict == GateVerdict.APPROVED),
        "reason": c9_res.message,
    }

    # C10: optional predicate missing
    p_c10_mand = GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)
    p_c10_opt = GoalPredicate(predicate_type=PredicateType.WINDOW_ACTIVE, is_mandatory=False, status=PredicateStatus.PENDING)
    c10_contract = GoalContract(acceptance_predicates=[p_c10_mand, p_c10_opt])
    c10_res = AuthoritativeCompletionGate.can_complete(goal_contract=c10_contract)
    cases["C10_optional_predicate_missing"] = {
        "description": "Optional predicate missing/PENDING does NOT block completion",
        "expected": "APPROVED",
        "actual": c10_res.verdict.value,
        "can_complete": c10_res.can_complete,
        "passed": (c10_res.can_complete and c10_res.verdict == GateVerdict.APPROVED),
        "reason": c10_res.message,
    }

    # C11: GOAL_COMPLETED manually emitted early
    telem = CausalTelemetry.get_instance()
    run_id_c11 = telem.start_run(query="Goal without postconditions", task_id="task_c11")
    ev_c11_direct = telem.emit(
        event_type=CausalEventType.GOAL_COMPLETED.value,
        component="AdversarialCaller",
        data={"status": "SUCCESS"},
    )
    end_ev_c11 = telem.end_run(status="SUCCESS")
    c11_passed = (ev_c11_direct is None and end_ev_c11 is not None and end_ev_c11.data.get("completed") is False)
    cases["C11_goal_completed_manually_emitted_early"] = {
        "description": "Direct manual emission of GOAL_COMPLETED before postconditions are verified returns None and end_run fails closed",
        "expected": "REJECTED (emission None, end_run uncompleted)",
        "actual": "REJECTED" if c11_passed else "EMITTED",
        "can_complete": False,
        "passed": c11_passed,
        "reason": "Direct emission returned None; end_run emitted completed=False",
    }

    # C12: stale evidence from another run
    p_c12 = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": "run_c12", "task_id": "task_c12", "stale": True},
    )
    c12_contract = GoalContract(acceptance_predicates=[p_c12])
    c12_res = AuthoritativeCompletionGate.can_complete(
        goal_contract=c12_contract, active_run_id="run_c12", active_task_id="task_c12"
    )
    cases["C12_stale_evidence_from_another_run"] = {
        "description": "Evidence marked stale from prior run",
        "expected": "REJECTED",
        "actual": c12_res.verdict.value,
        "can_complete": c12_res.can_complete,
        "passed": (not c12_res.can_complete and c12_res.verdict == GateVerdict.REJECTED),
        "reason": c12_res.message,
    }

    # C13: correct evidence with wrong task_id
    p_c13 = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": "run_c13", "task_id": "task_FOREIGN_123"},
    )
    c13_contract = GoalContract(acceptance_predicates=[p_c13])
    c13_res = AuthoritativeCompletionGate.can_complete(
        goal_contract=c13_contract, active_run_id="run_c13", active_task_id="task_c13_active"
    )
    cases["C13_correct_evidence_with_wrong_task_id"] = {
        "description": "Evidence has mismatched task_id",
        "expected": "REJECTED",
        "actual": c13_res.verdict.value,
        "can_complete": c13_res.can_complete,
        "passed": (not c13_res.can_complete and c13_res.verdict == GateVerdict.REJECTED),
        "reason": c13_res.message,
    }

    # C14: correct evidence with wrong run_id
    p_c14 = GoalPredicate(
        predicate_type=PredicateType.DATA_COMPUTED,
        is_mandatory=True,
        status=PredicateStatus.SATISFIED,
        evidence={"run_id": "run_FOREIGN_456", "task_id": "task_c14"},
    )
    c14_contract = GoalContract(acceptance_predicates=[p_c14])
    c14_res = AuthoritativeCompletionGate.can_complete(
        goal_contract=c14_contract, active_run_id="run_c14_active", active_task_id="task_c14"
    )
    cases["C14_correct_evidence_with_wrong_run_id"] = {
        "description": "Evidence has mismatched run_id",
        "expected": "REJECTED",
        "actual": c14_res.verdict.value,
        "can_complete": c14_res.can_complete,
        "passed": (not c14_res.can_complete and c14_res.verdict == GateVerdict.REJECTED),
        "reason": c14_res.message,
    }

    return cases


def main():
    cases = run_all_cases()
    passed_count = sum(1 for c in cases.values() if c["passed"])
    total_count = len(cases)

    report = {
        "phase": "F0-25F.3",
        "gate": "AuthoritativeCompletionGate",
        "total_adversarial_cases": total_count,
        "passed_cases": passed_count,
        "failed_cases": total_count - passed_count,
        "all_cases_passed": passed_count == total_count,
        "cases": cases,
    }

    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F3_COMPLETION_GATE_RESULTS.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Completion gate adversarial tests: {passed_count}/{total_count} PASSED.")
    print(f"Artifact written to {out_file}")


if __name__ == "__main__":
    main()
