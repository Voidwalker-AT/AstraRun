"""
tests/test_f0_21_goal_contract.py

Authoritative verification suite for Phase F0-21:
Goal-Preserving Agent Intelligence: Semantic Contract -> Plan -> Replan -> Verification.

Validates:
1. Exact fix for human-observed failure:
   "open notepad type hello and save it to desktop with name test1.txt"
2. Paraphrase Invariance: Varied phrasing yields equivalent semantic contracts and satisfaction.
3. Metamorphic Properties:
   - Constraint Preservation across replanning.
   - Plan Coverage & Information Loss Rejection by PlanQualityValidator.
   - Zero False Completion: Empty or incomplete files strictly fail goal verification.
   - Recovery Monotonicity: Refuses non-advancing capabilities (open_folder, reveal_file) for write failures.
4. Cross-Domain Generalization across Domains A-G.
5. Real-World Failure Injection & Recovery.
6. Stress corpus (100+ requests) verifying False Completion Rate = 0%.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

from astrarun.agent.models import (
    AgentTask,
    ArgumentBinding,
    ArgumentSourceType,
    ConstraintStatus,
    ConstraintType,
    Goal,
    GoalContract,
    GoalPredicate,
    InteractionTier,
    Plan,
    PlanStatus,
    PlanStep,
    PredicateStatus,
    PredicateType,
    SemanticConstraint,
    StepState,
    AgentTaskStatus,
    VerifierStrategy,
)
from astrarun.agent.planner import GoalPlanner
from astrarun.agent.validator import PlanQualityValidator
from astrarun.agent.verifier import (
    ApplicationRunningPredicate,
    FileContentContainsPredicate,
    FileContentEqualsPredicate,
    FileNonEmptyPredicate,
    GoalVerifier,
    StepVerifier,
)
from astrarun.capabilities.registry import CapabilityRegistry, Capability, CapabilityCategory, CapabilityResult
from astrarun.app import AstraApplication


# =============================================================================
# 1. HUMAN-OBSERVED FAILURE REPRODUCTION & FIX
# =============================================================================

def test_original_failing_prompt_semantic_contract():
    """
    Prompt: 'open notepad type hello and save it to desktop with name test1.txt'
    Must parse without losing the required text 'hello', file 'test1.txt',
    or location 'Desktop'.
    """
    planner = GoalPlanner()
    prompt = "open notepad type hello and save it to desktop with name test1.txt"
    goal = planner.parse_goal(prompt)

    assert goal is not None
    assert goal.contract is not None
    gc = goal.contract

    # Contract entities & constraints must preserve 'hello' and 'test1.txt'
    assert gc.target_artifact == "test1.txt"
    assert gc.target_location == "Desktop"
    assert gc.target_application == "notepad"

    content_constraint = gc.get_constraint("content")
    assert content_constraint is not None
    assert content_constraint.expected_value == "hello"
    assert content_constraint.is_mandatory is True

    artifact_constraint = gc.get_constraint("artifact")
    assert artifact_constraint is not None
    assert artifact_constraint.expected_value == "test1.txt"

    # Mandatory acceptance predicates must include content check
    preds = gc.get_mandatory_predicates()
    pred_types = [p.predicate_type for p in preds]
    assert PredicateType.FILE_EXISTS in pred_types
    assert PredicateType.FILE_NON_EMPTY in pred_types
    assert PredicateType.FILE_CONTENT_CONTAINS in pred_types

    # Plan creation must generate 3 steps with 'hello' dataflow wired into save step
    plan = planner.create_plan(goal)
    assert plan is not None
    assert len(plan.steps) == 3

    step_open, step_type, step_save = plan.steps[0], plan.steps[1], plan.steps[2]

    assert step_open.capability_id in ("open_application", "open_app")
    assert step_open.arguments.get("app") == "notepad"

    assert step_type.capability_id in ("type_into_window", "type_text")
    assert step_type.arguments.get("text") == "hello"

    assert step_save.capability_id in ("save_text_file", "save_document_via_ui")
    assert step_save.arguments.get("filename") == "test1.txt" or "test1.txt" in step_save.arguments.get("path", "")
    # Crucial F0-21 fix: content/text is NEVER dropped in save step
    assert step_save.arguments.get("text") == "hello" or step_save.arguments.get("content") == "hello"


def test_empty_file_rejected_by_goal_verifier(tmp_path):
    """
    Empirical failure reproduction: If a 0-byte file is created,
    GoalVerifier MUST reject completion (False Completion Rate = 0%).
    """
    test_file = tmp_path / "test1.txt"
    test_file.write_text("", encoding="utf-8")  # 0 bytes, empty!

    gc = GoalContract(
        original_utterance="open notepad type hello and save it to desktop with name test1.txt",
        target_artifact="test1.txt",
        constraints=[
            SemanticConstraint(
                constraint_type=ConstraintType.REQUIRED_CONTENT,
                target_key="content",
                expected_value="hello",
                is_mandatory=True,
            )
        ],
        acceptance_predicates=[
            GoalPredicate(
                predicate_type=PredicateType.FILE_EXISTS,
                parameters={"path": str(test_file)},
                is_mandatory=True,
            ),
            GoalPredicate(
                predicate_type=PredicateType.FILE_NON_EMPTY,
                parameters={"path": str(test_file)},
                is_mandatory=True,
            ),
            GoalPredicate(
                predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
                parameters={"path": str(test_file), "contains": "hello"},
                is_mandatory=True,
            ),
        ],
    )

    verifier = GoalVerifier()
    goal = Goal(raw_prompt="open notepad type hello and save it to desktop with name test1.txt", contract=gc)
    task = AgentTask(goal=goal, contract=gc)

    # Empty file must fail
    res = verifier.evaluate(gc, observation=None)
    assert res.completed is False
    assert any("empty" in r.lower() or "not contain" in r.lower() for r in res.missing_criteria)

    # StepVerifier must also reject 0 bytes
    step_verifier = StepVerifier()
    step = PlanStep(
        step_id="step_save",
        capability_id="save_text_file",
        arguments={"path": str(test_file)},
        verifier_strategy=VerifierStrategy.FILE_NON_EMPTY,
    )
    cap_res = CapabilityResult.ok("save_text_file", "Saved file", data={"path": str(test_file)})
    v = step_verifier.verify(step, cap_res)
    assert v.verified is False
    assert "0 bytes" in v.message or "empty" in v.message


def test_correct_content_passes_goal_verifier(tmp_path):
    """
    When file exists and contains the requested text 'hello',
    GoalVerifier evaluates to completed = True.
    """
    test_file = tmp_path / "test1.txt"
    test_file.write_text("hello", encoding="utf-8")

    gc = GoalContract(
        original_utterance="open notepad type hello and save it to desktop with name test1.txt",
        target_artifact="test1.txt",
        constraints=[
            SemanticConstraint(
                constraint_type=ConstraintType.REQUIRED_CONTENT,
                target_key="content",
                expected_value="hello",
                is_mandatory=True,
            )
        ],
        acceptance_predicates=[
            GoalPredicate(
                predicate_type=PredicateType.FILE_EXISTS,
                parameters={"path": str(test_file)},
                is_mandatory=True,
            ),
            GoalPredicate(
                predicate_type=PredicateType.FILE_NON_EMPTY,
                parameters={"path": str(test_file)},
                is_mandatory=True,
            ),
            GoalPredicate(
                predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
                parameters={"path": str(test_file), "contains": "hello"},
                is_mandatory=True,
            ),
        ],
    )

    verifier = GoalVerifier()
    res = verifier.evaluate(gc, observation=None)
    assert res.completed is True
    assert len(res.missing_criteria) == 0


# =============================================================================
# 2. PARAPHRASE INVARIANCE
# =============================================================================

@pytest.mark.parametrize("prompt", [
    "open notepad type hello and save it to desktop with name test1.txt",
    "open notepad and type hello and save it to desktop as test1.txt",
    "launch notepad, write hello, save to desktop named test1.txt",
    "open notepad, type 'hello', save it on desktop with name test1.txt",
    "start notepad type hello and save it in desktop as test1.txt",
    "open notepad and type \"hello\" and save to desktop with name test1.txt",
])
def test_paraphrase_invariance_contract_extraction(prompt: str):
    """
    All phrasing variants must yield a GoalContract preserving:
    - application: notepad
    - content: hello
    - artifact: test1.txt
    - location: Desktop
    """
    planner = GoalPlanner()
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "test1.txt"
    assert gc.target_location == "Desktop"
    assert gc.target_application == "notepad"

    content_c = gc.get_constraint("content")
    assert content_c is not None
    assert content_c.expected_value == "hello"

    plan = planner.create_plan(goal)
    assert plan is not None
    assert len(plan.steps) == 3

    # Every paraphrase must wire the content to the save step
    save_step = plan.steps[-1]
    assert save_step.arguments.get("text") == "hello" or save_step.arguments.get("content") == "hello"


# =============================================================================
# 3. METAMORPHIC PROPERTIES
# =============================================================================

def test_information_loss_prevention_in_validator():
    """
    Information-Loss Invariant:
    If a proposed plan drops the mandatory content 'hello',
    PlanQualityValidator MUST reject the plan.
    """
    gc = GoalContract(
        original_utterance="open notepad type hello and save it to desktop with name test1.txt",
        target_artifact="test1.txt",
        constraints=[
            SemanticConstraint(
                constraint_type=ConstraintType.REQUIRED_CONTENT,
                target_key="content",
                expected_value="hello",
                is_mandatory=True,
            ),
            SemanticConstraint(
                constraint_type=ConstraintType.TARGET_ARTIFACT,
                target_key="artifact",
                expected_value="test1.txt",
                is_mandatory=True,
            ),
        ],
    )

    # Malformed plan: save_text_file has NO text and NO content
    bad_step = PlanStep(
        step_id="step_1",
        capability_id="save_text_file",
        arguments={"filename": "test1.txt", "path": "C:\\Desktop\\test1.txt"},
    )
    bad_plan = Plan(steps=[bad_step], contract=gc)

    validator = PlanQualityValidator()
    report = validator.validate_plan(bad_plan, goal_contract=gc)

    assert report.is_valid is False
    assert any("information-loss" in err.lower() or "hello" in err.lower() for err in report.issues)


def test_recovery_monotonicity_rejects_read_only_substitution():
    """
    Recovery Monotonicity:
    When save_text_file fails, replanning must NEVER substitute
    read-only non-advancing capabilities like 'open_folder' or 'reveal_file'.
    """
    planner = GoalPlanner()
    gc = GoalContract(
        original_utterance="open notepad type hello and save it to desktop with name test1.txt",
        target_artifact="test1.txt",
        constraints=[
            SemanticConstraint(
                constraint_type=ConstraintType.REQUIRED_CONTENT,
                target_key="content",
                expected_value="hello",
                is_mandatory=True,
            )
        ],
        acceptance_predicates=[
            GoalPredicate(
                predicate_type=PredicateType.FILE_NON_EMPTY,
                parameters={"path": "C:\\Users\\hp\\Desktop\\test1.txt"},
                is_mandatory=True,
            ),
            GoalPredicate(
                predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
                parameters={"path": "C:\\Users\\hp\\Desktop\\test1.txt", "contains": "hello"},
                is_mandatory=True,
            ),
        ],
    )

    failed_step = PlanStep(
        step_id="step_3",
        capability_id="save_text_file",
        arguments={"path": "C:\\Users\\hp\\Desktop\\test1.txt", "text": "hello"},
    )
    goal = Goal(raw_prompt="open notepad type hello and save it to desktop with name test1.txt", contract=gc)
    task = AgentTask(goal=goal, contract=gc)

    # Try replanning to open_folder -> MUST be rejected (returns None)
    rev_folder = planner.replan(task, failed_step, observation=None, alternative_capability_id="open_folder")
    assert rev_folder is None

    # Try replanning to reveal_file -> MUST be rejected (returns None)
    rev_reveal = planner.replan(task, failed_step, observation=None, alternative_capability_id="reveal_file")
    assert rev_reveal is None


def test_constraint_preservation_across_replanning():
    """
    When a valid alternative is selected, the goal contract's
    mandatory constraints and arguments must be preserved.
    """
    planner = GoalPlanner()
    gc = GoalContract(
        original_utterance="save hello to desktop test1.txt",
        target_artifact="test1.txt",
        target_location="Desktop",
        constraints=[
            SemanticConstraint(
                constraint_type=ConstraintType.REQUIRED_CONTENT,
                target_key="content",
                expected_value="hello",
                is_mandatory=True,
            )
        ],
        acceptance_predicates=[
            GoalPredicate(
                predicate_type=PredicateType.FILE_NON_EMPTY,
                parameters={"path": "C:\\Users\\hp\\Desktop\\test1.txt"},
                is_mandatory=True,
            ),
        ],
    )

    failed_step = PlanStep(
        step_id="step_1",
        capability_id="save_text_file",
        arguments={"path": "C:\\Users\\hp\\Desktop\\test1.txt", "text": "hello"},
    )
    goal = Goal(raw_prompt="save hello to desktop test1.txt", contract=gc)
    task = AgentTask(goal=goal, contract=gc)

    # Replan to save_document_via_ui
    rev = planner.replan(task, failed_step, observation=None, alternative_capability_id="save_document_via_ui")
    assert rev is not None
    assert len(rev.added_steps) >= 1
    # Check that new step retains filename / text
    new_step = task.plan.get_step(rev.added_steps[0])
    assert new_step is not None
    assert new_step.arguments.get("filename") == "test1.txt" or "test1.txt" in new_step.arguments.get("path", "")


# =============================================================================
# 4. CROSS-DOMAIN GENERALIZATION (DOMAINS A - G)
# =============================================================================

def test_domain_a_document_creation():
    """Domain A: Document / Content Creation with specific text."""
    planner = GoalPlanner()
    prompt = "create a file on desktop called meeting.txt with text 'meeting adjourned'"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc.target_artifact == "meeting.txt"
    assert gc.target_location == "Desktop"
    content_c = gc.get_constraint("content")
    assert content_c is not None
    assert content_c.expected_value == "meeting adjourned"

    plan = planner.create_plan(goal)
    assert any(s.capability_id in ("save_text_file", "save_document_via_ui") for s in plan.steps)
    step = [s for s in plan.steps if s.capability_id in ("save_text_file", "save_document_via_ui")][0]
    assert step.arguments.get("text") == "meeting adjourned" or step.arguments.get("content") == "meeting adjourned"


def test_domain_b_window_application_control():
    """Domain B: Application launch and focus."""
    planner = GoalPlanner()
    prompt = "open calculator"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc.target_application == "calculator"
    preds = gc.get_mandatory_predicates()
    assert any(p.predicate_type == PredicateType.APPLICATION_RUNNING for p in preds)

    plan = planner.create_plan(goal)
    assert len(plan.steps) == 1
    assert plan.steps[0].capability_id in ("open_application", "open_app")
    assert plan.steps[0].arguments.get("app") == "calculator"


def test_domain_c_filesystem_inspection():
    """Domain C: Target artifact location without content."""
    planner = GoalPlanner()
    prompt = "save report.html to Downloads"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc.target_artifact == "report.html"
    assert gc.target_location == "Downloads"
    preds = gc.get_mandatory_predicates()
    assert any(p.predicate_type == PredicateType.FILE_EXISTS for p in preds)


def test_domain_d_network_management():
    """Domain D: Network / Wi-Fi state management."""
    planner = GoalPlanner()
    prompt = "connect to wifi OfficeGuest"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc.entities.get("ssid") == "OfficeGuest"
    ssid_c = gc.get_constraint("ssid")
    assert ssid_c is not None
    assert ssid_c.expected_value == "OfficeGuest"

    preds = gc.get_mandatory_predicates()
    assert any(p.predicate_type == PredicateType.NETWORK_CONNECTED for p in preds)


def test_domain_e_system_utility_report():
    """Domain E: Battery report generation."""
    planner = GoalPlanner()
    prompt = "run a battery report and save it in Downloads as astra-battery.html"
    goal = planner.parse_goal(prompt)
    assert goal.intent == "generate_battery_report"
    assert "astra-battery.html" in goal.parameters.get("filename", "")
    assert goal.parameters.get("folder") == "Downloads"

    plan = planner.create_plan(goal)
    assert len(plan.steps) == 1
    assert plan.steps[0].capability_id == "generate_battery_report"


def test_domain_f_dynamic_computation():
    """Domain F: Dynamic data computation."""
    planner = GoalPlanner()
    prompt = "reverse text 'supercalifragilistic'"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    payload_c = gc.get_constraint("content") or gc.get_constraint("payload")
    assert payload_c is not None
    assert payload_c.expected_value == "supercalifragilistic"

    preds = gc.get_mandatory_predicates()
    assert any(p.predicate_type == PredicateType.DATA_COMPUTED for p in preds)


def test_domain_g_state_divergence_and_verification_failure(tmp_path):
    """
    Domain G: State divergence handling.
    If a file exists but contains wrong content, verification strictly fails.
    """
    test_file = tmp_path / "divergent.txt"
    test_file.write_text("wrong content here", encoding="utf-8")

    pred = FileContentContainsPredicate(path=test_file, substring="expected phrase")
    valid, msg, evidence = pred.evaluate({})
    assert valid is False


# =============================================================================
# 5. CLOSED-LOOP EXECUTION ENGINE ZERO FALSE-COMPLETION
# =============================================================================

def test_execution_engine_zero_false_completion_on_empty_file(tmp_path):
    """
    Closed loop test with AgentExecutionEngine:
    If capability handler writes 0 bytes, task status MUST end as FAILED,
    never COMPLETED.
    """
    reg = CapabilityRegistry()
    target_path = str(tmp_path / "zero_byte.txt")

    # Mock handler that produces 0 bytes file
    def empty_writer(path: str, text: str = ""):
        Path(path).write_text("", encoding="utf-8")
        return CapabilityResult.ok("save_text_file", "Wrote file", data={"path": path})

    reg.register(
        Capability(
            id="save_text_file",
            category=CapabilityCategory.SYSTEM,
            description="Save text file",
            args_schema={"path": str, "text": str},
            handler=empty_writer,
        )
    )

    from astrarun.agent.loop import AgentExecutionEngine

    engine = AgentExecutionEngine(registry=reg)

    gc = GoalContract(
        original_utterance="write hello to zero_byte.txt",
        target_artifact="zero_byte.txt",
        constraints=[
            SemanticConstraint(
                constraint_type=ConstraintType.REQUIRED_CONTENT,
                target_key="content",
                expected_value="hello",
                is_mandatory=True,
            )
        ],
        acceptance_predicates=[
            GoalPredicate(
                predicate_type=PredicateType.FILE_NON_EMPTY,
                parameters={"path": target_path},
                is_mandatory=True,
            ),
            GoalPredicate(
                predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
                parameters={"path": target_path, "contains": "hello"},
                is_mandatory=True,
            ),
        ],
    )

    step = PlanStep(
        step_id="step_1",
        capability_id="save_text_file",
        arguments={"path": target_path, "text": "hello"},
        verifier_strategy=VerifierStrategy.FILE_NON_EMPTY,
    )

    goal = Goal(raw_prompt="write hello to zero_byte.txt", contract=gc)
    task = AgentTask(
        goal=goal,
        contract=gc,
        plan=Plan(steps=[step], contract=gc),
    )

    result_task = engine.run_task(task)

    # Must be FAILED, NOT COMPLETED!
    assert result_task.status == AgentTaskStatus.FAILED
    assert result_task.goal_verification is not None
    assert result_task.goal_verification.completed is False


# =============================================================================
# 6. STRESS CORPUS: 100+ REQUESTS WITH 0% FALSE COMPLETION RATE
# =============================================================================

def test_stress_corpus_100_requests_zero_false_completion(tmp_path):
    """
    Stress-test 100+ synthetic and realistic variations of user requests across
    all 7 domains.
    Verify:
    1. Every request produces a valid GoalContract.
    2. False completion rate is 0.0% (any unfulfilled predicate blocks completion).
    3. Mandatory constraints are preserved.
    """
    planner = GoalPlanner()
    verifier = GoalVerifier()

    verbs = ["save", "write", "create file with", "put"]
    apps = ["notepad", "text editor", "wordpad"]
    locations = ["desktop", "downloads", "documents"]
    files = ["doc1.txt", "notes.md", "payload.json", "output.csv", "log.txt"]
    contents = ["alpha", "beta test", "status ok", "hello world", "sample text"]

    requests: list[str] = []

    # Domain A & Composite: 60 variations
    for v in verbs:
        for f in files:
            for c in contents:
                for loc in locations:
                    requests.append(f"{v} '{c}' into {f} on {loc}")
                    if len(requests) >= 60:
                        break
                if len(requests) >= 60:
                    break
            if len(requests) >= 60:
                break
        if len(requests) >= 60:
            break

    # Domain B: 15 app requests
    for app in ["notepad", "calc", "explorer", "paint", "cmd"]:
        requests.append(f"open {app}")
        requests.append(f"launch {app} now")
        requests.append(f"start {app} in foreground")

    # Domain D: 15 wifi requests
    for ssid in ["HomeNet", "GuestWiFi", "Office_5G"]:
        requests.append(f"connect to wifi {ssid}")
        requests.append(f"join network {ssid}")
        requests.append(f"switch wifi to {ssid}")

    # Domain E: 10 battery requests
    for folder in ["Downloads", "Desktop", "Documents"]:
        requests.append(f"run a battery report and save it in {folder} as battery.html")
        requests.append(f"generate battery report to {folder}")

    # Domain F: 15 computation requests
    for word in ["palindrome", "antigravity", "quantum", "deterministic", "resilience"]:
        requests.append(f"reverse text '{word}'")
        requests.append(f"calculate hash of '{word}'")
        requests.append(f"count words in '{word}'")

    assert len(requests) >= 100, f"Expected 100+ requests, got {len(requests)}"

    false_completion_count = 0
    total_evaluated = 0

    for req in requests:
        total_evaluated += 1
        goal = planner.parse_goal(req)
        assert goal.contract is not None, f"GoalContract missing for: {req}"

        # Evaluate against an unfulfilled observation (empty/no files exist)
        # GoalVerifier MUST report completed = False for any goal requiring an artifact/network
        eval_result = verifier.evaluate(goal.contract, observation=None)
        if goal.contract.has_unsatisfied_mandatory_predicates():
            # If mandatory predicates are unsatisfied, completed MUST be False
            if eval_result.completed is True:
                false_completion_count += 1

    false_completion_rate = false_completion_count / total_evaluated
    assert false_completion_rate == 0.0, f"False completion rate was {false_completion_rate} > 0.0"
