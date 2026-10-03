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
    sanitized_trace = broker.scrub_text(raw_trace)
    sanitized_msg = broker.scrub_text(str(exc_value))

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
            write_crash_report(exc_type, exc_value, exc_tb)
        except Exception:
            pass
        # Call original excepthook
        orig_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _unhandled_exception_handler
    logger.debug("AstraRun crash handler registered.")


def get_last_gasp_file() -> Path:
    """Return path to atomic last_gasp.json file."""
    from astrarun.core.paths import get_data_dir
    return get_data_dir() / "last_gasp.json"


def record_subsystem_operation(operation: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Record an atomic last-gasp state marker before invoking external/native subsystem operations."""
    try:
        from astrarun.core.paths import get_data_dir
        data_dir = get_data_dir()
        data_dir.mkdir(parents=True, exist_ok=True)
        gasp_file = get_last_gasp_file()

        payload = {
            "pid": os.getpid(),
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
    
    If detected, captures last recorded subsystem operation and surfaces Windows Event/WER information.
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
        if not prev_pid or prev_pid == os.getpid():
            return None

        # Check if previous process cleanly shutdown
        clean_exit = last_state.get("stage") == "SHUTDOWN" or last_gasp.get("operation") in ("IDLE", "CLEAN_SHUTDOWN")
        if clean_exit:
            return None

        # Abnormal termination identified
        logger.warning(
            "[ABNORMAL_TERMINATION_DETECTED] Prior AstraRun session PID %s did not terminate cleanly. Last operation: '%s'",
            prev_pid, last_gasp.get("operation", "UNKNOWN")
        )

        recovery_info = {
            "prior_pid": prev_pid,
            "detected_at": time.time(),
            "last_operation": last_gasp.get("operation", "UNKNOWN"),
            "last_operation_time": last_gasp.get("timestamp_iso", "UNKNOWN"),
            "last_details": last_gasp.get("details", {}),
            "prior_state": last_state,
        }

        # Try to gather recent Windows Application Error event for AstraRun
        if sys.platform == "win32":
            try:
                import subprocess
                cmd = (
                    "Get-WinEvent -FilterHashtable @{LogName='Application'; ProviderName='Application Error'} -MaxEvents 3 "
                    "| Where-Object { $_.Message -like '*AstraRun.exe*' } | Select-Object -First 1 Message | Format-List"
                )
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", cmd],
                    capture_output=True, text=True, timeout=3,
                    creationflags=0x08000000,
                )
                if res.returncode == 0 and res.stdout.strip():
                    recovery_info["windows_event"] = res.stdout.strip()
            except Exception:
                pass

        # Write recovery report
        try:
            logs_dir = get_logs_dir()
            rep_path = logs_dir / f"crash_recovery_{int(time.time())}.json"
            rep_path.write_text(json.dumps(recovery_info, indent=2), encoding="utf-8")
            logger.info("Saved abnormal termination recovery report to %s", rep_path)
        except Exception:
            pass

        # Mark last gasp as acknowledged
        record_subsystem_operation("RECOVERED_FROM_CRASH", {"acknowledged_pid": prev_pid})
        return recovery_info
    except Exception as err:
        logger.debug("Abnormal termination check failed: %s", err)
        return None
