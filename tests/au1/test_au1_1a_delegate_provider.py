"""
AU-1.1A Delegate Provider Separation & Production Seam Cleanup Tests.

Verifies:
1. MockDelegateProvider is no longer the default in production delegation.
2. Unconfigured delegation fails honestly with ProviderUnavailableError / PROVIDER_UNAVAILABLE.
3. Natural-language query containing 'mock' does not hijack provider_name.
4. Explicit test provider registration works cleanly.
"""

import pytest
from astrarun.agent.planner import GoalPlanner
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.delegation.provider import (
    DelegateRegistry,
    ProviderUnavailableError,
)
from astrarun.delegation.mock import MockDelegateProvider


def test_production_delegation_registry_has_no_default_mock():
    """Verify clean DelegateRegistry has no default mock provider registered."""
    reg = DelegateRegistry()
    assert reg.list_providers() == []
    with pytest.raises(ProviderUnavailableError) as exc_info:
        reg.resolve_provider()
    assert "PROVIDER_UNAVAILABLE" in str(exc_info.value)


def test_unconfigured_delegation_capability_fails_honestly():
    """Verify consult_delegate capability fails with PROVIDER_UNAVAILABLE when unconfigured."""
    registry = CapabilityRegistry()
    # Execute consult_delegate without setting up an external provider
    res = registry.execute("consult_delegate", {"goal": "summarize article", "provider_name": "nonexistent"})
    assert res.success is False
    assert res.data.get("reason_code") == "PROVIDER_UNAVAILABLE" or "unavailable" in res.message.lower()


def test_planner_query_mock_word_does_not_hijack_provider():
    """Verify that a goal containing 'mock' does not set provider_name='mock'."""
    planner = GoalPlanner(registry=CapabilityRegistry())
    goal = planner.parse_goal("test mock window and check response")
    provider = goal.parameters.get("provider_name")
    assert provider != "mock", f"Expected provider_name not to be 'mock', got: {provider}"


def test_explicit_mock_provider_registration_works_for_tests():
    """Verify test suites can still explicitly inject a mock provider."""
    reg = DelegateRegistry()
    mock_prov = MockDelegateProvider(name="test_mock")
    reg.register(mock_prov, set_default=True)

    assert "test_mock" in reg.list_providers()
    resolved = reg.resolve_provider("test_mock")
    assert resolved is mock_prov

    # Executing delegation works when explicitly configured
    from astrarun.delegation.models import DelegateSession
    session = DelegateSession(
        session_id="test_session",
        provider="test_mock",
        conversation_handle="mock_handle_1",
        task_id="task_test_1",
        objective="test query",
    )
    result = resolved.ask(session=session, prompt="hello")
    assert result.raw_content != ""
