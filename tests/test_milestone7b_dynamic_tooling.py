"""Unit and Governance Tests for Milestone 7B Dynamic Tooling & Product Hardening.

Covers:
- Trust Kernel boundary and mutation rejection.
- CandidateTool schema and DependencyRequest.
- AST Inspector safety screening (ctypes, socket, pip, exec, os.system).
- SandboxManager environment scrubbing and contained execution.
- NetworkBroker URL validation and DownloadQuarantine.
- DynamicToolBuilder pipeline and bounded repair loop.
- Dynamic Tool -> Skill promotion lifecycle.
- Continuity engine (task, session, semantic continuation).
- Config and SQLite database schema migrations.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from astrarun.config.migrations import (
    CURRENT_CONFIG_VERSION,
    CURRENT_DB_VERSION,
    migrate_config_dict,
    migrate_database,
)
from astrarun.network.broker import NetworkBroker
from astrarun.network.quarantine import DownloadQuarantine
from astrarun.sandbox.manager import SandboxManager
from astrarun.sandbox.models import SandboxConfig, SandboxProfile
from astrarun.security.trust_kernel import (
    is_trust_kernel_path,
    validate_kernel_mutation_request,
)
from astrarun.tasks.continuity import ContinuityEngine, TaskCheckpoint
from astrarun.tools.ast_inspector import ASTInspector
from astrarun.tools.candidate import CandidateTool, DependencyRequest
from astrarun.tools.dynamic_builder import DynamicToolBuilder
from astrarun.tools.lifecycle import ToolLifecycleManager


# =========================================================================
# 1. Trust Kernel Boundary Tests
# =========================================================================

def test_trust_kernel_invariants():
    """Verify that Trust Kernel components cannot be mutated autonomously."""
    # Protected paths
    assert is_trust_kernel_path("src/astrarun/security/action_gate.py")
    assert is_trust_kernel_path("src/astrarun/sandbox/manager.py")
    assert is_trust_kernel_path("src/astrarun/network/broker.py")
    # Unprotected paths
    assert not is_trust_kernel_path("src/astrarun/ui/cards.py")
    assert not is_trust_kernel_path("skills/open_notepad/SKILL.md")

    # Autonomous modification denied
    allowed, msg = validate_kernel_mutation_request(
        "src/astrarun/security/action_gate.py",
        is_autonomous_agent=True,
        has_explicit_human_approval=False,
    )
    assert not allowed
    assert "strictly prohibited" in msg

    # Human authorized developer modification allowed
    allowed_human, _ = validate_kernel_mutation_request(
        "src/astrarun/security/action_gate.py",
        is_autonomous_agent=False,
        has_explicit_human_approval=True,
    )
    assert allowed_human


# =========================================================================
# 2. CandidateTool Schema & Serialization
# =========================================================================

def test_candidate_tool_schema_and_serialization():
    """Verify CandidateTool dataclass serialization and full script composition."""
    dep = DependencyRequest(package="numpy", version_spec=">=1.24", reason="Array operations")
    tool = CandidateTool(
        goal="Calculate matrix eigenvalues",
        executable_code="import numpy as np\ndef calc(): return np.eye(3)",
        test_verification_block="assert calc().shape == (3, 3)",
        inputs={"dimension": 3},
        outputs={"matrix": "identity"},
        external_dependencies=[dep],
        sandbox_profile="EPHEMERAL_TOOL",
    )

    d = tool.to_dict()
    assert d["goal"] == "Calculate matrix eigenvalues"
    assert len(d["external_dependencies"]) == 1
    assert d["external_dependencies"][0]["package"] == "numpy"

    restored = CandidateTool.from_dict(d)
    assert restored.tool_id == tool.tool_id
    assert restored.external_dependencies[0].reason == "Array operations"

    script = tool.full_script(include_test=True)
    assert "Candidate Tool" in script
    assert "if __name__ == '__main__':" in script
    assert "assert calc().shape == (3, 3)" in script


# =========================================================================
# 3. AST Inspector Safety Screening
# =========================================================================

def test_ast_inspector_safety_detection():
    """Verify static AST screening catches dangerous modules and calls."""
    inspector = ASTInspector()

    # 1. Safe calculation
    safe_code = """
import math
def compute(x):
    return math.sqrt(x) * 2
print(compute(16))
"""
    res = inspector.inspect(safe_code)
    assert res.is_safe
    assert "math" in res.imported_modules

    # 2. Prohibited ctypes
    unsafe_ctypes = """
import ctypes
ctypes.windll.kernel32.ExitProcess(0)
"""
    res = inspector.inspect(unsafe_ctypes)
    assert not res.is_safe
    assert any("ctypes" in v for v in res.violations)

    # 3. Prohibited raw socket
    unsafe_socket = """
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('127.0.0.1', 80))
"""
    res = inspector.inspect(unsafe_socket)
    assert not res.is_safe
    assert any("socket" in v for v in res.violations)

    # 4. Prohibited pip
    unsafe_pip = """
import pip
pip.main(['install', 'requests'])
"""
    res = inspector.inspect(unsafe_pip)
    assert not res.is_safe
    assert any("pip" in v for v in res.violations)

    # 5. Prohibited eval/exec
    unsafe_eval = """
user_str = "__import__('os').system('dir')"
eval(user_str)
"""
    res = inspector.inspect(unsafe_eval)
    assert not res.is_safe
    assert any("eval" in v for v in res.violations)

    # 6. Prohibited os.system
    unsafe_os = """
import os
os.system("rmdir /s /q C:\\\\")
"""
    res = inspector.inspect(unsafe_os)
    assert not res.is_safe
    assert any("os.system" in v for v in res.violations)


# =========================================================================
# 4. SandboxManager Environment Scrubbing & Contained Execution
# =========================================================================

def test_sandbox_manager_environment_and_execution(tmp_path):
    """Verify environment sanitization and contained execution in SandboxManager."""
    sb = SandboxManager(base_dir=tmp_path / "sandbox")

    # Verify secret scrubbing
    os.environ["FAKE_OPENAI_API_KEY"] = "sk-supersecret12345"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "superawssecret"
    clean_env = sb.sanitize_environment()
    assert "FAKE_OPENAI_API_KEY" not in clean_env
    assert "AWS_SECRET_ACCESS_KEY" not in clean_env
    assert "PATH" in clean_env

    # Execute harmless Python code in sandbox
    script = """
import sys
print("SANDBOX_TEST_OK")
with open("test_artifact.txt", "w") as f:
    f.write("artifact_content")
"""
    cfg = SandboxConfig(profile=SandboxProfile.EPHEMERAL_TOOL, preserve_on_exit=True)
    res = sb.execute_script(script, config=cfg)
    assert res.is_success
    assert "SANDBOX_TEST_OK" in res.stdout
    assert len(res.created_artifacts) >= 1
    assert any(a.name == "test_artifact.txt" for a in res.created_artifacts)

    # RESEARCH_DOWNLOAD profile disallows script execution
    cfg_quar = SandboxConfig(profile=SandboxProfile.RESEARCH_DOWNLOAD)
    res_quar = sb.execute_script(script, config=cfg_quar)
    assert res_quar.status == "DENIED"


# =========================================================================
# 5. NetworkBroker & Download Quarantine
# =========================================================================

def test_network_broker_and_quarantine(tmp_path):
    """Verify default DENY URL validation and DownloadQuarantine staging."""
    quar = DownloadQuarantine(quarantine_dir=tmp_path / "quarantine")
    broker = NetworkBroker(quarantine=quar)

    # Protocol validation
    valid, _ = broker.validate_url("https://docs.python.org/3/")
    assert valid
    invalid_proto, msg = broker.validate_url("ftp://malicious.org/file.bin")
    assert not invalid_proto
    assert "protocol" in msg

    # Loopback / Private IP protection
    blocked_ip, msg = broker.validate_url("http://169.254.169.254/latest/meta-data/")
    assert not blocked_ip
    assert "blocked" in msg

    # Quarantine file staging
    test_bytes = b"print('external downloaded script')\n"
    record = quar.stage_file(
        content=test_bytes,
        filename="untrusted_script.py",
        source_url="https://example.com/untrusted_script.py",
        content_type="text/x-python",
    )
    assert record.status == "QUARANTINED"
    assert not record.execution_permitted
    assert Path(record.local_path).exists()
    assert Path(record.meta_path).exists()

    # Automatic execution check returns False
    assert not quar.is_execution_permitted(record.local_path)


# =========================================================================
# 6. DynamicToolBuilder & Bounded Repair
# =========================================================================

def test_dynamic_tool_builder_pipeline_and_repair(tmp_path):
    """Verify tool synthesis, AST inspection, sandbox execution, and bounded repair."""
    sb = SandboxManager(base_dir=tmp_path / "sandbox")
    builder = DynamicToolBuilder(sandbox_manager=sb, max_repair_attempts=2)

    # 1. Existing capability check
    found = builder.search_existing_capabilities("inspect the process on port 8080")
    assert found == "inspect_port"

    # 2. Dynamic math synthesis and execution
    candidate = builder.synthesize_tool_for_goal("compute mathematical constants")
    report = builder.build_and_execute(candidate)
    assert report.is_success
    assert "pi" in report.sandbox_result.stdout

    # 3. Bounded repair: intentional ZeroDivisionError repaired by builder
    buggy_code = """
import numpy as np
R = np.array([0.0, 1.0, 2.0])
# Buggy division by zero
if R[0] == 0:
    raise ZeroDivisionError("division by zero in R")
print("Done")
"""
    buggy_candidate = CandidateTool(
        goal="Test repair",
        executable_code=buggy_code,
        sandbox_profile="EPHEMERAL_TOOL",
    )
    # Mocking repair to simulate fixing the error on attempt 1
    def mock_repair(cand, err, attempt):
        return "import numpy as np\nprint('REPAIRED_SUCCESS')\n"
    builder.repair_code = mock_repair

    repair_report = builder.build_and_execute(buggy_candidate)
    assert repair_report.is_success
    assert repair_report.repair_attempts == 1
    assert "REPAIRED_SUCCESS" in repair_report.sandbox_result.stdout


# =========================================================================
# 7. Dynamic Tool -> Skill Promotion Lifecycle
# =========================================================================

def test_dynamic_tool_to_skill_promotion(tmp_path):
    """Verify trajectory recording and skill promotion into SKILL.md format."""
    mgr = ToolLifecycleManager(
        storage_path=tmp_path / "trajectories.json",
        skills_dir=tmp_path / "skills",
        promotion_threshold=2,
    )

    candidate = CandidateTool(
        goal="Extract table data from CSV",
        executable_code="import csv\nprint('Parsed CSV')",
        test_verification_block="print('Verified')",
    )

    # Run 1: Not eligible yet
    mgr.record_execution(candidate, success=True)
    assert not mgr.is_eligible_for_promotion(candidate.goal)

    # Run 2: Eligible for promotion
    mgr.record_execution(candidate, success=True)
    assert mgr.is_eligible_for_promotion(candidate.goal)

    # Promote to permanent skill
    skill_file = mgr.promote_to_skill(candidate, skill_name="csv_table_extractor")
    assert skill_file.exists()
    content = skill_file.read_text(encoding="utf-8")
    assert "name: csv_table_extractor" in content
    assert "## Verification Procedure" in content


# =========================================================================
# 8. Continuity Engine (Task, Session, Semantic Continuation)
# =========================================================================

def test_continuity_engine(tmp_path):
    """Verify task checkpoint saving, interrupted task recovery, and semantic resolution."""
    engine = ContinuityEngine(checkpoints_dir=tmp_path / "checkpoints")

    # 1. Save checkpoint
    cp1 = engine.save_checkpoint(
        task_id="task_graph_001",
        goal="Create 3D graph of z = sin(sqrt(x^2 + y^2))",
        status="COMPLETED",
        artifacts=["dynamic_3d_graph.png"],
        summary="Rendered 3D sine surface to dynamic_3d_graph.png",
    )
    assert cp1.task_id == "task_graph_001"

    # 2. Interrupted task discovery
    engine.save_checkpoint(
        task_id="task_calc_002",
        goal="Process log file",
        status="IN_PROGRESS",
    )
    interrupted = engine.discover_interrupted_tasks()
    assert len(interrupted) == 1
    assert interrupted[0].task_id == "task_calc_002"

    # 3. Semantic continuity resolution: "continue the graph thing we were doing"
    res = engine.resolve_continuation_request("continue the graph thing we were doing")
    assert res.resolved
    assert res.target_task is not None
    assert res.target_task.task_id == "task_graph_001"
    assert res.confidence >= 0.80

    # 4. Generic "continue what we were doing" picks most recent task
    res_generic = engine.resolve_continuation_request("continue what we were doing")
    assert res_generic.resolved
    assert res_generic.target_task.task_id == "task_calc_002"


# =========================================================================
# 9. Config and Database Schema Migrations
# =========================================================================

def test_config_and_database_migrations(tmp_path):
    """Verify schema migrations for config JSON and SQLite database."""
    # 1. Config migration v0 -> v2
    old_config = {
        "ui": {"theme": "dark"},
        "history": {"enabled": True},
    }
    migrated, ver, applied = migrate_config_dict(old_config)
    assert ver == CURRENT_CONFIG_VERSION
    assert "sandbox" in migrated
    assert "network" in migrated
    assert "dynamic_tools" in migrated
    assert "trust_kernel" in migrated
    assert len(applied) == 2

    # 2. Database migration
    db_file = tmp_path / "test_history.db"
    final_ver, db_applied = migrate_database(db_file)
    assert final_ver == CURRENT_DB_VERSION
    assert len(db_applied) == 2

    # Verify columns in migrated DB
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(task_history)")
    cols = {row[1] for row in cur.fetchall()}
    assert "task_id" in cols
    assert "artifacts" in cols
    assert "risk_level" in cols
    assert "tool_id" in cols

    cur.execute("SELECT version, description FROM _schema_migrations")
    mig_rows = cur.fetchall()
    assert len(mig_rows) == 2
    conn.close()
