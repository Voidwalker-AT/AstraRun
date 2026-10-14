"""
AU-1.1A ModelRole Canonical Definition & Import Tests.

Verifies:
1. ModelRole is imported and resolved in astrarun.agent.planner without NameError.
2. GoalPlanner Tier-2 evaluation passes ModelRole.FAST and ModelRole.DEEP to supervisor.
3. Canonical ModelRole enum values match cognition contracts.
"""

from unittest.mock import MagicMock, patch
import pytest

from astrarun.agent.planner import GoalPlanner
from astrarun.cognition.models import IntentClass, IntentReasonerResult, ModelRole
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.routing.context_sufficiency import SufficiencyAssessment


def test_modelrole_enum_values():
    assert ModelRole.FAST == "FAST"
    assert ModelRole.DEEP == "DEEP"


def test_planner_tier2_modelrole_access():
    """Verify that GoalPlanner evaluates supervisor with canonical ModelRole without NameError."""
    registry = CapabilityRegistry()
    mock_model_service = MagicMock()
    mock_supervisor = MagicMock()
    mock_supervisor.is_running.side_effect = lambda role: role == ModelRole.FAST
    mock_model_service.supervisor = mock_supervisor
    mock_model_service.classify_intent_reasoner.return_value = IntentReasonerResult(
        intent_class=IntentClass.DYNAMIC_COMPUTATION,
        confidence=0.9,
        requires_code=True,
        candidate_capabilities=[],
    )

    planner = GoalPlanner(registry=registry, model_service=mock_model_service)

    with patch(
        "astrarun.routing.context_sufficiency.ContextSufficiencyEngine.evaluate",
        return_value=SufficiencyAssessment(classification=None, is_sufficient=True, confidence=0.5, reason="test"),
    ):
        goal = planner.parse_goal("qwfp arst zxcv bnmk arbitrary non-capability tokens")

    # Verify supervisor was called with ModelRole
    assert mock_supervisor.is_running.called
    called_roles = [call[0][0] for call in mock_supervisor.is_running.call_args_list]
    assert ModelRole.FAST in called_roles
    assert goal is not None
