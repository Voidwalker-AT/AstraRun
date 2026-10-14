"""Unit verification for F0-25F.4 Verification Strategies & Semantic File Verification."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest

from astrarun.agent.models import (
    GoalContract,
    GoalPredicate,
    PlanStep,
    PredicateStatus,
    PredicateType,
)
from astrarun.agent.planner import GoalPlanner
from astrarun.agent.verifier import (
    FileContentContainsPredicate,
    FileContentEqualsPredicate,
    FileExistsPredicate,
    FileNonEmptyPredicate,
    GoalVerifier,
    StepVerifier,
)
from astrarun.capabilities.models import CapabilityResult
from astrarun.capabilities.schema import VerifierStrategy
from astrarun.core.telemetry import CausalTelemetry


def test_step_verifier_rejects_return_code_only():
    """StepVerifier fail-closed rejects RETURN_CODE_ONLY as dispatch-level only."""
    verifier = StepVerifier()
    step = PlanStep(
        step_id="step_1",
        capability_id="execute_dynamic_tool",
        verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
    )
    res = CapabilityResult.ok("execute_dynamic_tool", "Succeeded", data={"exit_code": 0})
    verif = verifier.verify(step, res)

    assert not verif.verified
    assert "RETURN_CODE_ONLY is insufficient" in verif.message


def test_step_verifier_file_exists():
    """StepVerifier correctly checks FILE_EXISTS on disk."""
    verifier = StepVerifier()
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write("hello")
        p = tf.name

    try:
        step = PlanStep(
            step_id="step_1",
            capability_id="write_file",
            verifier_strategy=VerifierStrategy.FILE_EXISTS,
            verifier_params={"path": p},
        )
        res = CapabilityResult.ok("write_file", "Written", data={"path": p})
        verif = verifier.verify(step, res)
        assert verif.verified
        assert "Verified file exists" in verif.message

        # Nonexistent file
        step_missing = PlanStep(
            step_id="step_1",
            capability_id="write_file",
            verifier_strategy=VerifierStrategy.FILE_EXISTS,
            verifier_params={"path": p + ".nonexistent"},
        )
        res_missing = CapabilityResult.ok("write_file", "Written", data={"path": p + ".nonexistent"})
        verif_missing = verifier.verify(step_missing, res_missing)
        assert not verif_missing.verified
        assert "does not exist" in verif_missing.message
    finally:
        Path(p).unlink(missing_ok=True)


def test_step_verifier_file_non_empty():
    """StepVerifier checks FILE_NON_EMPTY: fails on 0-byte, passes on >0 bytes."""
    verifier = StepVerifier()
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        p = tf.name

    try:
        # Initially 0 bytes
        step = PlanStep(
            step_id="step_1",
            capability_id="write_file",
            verifier_strategy=VerifierStrategy.FILE_NON_EMPTY,
            verifier_params={"path": p},
        )
        res = CapabilityResult.ok("write_file", "Written", data={"path": p})
        verif_empty = verifier.verify(step, res)
        assert not verif_empty.verified
        assert "is empty (0 bytes)" in verif_empty.message

        # Write data
        Path(p).write_text("some content", encoding="utf-8")
        verif_non_empty = verifier.verify(step, res)
        assert verif_non_empty.verified
        assert "Verified file exists and is non-empty" in verif_non_empty.message
    finally:
        Path(p).unlink(missing_ok=True)


def test_step_verifier_file_contains():
    """StepVerifier checks FILE_CONTAINS: fails if token absent, passes if token present."""
    verifier = StepVerifier()
    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write("The quick brown fox jumps over the lazy dog")
        p = tf.name

    try:
        step_match = PlanStep(
            step_id="step_1",
            capability_id="write_file",
            verifier_strategy=VerifierStrategy.FILE_CONTAINS,
            verifier_params={"path": p, "contains": "brown fox"},
        )
        res = CapabilityResult.ok("write_file", "Written", data={"path": p})
        verif_match = verifier.verify(step_match, res)
        assert verif_match.verified
        assert "File contains required substring" in verif_match.message

        step_no_match = PlanStep(
            step_id="step_1",
            capability_id="write_file",
            verifier_strategy=VerifierStrategy.FILE_CONTAINS,
            verifier_params={"path": p, "contains": "blue elephant"},
        )
        verif_no_match = verifier.verify(step_no_match, res)
        assert not verif_no_match.verified
        assert "File did not contain required substring" in verif_no_match.message
    finally:
        Path(p).unlink(missing_ok=True)


def test_goal_verifier_semantic_predicates():
    """GoalVerifier verifies typed file predicates and attaches active run_id and task_id."""
    telem = CausalTelemetry.get_instance()
    run_id = telem.start_run(query="Semantic verification test", task_id="task_sem_verif")

    with tempfile.NamedTemporaryFile("w", delete=False) as tf:
        tf.write("Fibonacci: 0, 1, 1, 2, 3, 5, 8, 13, 21, 34")
        p = tf.name

    try:
        p1 = GoalPredicate(
            predicate_id="pred_exists",
            predicate_type=PredicateType.FILE_EXISTS,
            parameters={"path": p},
            is_mandatory=True,
        )
        p2 = GoalPredicate(
            predicate_id="pred_non_empty",
            predicate_type=PredicateType.FILE_NON_EMPTY,
            parameters={"path": p},
            is_mandatory=True,
        )
        p3 = GoalPredicate(
            predicate_id="pred_content",
            predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
            parameters={"path": p, "contains": "34"},
            is_mandatory=True,
        )
        contract = GoalContract(original_utterance="Compute fibonacci", acceptance_predicates=[p1, p2, p3])

        gv = GoalVerifier()
        result = gv.evaluate(contract)

        assert p1.status == PredicateStatus.SATISFIED
        assert p2.status == PredicateStatus.SATISFIED
        assert p3.status == PredicateStatus.SATISFIED
        assert p1.evidence.get("run_id") == run_id
        assert p1.evidence.get("task_id") == "task_sem_verif"
    finally:
        Path(p).unlink(missing_ok=True)
        telem.end_run(status="SUCCESS", goal_contract=contract)


def test_planner_derives_semantic_verifier_strategy():
    """GoalPlanner derives FILE_NON_EMPTY / FILE_CONTAINS from goal contract instead of RETURN_CODE_ONLY."""
    planner = GoalPlanner()
    goal = planner.parse_goal("compute first 50 fibonacci numbers and save to fibonacci.txt and reveal in explorer")
    plan = planner.create_plan(goal)

    step_1 = plan.steps[0]
    assert step_1.capability_id == "execute_dynamic_tool"
    assert step_1.verifier_strategy in (VerifierStrategy.FILE_NON_EMPTY, VerifierStrategy.FILE_CONTAINS)
    assert step_1.verifier_strategy != VerifierStrategy.RETURN_CODE_ONLY
