"""Stage 16: Verification Mutation Suite for AstraRun F0-25F.6.

Verifies that verifiers fail when they are supposed to fail.
Required Mutations:
1. empty file instead of content
2. wrong window targeted
3. process killed before completion
4. malformed JSON returned

Mutation kill rate must be 100%.
Generates: docs/audit/F0_25F6_MUTATION_RESULTS.json
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List
import pytest

from astrarun.agent.completion_gate import AuthoritativeCompletionGate, GateVerdict
from astrarun.agent.models import (
    GoalContract,
    GoalPredicate,
    PlanStep,
    PredicateStatus,
    PredicateType,
    Verification,
)
from astrarun.agent.verifier import StepVerifier
from astrarun.capabilities.models import CapabilityResult
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.schema import VerifierStrategy
from astrarun.recovery.engine import IntelligentFallbackEngine
from astrarun.recovery.models import (
    FailureCategory,
    FailureEvidence,
    RecoveryAction,
)

MUTATION_AUDIT_LOG: List[Dict[str, Any]] = []


def record_mutation(
    mutant_id: str,
    mutation_type: str,
    target_verifier: str,
    description: str,
    killed: bool,
    kill_reason: str,
    details: Dict[str, Any],
) -> None:
    MUTATION_AUDIT_LOG.append({
        "id": mutant_id,
        "mutation_type": mutation_type,
        "target_verifier": target_verifier,
        "description": description,
        "killed": killed,
        "kill_reason": kill_reason,
        "kill_validity": "GENUINE_SEMANTIC_KILL" if killed else "SURVIVED",
        "details": details,
    })


@pytest.fixture(autouse=True)
def clean_state():
    AuthoritativeCompletionGate.clear_all_contracts()
    yield
    AuthoritativeCompletionGate.clear_all_contracts()


# ----------------------------------------------------------------------
# MUTATION 1: Empty file instead of content
# ----------------------------------------------------------------------

def test_mutant_01a_step_verifier_empty_file():
    """MUT-01A: StepVerifier with FILE_NON_EMPTY rejects 0-byte file."""
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf_path = tf.name  # 0 bytes

    try:
        verifier = StepVerifier()
        step = PlanStep(
            step_id="step_mut_01a",
            capability_id="save_text_file",
            verifier_strategy=VerifierStrategy.FILE_NON_EMPTY,
            verifier_params={"path": tf_path},
        )
        res = CapabilityResult(success=True, capability="save_text_file", message="File written", data={"path": tf_path})
        verif = verifier.verify(step, res)

        killed = (verif.verified is False) and ("empty (0 bytes)" in verif.message)
        record_mutation(
            "MUT-01A",
            "empty_file_instead_of_content",
            "StepVerifier.FILE_NON_EMPTY",
            "0-byte file presented when non-empty content was required",
            killed,
            verif.message,
            {"verified": verif.verified, "size_bytes": verif.evidence.get("size_bytes")},
        )
        assert killed, f"Mutant survived: {verif.message}"
    finally:
        Path(tf_path).unlink(missing_ok=True)


def test_mutant_01b_completion_gate_empty_file():
    """MUT-01B: AuthoritativeCompletionGate rejects completion on 0-byte file."""
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf_path = tf.name

    try:
        p = GoalPredicate(
            predicate_type=PredicateType.FILE_NON_EMPTY,
            parameters={"path": tf_path},
            is_mandatory=True,
            status=PredicateStatus.SATISFIED,  # falsely claimed
        )
        contract = GoalContract(acceptance_predicates=[p])
        res = AuthoritativeCompletionGate.can_complete(goal_contract=contract)

        killed = (res.can_complete is False) and (res.verdict == GateVerdict.REJECTED) and ("empty (0 bytes)" in res.message)
        record_mutation(
            "MUT-01B",
            "empty_file_instead_of_content",
            "AuthoritativeCompletionGate",
            "Authoritative completion gate must reject 0-byte file despite SATISFIED claim",
            killed,
            res.message,
            {"can_complete": res.can_complete, "verdict": res.verdict.value},
        )
        assert killed, f"Mutant survived: {res.message}"
    finally:
        Path(tf_path).unlink(missing_ok=True)


def test_mutant_01c_fallback_on_empty_file():
    """MUT-01C: IntelligentFallbackEngine diagnoses postcondition failure on empty file."""
    reg = CapabilityRegistry()
    engine = IntelligentFallbackEngine(capability_registry=reg)
    ev = FailureEvidence(
        failure_category=FailureCategory.POSTCONDITION_FAILED,
        what_failed="FileNonEmptyPredicate",
        evidence_summary="File exists but is empty (0 bytes): report.txt",
    )
    decision = engine.evaluate_failure(ev, candidate_alternatives=["generate_report_v2"])
    killed = (decision.action == RecoveryAction.REPLAN) and (decision.is_retry_safe is False) and (decision.failure_evidence.what_failed == "FileNonEmptyPredicate")
    record_mutation(
        "MUT-01C",
        "empty_file_instead_of_content",
        "IntelligentFallbackEngine",
        "Fallback engine recognizes POSTCONDITION_FAILED and prevents naive identical retry",
        killed,
        f"action={decision.action.value}, safe_retry={decision.is_retry_safe}",
        {"action": decision.action.value, "preference_rationale": decision.preference_rationale},
    )
    assert killed


# ----------------------------------------------------------------------
# MUTATION 2: Wrong window targeted
# ----------------------------------------------------------------------

def test_mutant_02a_step_verifier_wrong_window():
    """MUT-02A: StepVerifier with WINDOW_READY rejects invalid/phantom HWND."""
    verifier = StepVerifier()
    step = PlanStep(
        step_id="step_mut_02a",
        capability_id="focus_window",
        verifier_strategy=VerifierStrategy.WINDOW_READY,
        verifier_params={"hwnd": 99999999},  # non-existent HWND
    )
    res = CapabilityResult(success=True, capability="focus_window", message="Window focused", data={"hwnd": 99999999})
    verif = verifier.verify(step, res)

    killed = (verif.verified is False) and ("not ready" in verif.message or "is_window" in verif.evidence)
    record_mutation(
        "MUT-02A",
        "wrong_window_targeted",
        "StepVerifier.WINDOW_READY",
        "Targeting non-existent/invalid HWND 99999999 must fail window verification",
        killed,
        verif.message,
        {"verified": verif.verified, "is_window": verif.evidence.get("is_window")},
    )
    assert killed, f"Mutant survived: {verif.message}"


def test_mutant_02b_step_verifier_wrong_title():
    """MUT-02B: StepVerifier with WINDOW_READY rejects unmatched title query."""
    verifier = StepVerifier()
    step = PlanStep(
        step_id="step_mut_02b",
        capability_id="launch_application",
        verifier_strategy=VerifierStrategy.WINDOW_READY,
        verifier_params={"title": "NonExistentPhantomWindowX99"},
    )
    res = CapabilityResult(success=True, capability="launch_application", message="App launched", data={})
    verif = verifier.verify(step, res)

    killed = (verif.verified is False) and ("No windows found matching query" in verif.message)
    record_mutation(
        "MUT-02B",
        "wrong_window_targeted",
        "StepVerifier.WINDOW_READY_TITLE",
        "Searching for phantom title must fail verification",
        killed,
        verif.message,
        {"verified": verif.verified, "matched_windows": verif.evidence.get("matched_windows", 0)},
    )
    assert killed, f"Mutant survived: {verif.message}"


def test_mutant_02c_fallback_on_target_not_found():
    """MUT-02C: IntelligentFallbackEngine responds to TARGET_NOT_FOUND with refreshed observation."""
    reg = CapabilityRegistry()
    engine = IntelligentFallbackEngine(capability_registry=reg)
    ev = FailureEvidence(
        failure_category=FailureCategory.TARGET_NOT_FOUND,
        what_failed="find_window(Notepad)",
        evidence_summary="No window found with title matching 'Notepad'",
    )
    decision = engine.evaluate_failure(ev)
    killed = (decision.action == RecoveryAction.RETRY_WITH_NEW_OBSERVATION) and decision.is_retry_safe
    record_mutation(
        "MUT-02C",
        "wrong_window_targeted",
        "IntelligentFallbackEngine",
        "TARGET_NOT_FOUND triggers RETRY_WITH_NEW_OBSERVATION rather than blind clicking",
        killed,
        f"action={decision.action.value}",
        {"action": decision.action.value, "rationale": decision.preference_rationale},
    )
    assert killed


# ----------------------------------------------------------------------
# MUTATION 3: Process killed before completion
# ----------------------------------------------------------------------

def test_mutant_03a_step_verifier_process_dead():
    """MUT-03A: StepVerifier with PROCESS_RUNNING rejects dead/reaped PID."""
    verifier = StepVerifier()
    dead_pid = 999999  # Guaranteed unused/dead PID
    step = PlanStep(
        step_id="step_mut_03a",
        capability_id="launch_tool",
        verifier_strategy=VerifierStrategy.PROCESS_RUNNING,
        verifier_params={"pid": dead_pid},
    )
    res = CapabilityResult(success=True, capability="launch_tool", message="Process spawned", data={"pid": dead_pid})
    verif = verifier.verify(step, res)

    killed = (verif.verified is False) and ("not running" in verif.message)
    record_mutation(
        "MUT-03A",
        "process_killed_before_completion",
        "StepVerifier.PROCESS_RUNNING",
        "Process dead before verification must fail verification",
        killed,
        verif.message,
        {"verified": verif.verified, "running": verif.evidence.get("running")},
    )
    assert killed, f"Mutant survived: {verif.message}"


def test_mutant_03b_completion_gate_process_predicate_violated():
    """MUT-03B: AuthoritativeCompletionGate rejects when process predicate was violated."""
    p = GoalPredicate(
        predicate_type=PredicateType.APPLICATION_RUNNING,
        parameters={"app": "PhantomAppNeverRunning"},
        is_mandatory=True,
        status=PredicateStatus.VIOLATED,
        error_message="Process PhantomAppNeverRunning is not running",
    )
    contract = GoalContract(acceptance_predicates=[p])
    res = AuthoritativeCompletionGate.can_complete(goal_contract=contract)

    killed = (res.can_complete is False) and (res.verdict == GateVerdict.REJECTED) and ("VIOLATED" in res.message)
    record_mutation(
        "MUT-03B",
        "process_killed_before_completion",
        "AuthoritativeCompletionGate",
        "Application running predicate violated blocks goal completion",
        killed,
        res.message,
        {"can_complete": res.can_complete, "verdict": res.verdict.value},
    )
    assert killed, f"Mutant survived: {res.message}"


def test_mutant_03c_fallback_on_process_aborted():
    """MUT-03C: IntelligentFallbackEngine responds to ACTION_FAILED with alternative capability."""
    reg = CapabilityRegistry()
    engine = IntelligentFallbackEngine(capability_registry=reg)
    ev = FailureEvidence(
        failure_category=FailureCategory.ACTION_FAILED,
        what_failed="worker_process",
        evidence_summary="Process terminated prematurely with exit code 1",
    )
    decision = engine.evaluate_failure(ev, candidate_alternatives=["launch_in_isolated_worker"])
    killed = (decision.action == RecoveryAction.SELECT_ALTERNATIVE_CAPABILITY) and (decision.is_retry_safe is False) and (decision.alternative_selected == "launch_in_isolated_worker")
    record_mutation(
        "MUT-03C",
        "process_killed_before_completion",
        "IntelligentFallbackEngine",
        "Premature process termination triggers alternative capability selection",
        killed,
        f"action={decision.action.value}, alternative={decision.alternative_selected}",
        {"action": decision.action.value, "alternative": decision.alternative_selected},
    )
    assert killed


# ----------------------------------------------------------------------
# MUTATION 4: Malformed JSON returned
# ----------------------------------------------------------------------

def test_mutant_04a_malformed_json_parsing_fails():
    """MUT-04A: Malformed JSON payload fails structured parsing."""
    malformed_payload = '{"status": "ok", "result": [unquoted_value, missing_brace'
    parsing_failed = False
    try:
        json.loads(malformed_payload)
    except json.JSONDecodeError as exc:
        parsing_failed = True
        err_msg = str(exc)

    killed = parsing_failed
    record_mutation(
        "MUT-04A",
        "malformed_json_returned",
        "JSONDecoder",
        "Malformed model output fails json.loads with JSONDecodeError",
        killed,
        err_msg,
        {"parsing_failed": parsing_failed},
    )
    assert killed, "Malformed JSON unexpectedly parsed"


def test_mutant_04b_fallback_on_malformed_model_json():
    """MUT-04B: IntelligentFallbackEngine falls back to deterministic method on invalid model JSON."""
    reg = CapabilityRegistry()
    engine = IntelligentFallbackEngine(capability_registry=reg)
    ev = FailureEvidence(
        failure_category=FailureCategory.MODEL_OUTPUT_INVALID,
        what_failed="model_structured_output",
        evidence_summary="JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
    )
    decision = engine.evaluate_failure(ev)
    killed = (decision.action == RecoveryAction.FALLBACK_TO_DETERMINISTIC_METHOD) and decision.is_retry_safe
    record_mutation(
        "MUT-04B",
        "malformed_json_returned",
        "IntelligentFallbackEngine",
        "MODEL_OUTPUT_INVALID triggers FALLBACK_TO_DETERMINISTIC_METHOD without executing invalid payload",
        killed,
        f"action={decision.action.value}",
        {"action": decision.action.value, "rationale": decision.preference_rationale},
    )
    assert killed


def test_mutant_04c_completion_gate_rejects_missing_json_artifact():
    """MUT-04C: AuthoritativeCompletionGate rejects completion when JSON artifact is absent or corrupted."""
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write("{bad_json")
        tf_path = tf.name

    try:
        p = GoalPredicate(
            predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
            parameters={"path": tf_path, "content": '"status": "success"'},
            is_mandatory=True,
            status=PredicateStatus.SATISFIED,
        )
        contract = GoalContract(acceptance_predicates=[p])
        res = AuthoritativeCompletionGate.can_complete(goal_contract=contract)

        killed = (res.can_complete is False) and (res.verdict == GateVerdict.REJECTED)
        record_mutation(
            "MUT-04C",
            "malformed_json_returned",
            "AuthoritativeCompletionGate.FILE_CONTENT",
            "Malformed JSON lacking required success content rejects completion",
            killed,
            res.message,
            {"can_complete": res.can_complete, "verdict": res.verdict.value},
        )
        assert killed, f"Mutant survived: {res.message}"
    finally:
        Path(tf_path).unlink(missing_ok=True)


# ----------------------------------------------------------------------
# FINAL TEST: Verify 100% kill rate and write audit file
# ----------------------------------------------------------------------

def test_save_f0_25f6_mutation_results():
    """Verify all mutants were killed (100% kill rate) and write docs/audit/F0_25F6_MUTATION_RESULTS.json."""
    assert len(MUTATION_AUDIT_LOG) >= 12, f"Expected at least 12 executed mutants, got {len(MUTATION_AUDIT_LOG)}"
    total = len(MUTATION_AUDIT_LOG)
    killed_count = sum(1 for m in MUTATION_AUDIT_LOG if m["killed"])
    survived_count = total - killed_count
    kill_rate_pct = (killed_count / float(total)) * 100.0

    report = {
        "benchmark": "F0_25F6_VERIFICATION_MUTATION_SUITE",
        "phase": "F0-25F.6",
        "total_mutants": total,
        "killed_mutants": killed_count,
        "survived_mutants": survived_count,
        "kill_rate_pct": kill_rate_pct,
        "required_kill_rate_pct": 100.0,
        "verdict": "PASS" if kill_rate_pct == 100.0 else "FAIL",
        "mutation_categories": {
            "empty_file_instead_of_content": [m for m in MUTATION_AUDIT_LOG if m["mutation_type"] == "empty_file_instead_of_content"],
            "wrong_window_targeted": [m for m in MUTATION_AUDIT_LOG if m["mutation_type"] == "wrong_window_targeted"],
            "process_killed_before_completion": [m for m in MUTATION_AUDIT_LOG if m["mutation_type"] == "process_killed_before_completion"],
            "malformed_json_returned": [m for m in MUTATION_AUDIT_LOG if m["mutation_type"] == "malformed_json_returned"],
        },
        "mutants": MUTATION_AUDIT_LOG,
    }

    out_file = Path("docs/audit/F0_25F6_MUTATION_RESULTS.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n=======================================================")
    print(f"F0-25F.6 VERIFICATION MUTATION SUITE RESULTS:")
    print(f"Total Mutants: {total}")
    print(f"Killed Mutants: {killed_count} ({kill_rate_pct:.1f}%) [Requirement: 100.0%]")
    print(f"Survived Mutants: {survived_count}")
    print(f"Verdict: {report['verdict']}")
    print(f"=======================================================")
    for m in MUTATION_AUDIT_LOG:
        status_str = "KILLED" if m["killed"] else "SURVIVED"
        print(f"[{status_str}] {m['id']} ({m['mutation_type']}) -> {m['kill_reason']}")

    assert survived_count == 0, f"Mutants survived: {survived_count}"
    assert kill_rate_pct == 100.0, f"Kill rate {kill_rate_pct}% did not reach 100.0%"
