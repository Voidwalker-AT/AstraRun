"""Tests for Human Interruption and World-State Drift Architecture.

Verifies:
- All 11 typed interruption classifications are handled
- Invariant: HUMAN INTENT > ASTRA PLAN
- Physical user takeover preempts automation immediately
- User closing a resource pauses plan without fighting or reopening
- Process crashes trigger RECOVERING rather than unhandled exception
- Assumption verification prevents step N+1 on stale state from step N
"""

import time
import pytest

from astrarun.agent.coordinator import AgentCoordinator, TurnStatus
from astrarun.agent.interruption import (
    InterruptionAssessment,
    InterruptionPolicyEngine,
    InterruptionType,
    WorldDriftDetector,
    WorldResourceSnapshot,
)
from astrarun.ingress.models import RequestEnvelope, RequestOrigin
from astrarun.session.models import ConversationSession
from astrarun.session.store import SessionStore


@pytest.fixture
def coordinator():
    return AgentCoordinator()


@pytest.fixture
def session_store():
    store = SessionStore.get_instance()
    store.clear()
    return store


def test_all_11_interruption_types_classified_and_governed():
    """Verify that all 11 typed interruptions are recognized by detector and policy engine."""
    detector = WorldDriftDetector()
    engine = InterruptionPolicyEngine()
    session = ConversationSession(session_id="test-drift-all")

    expected_types = [
        InterruptionType.USER_TAKEOVER,
        InterruptionType.USER_CLOSED_RESOURCE,
        InterruptionType.USER_MODIFIED_RESOURCE,
        InterruptionType.FOCUS_CHANGED,
        InterruptionType.RESOURCE_DISAPPEARED,
        InterruptionType.RESOURCE_REPLACED,
        InterruptionType.MODAL_APPEARED,
        InterruptionType.PROCESS_CRASHED,
        InterruptionType.FILESYSTEM_CHANGED,
        InterruptionType.NETWORK_CHANGED,
        InterruptionType.UNKNOWN_WORLD_DRIFT,
    ]

    before_snap = WorldResourceSnapshot(target_pid=1234, target_file_path="C:/test/file.txt")
    after_snap = WorldResourceSnapshot(target_pid=1234, target_file_path="C:/test/file.txt")

    for itype in expected_types:
        detector.inject_fault(itype)
        assessment = detector.detect_drift(before_snap, after_snap, "test_action", {"pid": 1234})
        assert assessment is not None, f"Failed to detect injected fault {itype}"
        assert assessment.has_drift is True
        assert assessment.interruption_type == itype

        outcome = engine.apply_policy(assessment, {"pid": 1234}, session)
        assert "action" in outcome
        assert "coordinator_state" in outcome
        assert "message" in outcome
        assert len(outcome["message"]) > 10


def test_user_takeover_preempts_coordinator(coordinator: AgentCoordinator, session_store: SessionStore):
    """
    Invariant: Physical human takeover immediately pauses automation.
    Astra yields workstation control without fighting the user.
    """
    session = session_store.create_session("sess-takeover")
    
    # Configure coordinator's drift detector with takeover override
    coordinator.drift_detector.simulate_user_takeover(True)

    # Issue a request that plans an action
    env = RequestEnvelope.create("List running processes.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    result = coordinator.handle_turn(env, session)

    # Invariant: Must pause immediately with PAUSED_USER_ACTIVE
    assert result.status == TurnStatus.PAUSED_USER_ACTIVE
    assert "user activity detected" in result.response_text.lower() or "takeover" in result.response_text.lower() or "yields" in result.response_text.lower()

    # Reset takeover override
    coordinator.drift_detector.simulate_user_takeover(False)


def test_user_closed_resource_pauses_plan(coordinator: AgentCoordinator, session_store: SessionStore):
    """
    Invariant: If user closes a resource Astra was interacting with,
    Astra treats it as explicit human intent, does NOT reopen it, and pauses.
    """
    session = session_store.create_session("sess-user-close")

    coordinator.drift_detector.inject_fault(InterruptionType.USER_CLOSED_RESOURCE)

    env = RequestEnvelope.create("Inspect running process status.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    result = coordinator.handle_turn(env, session)

    assert result.status == TurnStatus.PAUSED_USER_ACTIVE
    assert "closed by user" in result.response_text.lower() or "human intent" in result.response_text.lower() or "paused" in result.response_text.lower()


def test_process_crashed_triggers_recovering(coordinator: AgentCoordinator, session_store: SessionStore):
    """
    Invariant: Unexpected process crash transitions coordinator to RECOVERING state.
    """
    session = session_store.create_session("sess-crash")

    coordinator.drift_detector.inject_fault(InterruptionType.PROCESS_CRASHED)

    env = RequestEnvelope.create("Inspect running process status.", origin=RequestOrigin.LAUNCHER, session_id=session.session_id)
    result = coordinator.handle_turn(env, session)

    assert result.status == TurnStatus.RECOVERING
    assert "terminated unexpectedly" in result.response_text.lower() or "crash" in result.response_text.lower()


def test_step_n_plus_one_assumption_verification(coordinator: AgentCoordinator, session_store: SessionStore):
    """
    Invariant: Step N+1 verifies assumptions before continuing.
    Never blindly execute step N+1 using stale state from step N.
    """
    detector = WorldDriftDetector()

    # Snapshot at end of Step 1: file exists
    snap1 = WorldResourceSnapshot(
        target_file_path="C:/nonexistent/temp_drift_test.txt",
        target_file_exists=True,
        target_file_sha256="abc123hash",
    )

    # Step 2 relies on that file, but file does not actually exist on disk now
    step2_args = {"path": "C:/nonexistent/temp_drift_test.txt"}

    assumptions_valid, assessment = detector.verify_assumptions(step2_args, snap1)
    assert assumptions_valid is False
    assert assessment is not None
    assert assessment.has_drift is True
    assert assessment.interruption_type == InterruptionType.RESOURCE_DISAPPEARED
