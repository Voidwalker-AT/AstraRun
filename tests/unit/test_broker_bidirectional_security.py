"""Bidirectional adversarial security tests for ExecutionBroker and ActionGate (C1.6 Item 10).

Proves that security is neither 'block everything' nor 'allow everything'.
Tests:
  A: OBSERVE spoof against terminate_process => must NOT execute
  B: unknown consequential capability => DENY (BLOCK)
  C: execute_dynamic_tool with safe computational goal => allowed through broker
  D: dynamic tool code with prohibited AST behavior => blocked by ASTInspector
  E: dynamic code attempting network/subprocess/escape => blocked by AST inspection
  F: terminate_process => confirmation required, allowed only with valid token
"""

import pytest

from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.security.execution_broker import ActionCategory, ActionProposal, ExecutionBroker
from astrarun.tools.ast_inspector import ASTInspector
from astrarun.security.policies import ASTCodePolicy
from astrarun.tools.dynamic_builder import CandidateTool, DynamicToolBuilder


def test_adversarial_suite_a_observe_spoof_blocked():
    """A: OBSERVE spoof against terminate_process must be overridden to ACT and require confirmation."""
    reg = CapabilityRegistry()
    broker = ExecutionBroker(capability_registry=reg)

    prop = ActionProposal(
        category=ActionCategory.OBSERVE,
        capability_id="terminate_process",
        parameters={"pid": 9999},
        source="adversarial_test",
    )
    res = broker.execute(prop)

    assert not res.success, "Spoofed terminate_process should not succeed"
    assert res.verdict == "CONFIRM", f"Expected CONFIRM verdict, got {res.verdict}"
    assert res.requires_confirmation is True
    assert res.confirmation_token is not None


def test_adversarial_suite_b_unknown_consequential_denied():
    """B: Unknown/unregistered consequential capability must be unconditionally DENIED (BLOCK)."""
    reg = CapabilityRegistry()
    broker = ExecutionBroker(capability_registry=reg)

    prop = ActionProposal(
        category=ActionCategory.ACT,
        capability_id="unregistered_destructive_payload",
        parameters={"payload": "malicious"},
        source="adversarial_test",
    )
    res = broker.execute(prop)

    assert res.success is False
    assert res.verdict == "BLOCK"
    assert res.blocked is True
    assert "SECURITY_DENY" in res.message


def test_adversarial_suite_c_safe_dynamic_tool_allowed():
    """C: execute_dynamic_tool with normal safe computational goal is allowed through broker."""
    reg = CapabilityRegistry()
    broker = ExecutionBroker(capability_registry=reg)

    # Use executor_override to verify that ExecutionBroker ALLOWS dispatch
    override_invoked = False
    def mock_safe_executor(goal: str, **kwargs):
        nonlocal override_invoked
        override_invoked = True
        return {"result": "success", "primes": [2, 3, 5]}

    prop = ActionProposal(
        category=ActionCategory.ACT,
        capability_id="execute_dynamic_tool",
        parameters={"goal": "calculate primes up to 10"},
        source="test_runner",
    )
    res = broker.execute(prop, executor_override=mock_safe_executor)

    assert res.success is True, f"Broker rejected safe dynamic execution: {res.message}"
    assert res.verdict == "ALLOW"
    assert not res.blocked
    assert not res.requires_confirmation
    assert override_invoked is True


def test_adversarial_suite_d_prohibited_ast_blocked():
    """D: Dynamic tool code containing prohibited AST constructs is blocked by ASTInspector."""
    inspector = ASTInspector()

    unsafe_code = """
import ctypes
ctypes.windll.user32.MessageBoxW(0, "pwned", "hacked", 0)
"""
    result = inspector.inspect(unsafe_code)
    assert not result.is_safe, "ASTInspector should have rejected ctypes code"
    assert any("ctypes" in v.lower() for v in result.violations), f"Expected ctypes violation, got: {result.violations}"


def test_adversarial_suite_e_escape_attempts_blocked():
    """E: Dynamic code attempting socket, subprocess, or winreg escape is strictly blocked."""
    policy = ASTCodePolicy()

    # Vector 1: raw socket
    socket_code = """
import socket
s = socket.socket()
s.connect(("evil.com", 80))
"""
    verdict, reason, risk = policy.evaluate_code(socket_code)
    assert verdict.value == "DENY", f"Socket code was not denied: {reason}"

    # Vector 2: subprocess
    subprocess_code = """
import subprocess
subprocess.run(["cmd.exe", "/c", "dir"])
"""
    verdict, reason, risk = policy.evaluate_code(subprocess_code)
    assert verdict.value == "DENY", f"Subprocess code was not denied: {reason}"

    # Vector 3: winreg
    winreg_code = """
import winreg
key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "Software")
"""
    verdict, reason, risk = policy.evaluate_code(winreg_code)
    assert verdict.value == "DENY", f"Winreg code was not denied: {reason}"


def test_adversarial_suite_f_terminate_process_confirmation_cycle():
    """F: terminate_process requires confirmation token, and succeeds once valid token provided."""
    reg = CapabilityRegistry()
    broker = ExecutionBroker(capability_registry=reg)

    prop = ActionProposal(
        category=ActionCategory.ACT,
        capability_id="terminate_process",
        parameters={"pid": 12345},
        source="test_user",
    )
    # Turn 1: Without token -> CONFIRM
    res1 = broker.execute(prop)
    assert res1.verdict == "CONFIRM"
    assert res1.requires_confirmation is True
    token = res1.confirmation_token
    assert token is not None

    # Turn 2: With valid confirmation token -> ALLOW and dispatched
    dispatched = False
    def mock_terminate_executor(pid: int):
        nonlocal dispatched
        dispatched = True
        return {"terminated": True, "pid": pid}

    res2 = broker.execute(prop, confirmation_token=token, executor_override=mock_terminate_executor)
    assert res2.success is True
    assert res2.verdict == "ALLOW"
    assert dispatched is True
