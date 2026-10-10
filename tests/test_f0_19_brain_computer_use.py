"""Comprehensive verification test suite for Phase F0-19:
Architectural Ownership Refactor (Brain + Universal Computer_Use + Multi-Step Agent Loop).
"""

import inspect
import sys
from pathlib import Path
import pytest

from astrarun.brain import (
    Brain,
    BrainDecision,
    BrainIntent,
    GoalPlanner,
    AgentExecutionEngine,
    GoalVerifier,
    SemanticEntityResolver,
    ResolvedEntity,
)
from astrarun.brain.models import PlanningLevel, PlanStatus, StepState
from astrarun.computer_use import (
    ComputerUse,
    ComputerUseController,
    ApplicationSession,
    SessionState,
    ActionBackend,
    ComputerUseObservation,
    UIAction,
    VerificationCondition,
    VerificationResult,
    RecoveryAction,
)
from astrarun.app import AstraApplication
from astrarun.routing.input_router import classify_launcher_input, InputIntent


# =============================================================================
# 1. BRAIN ARCHITECTURAL INVARIANTS
# =============================================================================

def test_brain_facade_integrity():
    """Verify Brain facade exposes canonical cognitive operations."""
    brain = Brain.get_instance()
    assert brain is not None
    assert hasattr(brain, "decide_intent")
    assert hasattr(brain, "resolve_entity")
    assert hasattr(brain, "plan_goal")
    assert hasattr(brain, "execute_goal")


def test_brain_contains_no_os_automation_primitives():
    """Invariant: The Brain domain MUST NOT contain OS automation primitives (ctypes, user32, SendInput)."""
    import astrarun.brain
    import astrarun.brain.decision
    import astrarun.brain.reasoning
    import astrarun.brain.models

    brain_modules = [
        "astrarun.brain",
        "astrarun.brain.decision.intent",
        "astrarun.brain.reasoning",
        "astrarun.brain.models",
    ]

    forbidden_tokens = ["ctypes.windll.user32", "user32.SendInput", "user32.PostMessageW", "WM_CLOSE"]

    for mod_name in brain_modules:
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "__file__") and mod.__file__:
            source = Path(mod.__file__).read_text(encoding="utf-8")
            for tok in forbidden_tokens:
                assert tok not in source, f"Forbidden OS automation primitive '{tok}' found in brain module '{mod_name}'"


def test_brain_intent_classification():
    """Verify Brain.decide_intent categorizes requests correctly."""
    brain = Brain.get_instance()

    # Conversational
    d1 = brain.decide_intent("hello")
    assert d1.intent == BrainIntent.CONVERSATIONAL

    # Question
    d2 = brain.decide_intent("what gpu do i have")
    assert d2.intent == BrainIntent.QUESTION

    # Security Rejection
    d3 = brain.decide_intent("delete system32")
    assert d3.intent == BrainIntent.SECURITY_REJECTION

    # Compound goal
    d4 = brain.decide_intent("open notepad and type hello and save it to desktop and name it test.txt")
    assert d4.intent == BrainIntent.COMPOSITE_GOAL


# =============================================================================
# 2. COMPUTER-USE DOMAIN INVARIANTS
# =============================================================================

def test_computer_use_controller_primitives():
    """Verify ComputerUseController exposes universal Observe, Interact, Verify, Recover."""
    controller = ComputerUseController()

    # 1. Observe
    obs = controller.observe()
    assert isinstance(obs, ComputerUseObservation)
    assert obs.timestamp > 0
    assert isinstance(obs.available_actions, list)

    # 2. Recover
    rec = controller.recover("Element handle is stale.", attempt=1, max_attempts=3)
    assert isinstance(rec, RecoveryAction)
    assert rec.action == "reobserve"

    # 3. Verify
    cond = VerificationCondition(condition_type="process_running", target="python.exe", timeout_seconds=0.5)
    v_res = controller.verify(cond)
    assert isinstance(v_res, VerificationResult)
    assert v_res.verified is True


def test_application_session_lifecycle():
    """Verify ApplicationSession abstraction maintains state and alive checking."""
    sess = ApplicationSession(
        session_id="sess_test_1",
        app_name="notepad",
        pid=12345,
        state=SessionState.ACTIVE,
    )
    assert sess.session_id == "sess_test_1"
    assert sess.state == SessionState.ACTIVE

    sess.state = SessionState.TERMINATED
    assert not sess.is_alive


# =============================================================================
# 3. MULTI-STEP AGENT PLANNING & DATAFLOW RESOLUTION
# =============================================================================

def test_multi_step_compound_goal_planning():
    """
    Verify 'open notepad and type hello and save it to desktop and name it test.txt'
    decomposes into generic steps with proper dataflow dependencies.
    """
    app = AstraApplication()
    planner = app.agent_engine.planner

    goal = planner.parse_goal("open notepad and type hello and save it to desktop and name it test.txt")
    assert goal is not None

    plan = planner.create_plan(goal)
    assert plan is not None
    assert plan.status == PlanStatus.ACTIVE
    assert len(plan.steps) == 3

    # Step 1: open_application
    s1 = plan.steps[0]
    assert s1.capability_id in ("open_application", "open_app")
    assert s1.arguments.get("app") == "notepad"

    # Step 2: type_into_window
    s2 = plan.steps[1]
    assert s2.capability_id in ("type_into_window", "type_text")
    assert s2.arguments.get("text") == "hello"

    # Step 3: save_text_file
    s3 = plan.steps[2]
    assert s3.capability_id == "save_text_file"
    assert "Desktop" in s3.arguments.get("path", "")
    assert "test.txt" in s3.arguments.get("path", "")
    assert s3.arguments.get("text") == "hello" or s3.arguments.get("content") is not None


# =============================================================================
# 4. LAUNCHER UX: AUTO-COMPLETE SUPPRESSION ON ACTION COMMANDS
# =============================================================================

def test_launcher_suppresses_suggestions_on_action_typing():
    """
    Human-observed defect fix: Typing 'open no...' must suppress suggestions list
    and NOT dump raw fuzzy application matches into dropdown.
    """
    assert classify_launcher_input("open no") == InputIntent.DIRECT_APP_INTENT
    assert classify_launcher_input("launch calc") == InputIntent.DIRECT_APP_INTENT
    assert classify_launcher_input("hello") == InputIntent.NATURAL_LANGUAGE
    assert classify_launcher_input("how much ram") == InputIntent.QUESTION
