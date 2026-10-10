"""
tests/test_f0_21_adversarial_false_completion.py

Adversarial False-Completion Stress Suite for Phase F0-21 / F0-21A.
Deliberately creates scenarios where individual steps or capabilities return success
or create superficial artifacts, but the ground-truth GoalContract predicates remain false.

Mandatory Invariant:
    Under NO condition may a task transition to AgentTaskStatus.COMPLETED
    when any mandatory predicate is unsatisfied.
    Required False-Completion Rate: EXACTLY 0.0%.

Evidence Classification: SOURCE_TREE_TEST
"""

from __future__ import annotations

import tempfile
from pathlib import Path
import pytest

from astrarun.agent.loop import AgentExecutionEngine
from astrarun.agent.models import (
    AgentTask,
    AgentTaskStatus,
    ConstraintType,
    Goal,
    GoalContract,
    GoalPredicate,
    Plan,
    PlanStep,
    PredicateStatus,
    PredicateType,
    SemanticConstraint,
    StepState,
    VerifierStrategy,
)
from astrarun.agent.verifier import (
    FileContentContainsPredicate,
    FileContentEqualsPredicate,
    FileNonEmptyPredicate,
    GoalVerifier,
    StepVerifier,
)
from astrarun.capabilities.models import CapabilityResult
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.schema import InteractionTier
from astrarun.security.execution_broker import ExecutionBroker
from astrarun.security.action_gate import ActionGate


@pytest.fixture
def test_engine():
    reg = CapabilityRegistry()
    gate = ActionGate(capability_registry=reg)
    broker = ExecutionBroker(action_gate=gate)
    return AgentExecutionEngine(registry=reg, execution_broker=broker)


def test_adversarial_correct_filename_wrong_contents(test_engine):
    """Adversarial 1: Correct filename exists and is non-empty, but contains corrupted/wrong contents."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = Path(tmpdir) / "classified_doc.txt"
        target_path.write_text("CORRUPTED_WRONG_PAYLOAD_XYZ", encoding="utf-8")

        gc = GoalContract(
            original_utterance="create classified_doc.txt containing 'EXPECTED_AUTHORIZED_PAYLOAD'",
            objective="PRODUCE_DOCUMENT",
            target_artifact="classified_doc.txt",
            target_location=tmpdir,
            constraints=[
                SemanticConstraint(
                    constraint_type=ConstraintType.REQUIRED_CONTENT,
                    description="Expected payload",
                    target_key="content",
                    expected_value="EXPECTED_AUTHORIZED_PAYLOAD",
                    is_mandatory=True,
                )
            ],
            acceptance_predicates=[
                GoalPredicate(
                    predicate_type=PredicateType.FILE_EXISTS,
                    parameters={"path": str(target_path)},
                    is_mandatory=True,
                ),
                GoalPredicate(
                    predicate_type=PredicateType.FILE_NON_EMPTY,
                    parameters={"path": str(target_path)},
                    is_mandatory=True,
                ),
                GoalPredicate(
                    predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
                    parameters={"path": str(target_path), "contains": "EXPECTED_AUTHORIZED_PAYLOAD"},
                    is_mandatory=True,
                ),
            ],
        )

        verifier = GoalVerifier()
        eval_res = verifier.evaluate(gc)
        assert eval_res.completed is False, "GoalVerifier falsely accepted wrong file content!"

        # Now execute task with simulated steps returning SUCCESS
        goal = Goal(goal_id="adv_goal_1", raw_prompt="dummy", contract=gc)
        plan = Plan(plan_id="adv_plan_1", goal_id=goal.goal_id, contract=gc)
        step = PlanStep(
            step_id="step_1",
            capability_id="save_text_file",
            arguments={"path": str(target_path), "text": "CORRUPTED_WRONG_PAYLOAD_XYZ"},
            interaction_tier=InteractionTier.TIER_A_NATIVE,
            verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
        )
        plan.steps.append(step)

        task = AgentTask(task_id="adv_task_1", goal=goal, contract=gc, plan=plan)
        res_task = test_engine.run_task(task)

        assert res_task.status != AgentTaskStatus.COMPLETED, "CRITICAL: Task reached COMPLETED despite wrong contents!"
        assert res_task.status == AgentTaskStatus.FAILED


def test_adversarial_non_empty_wrong_content(test_engine):
    """Adversarial 2: Non-empty file exists (100+ bytes), but expected semantic token is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = Path(tmpdir) / "token.txt"
        target_path.write_text("A" * 500, encoding="utf-8")  # Large file, wrong data

        gc = GoalContract(
            original_utterance="save token.txt with token 'TOKEN_SECRET_999'",
            objective="PRODUCE_DOCUMENT",
            target_artifact="token.txt",
            constraints=[
                SemanticConstraint(
                    constraint_type=ConstraintType.REQUIRED_CONTENT,
                    description="Secret token",
                    target_key="content",
                    expected_value="TOKEN_SECRET_999",
                    is_mandatory=True,
                )
            ],
            acceptance_predicates=[
                GoalPredicate(
                    predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
                    parameters={"path": str(target_path), "contains": "TOKEN_SECRET_999"},
                    is_mandatory=True,
                )
            ],
        )

        goal = Goal(goal_id="adv_goal_2", raw_prompt="dummy", contract=gc)
        plan = Plan(plan_id="adv_plan_2", goal_id=goal.goal_id, contract=gc)
        plan.steps.append(
            PlanStep(
                step_id="step_1",
                capability_id="save_text_file",
                arguments={"path": str(target_path), "text": "A" * 500},
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
            )
        )

        task = AgentTask(task_id="adv_task_2", goal=goal, contract=gc, plan=plan)
        res_task = test_engine.run_task(task)

        assert res_task.status == AgentTaskStatus.FAILED
        assert "TOKEN_SECRET_999" in (res_task.error or "")


def test_adversarial_artifact_in_wrong_directory(test_engine):
    """Adversarial 3: Artifact was created with correct name and content, but in the WRONG directory."""
    with tempfile.TemporaryDirectory() as expected_dir, tempfile.TemporaryDirectory() as wrong_dir:
        expected_path = Path(expected_dir) / "output.txt"
        wrong_path = Path(wrong_dir) / "output.txt"
        # Write to wrong directory
        wrong_path.write_text("correct_data", encoding="utf-8")

        gc = GoalContract(
            original_utterance="save output.txt in expected directory",
            objective="PRODUCE_DOCUMENT",
            target_artifact="output.txt",
            target_location=str(expected_dir),
            acceptance_predicates=[
                GoalPredicate(
                    predicate_type=PredicateType.FILE_EXISTS,
                    parameters={"path": str(expected_path)},
                    is_mandatory=True,
                )
            ],
        )

        goal = Goal(goal_id="adv_goal_3", raw_prompt="dummy", contract=gc)
        plan = Plan(plan_id="adv_plan_3", goal_id=goal.goal_id, contract=gc)
        plan.steps.append(
            PlanStep(
                step_id="step_1",
                capability_id="save_text_file",
                arguments={"path": str(wrong_path), "text": "correct_data"},
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
            )
        )

        task = AgentTask(task_id="adv_task_3", goal=goal, contract=gc, plan=plan)
        res_task = test_engine.run_task(task)

        assert res_task.status == AgentTaskStatus.FAILED
        assert str(expected_path) in (res_task.error or "")


def test_adversarial_capability_success_but_state_unchanged(test_engine):
    """Adversarial 4: Capability claims success, but created file is 0 bytes (empty)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        empty_path = Path(tmpdir) / "empty.txt"
        empty_path.write_bytes(b"")  # 0 bytes

        gc = GoalContract(
            original_utterance="create non-empty file empty.txt",
            objective="PRODUCE_DOCUMENT",
            target_artifact="empty.txt",
            acceptance_predicates=[
                GoalPredicate(
                    predicate_type=PredicateType.FILE_NON_EMPTY,
                    parameters={"path": str(empty_path)},
                    is_mandatory=True,
                )
            ],
        )

        goal = Goal(goal_id="adv_goal_4", raw_prompt="dummy", contract=gc)
        plan = Plan(plan_id="adv_plan_4", goal_id=goal.goal_id, contract=gc)
        plan.steps.append(
            PlanStep(
                step_id="step_1",
                capability_id="save_text_file",
                arguments={"path": str(empty_path), "text": ""},
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
            )
        )

        task = AgentTask(task_id="adv_task_4", goal=goal, contract=gc, plan=plan)
        res_task = test_engine.run_task(task)

        assert res_task.status == AgentTaskStatus.FAILED
        assert "0 bytes" in (res_task.error or "")


def test_adversarial_intermediate_step_succeeds_final_predicate_false(test_engine):
    """Adversarial 5: Multi-step pipeline where all intermediate steps return success, but goal predicate fails."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = Path(tmpdir) / "pipeline_artifact.txt"
        # File is not created at all

        gc = GoalContract(
            original_utterance="multi step pipeline ending in file creation",
            objective="PRODUCE_DOCUMENT",
            target_artifact="pipeline_artifact.txt",
            acceptance_predicates=[
                GoalPredicate(
                    predicate_type=PredicateType.FILE_EXISTS,
                    parameters={"path": str(target_path)},
                    is_mandatory=True,
                )
            ],
        )

        goal = Goal(goal_id="adv_goal_5", raw_prompt="dummy", contract=gc)
        plan = Plan(plan_id="adv_plan_5", goal_id=goal.goal_id, contract=gc)
        # Step 1 succeeds
        plan.steps.append(
            PlanStep(
                step_id="step_1",
                capability_id="list_directory",
                arguments={"path": tmpdir},
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
            )
        )

        task = AgentTask(task_id="adv_task_5", goal=goal, contract=gc, plan=plan)
        res_task = test_engine.run_task(task)

        assert res_task.status == AgentTaskStatus.FAILED


def test_adversarial_ui_element_state_mismatch():
    """Adversarial 6: UI text state verifier rejects when target window does not display expected text."""
    verifier = StepVerifier()
    step = PlanStep(
        step_id="step_ui",
        capability_id="type_into_window",
        arguments={"text": "UNIQUE_NONEXISTENT_UI_PAYLOAD_9999", "hwnd": 999999},
        interaction_tier=InteractionTier.TIER_C_UI_AUTOMATION,
        verifier_strategy=VerifierStrategy.UI_ELEMENT_STATE,
        verifier_params={"text": "UNIQUE_NONEXISTENT_UI_PAYLOAD_9999", "hwnd": 999999},
    )
    # Mock capability result returning success
    cap_res = CapabilityResult.ok(capability="type_into_window", message="Entered 34 characters.", data={"length": 0})

    ver = verifier.verify(step, cap_res)
    assert ver.verified is False, "UI_ELEMENT_STATE falsely verified nonexistent text!"
    assert "UNIQUE_NONEXISTENT_UI_PAYLOAD_9999" in ver.message
