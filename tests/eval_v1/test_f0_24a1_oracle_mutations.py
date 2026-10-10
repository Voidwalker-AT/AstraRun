"""Mutation tests for F0-24A.1 oracle predicates.

Deliberately weaken representative predicates and prove the adversarial suite
(oracles) kill the mutations. Record kill evidence in returned structures.

Evidence class: SOURCE_TREE_TEST
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from astrarun.agent.models import GoalContract, GoalPredicate, PredicateType
from astrarun.agent.verifier import GoalVerifier, StepVerifier, FileNonEmptyPredicate, FileExistsPredicate
from astrarun.capabilities.models import CapabilityResult
from astrarun.capabilities.schema import VerifierStrategy
from astrarun.agent.models import PlanStep
from astrarun.evaluation.execution_truth import (
    evaluate_resource_cleanup,
    assert_pass_rate_not_fabricated,
    summarize_case_outcomes,
)


def test_mutation_file_exists_instead_of_non_empty_is_killed():
    """Weakened oracle: FILE_EXISTS only, empty file present."""
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "x.txt"
        empty.write_text("", encoding="utf-8")
        # Mutation: only FILE_EXISTS
        weak_ok = FileExistsPredicate(empty).evaluate({})[0]
        assert weak_ok is True  # mutation is present
        # Strong predicate kills it
        strong_ok = FileNonEmptyPredicate(empty).evaluate({})[0]
        assert strong_ok is False


def test_mutation_skip_content_verification_is_killed():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "x.txt"
        path.write_text("WRONG", encoding="utf-8")
        gc_exists_only = GoalContract(
            "gc",
            "save",
            "PRODUCE_DOCUMENT",
            acceptance_predicates=[
                GoalPredicate(predicate_type=PredicateType.FILE_EXISTS, parameters={"path": str(path)}, is_mandatory=True),
            ],
        )
        gc_with_content = GoalContract(
            "gc",
            "save",
            "PRODUCE_DOCUMENT",
            acceptance_predicates=[
                GoalPredicate(
                    predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
                    parameters={"path": str(path), "contains": "hello"},
                    is_mandatory=True,
                )
            ],
        )
        v = GoalVerifier()
        # Mutation path (exists-only) completes — dangerous if used alone.
        assert v.evaluate(gc_exists_only).completed is True
        # Content-aware oracle kills the mutation.
        assert v.evaluate(gc_with_content).completed is False


def test_mutation_ignore_process_cleanup_is_killed():
    # Mutation: treat empty/partial resource_delta as clean (historical oracle behavior)
    historical_empty_delta_clean = True  # mutation
    stage = evaluate_resource_cleanup(None)
    assert stage.satisfied is False
    assert historical_empty_delta_clean is True  # documents the mutation
    # Strong oracle kills incomplete evidence and remaining process
    for incomplete in ({}, {"cleanup_executed": True}, {"process_cleaned_up": True}, {"orphaned_processes": 0}):
        assert evaluate_resource_cleanup(incomplete).satisfied is False
    assert evaluate_resource_cleanup({"process_cleaned_up": False}).satisfied is False
    assert (
        evaluate_resource_cleanup(
            {
                "resources_owned": True,
                "process_cleanup_required": True,
                "process_residue_measured": True,
                "window_residue_measured": True,
                "ledger_residue_measured": True,
                "cleanup_executed": True,
                "process_cleaned_up": False,
                "orphaned_processes": 1,
                "orphaned_windows": 0,
                "active_ledger_resources": 0,
            }
        ).satisfied
        is False
    )


def test_mutation_treat_action_dispatch_as_success_is_killed():
    out = StepVerifier().verify(
        PlanStep(
            step_id="s1",
            capability_id="type_into_window",
            description="type",
            verifier_strategy=VerifierStrategy.UI_ELEMENT_STATE,
            verifier_params={"text": "hello"},
            arguments={"text": "hello"},
        ),
        CapabilityResult(success=True, capability="type_into_window", message="dispatched", data={"length": 5}),
    )
    # Mutation would set verified=True on length>0; hardening requires observation.
    assert out.verified is False


def test_mutation_accept_wrong_application_identity_is_killed():
    from astrarun.evaluation.acceptance_model import (
        AcceptanceDimension,
        AcceptancePredicate,
        FormalAcceptanceOracle,
    )

    # Mutation: no entity predicates => vacuous pass (historical)
    oracle = FormalAcceptanceOracle()
    report = oracle.evaluate(
        "id",
        "open app",
        GoalContract("gc", "open app", "LAUNCH"),
        plan=None,
        execution_trace=[{"ok": True}],
        resource_delta={
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
        },
        custom_predicates=[
            AcceptancePredicate(
                "e",
                "entity",
                AcceptanceDimension.ENTITY_CORRECTNESS,
                "psutil",
                "eval",
                "wrong app",
                is_mandatory=True,
                satisfied=False,
            )
        ],
    )
    assert report.passed is False
    assert report.dimensions["ENTITY_CORRECTNESS"].passed is False


def test_mutation_pass_rate_100_from_119_of_120_is_killed():
    violations = assert_pass_rate_not_fabricated(119, 120, 100.0)
    assert violations, "fabricated 100% must be flagged"
    summary = summarize_case_outcomes(
        [{"passed": True}] * 119 + [{"passed": False}]
    )
    assert summary["fraction"] == "119/120"
    assert assert_pass_rate_not_fabricated(119, 120, 100.0)


def test_mutation_return_code_only_completion_is_killed():
    out = StepVerifier().verify(
        PlanStep(
            step_id="s1",
            capability_id="save_text_file",
            description="save",
            verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
        ),
        CapabilityResult(success=True, capability="save_text_file", message="ok", data={}),
    )
    assert out.verified is False
