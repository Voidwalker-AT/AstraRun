"""Win32 desktop attachment hook for AstraRun ComputerUse."""

from __future__ import annotations

import sys
from typing import Optional

def ensure_desktop_attached() -> bool:
    """
    Ensure the current execution thread is attached to the interactive input desktop.
    Critical on Windows 11 where agent workers or async tasks may run on thread desktops
    isolated from the visible user interface.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        # DESKTOP_READOBJECTS (0x0001) | DESKTOP_WRITEOBJECTS (0x0080) | DESKTOP_SWITCHDESKTOP (0x0100) = 0x01FF
        h_input = user32.OpenInputDesktop(0, False, 0x01FF)
        if not h_input:
            h_input = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if h_input:
            user32.SetThreadDesktop(h_input)
            return True
    except Exception:
        pass
    return False
