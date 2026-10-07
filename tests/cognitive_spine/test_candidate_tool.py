"""Cognitive Spine Regression Suite: CandidateTool, AST Inspector & Sandbox Tests."""

import os
import pytest
from pathlib import Path

from astrarun.sandbox.manager import SandboxManager
from astrarun.sandbox.models import SandboxConfig, SandboxProfile
from astrarun.tools.ast_inspector import ASTInspector
from astrarun.tools.candidate import CandidateTool, CodeProvenance


def test_candidate_tool_provenance_and_hash():
    """Verify CandidateTool source hashing and provenance immutability."""
    cand = CandidateTool(
        goal="Test multi-file hashing",
        source_files={
            "main.py": "import helper\nhelper.greet()",
            "helper.py": "def greet(): print('Hello from helper!')",
        },
        entrypoint="main.py",
        task_id="test_prov_001",
    )
    h1 = cand.compute_source_hash()
    assert len(h1) == 64

    # Modifying content must change hash
    cand.source_files["helper.py"] = "def greet(): print('Modified!')"
    h2 = cand.compute_source_hash()
    assert h1 != h2


def test_ast_inspector_forbids_dangerous_calls():
    """Verify ASTInspector flags dangerous modules, dynamic exec, and system commands."""
    inspector = ASTInspector()

    # 1. os.system
    bad_code_1 = "import os\nos.system('dir')"
    res_1 = inspector.inspect(bad_code_1)
    assert not res_1.is_safe
    assert any("system" in v for v in res_1.violations)

    # 2. ctypes
    bad_code_2 = "import ctypes\nctypes.windll.user32.MessageBoxW(0, 'x', 'y', 0)"
    res_2 = inspector.inspect(bad_code_2)
    assert not res_2.is_safe
    assert any("ctypes" in v for v in res_2.violations)

    # 3. eval/exec
    bad_code_3 = "eval('2 + 2')"
    res_3 = inspector.inspect(bad_code_3)
    assert not res_3.is_safe
    assert any("eval" in v for v in res_3.violations)

    # 4. Multi-file candidate inspection
    cand = CandidateTool(
        goal="Malicious tool test",
        source_files={
            "main.py": "import mod\nmod.run()",
            "mod.py": "import socket\ns = socket.socket()",
        },
        entrypoint="main.py",
    )
    res_multi = inspector.inspect_candidate(cand)
    assert not res_multi.is_safe
    assert any("socket" in v for v in res_multi.violations)


def test_sandbox_path_containment():
    """Verify SandboxManager blocks directory traversal and path escapes."""
    sandbox = SandboxManager()
    cand_escape = CandidateTool(
        goal="Escape test",
        source_files={
            "../../escape.txt": "evil",
            "main.py": "print('ok')",
        },
        entrypoint="main.py",
    )
    result = sandbox.execute_candidate(cand_escape)
    assert result.status == "DENIED"
    assert "Path traversal detected" in result.stderr or "Target file path escapes sandbox" in result.stderr


def test_sandbox_candidate_execution():
    """Verify clean execution of safe candidate tool in sandbox with artifact generation."""
    import uuid
    sandbox = SandboxManager()
    run_id = f"test_sb_exec_{uuid.uuid4().hex[:8]}"
    cand = CandidateTool(
        goal="Safe execution test",
        source_files={
            "main.py": "with open('output.txt', 'w') as f: f.write('sandbox_ok')\nprint('done')",
        },
        entrypoint="main.py",
        task_id=run_id,
    )
    cfg = SandboxConfig(
        run_id=run_id,
        profile=SandboxProfile.EPHEMERAL_TOOL,
        preserve_on_exit=True,
    )
    result = sandbox.execute_candidate(cand, config=cfg)
    assert result.is_success
    assert result.exit_code == 0
    assert "done" in result.stdout
    assert any(a.name == "output.txt" for a in result.created_artifacts)
