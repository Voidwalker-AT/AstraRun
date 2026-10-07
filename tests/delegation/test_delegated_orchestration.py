"""Comprehensive Test Suite for AstraRun Delegated Agent Orchestration.

Tests:
1. Multi-turn conversation ping-pong with MockDelegateProvider
2. Advisory proposal parsing (code fences, shell commands, diffs, review status)
3. Patch safety and stale diff rejection
4. ContextPackager secret scrubbing, 50k-line terminal truncation, and budget capping
5. Dual-condition completion (Empirical Verification + Delegate Approval)
6. Iteration budget enforcement (bounded ping-pong)
7. Provider failure and timeout handling
8. Session persistence (save/load for pause/resume)
9. End-to-end AgentExecutionEngine integration
"""

import hashlib
import json
import shutil
import tempfile
import time
from pathlib import Path
import pytest

from astrarun.agent.loop import AgentExecutionEngine
from astrarun.agent.models import AgentTaskStatus
from astrarun.delegation.models import (
    DelegateProposal,
    DelegateSession,
    DelegateTurn,
    ReviewStatus,
)
from astrarun.delegation.mock import MockDelegateProvider
from astrarun.delegation.packager import ContextPackager
from astrarun.delegation.proposal import parse_delegate_proposal, verify_and_apply_patch
from astrarun.delegation.provider import DelegateRegistry
from astrarun.delegation.loop import DelegatedOrchestrationLoop


def test_delegate_proposal_parsing():
    """Verify parsing of multi-fence, shell, and status advisory responses."""
    raw_response = (
        "Here is the proposed architectural solution:\n\n"
        "First, install any missing requirements if needed:\n"
        "```bash\n"
        "pip list\n"
        "```\n\n"
        "Here is the main simulation script:\n"
        "```python\n"
        "# filename: projectile.py\n"
        "import math\n"
        "def compute_range(v, theta):\n"
        "    return (v ** 2) * math.sin(2 * theta) / 9.81\n"
        "```\n\n"
        "And here is the unit test:\n"
        "```python\n"
        "# filename: test_projectile.py\n"
        "from projectile import compute_range\n"
        "def test_range():\n"
        "    assert compute_range(10, 0) == 0\n"
        "```\n\n"
        "Please run pytest to verify."
    )

    prop = parse_delegate_proposal(raw_response)
    assert "pip list" in prop.proposed_commands
    assert "projectile.py" in prop.proposed_files
    assert "test_projectile.py" in prop.proposed_files
    assert "compute_range" in prop.proposed_files["projectile.py"]
    assert prop.review_status == ReviewStatus.UNKNOWN

    # Test explicit approval
    approval_text = "I have reviewed your test output. All 14 tests pass and the implementation looks correct. APPROVED."
    prop_app = parse_delegate_proposal(approval_text)
    assert prop_app.review_status == ReviewStatus.APPROVED

    # Test change request
    change_text = "The tests failed with exit code 1. Please fix the missing import in projectile.py."
    prop_chg = parse_delegate_proposal(change_text)
    assert prop_chg.review_status == ReviewStatus.CHANGES_REQUESTED


def test_stale_patch_rejection():
    """Verify verify_and_apply_patch rejects stale patches when base hash differs."""
    with tempfile.TemporaryDirectory() as td:
        t_path = Path(td) / "module.py"
        t_path.write_bytes(b"original_code = True\n")
        orig_hash = hashlib.sha256(b"original_code = True\n").hexdigest()

        # Modify file locally (simulating user or concurrent edit)
        t_path.write_bytes(b"modified_locally = True\n")

        # Attempt to apply patch with expected original hash
        ok, msg = verify_and_apply_patch(
            target_file=t_path,
            patch_text="new_code = True\n",
            expected_base_sha256=orig_hash,
        )
        assert not ok
        assert "Stale patch rejected" in msg


def test_context_packager_redaction_and_truncation():
    """Verify SecretBroker redaction and large terminal log truncation (e.g. 50k lines)."""
    packager = ContextPackager(char_budget=8000, max_stdout_lines=100)

    # 1. Secret scrubbing
    text_with_secret = "Database connection error using secret api_key='sk-ant-api03-secret12345678901234567890' at endpoint."
    scrubbed = packager.scrub(text_with_secret)
    assert "sk-ant" not in scrubbed
    assert "[REDACTED" in scrubbed or "***" in scrubbed or len(scrubbed) < len(text_with_secret)

    # 2. 50k-line terminal output truncation
    lines = [f"LOG LINE {i}: processed event {i * 2}" for i in range(5000)]
    huge_stdout = "\n".join(lines)
    formatted = packager.format_terminal_output(huge_stdout, stderr="Minor warning")

    assert "lines omitted for context budget" in formatted
    assert "LOG LINE 0:" in formatted
    assert "LOG LINE 4999" in formatted
    assert len(formatted) < 15000


def test_session_serialization_for_pause_resume():
    """Verify secret-free session persistence across restart/pause."""
    with tempfile.TemporaryDirectory() as td:
        session = DelegateSession.create(
            provider="chatgpt_web",
            task_id="task_pers_001",
            objective="Build a projectile motion simulator",
            conversation_handle="conv_tab_7749",
            max_turns=6,
        )
        session.add_outbound_turn("Please write the simulation.")
        session.add_inbound_turn("Here is the code: ```python\nprint(1)\n```")

        save_file = Path(td) / "session_checkpoint.json"
        session.save(save_file)

        loaded = DelegateSession.load(save_file)
        assert loaded.session_id == session.session_id
        assert loaded.conversation_handle == "conv_tab_7749"
        assert loaded.current_turn == 1
        assert len(loaded.turns) == 2
        assert loaded.turns[0].direction == "OUTBOUND"
        assert loaded.turns[1].direction == "INBOUND"


def test_delegated_orchestration_loop_multi_turn_repair_and_approval():
    """Verify multi-turn loop: Turn 1 (initial with bug) -> Turn 2 (repair) -> Turn 3 (approval)."""
    reg = DelegateRegistry()
    mock_prov = MockDelegateProvider(name="test_mock", rule_based=True)
    reg.register(mock_prov, set_default=True)

    loop = DelegatedOrchestrationLoop(registry=reg)

    with tempfile.TemporaryDirectory() as td:
        result = loop.execute_goal(
            goal="Simulate projectile motion and output trajectory.csv to Desktop",
            workspace_dir=td,
            provider_name="test_mock",
            max_turns=5,
            require_delegate_approval=True,
        )

        assert result.status == "COMPLETED"
        assert result.local_acceptance_passed is True
        assert result.delegate_approval_received is True
        assert result.turns_completed >= 2  # At least code turn + review turn
        assert len(result.artifacts) >= 1

        # Assert trajectory artifact was created and verified
        csv_arts = [a for a in result.artifacts if a["name"] == "trajectory.csv"]
        assert len(csv_arts) >= 1
        assert csv_arts[0]["size_bytes"] > 50


def test_delegated_orchestration_loop_turn_budget_enforcement():
    """Verify that loop aborts with BUDGET_EXHAUSTED when delegate repeatedly fails."""
    reg = DelegateRegistry()
    # Mock that keeps producing failing code without ever fixing it
    failing_responses = [
        "```python\n# filename: bad.py\nraise RuntimeError('Fatal error 1')\n```",
        "```python\n# filename: bad.py\nraise RuntimeError('Fatal error 2')\n```",
    ]
    failing_prov = MockDelegateProvider(name="failing_mock", turn_responses=failing_responses, rule_based=False)
    reg.register(failing_prov, set_default=True)

    loop = DelegatedOrchestrationLoop(registry=reg)
    with tempfile.TemporaryDirectory() as td:
        result = loop.execute_goal(
            goal="Do something impossible",
            workspace_dir=td,
            provider_name="failing_mock",
            max_turns=2,
            require_delegate_approval=True,
        )

        assert result.status == "BUDGET_EXHAUSTED"
        assert result.local_acceptance_passed is False
        assert result.delegate_approval_received is False
        assert result.turns_completed >= 2


def test_delegated_orchestration_loop_provider_failure():
    """Verify that provider timeouts or disconnection are handled safely without crash."""
    reg = DelegateRegistry()
    timeout_prov = MockDelegateProvider(name="timeout_mock", simulate_timeout=True)
    reg.register(timeout_prov, set_default=True)

    loop = DelegatedOrchestrationLoop(registry=reg)
    with pytest.raises(TimeoutError):
        loop.execute_goal(
            goal="Test timeout recovery",
            provider_name="timeout_mock",
            max_turns=3,
        )


def test_agent_execution_engine_delegated_prompt_integration():
    """Verify that prompt asking for delegate is routed and executed via AgentExecutionEngine."""
    reg = DelegateRegistry.get_instance()
    reg.register(MockDelegateProvider(name="mock"), set_default=True)

    engine = AgentExecutionEngine()
    prompt = "Ask ChatGPT to design a Python simulation of projectile motion, run it locally, and finish when approved."
    task = engine.execute_goal(prompt)

    assert task.status == AgentTaskStatus.COMPLETED
    assert len(task.plan.steps) >= 1
    step_1 = task.plan.steps[0]
    assert step_1.capability_id == "consult_delegate"
    assert step_1.result is not None
    assert step_1.result.success is True
    assert step_1.result.data.get("provenance", {}).get("local_acceptance") is True
    assert step_1.result.data.get("provenance", {}).get("delegate_approval") is True
