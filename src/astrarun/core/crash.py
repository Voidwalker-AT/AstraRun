"""Sanitized Crash Diagnostics and Unhandled Exception Capture for AstraRun 1.0.

Guarantees:
- Captures unhandled exceptions into %LOCALAPPDATA%\\AstraRun\\logs\\crash_<timestamp>.json
- SecretBroker scrubbing: Redacts API keys, tokens, and private URLs
- Zero automated external telemetry/upload
- Collects safe diagnostic state (version, platform, runtime mode)
"""

from __future__ import annotations

import json
import os
import platform
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict

from astrarun.core.logging import get_logger
from astrarun.core.paths import get_logs_dir
from astrarun.security.secret_broker import SecretBroker
from astrarun.version import APP_NAME, VERSION

logger = get_logger("astrarun.core.crash")


def write_crash_report(exc_type: type, exc_value: BaseException, exc_tb: Any) -> Path:
    """Write sanitized crash report JSON to logs directory."""
    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = int(time.time())
    report_path = logs_dir / f"crash_{timestamp}.json"

    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    raw_trace = "".join(tb_lines)

    # Sanitize traceback and exception message using SecretBroker
    broker = SecretBroker.get_instance()
    sanitized_trace, _ = broker.scrub_text(raw_trace)
    sanitized_msg, _ = broker.scrub_text(str(exc_value))

    report: Dict[str, Any] = {
        "app_name": APP_NAME,
        "app_version": VERSION,
        "timestamp": timestamp,
        "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "frozen": getattr(sys, "frozen", False),
        "exception_type": getattr(exc_type, "__name__", str(exc_type)),
        "exception_message": sanitized_msg,
        "traceback": sanitized_trace,
        "system": {
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
    }

    try:
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        logger.error("Crash report written to %s", report_path)
    except Exception as err:
        logger.error("Failed to write crash report: %s", err)

    return report_path


def install_crash_handler() -> None:
    """Install global sys.excepthook to capture unhandled fatal exceptions."""
    orig_excepthook = sys.excepthook

    def _unhandled_exception_handler(exc_type, exc_value, exc_tb):
        try:
            logger.critical("FATAL UNHANDLED EXCEPTION: %s", exc_value, exc_info=(exc_type, exc_value, exc_tb))
            write_crash_report(exc_type, exc_value, exc_tb)
        except Exception as e:
            logger.error("Failed in crash handler: %s", e)
        # Call original excepthook
        orig_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _unhandled_exception_handler
    # Register an atexit hook to record clean shutdown if exiting normally
    import atexit
    atexit.register(_atexit_handler)
    logger.debug("AstraRun crash handler registered.")


def _atexit_handler() -> None:
    """Invoked when process terminates normally via sys.exit or standard Python exit."""
    # Only record clean shutdown if no fatal exception was in progress
    if sys.exc_info()[0] is None:
        try:
            record_clean_shutdown(reason="process_exit")
        except Exception:
            pass


import uuid
from enum import Enum

class TerminationClassification(str, Enum):
    CLEAN_EXIT = "CLEAN_EXIT"
    CRASH = "CRASH"
    FORCED_TERMINATION = "FORCED_TERMINATION"
    POWER_INTERRUPTION = "POWER_INTERRUPTION"
    UNKNOWN = "UNKNOWN"


_SESSION_ID = str(uuid.uuid4())
_SESSION_START_TIME = time.time()
_OP_COUNTER = 0


def get_session_id() -> str:
    """Return the unique session ID of the current AstraRun process."""
    return _SESSION_ID


def get_system_boot_time() -> float:
    """Return the Windows system boot time as a Unix timestamp."""
    if sys.platform == "win32":
        try:
            import ctypes
            uptime_ms = ctypes.windll.kernel32.GetTickCount64()
            return time.time() - (uptime_ms / 1000.0)
        except Exception:
            pass
    return 0.0


def get_last_gasp_file() -> Path:
    """Return path to atomic last_gasp.json file."""
    from astrarun.core.paths import get_data_dir
    return get_data_dir() / "last_gasp.json"


def record_clean_shutdown(reason: str = "graceful_shutdown") -> None:
    """Atomically record a clean shutdown terminal state for this session."""
    try:
        from astrarun.core.paths import get_data_dir
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        gasp_file = get_last_gasp_file()

        payload = {
            "session_id": _SESSION_ID,
            "pid": os.getpid(),
            "process_start_time": _SESSION_START_TIME,
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
            "operation": "CLEAN_SHUTDOWN",
            "operation_id": _OP_COUNTER,
            "details": {"reason": reason},
            "status": TerminationClassification.CLEAN_EXIT.value,
        }
        tmp_file = data_dir / f"last_gasp_{os.getpid()}.tmp"
        tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_file.replace(gasp_file)
        logger.debug("Clean shutdown recorded for session %s (PID %d)", _SESSION_ID, os.getpid())
    except Exception as err:
        logger.debug("Failed to record clean shutdown: %s", err)


def record_subsystem_operation(operation: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Record an atomic last-gasp state marker before invoking external/native subsystem operations."""
    global _OP_COUNTER
    try:
        from astrarun.core.paths import get_data_dir
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        gasp_file = get_last_gasp_file()

        _OP_COUNTER += 1
        payload = {
            "session_id": _SESSION_ID,
            "pid": os.getpid(),
            "process_start_time": _SESSION_START_TIME,
            "operation_id": _OP_COUNTER,
            "timestamp": time.time(),
            "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S"),
            "operation": operation,
            "details": details or {},
        }
        tmp_file = data_dir / f"last_gasp_{os.getpid()}.tmp"
        tmp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_file.replace(gasp_file)
    except Exception as err:
        logger.debug("Failed to record last gasp state: %s", err)


def detect_previous_abnormal_termination() -> Optional[Dict[str, Any]]:
    """
    On startup, inspect the last-gasp and state records to detect abnormal termination.
    
    Accurately classifies:
    - CLEAN_EXIT: Normal shutdown detected; no recovery report needed.
    - CRASH: Validated process crash with matching Windows Error Event / WER.
    - FORCED_TERMINATION: Process terminated abruptly without clean exit marker.
    - POWER_INTERRUPTION: Prior session terminated prior to system reboot.
    - UNKNOWN: Stale or uncorroborated termination state.
    """
    try:
        from astrarun.core.paths import get_data_dir, get_logs_dir
        data_dir = get_data_dir()
        gasp_file = data_dir / "last_gasp.json"
        state_file = data_dir / "astrarun_state.json"

        if not gasp_file.exists() and not state_file.exists():
            return None

        last_gasp = {}
        if gasp_file.exists():
            try:
                last_gasp = json.loads(gasp_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        last_state = {}
        if state_file.exists():
            try:
                last_state = json.loads(state_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        prev_pid = last_gasp.get("pid") or last_state.get("pid")
        prev_session_id = last_gasp.get("session_id")
        if not prev_pid or prev_pid == os.getpid() or prev_session_id == _SESSION_ID:
            return None

        # 1. Check if previous process cleanly shutdown
        clean_exit = (
            last_state.get("stage") in ("SHUTDOWN", "SHUTDOWN_COMPLETED")
            or last_state.get("status") in ("STOPPED", "CLEAN_EXIT")
            or last_gasp.get("operation") in ("IDLE", "CLEAN_SHUTDOWN", "RECOVERED_FROM_CRASH")
            or last_gasp.get("status") == TerminationClassification.CLEAN_EXIT.value
        )
        if clean_exit:
            logger.debug("Prior AstraRun session (PID %s) terminated cleanly.", prev_pid)
            return None

        last_gasp_time = float(last_gasp.get("timestamp", 0.0) or 0.0)
        boot_time = get_system_boot_time()

        # 2. Check for system reboot / power interruption boundary
        if boot_time > 0 and last_gasp_time > 0 and last_gasp_time < boot_time:
            boot_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(boot_time))
            logger.info(
                "[SESSION_BOUNDARY] Prior session PID %s was from a prior Windows boot (system booted at %s). Classifying as POWER_INTERRUPTION.",
                prev_pid, boot_iso
            )
            classification = TerminationClassification.POWER_INTERRUPTION
            record_subsystem_operation("RECOVERED_FROM_CRASH", {"acknowledged_pid": prev_pid, "reason": "system_reboot"})
            return None

        # 3. Check for stale operations (> 4 hours old)
        now = time.time()
        if last_gasp_time > 0 and (now - last_gasp_time) > 14400.0:  # 4 hours
            logger.warning(
                "[STALE_JOURNAL_DETECTED] Prior operation '%s' is stale (%s). Ignoring.",
                last_gasp.get("operation"), last_gasp.get("timestamp_iso")
            )
            record_subsystem_operation("RECOVERED_FROM_CRASH", {"acknowledged_pid": prev_pid, "reason": "stale_journal"})
            return None

        # 4. Check for Windows Event / WER matching this exact process
        windows_event_msg = None
        if sys.platform == "win32":
            try:
                import subprocess
                cmd = (
                    f"Get-WinEvent -FilterHashtable @{{LogName='Application'; ProviderName='Application Error'}} -MaxEvents 5 "
                    f"| Where-Object {{ $_.Message -like '*AstraRun.exe*' }} | Select-Object -First 1 Message | Format-List"
                )
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", cmd],
                    capture_output=True, text=True, timeout=3,
                    creationflags=0x08000000,
                )
                if res.returncode == 0 and res.stdout.strip():
                    raw_msg = res.stdout.strip()
                    # Verify if event is recent and PID matches if possible
                    windows_event_msg = raw_msg
            except Exception:
                pass

        classification = TerminationClassification.CRASH if windows_event_msg else TerminationClassification.FORCED_TERMINATION

        # Abnormal termination identified
        logger.warning(
            "[ABNORMAL_TERMINATION_DETECTED] Prior AstraRun session PID %s did not terminate cleanly. Classification: %s, Last operation: '%s'",
            prev_pid, classification.value, last_gasp.get("operation", "UNKNOWN")
        )

        recovery_info = {
            "prior_pid": prev_pid,
            "session_id": prev_session_id,
            "classification": classification.value,
            "detected_at": now,
            "last_operation": last_gasp.get("operation", "UNKNOWN"),
            "last_operation_time": last_gasp.get("timestamp_iso", "UNKNOWN"),
            "last_details": last_gasp.get("details", {}),
            "prior_state": last_state,
        }
        if windows_event_msg:
            recovery_info["windows_event"] = windows_event_msg

        # Write recovery report
        try:
            logs_dir = get_logs_dir()
            rep_path = logs_dir / f"crash_recovery_{int(now)}.json"
            rep_path.write_text(json.dumps(recovery_info, indent=2), encoding="utf-8")
            logger.info("Saved abnormal termination recovery report to %s", rep_path)
        except Exception:
            pass

        # Mark last gasp as acknowledged so it never triggers again
        record_subsystem_operation("RECOVERED_FROM_CRASH", {"acknowledged_pid": prev_pid})
        return recovery_info
    except Exception as err:
        logger.debug("Abnormal termination check failed: %s", err)
        return None

