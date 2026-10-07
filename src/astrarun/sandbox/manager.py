"""AstraRun 1.0 SandboxManager.

Provides authoritative containment, environment sanitization, Job Object process
governance, and directory isolation for dynamic tool execution and workspace testing.
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
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
    "ASTRARUN_OUTPUT_DIR",
    "ASTRARUN_WORKSPACE_DIR",
    "OUTPUT_DIR",
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

    # Section 8: Concurrency ceiling: permit strictly ONE dynamic compute worker concurrently
    _concurrency_lock = threading.BoundedSemaphore(value=1)

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        secret_broker: Optional[SecretBroker] = None,
    ) -> None:
        from astrarun.core.paths import AstraPaths
        self.base_dir = Path(base_dir or AstraPaths.sandbox_dir()).resolve()
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
        script_file.write_bytes(script_code.encode("utf-8"))

        exe = python_executable or sys.executable
        clean_env = self.sanitize_environment(cfg.extra_env)

        # Record pre-existing files in working_dir to detect created artifacts
        pre_files = set(run_dir.glob("**/*"))
        pre_sizes = {f: f.stat().st_size for f in pre_files if f.is_file()}

        start_time = time.time()
        status = "SUCCESS"
        exit_code: Optional[int] = None
        stdout_text = ""
        stderr_text = ""
        peak_mb = 0.0

        isolation_type = "UNKNOWN"
        acquired = self._concurrency_lock.acquire(timeout=cfg.timeout_sec + 5.0)
        if not acquired:
            return SandboxResult(
                run_id=cfg.run_id,
                profile=cfg.profile,
                status="BUSY",
                exit_code=-1,
                stdout="",
                stderr="System compute concurrency ceiling reached (strictly 1 worker active).",
                duration_ms=0.0,
            )

        try:
            if os.name == "nt":
                if getattr(cfg, "launcher_preference", "APPCONTAINER") == "RESTRICTED_TOKEN":
                    from astrarun.sandbox.restricted_launcher import RestrictedWorkerLauncher
                    try:
                        worker_res = RestrictedWorkerLauncher.launch(
                            entrypoint_file=script_file,
                            workspace=run_dir,
                            run_id=cfg.run_id,
                            timeout_sec=cfg.timeout_sec,
                            memory_limit_bytes=cfg.memory_limit_bytes,
                            extra_env=cfg.extra_env,
                            python_executable=exe,
                        )
                        status = worker_res.status
                        exit_code = worker_res.exit_code
                        stdout_text = worker_res.stdout
                        stderr_text = worker_res.stderr
                        peak_mb = worker_res.peak_memory_mb
                        isolation_type = "RESTRICTED_TOKEN"
                        token_diag = {
                            "is_restricted_token": True,
                            "integrity_level": "LOW",
                        }
                    except Exception as e:
                        status = "ERROR"
                        stderr_text = f"RestrictedWorkerLauncher execution exception: {e}"
                        logger.exception("RestrictedWorkerLauncher execution failed")
                        isolation_type = "RESTRICTED_TOKEN_FAILED"
                        token_diag = {"error": str(e), "fail_closed": True}
                else:
                    from astrarun.sandbox.appcontainer_launcher import AppContainerLauncher
                    try:
                        worker_res = AppContainerLauncher.launch(
                            entrypoint_file=script_file,
                            workspace=run_dir,
                            run_id=cfg.run_id,
                            timeout_sec=cfg.timeout_sec,
                            memory_limit_bytes=cfg.memory_limit_bytes,
                            extra_env=cfg.extra_env,
                            python_executable=exe,
                        )
                        status = worker_res.status
                        exit_code = worker_res.exit_code
                        stdout_text = worker_res.stdout
                        stderr_text = worker_res.stderr
                        peak_mb = worker_res.peak_memory_mb
                        isolation_type = worker_res.isolation_type
                        token_diag = {
                            "is_appcontainer": worker_res.is_appcontainer,
                            "package_sid": worker_res.package_sid,
                            "capabilities_granted": worker_res.capabilities_granted,
                        }
                    except Exception as e:
                        status = "ERROR"
                        stderr_text = f"AppContainer execution exception: {e}"
                        logger.exception("AppContainerLauncher execution failed")
                        isolation_type = "APPCONTAINER_FAILED"
                        token_diag = {"error": str(e), "fail_closed": True}
            else:
                job = Win32JobObject(
                    name=f"sb_job_{cfg.run_id}",
                    memory_limit_bytes=cfg.memory_limit_bytes if cfg.memory_limit_bytes > 0 else None,
                )
                import subprocess
                try:
                    proc = subprocess.Popen(
                        [exe, str(script_file)],
                        cwd=str(run_dir),
                        env=clean_env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=CREATE_NO_WINDOW,
                    )
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
        finally:
            self._concurrency_lock.release()

        duration_ms = round((time.time() - start_time) * 1000.0, 2)

        # Detect newly created or populated artifact files
        post_files = set(run_dir.glob("**/*"))
        new_files = [
            f for f in post_files - {script_file}
            if f.is_file()
            and (
                f not in pre_files
                or (pre_sizes.get(f, 0) == 0 and f.stat().st_size > 0)
                or (f.stat().st_mtime >= start_time and f.stat().st_size != pre_sizes.get(f, 0))
            )
        ]

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
            isolation_type=isolation_type,
            token_diagnostics=token_diag,
        )

        # Cleanup if ephemeral and not preserved
        if not cfg.preserve_on_exit and len(new_files) == 0:
            try:
                shutil.rmtree(run_dir, ignore_errors=True)
            except Exception as e:
                logger.warning("Error cleaning sandbox dir %s: %s", run_dir, e)

        return result

    def execute_candidate(
        self,
        candidate: Any,
        config: Optional[SandboxConfig] = None,
        python_executable: Optional[str] = None,
    ) -> SandboxResult:
        """
        Execute a CandidateTool (single or multi-file) in an isolated sandbox workspace.
        Enforces strict path containment, Win32 Job Object limits, and secret scrubbing.
        """
        cfg = config or SandboxConfig(
            run_id=getattr(candidate, "tool_id", "dyn_run"),
            timeout_sec=getattr(candidate, "timeout", 30.0),
            memory_limit_bytes=int(getattr(candidate, "memory_limit_mb", 512.0) * 1024 * 1024),
        )

        run_dir = cfg.working_dir or (self.base_dir / getattr(candidate, "task_id", cfg.run_id))
        run_dir.mkdir(parents=True, exist_ok=True)

        # Governed Task Workspace contract: TASK_WORKSPACE/ (source, output, temp, evidence)
        source_dir = run_dir / "source"
        output_dir = cfg.output_dir or (run_dir / "output")
        temp_dir = run_dir / "temp"
        evidence_dir = run_dir / "evidence"

        source_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # Stage all files
        sources = getattr(candidate, "source_files", {})
        if not sources and hasattr(candidate, "executable_code"):
            entry = getattr(candidate, "entrypoint", "main.py")
            sources = {entry: candidate.full_script(include_test=True)}

        written_files: List[Path] = []
        for rel_path, content in sources.items():
            # Strict path containment check
            norm = Path(rel_path)
            if norm.is_absolute() or ".." in norm.parts:
                return SandboxResult(
                    run_id=cfg.run_id,
                    profile=cfg.profile,
                    status="DENIED",
                    exit_code=-1,
                    stdout="",
                    stderr=f"Path traversal detected in candidate source file: {rel_path}",
                    duration_ms=0.0,
                    violations=[f"Illegal file path: {rel_path}"],
                )
            target_f = (run_dir / norm).resolve()
            # Ensure it resolves within run_dir
            if not str(target_f).startswith(str(run_dir.resolve())):
                return SandboxResult(
                    run_id=cfg.run_id,
                    profile=cfg.profile,
                    status="DENIED",
                    exit_code=-1,
                    stdout="",
                    stderr=f"Target file path escapes sandbox: {rel_path}",
                    duration_ms=0.0,
                    violations=[f"Path escape: {rel_path}"],
                )
            target_f.parent.mkdir(parents=True, exist_ok=True)
            target_f.write_bytes(content.encode("utf-8"))
            written_files.append(target_f)

            # Mirror to source_dir for archive
            (source_dir / norm).parent.mkdir(parents=True, exist_ok=True)
            (source_dir / norm).write_bytes(content.encode("utf-8"))

        entry_file = run_dir / getattr(candidate, "entrypoint", "main.py")
        if not entry_file.exists():
            return SandboxResult(
                run_id=cfg.run_id,
                profile=cfg.profile,
                status="FAILED",
                exit_code=-1,
                stdout="",
                stderr=f"Entrypoint '{candidate.entrypoint}' not found in candidate source files.",
                duration_ms=0.0,
            )

        exe = python_executable or sys.executable
        extra = dict(cfg.extra_env or {})
        extra["ASTRARUN_OUTPUT_DIR"] = str(output_dir)
        extra["ASTRARUN_WORKSPACE_DIR"] = str(run_dir)
        extra["OUTPUT_DIR"] = str(output_dir)
        extra["TEMP"] = str(temp_dir)
        extra["TMP"] = str(temp_dir)
        clean_env = self.sanitize_environment(extra)

        # Record pre-existing files and sizes to detect newly produced or populated artifacts
        pre_files = set(run_dir.glob("**/*"))
        pre_sizes = {f: f.stat().st_size for f in pre_files if f.is_file()}

        start_time = time.time()
        status = "SUCCESS"
        exit_code: Optional[int] = None
        stdout_text = ""
        stderr_text = ""
        peak_mb = 0.0

        isolation_type = "UNKNOWN"
        token_diag: Dict[str, Any] = {}

        acquired = self._concurrency_lock.acquire(timeout=cfg.timeout_sec + 5.0)
        if not acquired:
            return SandboxResult(
                run_id=cfg.run_id,
                profile=cfg.profile,
                status="BUSY",
                exit_code=-1,
                stdout="",
                stderr="System compute concurrency ceiling reached (strictly 1 worker active).",
                duration_ms=0.0,
            )

        try:
            if os.name == "nt":
                if getattr(cfg, "launcher_preference", "APPCONTAINER") == "RESTRICTED_TOKEN":
                    from astrarun.sandbox.restricted_launcher import RestrictedWorkerLauncher
                    try:
                        worker_res = RestrictedWorkerLauncher.launch(
                            entrypoint_file=entry_file,
                            workspace=run_dir,
                            run_id=cfg.run_id,
                            timeout_sec=cfg.timeout_sec,
                            memory_limit_bytes=cfg.memory_limit_bytes,
                            extra_env=cfg.extra_env,
                            python_executable=exe,
                        )
                        status = worker_res.status
                        exit_code = worker_res.exit_code
                        stdout_text = worker_res.stdout
                        stderr_text = worker_res.stderr
                        peak_mb = worker_res.peak_memory_mb
                        isolation_type = "RESTRICTED_TOKEN"
                        token_diag = {
                            "is_restricted_token": True,
                            "integrity_level": "LOW",
                        }
                    except Exception as e:
                        status = "ERROR"
                        stderr_text = f"RestrictedWorkerLauncher execution exception: {e}"
                        logger.exception("RestrictedWorkerLauncher execution failed")
                        isolation_type = "RESTRICTED_TOKEN_FAILED"
                        token_diag = {"error": str(e), "fail_closed": True}
                else:
                    from astrarun.sandbox.appcontainer_launcher import AppContainerLauncher
                    try:
                        worker_res = AppContainerLauncher.launch(
                            entrypoint_file=entry_file,
                            workspace=run_dir,
                            run_id=cfg.run_id,
                            timeout_sec=cfg.timeout_sec,
                            memory_limit_bytes=cfg.memory_limit_bytes,
                            extra_env=cfg.extra_env,
                            python_executable=exe,
                        )
                        status = worker_res.status
                        exit_code = worker_res.exit_code
                        stdout_text = worker_res.stdout
                        stderr_text = worker_res.stderr
                        peak_mb = worker_res.peak_memory_mb
                        isolation_type = worker_res.isolation_type
                        token_diag = {
                            "is_appcontainer": worker_res.is_appcontainer,
                            "package_sid": worker_res.package_sid,
                            "capabilities_granted": worker_res.capabilities_granted,
                        }
                    except Exception as e:
                        status = "ERROR"
                        stderr_text = f"AppContainer execution exception: {e}"
                        logger.exception("AppContainerLauncher execution failed")
                        isolation_type = "APPCONTAINER_FAILED"
                        token_diag = {"error": str(e), "fail_closed": True}
            else:
                job = Win32JobObject(
                    name=f"sb_job_{cfg.run_id}",
                    memory_limit_bytes=cfg.memory_limit_bytes if cfg.memory_limit_bytes > 0 else None,
                )
                import subprocess
                try:
                    proc = subprocess.Popen(
                        [exe, str(entry_file)],
                        cwd=str(run_dir),
                        env=clean_env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=CREATE_NO_WINDOW,
                    )
                    if os.name == "nt" and hasattr(proc, "_handle"):
                        job.assign_process(int(proc._handle))

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
                    logger.exception("Sandbox candidate execution failed")
                finally:
                    try:
                        peak_bytes = job.query_peak_memory()
                        peak_mb = round(peak_bytes / (1024 * 1024), 2)
                    except Exception:
                        peak_mb = 0.0
                    job.close()
        finally:
            self._concurrency_lock.release()

        duration_ms = round((time.time() - start_time) * 1000.0, 2)

        # Detect newly created or populated artifact files (excluding staged source files and temp dirs)
        post_files = set(run_dir.glob("**/*"))
        staged_set = set(written_files)
        excluded_dirs = {source_dir, temp_dir}
        new_files = [
            f for f in post_files - staged_set
            if f.is_file() and not any(p in excluded_dirs for p in f.parents)
            and (
                f not in pre_files
                or (pre_sizes.get(f, 0) == 0 and f.stat().st_size > 0)
                or (f.stat().st_mtime >= start_time and f.stat().st_size != pre_sizes.get(f, 0))
            )
        ]

        scrubbed_stdout, was_redacted_out = self.secret_broker.scrub_text(stdout_text)
        scrubbed_stderr, was_redacted_err = self.secret_broker.scrub_text(stderr_text)

        return SandboxResult(
            run_id=cfg.run_id,
            profile=cfg.profile,
            status=status,
            exit_code=exit_code,
            stdout=scrubbed_stdout,
            stderr=scrubbed_stderr,
            duration_ms=duration_ms,
            peak_memory_mb=peak_mb,
            working_dir=run_dir,
            output_dir=output_dir,
            created_artifacts=new_files,
            redacted=was_redacted_out or was_redacted_err,
            isolation_type=isolation_type,
            token_diagnostics=token_diag,
        )

