"""Windows Per-User Autostart (Run at Login) Manager.

Uses the canonical per-user Windows Registry Run key:
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

Guarantees:
- Requires ZERO administrative privileges.
- Cleanly removable on uninstall or user toggle.
- Launches AstraRun with --background flag to start resident in system tray.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.core.autostart")

REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE_NAME = "AstraRun"


def get_default_executable_command() -> str:
    """Determine the canonical command to run AstraRun at login."""
    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}" --background'
    # In development mode, point to pythonw.exe running module
    pyw_path = Path(sys.executable).with_name("pythonw.exe")
    if not pyw_path.exists():
        pyw_path = Path(sys.executable)
    root = Path(__file__).resolve().parent.parent.parent.parent
    return f'"{pyw_path}" -m astrarun.main --background'


def is_autostart_enabled() -> bool:
    """Check if AstraRun is configured to run at Windows login."""
    if sys.platform != "win32":
        return False

    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_READ) as key:
            val, _ = winreg.QueryValueEx(key, REG_VALUE_NAME)
            return bool(val)
    except FileNotFoundError:
        return False
    except Exception as err:
        logger.debug("Could not read autostart registry key: %s", err)
        return False


def enable_autostart(custom_command: Optional[str] = None) -> bool:
    """Enable start-at-login in current user registry."""
    if sys.platform != "win32":
        return False

    import winreg
    cmd = custom_command or get_default_executable_command()
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY) as key:
            winreg.SetValueEx(key, REG_VALUE_NAME, 0, winreg.REG_SZ, cmd)
            logger.info("Autostart registered in HKCU: %s", cmd)
            return True
    except Exception as err:
        logger.error("Failed to enable autostart in registry: %s", err)
        return False


def disable_autostart() -> bool:
    """Disable start-at-login in current user registry."""
    if sys.platform != "win32":
        return False

    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, REG_VALUE_NAME)
            logger.info("Autostart removed from HKCU.")
            return True
    except FileNotFoundError:
        return True  # Already disabled
    except Exception as err:
        logger.error("Failed to disable autostart in registry: %s", err)
        return False
