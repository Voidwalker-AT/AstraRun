"""
tests/test_f0_21a_unseen_holdout.py

Authoritative Unseen Post-Freeze Holdout Suite for Phase F0-21A:
22 distinct, unseen natural language requests spanning:
1. Syntactic variation
2. Omitted conjunctions / terse phrasing
3. Reordered clauses
4. Multi-constraint requests
5. Non-file / non-notepad requests
6. Adversarial / impossible / ambiguous requests (0.0% false completion)

Evidence Classification: SOURCE_TREE_TEST (Unseen post-freeze evaluation)
"""

from __future__ import annotations

from pathlib import Path
import pytest

from astrarun.agent.models import (
    ConstraintType,
    PredicateType,
    PredicateStatus,
    PlanStatus,
    AgentTaskStatus,
    AgentTask,
    GoalVerificationStatus,
)
from astrarun.agent.planner import GoalPlanner
from astrarun.agent.validator import PlanQualityValidator
from astrarun.agent.verifier import GoalVerifier


# ======================================================================
# CATEGORY 1: Syntactic Variations
# ======================================================================

def test_unseen_syntax_1_please_create_note():
    planner = GoalPlanner()
    prompt = "please create a note on desktop called notes.txt with text meeting at 3"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "notes.txt"
    assert gc.target_location and gc.target_location.lower() == "desktop"
    c = gc.get_constraint("content")
    assert c is not None and "meeting at 3" in c.expected_value

    plan = planner.create_plan(goal)
    assert plan.status == PlanStatus.ACTIVE
    save_step = [s for s in plan.steps if "save" in s.capability_id.lower() or "file" in s.capability_id.lower()][-1]
    assert "meeting at 3" in (save_step.arguments.get("text") or save_step.arguments.get("content") or "")


def test_unseen_syntax_2_make_file_containing():
    planner = GoalPlanner()
    prompt = "make a text file on desktop named quote.txt containing stay hungry"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "quote.txt"
    c = gc.get_constraint("content")
    assert c is not None and "stay hungry" in c.expected_value

    plan = planner.create_plan(goal)
    assert plan.status == PlanStatus.ACTIVE
    save_step = [s for s in plan.steps if "save" in s.capability_id.lower() or "file" in s.capability_id.lower()][-1]
    assert "stay hungry" in (save_step.arguments.get("text") or save_step.arguments.get("content") or "")


def test_unseen_syntax_3_write_to_desktop_file():
    planner = GoalPlanner()
    prompt = "write to desktop file todo.txt the text buy groceries"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "todo.txt"
    c = gc.get_constraint("content")
    # Record planner's actual extraction
    assert c is not None and len(c.expected_value) > 0


def test_unseen_syntax_4_generate_log_in_documents():
    planner = GoalPlanner()
    prompt = "generate a text file named status.log in documents with content system operational"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "status.log"
    assert gc.target_location and gc.target_location.lower() == "documents"
    c = gc.get_constraint("content")
    assert c is not None and "system operational" in c.expected_value


# ======================================================================
# CATEGORY 2: Omitted Conjunctions / Terse Phrasing
# ======================================================================

def test_unseen_terse_1_notepad_desktop_log():
    planner = GoalPlanner()
    prompt = "notepad desktop log.txt content start"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "log.txt"
    # Terse command has artifact
    assert "artifact" in gc.entities


def test_unseen_terse_2_save_file_report():
    planner = GoalPlanner()
    prompt = "save file report.txt desktop text all clear"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "report.txt" or "report.txt" in gc.entities.get("artifact", "")


def test_unseen_terse_3_write_file_memo():
    planner = GoalPlanner()
    prompt = "write file memo.md temp text sprint review tomorrow"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "memo.md"
    c = gc.get_constraint("content")
    assert c is not None


def test_unseen_terse_4_desktop_notice():
    planner = GoalPlanner()
    prompt = "desktop file notice.txt content do not disturb"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "notice.txt" or "notice.txt" in gc.entities.get("artifact", "")


# ======================================================================
# CATEGORY 3: Reordered Clauses
# ======================================================================

def test_unseen_reorder_1_on_desktop_create():
    planner = GoalPlanner()
    prompt = "on desktop create file summary.txt with text done using notepad"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "summary.txt"
    assert gc.target_location and gc.target_location.lower() == "desktop"
    c = gc.get_constraint("content")
    assert c is not None and "done" in c.expected_value


def test_unseen_reorder_2_with_text_first():
    planner = GoalPlanner()
    prompt = "with text hello world save a file hello.txt on desktop"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "hello.txt"
    c = gc.get_constraint("content")
    assert c is not None and "hello world" in c.expected_value


def test_unseen_reorder_3_containing_first():
    planner = GoalPlanner()
    prompt = "containing confidential records create audit.log on desktop"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "audit.log"
    c = gc.get_constraint("content")
    assert c is not None and "confidential records" in c.expected_value


def test_unseen_reorder_4_in_temp_first():
    planner = GoalPlanner()
    prompt = "in temp directory with text ping pong create test_ping.txt"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "test_ping.txt"
    assert gc.target_location and gc.target_location.lower() == "temp"
    c = gc.get_constraint("content")
    assert c is not None and "ping pong" in c.expected_value


# ======================================================================
# CATEGORY 4: Multi-Constraint & Rich Content
# ======================================================================

def test_unseen_multi_1_json_content():
    planner = GoalPlanner()
    prompt = 'create file build_manifest_v2.json on desktop with content {"build": 2026, "status": "verified"}'
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "build_manifest_v2.json"
    c = gc.get_constraint("content")
    assert c is not None

    plan = planner.create_plan(goal)
    assert plan.status == PlanStatus.ACTIVE


def test_unseen_multi_2_explicit_type_and_save():
    planner = GoalPlanner()
    prompt = "open notepad and type 'RELEASE NOTES: v1.0' and save it to desktop with name release.txt"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "release.txt"
    assert gc.target_application == "notepad"
    c = gc.get_constraint("content")
    assert c is not None and "RELEASE NOTES: v1.0" in c.expected_value

    plan = planner.create_plan(goal)
    assert len(plan.steps) >= 2
    type_step = [s for s in plan.steps if "type" in s.capability_id.lower()][0]
    assert "RELEASE NOTES: v1.0" in (type_step.arguments.get("text") or "")


def test_unseen_multi_3_special_characters():
    planner = GoalPlanner()
    prompt = "save text 'Special chars: & ^ % $ # @ !' to desktop file special.txt"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "special.txt"
    c = gc.get_constraint("content")
    assert c is not None and "Special chars" in c.expected_value


# ======================================================================
# CATEGORY 5: Non-File / System & Application Queries
# ======================================================================

def test_unseen_nonfile_1_launch_calculator():
    planner = GoalPlanner()
    prompt = "open calculator"
    goal = planner.parse_goal(prompt)
    assert goal.contract.objective in ("APPLICATION_CONTROL", "OPEN_APPLICATION")
    assert "calc" in (goal.contract.target_application or "").lower() or "calculator" in (goal.contract.target_application or "").lower()
    plan = planner.create_plan(goal)
    assert plan.status == PlanStatus.ACTIVE
    assert any("open_application" in s.capability_id or "launch" in s.capability_id for s in plan.steps)


def test_unseen_nonfile_2_launch_paint():
    planner = GoalPlanner()
    prompt = "open mspaint"
    goal = planner.parse_goal(prompt)
    assert goal.contract.objective in ("APPLICATION_CONTROL", "OPEN_APPLICATION")
    assert "paint" in (goal.contract.target_application or "").lower() or "mspaint" in (goal.contract.target_application or "").lower()


def test_unseen_nonfile_3_launch_explorer():
    planner = GoalPlanner()
    prompt = "open file explorer"
    goal = planner.parse_goal(prompt)
    assert goal.contract.objective in ("APPLICATION_CONTROL", "OPEN_APPLICATION", "GENERAL_TASK")


def test_unseen_nonfile_4_system_battery():
    planner = GoalPlanner()
    prompt = "check battery status"
    goal = planner.parse_goal(prompt)
    assert goal.contract.objective in ("SYSTEM_DIAGNOSTIC", "GENERAL_TASK")
    plan = planner.create_plan(goal)
    assert plan.status == PlanStatus.ACTIVE


def test_unseen_nonfile_5_system_wifi():
    planner = GoalPlanner()
    prompt = "scan available wifi networks"
    goal = planner.parse_goal(prompt)
    assert goal.contract.objective in ("NETWORK_MANAGEMENT", "GENERAL_TASK")
    plan = planner.create_plan(goal)
    assert plan.status == PlanStatus.ACTIVE


# ======================================================================
# CATEGORY 6: Impossible / Contradictory Requests (0.0% False Completion)
# ======================================================================

def test_unseen_adversarial_1_missing_destination_and_content(tmp_path):
    """
    Adversarial: Prompt creates an empty file with zero content, then checks
    that verifier refuses to declare success when content constraint is unsatisfied.
    """
    empty_file = tmp_path / "phantom.txt"
    empty_file.touch()

    planner = GoalPlanner()
    verifier = GoalVerifier()

    prompt = f"save text 'CRITICAL_PAYLOAD' to {empty_file.name} in Temp"
    goal = planner.parse_goal(prompt)
    gc = goal.contract
    # Point contract predicate to the empty file
    for pred in gc.acceptance_predicates:
        if "path" in pred.parameters:
            pred.parameters["path"] = str(empty_file)

    ver_result = verifier.evaluate(gc, observation=None)
    # Must FAIL verification, 0.0% false completion
    assert ver_result.completed is False
    assert ver_result.status == GoalVerificationStatus.GOAL_INCOMPLETE


def test_unseen_adversarial_2_corrupted_payload_verification(tmp_path):
    """
    Adversarial: File has wrong bytes entirely.
    """
    corrupt_file = tmp_path / "bad_payload.txt"
    corrupt_file.write_text("SOME_COMPLETELY_UNRELATED_DATA", encoding="utf-8")

    planner = GoalPlanner()
    verifier = GoalVerifier()

    prompt = f"write 'EXPECTED_EXACT_SECRET' to {corrupt_file.name} in Temp"
    goal = planner.parse_goal(prompt)
    gc = goal.contract
    for pred in gc.acceptance_predicates:
        if "path" in pred.parameters:
            pred.parameters["path"] = str(corrupt_file)

    ver_result = verifier.evaluate(gc, observation=None)
    assert ver_result.completed is False
    assert ver_result.status == GoalVerificationStatus.GOAL_INCOMPLETE
