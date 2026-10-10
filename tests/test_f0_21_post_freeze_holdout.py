"""
tests/test_f0_21_post_freeze_holdout.py

REGRESSION SUITE (Formally reclassified from initial F0-21 holdout to regression
per F0-21A freeze discipline protocol. Unseen holdout evidence is moved to
dedicated independent post-freeze test runner).
Evidence Classification: SOURCE_TREE_TEST
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
)
from astrarun.agent.planner import GoalPlanner
from astrarun.agent.validator import PlanQualityValidator
from astrarun.agent.verifier import GoalVerifier


def test_holdout_novel_composite_document_workflow():
    """Holdout: Unseen document workflow with novel phrasing and extension."""
    planner = GoalPlanner()
    prompt = "start text editor and write 'Quarterly Financial Summary 2026' then save it to Documents as financial_summary.md"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.target_artifact == "financial_summary.md"
    assert gc.target_location == "Documents"
    assert gc.target_application in ("text editor", "notepad") or gc.target_application is not None

    content_c = gc.get_constraint("content")
    assert content_c is not None
    assert content_c.expected_value == "Quarterly Financial Summary 2026"

    plan = planner.create_plan(goal)
    assert plan.status == PlanStatus.ACTIVE
    assert len(plan.steps) >= 2

    # Verify that content is wired into the final save step
    save_step = plan.steps[-1]
    assert save_step.arguments.get("text") == "Quarterly Financial Summary 2026" or save_step.arguments.get("content") == "Quarterly Financial Summary 2026"
    assert save_step.arguments.get("filename") == "financial_summary.md" or "financial_summary.md" in save_step.arguments.get("path", "")


def test_holdout_novel_computation_and_save():
    """Holdout: Dynamic hash computation with hex payload."""
    planner = GoalPlanner()
    prompt = "compute sha256 hash for 'confidential_payload_789'"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.objective == "DYNAMIC_COMPUTATION"
    content_c = gc.get_constraint("content") or gc.get_constraint("payload")
    assert content_c is not None
    assert content_c.expected_value == "confidential_payload_789"

    plan = planner.create_plan(goal)
    assert plan.status == PlanStatus.ACTIVE
    assert any(s.capability_id in ("execute_dynamic_tool", "compute_hash") or "hash" in s.capability_id.lower() for s in plan.steps)


def test_holdout_novel_network_switch():
    """Holdout: Wi-Fi connection with hyphenated enterprise SSID."""
    planner = GoalPlanner()
    prompt = "switch wifi to Enterprise-Secure-99"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    assert gc is not None
    assert gc.objective == "NETWORK_MANAGEMENT"
    assert gc.entities.get("ssid") == "Enterprise-Secure-99"

    plan = planner.create_plan(goal)
    assert plan.status == PlanStatus.ACTIVE
    assert any("wifi" in s.capability_id.lower() for s in plan.steps)
    step = [s for s in plan.steps if "wifi" in s.capability_id.lower()][0]
    assert step.arguments.get("ssid") == "Enterprise-Secure-99"


def test_holdout_zero_byte_content_tampering(tmp_path):
    """
    Holdout: Verifier integrity when a malicious or faulty runner
    creates the file but puts empty whitespace or 0 bytes.
    """
    tampered_file = tmp_path / "tampered_artifact.json"
    tampered_file.write_text("   \n\t  ", encoding="utf-8")  # Whitespace only, no required content

    planner = GoalPlanner()
    verifier = GoalVerifier()

    prompt = f"save '{{\"status\": \"ok\"}}' into {tampered_file.name} on Temp"
    goal = planner.parse_goal(prompt)
    gc = goal.contract

    # Set exact path in predicates for evaluation
    for p in gc.acceptance_predicates:
        if "path" in p.parameters:
            p.parameters["path"] = str(tampered_file)

    eval_res = verifier.evaluate(gc, observation=None)
    assert eval_res.completed is False
    assert any("not contain" in msg.lower() for msg in eval_res.missing_criteria)


def test_holdout_information_loss_rejection():
    """Holdout: Plan validator catches any dropped payload in novel plan."""
    planner = GoalPlanner()
    validator = PlanQualityValidator()

    prompt = "create file on Desktop called audit.log with text 'SYSTEM_HEALTH_OPTIMAL'"
    goal = planner.parse_goal(prompt)
    plan = planner.create_plan(goal)

    # Corrupt the plan by clearing the arguments in save step
    save_step = plan.steps[-1]
    save_step.arguments = {"filename": "audit.log"}  # Dropped text/content!

    report = validator.validate_plan(plan, goal_contract=goal.contract)
    assert report.is_valid is False
    assert any("information-loss" in issue.lower() or "system_health_optimal" in issue.lower() for issue in report.issues)
