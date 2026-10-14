"""Unit tests for ExecutionBroker security choke-point."""

import pytest
from astrarun.security.action_gate import ActionGate
from astrarun.security.execution_broker import (
    ActionCategory,
    ActionProposal,
    ExecutionBroker,
)


def test_passive_observation_allowed():
    broker = ExecutionBroker()
    proposal = ActionProposal(
        category=ActionCategory.OBSERVE,
        capability_id="list_processes",
        parameters={"limit": 10},
    )
    result = broker.execute(proposal, executor_override=lambda **kw: {"processes": [1, 2, 3]})
    assert result.success is True
    assert result.verdict == "ALLOW"
    assert result.blocked is False
    assert result.requires_confirmation is False
    assert len(broker.get_audit_trail()) == 1


def test_mutation_action_evaluated():
    broker = ExecutionBroker()
    proposal = ActionProposal(
        category=ActionCategory.ACT,
        capability_id="open_application",
        parameters={"app": "notepad"},
    )
    result = broker.execute(proposal, executor_override=lambda **kw: "Notepad opened")
    assert result.success is True
    assert result.verdict == "ALLOW"
    assert len(broker.get_audit_trail()) >= 1


def test_destructive_action_requires_confirmation():
    broker = ExecutionBroker()
    proposal = ActionProposal(
        category=ActionCategory.ACT,
        capability_id="terminate_process",
        parameters={"process_name": "critical_task.exe", "pid": 9999},
    )
    result = broker.execute(proposal)
    assert result.requires_confirmation is True
    assert result.confirmation_token is not None
    assert result.verdict == "CONFIRM"
