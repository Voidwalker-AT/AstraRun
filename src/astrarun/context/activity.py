"""Foreground activity inspection using native Win32 APIs and psutil."""

from __future__ import annotations

import sys
from typing import Optional, Tuple

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.context.activity")


def get_foreground_window_info() -> Tuple[Optional[str], Optional[str], Optional[int]]:
    """
    Query the foreground window title, owning executable name, and PID.
    
    Returns:
        (app_name, window_title, pid) or (None, None, None) on failure/headless.
    """
    if sys.platform != "win32":
        return None, None, None

    try:
        import ctypes
        import ctypes.wintypes
        import psutil

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, None, None

        # Window title
        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value

        # Window Process ID
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_id = pid.value if pid.value > 0 else None

        app_name = None
        if process_id:
            try:
                proc = psutil.Process(process_id)
                app_name = proc.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                app_name = None

        return app_name, title, process_id
    except Exception as err:
        logger.debug("Error querying foreground window info: %s", err)
        return None, None, None
