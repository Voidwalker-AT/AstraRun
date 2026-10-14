"""Comprehensive test suite for AstraRun 1.0 Milestone 1:
Core Foundation & Sandboxed Execution Runtime.

Covers:
  1. Safe operations (workspace read/create, harmless Python/PowerShell)
  2. Path attacks (traversal, system dirs, 8.3 aliases, %SystemRoot%, workspace escape)
  3. Command attacks (rm -rf, del /f /q, format, git reset --hard, encoded powershell)
  4. AST code inspection (shutil.rmtree, raw sockets, eval/exec, obfuscated base64)
  5. Process lifecycle & Win32 Job Object containment (timeouts, cancel_task, tree cleanup, ownership)
  6. SecretBroker & real-time stream scrubbing (Bearer, API keys, URLs, JIT resolution)
  7. Stealth headless execution (CREATE_NO_WINDOW)
  8. Adversarial injection & tool abuse prevention
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

from astrarun.execution.job_object import Win32JobObject
from astrarun.execution.models import (
    ExecutionObservation,
    ExecutionRequest,
    ExecutionStatus,
)
from astrarun.execution.process_tracker import ProcessTracker
from astrarun.execution.runtime import CREATE_NO_WINDOW, DynamicExecutionRuntime
from astrarun.security.action_gate import ActionGate, ActionGateConfig
from astrarun.security.models import (
    ActionGateVerdict,
    ActionRequest,
    Operation,
    RiskLevel,
)
from astrarun.security.policies import ASTCodePolicy, CommandPolicy, PathPolicy
from astrarun.security.secret_broker import RedactionReport, SecretBroker


# =============================================================================
# 1. SAFE OPERATIONS
# =============================================================================

class TestSafeOperations:
    """Verifies that legitimate development operations proceed cleanly."""

    def test_workspace_file_read_allowed(self, tmp_path):
        gate = ActionGate(path_policy=PathPolicy(allowed_workspace_roots=[str(tmp_path)]))
        test_file = tmp_path / "README.md"
        test_file.write_text("# Test Workspace", encoding="utf-8")

        req = ActionRequest(
            operation=Operation.READ,
            capability="file_system",
            target=str(test_file),
        )
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.ALLOW
        assert eval_res.risk == RiskLevel.LOW

    def test_workspace_file_create_allowed(self, tmp_path):
        gate = ActionGate(path_policy=PathPolicy(allowed_workspace_roots=[str(tmp_path)]))
        new_file = tmp_path / "src" / "main.py"

        req = ActionRequest(
            operation=Operation.CREATE,
            capability="file_system",
            target=str(new_file),
        )
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.ALLOW
        assert eval_res.risk == RiskLevel.LOW

    def test_harmless_python_execution(self):
        runtime = DynamicExecutionRuntime()
        req = ExecutionRequest(
            executable=sys.executable,
            args=["-c", "print('ASTRA_SANDBOX_ONLINE')"],
            timeout=5.0,
        )
        obs = asyncio.run(runtime.execute(req))
        assert obs.status == ExecutionStatus.SUCCESS
        assert obs.exit_code == 0
        assert "ASTRA_SANDBOX_ONLINE" in obs.stdout
        assert obs.killed is False

    def test_harmless_powershell_execution(self):
        runtime = DynamicExecutionRuntime()
        req = ExecutionRequest(
            executable="powershell.exe",
            args=["-NoProfile", "-Command", "Write-Output 'POWERSHELL_SAFE'"],
            timeout=5.0,
        )
        obs = asyncio.run(runtime.execute(req))
        assert obs.status == ExecutionStatus.SUCCESS
        assert obs.exit_code == 0
        assert "POWERSHELL_SAFE" in obs.stdout


# =============================================================================
# 2. PATH ATTACKS
# =============================================================================

class TestPathAttacks:
    """Verifies path boundary enforcement and defense against traversal attacks."""

    @pytest.fixture
    def path_policy(self, tmp_path):
        return PathPolicy(
            allowed_workspace_roots=[str(tmp_path)],
            disallowed_system_roots=[r"C:\Windows", r"C:\Program Files"],
        )

    def test_path_traversal_into_system_dir_denied(self, path_policy):
        # Traversal using .. that resolves into C:\Windows
        traversal_target = r"C:\Program Files\..\Windows\System32\cmd.exe"
        req = ActionRequest(
            operation=Operation.MODIFY,
            capability="file_system",
            target=traversal_target,
        )
        gate = ActionGate(path_policy=path_policy)
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.DENY
        assert "Forbidden mutation targeting protected system directory" in eval_res.reason
        assert eval_res.risk == RiskLevel.CRITICAL

    def test_path_traversal_outside_workspace_requires_confirmation(self, path_policy, tmp_path):
        # Traversal using .. that escapes the workspace into an unauthorized user folder
        traversal_target = str(tmp_path / ".." / "OtherFolder" / "data.json")
        req = ActionRequest(
            operation=Operation.MODIFY,
            capability="file_system",
            target=traversal_target,
        )
        gate = ActionGate(path_policy=path_policy)
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.REQUIRE_CONFIRMATION
        assert "outside primary workspace boundaries" in eval_res.reason

    def test_system_directory_modification_denied(self, path_policy):
        gate = ActionGate(path_policy=path_policy)
        for sys_path in [r"C:\Windows\System32\drivers\etc\hosts", r"C:\Windows\explorer.exe"]:
            req = ActionRequest(
                operation=Operation.MODIFY,
                capability="file_system",
                target=sys_path,
            )
            eval_res = gate.evaluate_request(req)
            assert eval_res.verdict == ActionGateVerdict.DENY
            assert eval_res.risk == RiskLevel.CRITICAL

    def test_mixed_case_normalization_bypass(self, path_policy):
        gate = ActionGate(path_policy=path_policy)
        mixed_case = r"c:\wInDoWs\sYsTeM32\cOnFiG\sAm"
        req = ActionRequest(
            operation=Operation.READ,
            capability="file_system",
            target=mixed_case,
        )
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.DENY
        assert eval_res.risk == RiskLevel.CRITICAL

    def test_systemroot_env_expansion_bypass(self, path_policy):
        gate = ActionGate(path_policy=path_policy)
        env_path = r"%SystemRoot%\System32\drivers\etc\hosts"
        req = ActionRequest(
            operation=Operation.MODIFY,
            capability="file_system",
            target=env_path,
        )
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.DENY
        assert eval_res.risk == RiskLevel.CRITICAL

    def test_workspace_root_escape_requires_confirmation(self, path_policy):
        gate = ActionGate(path_policy=path_policy)
        outside_target = r"D:\ExternalProject\config.json"
        req = ActionRequest(
            operation=Operation.MODIFY,
            capability="file_system",
            target=outside_target,
        )
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.REQUIRE_CONFIRMATION
        assert "outside primary workspace boundaries" in eval_res.reason


# =============================================================================
# 3. COMMAND ATTACKS
# =============================================================================

class TestCommandAttacks:
    """Verifies that destructive, formatting, and forced shell commands are blocked or quarantined."""

    @pytest.fixture
    def gate(self):
        return ActionGate()

    def test_format_disk_hard_blocked(self, gate):
        for cmd in ["format c: /y", "format d: -q"]:
            req = ActionRequest(
                operation=Operation.EXECUTE,
                capability="execution_runtime",
                target="cmd.exe",
                parameters={"command": cmd},
            )
            eval_res = gate.evaluate_request(req)
            assert eval_res.verdict == ActionGateVerdict.DENY
            assert "Disk format command is strictly forbidden" in eval_res.reason
            assert eval_res.risk == RiskLevel.CRITICAL

    def test_diskpart_hard_blocked(self, gate):
        req = ActionRequest(
            operation=Operation.EXECUTE,
            capability="execution_runtime",
            target="diskpart.exe",
            parameters={"command": "diskpart /s script.txt"},
        )
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.DENY
        assert "Diskpart utility execution is strictly forbidden" in eval_res.reason
        assert eval_res.risk == RiskLevel.CRITICAL

    def test_system_file_deletion_hard_blocked(self, gate):
        for cmd in [
            r"del C:\Windows\System32\drivers\etc\hosts",
            r"rmdir /s /q C:\Windows",
            r"Remove-Item -Recurse C:\Windows\System32",
        ]:
            req = ActionRequest(
                operation=Operation.EXECUTE,
                capability="execution_runtime",
                target="cmd.exe",
                parameters={"command": cmd},
            )
            eval_res = gate.evaluate_request(req)
            assert eval_res.verdict == ActionGateVerdict.DENY
            assert eval_res.risk == RiskLevel.CRITICAL

    def test_git_reset_hard_requires_confirmation(self, gate):
        req = ActionRequest(
            operation=Operation.EXECUTE,
            capability="execution_runtime",
            target="git.exe",
            parameters={"command": "git reset --hard HEAD~1"},
        )
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.REQUIRE_CONFIRMATION
        assert "git reset --hard" in eval_res.reason
        assert eval_res.confirmation_token is not None

    def test_git_force_push_requires_confirmation(self, gate):
        req = ActionRequest(
            operation=Operation.EXECUTE,
            capability="execution_runtime",
            target="git.exe",
            parameters={"command": "git push origin master --force"},
        )
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.REQUIRE_CONFIRMATION
        assert "force push" in eval_res.reason

    def test_rm_rf_and_del_fq_require_confirmation(self, gate):
        for cmd in ["rm -rf ./build", "del /f /q *.log"]:
            req = ActionRequest(
                operation=Operation.EXECUTE,
                capability="execution_runtime",
                target="cmd.exe",
                parameters={"command": cmd},
            )
            eval_res = gate.evaluate_request(req)
            assert eval_res.verdict == ActionGateVerdict.REQUIRE_CONFIRMATION
            assert eval_res.confirmation_token is not None

    def test_encoded_powershell_requires_confirmation(self, gate):
        req = ActionRequest(
            operation=Operation.EXECUTE,
            capability="execution_runtime",
            target="powershell.exe",
            parameters={"command": "powershell.exe -EncodedCommand SGVsbG8gV29ybGQgZnJvbSBBc3RyYQ=="},
        )
        eval_res = gate.evaluate_request(req)
        assert eval_res.verdict == ActionGateVerdict.REQUIRE_CONFIRMATION
        assert "Encoded PowerShell script" in eval_res.reason


# =============================================================================
# 4. AST CODE INSPECTION
# =============================================================================

class TestASTCodeInspection:
    """Verifies static AST inspection of dynamic Python payloads."""

    @pytest.fixture
    def ast_policy(self):
        return ASTCodePolicy()

    def test_ast_detects_shutil_rmtree(self, ast_policy):
        code = "import shutil\nshutil.rmtree('/some/path')"
        verdict, reason, risk = ast_policy.evaluate_code(code)
        assert verdict == ActionGateVerdict.DENY
        assert "shutil.rmtree" in reason
        assert risk == RiskLevel.CRITICAL

    def test_ast_detects_raw_sockets(self, ast_policy):
        code = "import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\ns.connect(('1.1.1.1', 80))"
        verdict, reason, risk = ast_policy.evaluate_code(code)
        assert verdict == ActionGateVerdict.DENY
        assert "socket" in reason
        assert risk == RiskLevel.CRITICAL

    def test_ast_detects_eval_exec(self, ast_policy):
        for code in ["eval('__import__(\"os\").system(\"whoami\")')", "exec('print(123)')"]:
            verdict, reason, risk = ast_policy.evaluate_code(code)
            assert verdict == ActionGateVerdict.REQUIRE_CONFIRMATION
            assert "eval" in reason or "exec" in reason

    def test_ast_detects_obfuscated_base64_exec(self, ast_policy):
        code = "import base64\npayload = base64.b64decode('cHJpbnQoMSk=')\nexec(payload)"
        verdict, reason, risk = ast_policy.evaluate_code(code)
        assert verdict == ActionGateVerdict.REQUIRE_CONFIRMATION

    def test_ast_harmless_scientific_script_passes(self, ast_policy):
        code = """
import math
import json

data = {"values": [math.sqrt(i) for i in range(10)]}
output = json.dumps(data)
print(output)
"""
        verdict, reason, risk = ast_policy.evaluate_code(code)
        assert verdict == ActionGateVerdict.ALLOW
        assert risk == RiskLevel.LOW


# =============================================================================
# 5. PROCESS LIFECYCLE & WIN32 JOB OBJECTS
# =============================================================================

class TestProcessAndJobObjects:
    """Verifies Win32 Job Object containment, timeouts, cancellation, and tree cleanup."""

    def test_execution_timeout_enforced(self):
        runtime = DynamicExecutionRuntime()
        req = ExecutionRequest(
            executable=sys.executable,
            args=["-c", "import time; time.sleep(10)"],
            timeout=1.0,
        )
        t0 = time.monotonic()
        obs = asyncio.run(runtime.execute(req))
        dur = time.monotonic() - t0

        assert obs.status == ExecutionStatus.TIMEOUT
        assert obs.timeout is True
        assert obs.killed is True
        assert obs.exit_code == 124
        assert dur < 3.0, f"Timeout took too long: {dur}s"

    def test_cancel_task_stops_immediately(self):
        runtime = DynamicExecutionRuntime()
        task_id = "test_cancel_task_id_001"
        req = ExecutionRequest(
            executable=sys.executable,
            args=["-c", "import time; time.sleep(15)"],
            task_id=task_id,
            timeout=15.0,
        )

        async def run_and_cancel():
            task = asyncio.create_task(runtime.execute(req))
            await asyncio.sleep(0.5)
            cancelled = runtime.cancel_task(task_id)
            obs = await task
            return cancelled, obs

        cancelled, obs = asyncio.run(run_and_cancel())
        assert cancelled is True
        assert obs.status == ExecutionStatus.CANCELLED
        assert obs.killed is True
        assert obs.duration_ms < 3000.0

    def test_win32_job_object_lifecycle(self):
        if os.name != "nt":
            pytest.skip("Win32 Job Objects are Windows-specific")

        with Win32JobObject(name="test_job_lifecycle", memory_limit_bytes=100 * 1024 * 1024) as job:
            assert job.is_valid
            assert job.handle is not None
            peak = job.query_peak_memory()
            assert isinstance(peak, int)

    def test_child_process_tree_termination_zero_orphans(self):
        if os.name != "nt":
            pytest.skip("Win32 Job Objects are Windows-specific")

        import subprocess
        import psutil

        job = Win32JobObject()
        p = subprocess.Popen(
            ["cmd.exe", "/c", "powershell -NoProfile -Command Start-Sleep 20"],
            creationflags=CREATE_NO_WINDOW,
        )
        assert job.assign_process(int(p._handle)) is True
        time.sleep(1.0)

        # Confirm child/grandchild powershell process exists under p
        try:
            parent_proc = psutil.Process(p.pid)
            spawned_pids = [cp.pid for cp in parent_proc.children(recursive=True)]
        except psutil.NoSuchProcess:
            spawned_pids = []
        assert len(spawned_pids) >= 1

        # Terminate and close job
        assert job.terminate() is True
        job.close()
        time.sleep(0.5)

        # Confirm that the spawned processes were killed by the job closure
        ps_pids_after = [
            pid for pid in spawned_pids
            if psutil.pid_exists(pid)
        ]
        assert len(ps_pids_after) == 0, f"Orphaned processes remained: {ps_pids_after}"

    def test_process_ownership_protection(self):
        tracker = ProcessTracker.get_instance()
        current_pid = os.getpid()

        # Current process is NOT registered with AstraRun
        assert tracker.is_astra_owned(current_pid) is False

        # Attempting to kill an unowned process PID raises PermissionError
        with pytest.raises(PermissionError) as exc_info:
            tracker.kill_process_tree(current_pid)

        assert "Safety violation: PID" in str(exc_info.value)
        assert "is not owned by AstraRun" in str(exc_info.value)


# =============================================================================
# 6. SECRETS & REDACTION
# =============================================================================

class TestSecretsAndRedaction:
    """Verifies JIT secret resolution and real-time output stream scrubbing."""

    @pytest.fixture(autouse=True)
    def clean_secret_broker(self):
        broker = SecretBroker.get_instance()
        broker.clear()
        yield broker
        broker.clear()

    def test_bearer_token_scrubbed_from_stdout(self, clean_secret_broker):
        raw = "User token: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\nStatus: active"
        clean, report = clean_secret_broker.scrub_text(raw)
        assert "Bearer ***REDACTED***" in clean
        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in clean
        assert report.has_redactions is True
        assert "BEARER_TOKEN" in report.redacted_types

    def test_api_key_scrubbed_from_stderr(self, clean_secret_broker):
        raw = "Error: Invalid API Key passed: sk-ant-api03-abcdef1234567890abcdef1234567890"
        clean, report = clean_secret_broker.scrub_text(raw)
        assert "***REDACTED:ANTHROPIC_KEY***" in clean
        assert "sk-ant-api03-abcdef1234567890abcdef1234567890" not in clean
        assert report.has_redactions is True

    def test_url_credentials_scrubbed(self, clean_secret_broker):
        raw = "Connecting to https://admin:SuperSecretPass123!@internal.cluster.corp/api/v1"
        clean, report = clean_secret_broker.scrub_text(raw)
        assert "https://admin:***REDACTED***@internal.cluster.corp" in clean
        assert "SuperSecretPass123!" not in clean
        assert report.has_redactions is True

    def test_registered_vault_secret_resolved_only_at_boundary_and_scrubbed(self, clean_secret_broker):
        secret_val = "SUPER_SECRET_PRODUCTION_KEY_998877"
        handle = "secret://VAULT/PROD_TOKEN"
        clean_secret_broker.register_secret(handle, secret_val)

        runtime = DynamicExecutionRuntime(secret_broker=clean_secret_broker)
        # Process echoes the environment variable that had the secret handle
        req = ExecutionRequest(
            executable=sys.executable,
            args=["-c", "import os; print('SECRET_IS=' + os.environ.get('MY_TOKEN', ''))"],
            environment={"MY_TOKEN": handle},
            timeout=5.0,
        )

        obs = asyncio.run(runtime.execute(req))
        assert obs.status == ExecutionStatus.SUCCESS

        # The raw secret must NEVER appear in stdout or audit record!
        assert secret_val not in obs.stdout
        assert secret_val not in str(obs.audit_event)
        assert obs.redaction_occurred is True
        assert f"***REDACTED:{handle}***" in obs.stdout


# =============================================================================
# 7. STEALTH EXECUTION
# =============================================================================

class TestStealthExecution:
    """Verifies headless execution flags without console flashing."""

    def test_stealth_defaults_to_true(self):
        req = ExecutionRequest(executable="cmd.exe")
        assert req.stealth is True

    def test_create_no_window_constant(self):
        assert CREATE_NO_WINDOW == 0x08000000


# =============================================================================
# 8. ADVERSARIAL INJECTION & TOOL ABUSE PREVENTION
# =============================================================================

class TestAdversarialDefense:
    """Verifies that ActionGate blocks unauthorized execution even if model output is hostile."""

    def test_adversarial_prompt_injection_action_quarantined(self):
        gate = ActionGate()
        runtime = DynamicExecutionRuntime(action_gate=gate)

        # Injected prompt payload attempting system wipe
        req = ExecutionRequest(
            executable="cmd.exe",
            args=["/c", "del", "/f", "/q", r"C:\Windows\System32\*.dll"],
        )
        obs = asyncio.run(runtime.execute(req))
        assert obs.status == ExecutionStatus.DENIED
        assert obs.exit_code is None
        assert "Execution DENIED by ActionGate" in obs.stderr or "Execution blocked" in obs.stderr

    def test_adversarial_indirect_shell_injection(self):
        gate = ActionGate()
        runtime = DynamicExecutionRuntime(action_gate=gate)

        # Injected payload chaining disk format
        req = ExecutionRequest(
            executable="cmd.exe",
            args=["/c", "echo harmless & format c: /y"],
        )
        obs = asyncio.run(runtime.execute(req))
        assert obs.status == ExecutionStatus.DENIED
        assert obs.exit_code is None
        assert "strictly forbidden" in obs.stderr
