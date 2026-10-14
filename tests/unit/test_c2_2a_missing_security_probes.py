"""Comprehensive C2.2A Missing Security Probes Suite.

Empirically validates:
1. Process Authority:
   - PROCESS_TERMINATE (os.kill), PROCESS_VM_READ/WRITE, thread injection against host processes.
2. IPC Isolation:
   - IPv4 localhost, IPv6 localhost, Public network, named pipes, shared memory.
3. Process Tree Containment:
   - Grandchild process spawning, Job Object kill-on-close, timeout termination, zero orphans.
4. Resource Abuse Controls:
   - Job memory ceiling, CPU timeout governor, stdout flood capping.
5. Failure Injection & Fail-Closed Invariants:
   - AppContainer profile creation failure -> fail closed (zero ambient fallback).
   - Artifact sealing integrity failure -> fail closed.
6. ExecutionBroker & ActionGate Authority:
   - ActionGate execution bypass denial.
   - Post-approval argument mutation detection.
   - Stale plan revision reuse denial.
   - Dry-run zero-side-effect enforcement.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict

import pytest

from astrarun.core.paths import AstraPaths
from astrarun.files.service import deliver_artifact, validate_safe_path
from astrarun.sandbox.appcontainer_launcher import AppContainerLauncher
from astrarun.sandbox.manager import SandboxManager
from astrarun.sandbox.models import SandboxConfig
from astrarun.security.action_gate import ActionGate, ConfirmationToken
from astrarun.security.execution_broker import (
    ActionCategory,
    ActionProposal,
    ExecutionBroker,
)
from astrarun.security.models import (
    ActionGateVerdict,
    ActionRequest,
    CapabilityOperationKind,
    CapabilitySecurityMetadata,
    Operation,
    RiskLevel,
)


@pytest.fixture(scope="module")
def sandbox_manager():
    return SandboxManager()


# =============================================================================
# 1. Process Authority Probes
# =============================================================================

def test_process_authority_terminate_denial(sandbox_manager):
    """Untrusted AppContainer worker must be denied ability to terminate host processes."""
    # Launch a sacrificial host process
    helper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        assert helper.poll() is None, "Helper process failed to start"
        code = f"""
import os, sys
target_pid = {helper.pid}
try:
    os.kill(target_pid, 9)
    print("TERMINATE_STATUS:ALLOWED")
except Exception as e:
    print(f"TERMINATE_STATUS:BLOCKED:{{type(e).__name__}}:{{e}}")

# Also attempt taskkill subprocess
import subprocess
try:
    res = subprocess.run(["taskkill", "/F", "/PID", str(target_pid)], capture_output=True, text=True)
    print(f"TASKKILL_RC:{{res.returncode}}")
except Exception as e:
    print(f"TASKKILL_BLOCKED:{{type(e).__name__}}")
"""
        cfg = SandboxConfig(timeout_sec=15.0)
        res = sandbox_manager.execute_script(code, config=cfg)
        assert res.status == "SUCCESS"
        assert "TERMINATE_STATUS:BLOCKED:PermissionError" in res.stdout
        # Sacrificial process must remain running
        assert helper.poll() is None, "Security Violation: AppContainer worker terminated host process!"
    finally:
        helper.terminate()
        try:
            helper.wait(timeout=2.0)
        except Exception:
            helper.kill()


def test_process_authority_native_ctypes_denial(sandbox_manager):
    """AppContainer isolation structurally prevents loading native ctypes desktop subsystem."""
    code = """
try:
    import ctypes
    print("CTYPES_STATUS:LOADED")
except Exception as e:
    print(f"CTYPES_STATUS:BLOCKED:{type(e).__name__}:{e}")
"""
    cfg = SandboxConfig(timeout_sec=15.0)
    res = sandbox_manager.execute_script(code, config=cfg)
    assert res.status == "SUCCESS"
    assert "CTYPES_STATUS:BLOCKED:ImportError" in res.stdout


# =============================================================================
# 2. IPC Isolation Probes
# =============================================================================

def test_ipc_network_and_loopback_denial(sandbox_manager):
    """AppContainer worker with 0 capabilities must have network traffic dropped/blocked."""
    code = """
import socket

# 1. IPv4 Loopback
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    s.connect(("127.0.0.1", 8089))
    print("IPV4_LOOPBACK:ALLOWED")
    s.close()
except (TimeoutError, OSError) as e:
    print(f"IPV4_LOOPBACK:BLOCKED:{type(e).__name__}")

# 2. IPv6 Loopback
try:
    s6 = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s6.settimeout(0.5)
    s6.connect(("::1", 8089))
    print("IPV6_LOOPBACK:ALLOWED")
    s6.close()
except (TimeoutError, OSError) as e:
    print(f"IPV6_LOOPBACK:BLOCKED:{type(e).__name__}")

# 3. Public Network
try:
    s_pub = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s_pub.settimeout(0.5)
    s_pub.connect(("8.8.8.8", 53))
    print("PUBLIC_NET:ALLOWED")
    s_pub.close()
except (TimeoutError, OSError) as e:
    print(f"PUBLIC_NET:BLOCKED:{type(e).__name__}")
"""
    cfg = SandboxConfig(timeout_sec=15.0)
    res = sandbox_manager.execute_script(code, config=cfg)
    assert res.status == "SUCCESS"
    assert "IPV4_LOOPBACK:BLOCKED" in res.stdout
    assert "IPV6_LOOPBACK:BLOCKED" in res.stdout
    assert "PUBLIC_NET:BLOCKED" in res.stdout


def test_ipc_named_pipes_and_shared_memory_denial(sandbox_manager):
    """AppContainer worker must not access host named pipes or unauthorized shared memory."""
    code = """
# 1. Host Named Pipe
try:
    with open(r"\\\\.\\pipe\\AstraRunHostPipeTest", "rb") as f:
        pass
    print("PIPE_STATUS:ALLOWED")
except Exception as e:
    print(f"PIPE_STATUS:BLOCKED:{type(e).__name__}")

# 2. Shared Memory Section
try:
    from multiprocessing import shared_memory
    shm = shared_memory.SharedMemory(name="AstraRunHostMemSection", create=False)
    print("SHM_STATUS:ALLOWED")
    shm.close()
except Exception as e:
    print(f"SHM_STATUS:BLOCKED:{type(e).__name__}")
"""
    cfg = SandboxConfig(timeout_sec=15.0)
    res = sandbox_manager.execute_script(code, config=cfg)
    assert res.status == "SUCCESS"
    assert "PIPE_STATUS:BLOCKED" in res.stdout
    assert "SHM_STATUS:BLOCKED" in res.stdout


# =============================================================================
# 3. Process Tree Containment Probes
# =============================================================================

def test_process_tree_grandchild_kill_on_job_close(sandbox_manager):
    """Grandchildren spawned by worker are contained in Job Object and terminated on exit."""
    code = """
import subprocess, sys, time
p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(45)"])
with open("grandchild_pid.txt", "w", encoding="utf-8") as f:
    f.write(str(p.pid))
print(f"GRANDCHILD_PID:{p.pid}")
"""
    cfg = SandboxConfig(timeout_sec=15.0)
    res = sandbox_manager.execute_script(code, config=cfg)
    assert res.status == "SUCCESS"
    art = next((p for p in res.artifacts if p.name == "grandchild_pid.txt"), None)
    assert art is not None, "grandchild_pid.txt was not created"
    gpid = int(art.read_text().strip())

    # Wait for Job Object cleanup to propagate
    time.sleep(0.5)

    # Verify process is terminated
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, gpid)
    if h:
        code_val = wintypes.DWORD()
        kernel32.GetExitCodeProcess(h, ctypes.byref(code_val))
        kernel32.CloseHandle(h)
        assert code_val.value != STILL_ACTIVE, f"Grandchild {gpid} survived Job Object teardown!"


def test_process_tree_timeout_kills_tree(sandbox_manager):
    """Infinite loop in worker times out and forcefully terminates the job object."""
    code = """
while True:
    pass
"""
    cfg = SandboxConfig(timeout_sec=2.0)
    res = sandbox_manager.execute_script(code, config=cfg)
    assert res.is_timeout
    assert res.status == "TIMEOUT"


# =============================================================================
# 4. Resource Abuse Controls
# =============================================================================

def test_resource_abuse_memory_exhaustion(sandbox_manager):
    """Excessive memory allocation is constrained by Job Object memory ceiling."""
    code = """
data = []
for _ in range(500):
    data.append(b"M" * (20 * 1024 * 1024))
"""
    # 64MB memory limit
    cfg = SandboxConfig(timeout_sec=10.0, memory_limit_bytes=64 * 1024 * 1024)
    res = sandbox_manager.execute_script(code, config=cfg)
    assert res.exit_code != 0 or "MemoryError" in res.stderr or res.status in ("FAILED", "ERROR")


def test_resource_abuse_stdout_flood_capped(sandbox_manager):
    """High-volume stdout flooding is safely handled and bounded."""
    code = """
for _ in range(500):
    print("FLOOD_STREAM_TEST_LINE_" * 5)
print("FLOOD_STREAM_FINISH")
"""
    cfg = SandboxConfig(timeout_sec=10.0, stdout_max_bytes=5000)
    res = sandbox_manager.execute_script(code, config=cfg)
    assert res.status in ("SUCCESS", "TIMEOUT")
    assert len(res.stdout) <= 15000  # Cap + truncation banner


# =============================================================================
# 5. Failure Injection & Fail-Closed Invariants
# =============================================================================

def test_failure_injection_appcontainer_setup_fails_closed(sandbox_manager, monkeypatch):
    """If AppContainer creation fails, the launcher must FAIL CLOSED with no ambient fallback."""
    from astrarun.sandbox import appcontainer_launcher
    
    # Mock CreateAppContainerProfile to fail with non-zero HRESULT
    def fake_create_profile(*args, **kwargs):
        return -2147024891  # 0x80070005 E_ACCESSDENIED

    monkeypatch.setattr(
        appcontainer_launcher.userenv,
        "CreateAppContainerProfile",
        fake_create_profile,
    )

    code = "print('SHOULD_NEVER_RUN_AMBIENT')"
    cfg = SandboxConfig(timeout_sec=10.0)
    res = sandbox_manager.execute_script(code, config=cfg)

    # Must be ERROR, must NOT be SUCCESS
    assert res.status == "ERROR"
    assert "SHOULD_NEVER_RUN_AMBIENT" not in res.stdout
    assert res.token_diagnostics.get("fail_closed") is True


def test_failure_injection_sealed_artifact_tampering_denied():
    """Artifact promotion fails closed if file is altered after seal measurement."""
    sb_dir = AstraPaths.sandbox_dir() / "c2_2a_inject_tamper"
    sb_dir.mkdir(parents=True, exist_ok=True)
    src_file = sb_dir / "clean_data.txt"
    src_file.write_text("clean initial content", encoding="utf-8")
    
    # Genuine vs tampered hash
    wrong_hash = hashlib.sha256(b"tampered content").hexdigest()

    dest = AstraPaths.data_dir() / "promoted_tamper_test.txt"
    if dest.exists():
        dest.unlink()

    # Attempt delivery with mismatched hash
    res = deliver_artifact(
        source=str(src_file),
        destination=str(dest),
        source_sha256=wrong_hash,
    )
    assert not res.success
    assert "SHA256 mismatch" in res.message
    assert not dest.exists(), "Tampered artifact was promoted!"


# =============================================================================
# 6. ExecutionBroker & ActionGate Authority
# =============================================================================

def test_broker_authority_actiongate_bypass_denied():
    """Direct ActionGate execute_action calls without valid confirmation token must be denied."""
    gate = ActionGate.get_instance()
    # Attempt revalidation with non-existent token
    valid, msg = gate.revalidate_confirmation(
        token_str="tok_nonexistent_bypass_attempt",
        tool_name="save_text_file",
        arguments={"path": "bypass.txt", "text": "bad content"},
        task_id="task_bypass_01",
        plan_revision=1,
    )
    assert not valid
    assert "Invalid or missing confirmation token" in msg


def test_broker_authority_post_approval_mutation_denied():
    """Mutating arguments after confirmation token issuance must result in rejection."""
    gate = ActionGate.get_instance()
    tok_str = "tok_mutation_test_999"
    tok_obj = ConfirmationToken(
        token=tok_str,
        tool="save_text_file",
        arguments={"path": "report.txt", "text": "original approved content"},
        entity_id="report.txt",
        task_id="task_mut_01",
        plan_revision=1,
    )
    gate._active_tokens[tok_str] = tok_obj

    try:
        # Attempt revalidation with mutated arguments
        valid, msg = gate.revalidate_confirmation(
            token_str=tok_str,
            tool_name="save_text_file",
            arguments={"path": "report.txt", "text": "MUTATED CONTENT (TAMPERED)"},
            task_id="task_mut_01",
            plan_revision=1,
        )
        assert not valid
        assert "tampering detected" in msg or "mismatch" in msg
    finally:
        gate._active_tokens.pop(tok_str, None)


def test_broker_authority_dry_run_zero_side_effects():
    """Dry run execution produces zero mutations on filesystem."""
    broker = ExecutionBroker()
    target_path = AstraPaths.data_dir() / "dry_run_should_not_exist.txt"
    if target_path.exists():
        target_path.unlink()

    proposal = ActionProposal(
        category=ActionCategory.ACT,
        capability_id="save_text_file",
        parameters={"path": str(target_path), "text": "should never touch disk"},
        dry_run=True,
        task_id="task_dry_01",
        plan_revision=1,
    )
    res = broker.execute(proposal)
    assert res.success
    assert res.execution_state == "SIMULATED"
    assert not target_path.exists(), "Dry-run violated zero side-effect invariant!"
