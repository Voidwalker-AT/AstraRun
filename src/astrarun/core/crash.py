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
