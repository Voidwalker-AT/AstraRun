"""Screen perception and visual capture for AstraRun ComputerUse."""

from __future__ import annotations

import sys
import time
from typing import Any, Dict, Optional, Tuple
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.computer_use.perception.screen")


class ScreenPerception:
    """
    Captures screenshots and extracts visual / layout context from desktop displays.
    """

    def capture_screen(self, region: Optional[Tuple[int, int, int, int]] = None) -> Optional[Any]:
        """Capture desktop screen pixels."""
        try:
            from astrarun.perception.screen import capture_active_window_screenshot
            return capture_active_window_screenshot()
        except Exception as e:
            logger.debug("Failed screen capture: %s", e)
            return None

    def get_window_rect(self, hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        """Get window client bounding rectangle (left, top, width, height)."""
        if sys.platform != "win32" or not hwnd:
            return None
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
        return None
