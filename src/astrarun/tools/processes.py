"""Process and port execution tools with strict TOCTOU and safety validation."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import psutil

from astrarun.context.processes import inspect_port_details, inspect_process_details
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tools.processes")

# Critical Windows processes that may NEVER be terminated under any circumstances
PROTECTED_PROCESS_NAMES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe",
    "explorer.exe", "dwm.exe", "spoolsv.exe", "fontdrvhost.exe"
}


def inspect_port(port: int) -> dict[str, Any]:
    """Inspect listening status and metadata of a network port (Read-only)."""
    logger.info("Inspecting port %d", port)
    return inspect_port_details(port)


def inspect_process(pid: int) -> dict[str, Any]:
    """Inspect running process details by PID (Read-only)."""
    logger.info("Inspecting process PID %d", pid)
    return inspect_process_details(pid)


def terminate_process(
    pid: int,
    expected_create_time: float = 0.0,
    expected_name: str = "",
) -> bool:
    """
    Safely terminate a non-protected process with Time-of-Check/Time-of-Use (TOCTOU) validation.
    
    Safety Invariants:
    1. PID 0, PID 4, and protected system processes are unconditionally blocked.
    2. If expected_create_time is provided, the process must have the exact same creation time.
    3. If expected_name is provided, the process name must match.
    """
    if pid <= 4:
        logger.error("Attempted termination of critical kernel PID %d blocked by policy", pid)
        return False

    if not psutil.pid_exists(pid):
        logger.warning("TOCTOU Check Failed: Process PID %d no longer exists", pid)
        return False

    try:
        proc = psutil.Process(pid)
        current_name = proc.name().lower()

        # Invariant 1: Protected Process Block
        if current_name in PROTECTED_PROCESS_NAMES or current_name.replace(".exe", "") in PROTECTED_PROCESS_NAMES:
            logger.error("Termination of protected system process '%s' (PID %d) BLOCKED", current_name, pid)
            return False

        # Invariant 2: TOCTOU Creation Time Revalidation
        if expected_create_time > 0.0:
            current_create_time = proc.create_time()
            if abs(current_create_time - expected_create_time) > 1.0:
                logger.error(
                    "TOCTOU Check Failed: PID %d was reused (creation time %.2f != expected %.2f)",
                    pid, current_create_time, expected_create_time
                )
                return False

        # Invariant 3: TOCTOU Process Name Revalidation
        if expected_name and expected_name.lower() not in (current_name, current_name.replace(".exe", "")):
            logger.error(
                "TOCTOU Check Failed: Process name changed for PID %d ('%s' != expected '%s')",
                pid, current_name, expected_name
            )
            return False

        logger.warning("Terminating verified process '%s' (PID %d)", current_name, pid)
        proc.terminate()
        try:
            proc.wait(timeout=2.0)
        except psutil.TimeoutExpired:
            proc.kill()
        logger.info("Successfully terminated PID %d", pid)
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied) as err:
        logger.error("Failed to terminate PID %d: %s", pid, err)
        return False
