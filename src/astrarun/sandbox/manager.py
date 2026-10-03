"""AstraRun 1.0 SandboxManager.

Provides authoritative containment, environment sanitization, Job Object process
governance, and directory isolation for dynamic tool execution and workspace testing.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from astrarun.core.logging import get_logger
from astrarun.execution.job_object import Win32JobObject
from astrarun.execution.runtime import CREATE_NO_WINDOW
from astrarun.sandbox.models import SandboxConfig, SandboxProfile, SandboxResult
from astrarun.security.secret_broker import SecretBroker
from astrarun.security.trust_kernel import is_trust_kernel_path

logger = get_logger("astrarun.sandbox.manager")

# Safe environment variables permitted in sandboxed child processes
SAFE_ENV_ALLOWLIST: Set[str] = {
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "PATH",
    "TMP",
    "TEMP",
    "PATHEXT",
    "COMSPEC",
    "USERPROFILE",
    "USERNAME",
    "HOMEDRIVE",
    "HOMEPATH",
    "NUMBER_OF_PROCESSORS",
    "OS",
    "PROCESSOR_ARCHITECTURE",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONUNBUFFERED",
    "PYTHONIOENCODING",
}

# Substrings identifying sensitive variables to strictly redact from child environments
SENSITIVE_KEY_SUBSTRINGS: Set[str] = {
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "AUTH",
    "CREDENTIAL",
    "PRIVATE",
    "AWS",
    "AZURE",
    "OPENAI",
    "ANTHROPIC",
    "GEMINI",
    "GITHUB",
    "BEARER",
}


class SandboxManager:
    """Manages isolated sandbox environments and contained execution."""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        secret_broker: Optional[SecretBroker] = None,
    ) -> None:
        self.base_dir = Path(base_dir or Path("data/sandbox")).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.secret_broker = secret_broker or SecretBroker.get_instance()

    def sanitize_environment(
        self,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Construct a sanitized, stripped environment with zero host secret leakage."""
        clean_env: Dict[str, str] = {}

        # Retain only allowlisted system variables
        for k, v in os.environ.items():
            k_upper = k.upper()
            if k_upper in SAFE_ENV_ALLOWLIST:
                # Double check that value doesn't look like an exported secret
                if not any(sub in k_upper for sub in SENSITIVE_KEY_SUBSTRINGS):
                    clean_env[k] = v

        # Enforce UTF-8 Python environment
        clean_env["PYTHONIOENCODING"] = "utf-8"
        clean_env["PYTHONUNBUFFERED"] = "1"

        # Apply any explicit extra variables (after safety screening)
        if extra_env:
            for k, v in extra_env.items():
                k_upper = k.upper()
                if any(sub in k_upper for sub in SENSITIVE_KEY_SUBSTRINGS):
                    logger.warning("Rejecting extra env var containing secret key substring: %s", k)
                    continue
                clean_env[k] = str(v)

        return clean_env

    def validate_path_safety(self, path: Path | str, for_write: bool = False) -> tuple[bool, str]:
        """Validate if a target path is permissible for read or write in sandbox."""
        p = Path(path).resolve()
        # Trust kernel files are never writable in sandbox
        if for_write and is_trust_kernel_path(p):
            return False, f"Writing to Trust Kernel path is strictly forbidden: {p}"

        # Windows system folder protection
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()
        try:
            if for_write and system_root in p.parents:
                return False, f"Writing to System directory is strictly forbidden: {p}"
        except Exception:
            pass

        return True, "Path safety verified."

    def execute_script(
        self,
        script_code: str,
        config: Optional[SandboxConfig] = None,
        python_executable: Optional[str] = None,
    ) -> SandboxResult:
        """
        Execute Python script code inside a strictly contained sandbox environment.
        """
        cfg = config or SandboxConfig()

        if cfg.profile == SandboxProfile.RESEARCH_DOWNLOAD:
            return SandboxResult(
                run_id=cfg.run_id,
                profile=cfg.profile,
                status="DENIED",
                exit_code=-1,
                stdout="",
                stderr="Execution is prohibited under RESEARCH_DOWNLOAD sandbox profile.",
                duration_ms=0.0,
                violations=["Execution disallowed in download quarantine staging."],
            )

        run_dir = cfg.working_dir or (self.base_dir / cfg.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)

        script_file = run_dir / "candidate_script.py"
        script_file.write_text(script_code, encoding="utf-8")

        exe = python_executable or sys.executable
        clean_env = self.sanitize_environment(cfg.extra_env)

        # Record pre-existing files in working_dir to detect created artifacts
        pre_files = set(run_dir.glob("**/*"))

        job = Win32JobObject(
            name=f"sb_job_{cfg.run_id}",
            memory_limit_bytes=cfg.memory_limit_bytes if cfg.memory_limit_bytes > 0 else None,
        )

        import subprocess
        start_time = time.time()
        status = "SUCCESS"
        exit_code: Optional[int] = None
        stdout_text = ""
        stderr_text = ""
        peak_mb = 0.0

        try:
            proc = subprocess.Popen(
                [exe, str(script_file)],
                cwd=str(run_dir),
                env=clean_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=CREATE_NO_WINDOW,
            )

            # Assign to Win32 Job Object
            if os.name == "nt" and hasattr(proc, "_handle"):
                job.assign_process(int(proc._handle))

            # Wait with bounded timeout
            try:
                stdout_bytes, stderr_bytes = proc.communicate(timeout=cfg.timeout_sec)
                exit_code = proc.returncode
                if exit_code != 0:
                    status = "FAILED"
            except subprocess.TimeoutExpired:
                status = "TIMEOUT"
                proc.kill()
                job.terminate(exit_code=1)
                stdout_bytes, stderr_bytes = proc.communicate()
                stderr_text += f"\nExecution exceeded timeout limit ({cfg.timeout_sec}s)."

            # Truncate output to size caps
            max_bytes = cfg.stdout_max_bytes
            if len(stdout_bytes) > max_bytes:
                stdout_bytes = stdout_bytes[:max_bytes] + b"\n[TRUNCATED: Output exceeded cap]"
            if len(stderr_bytes) > max_bytes:
                stderr_bytes = stderr_bytes[:max_bytes] + b"\n[TRUNCATED: Output exceeded cap]"

            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        except Exception as e:
            status = "ERROR"
            stderr_text = f"Execution exception: {e}"
            logger.exception("Sandbox execution failed")
        finally:
            # Query job telemetry
            try:
                peak_bytes = job.query_peak_memory()
                peak_mb = round(peak_bytes / (1024 * 1024), 2)
            except Exception:
                peak_mb = 0.0

            job.close()

        duration_ms = round((time.time() - start_time) * 1000.0, 2)

        # Detect newly created artifact files
        post_files = set(run_dir.glob("**/*"))
        new_files = [f for f in post_files - pre_files if f.is_file() and f != script_file]

        # Output scrubbing via SecretBroker
        scrubbed_stdout, was_redacted_out = self.secret_broker.scrub_text(stdout_text)
        scrubbed_stderr, was_redacted_err = self.secret_broker.scrub_text(stderr_text)

        result = SandboxResult(
            run_id=cfg.run_id,
            profile=cfg.profile,
            status=status,
            exit_code=exit_code,
            stdout=scrubbed_stdout,
            stderr=scrubbed_stderr,
            duration_ms=duration_ms,
            peak_memory_mb=peak_mb,
            working_dir=run_dir,
            created_artifacts=new_files,
            redacted=was_redacted_out or was_redacted_err,
        )

        # Cleanup if ephemeral and not preserved
        if not cfg.preserve_on_exit and len(new_files) == 0:
            try:
                shutil.rmtree(run_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("Error cleaning sandbox dir %s: %s", run_dir, e)

        return result
