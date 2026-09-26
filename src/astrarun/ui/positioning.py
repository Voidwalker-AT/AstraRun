"""Display and monitor positioning utilities for AstraRun."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRect
from PySide6.QtGui import QCursor, QGuiApplication

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.ui.positioning")


def get_foreground_window_work_area() -> QRect | None:
    """Query the work area rectangle of the monitor hosting the active foreground window."""
    if sys.platform != "win32":
        return None

    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        # MONITOR_DEFAULTTONEAREST = 2
        hmon = user32.MonitorFromWindow(hwnd, 2)
        if not hmon:
            return None

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            rc = mi.rcWork
            width = rc.right - rc.left
            height = rc.bottom - rc.top
            if width > 0 and height > 0:
                logger.debug(
                    "Foreground window monitor detected: %dx%d at (%d, %d)",
                    width, height, rc.left, rc.top
                )
                return QRect(rc.left, rc.top, width, height)
    except Exception as err:
        logger.debug("Error querying foreground window monitor: %s", err)

    return None


def get_target_screen_geometry() -> QRect:
    """
    Determine target display geometry using the priority hierarchy:
    1. Foreground window monitor
    2. Cursor monitor fallback
    3. Primary monitor fallback
    """
    # 1. Try foreground window monitor
    fg_area = get_foreground_window_work_area()
    if fg_area is not None:
        return fg_area

    # 2. Try cursor monitor
    cursor_pos = QCursor.pos()
    cursor_screen = QGuiApplication.screenAt(cursor_pos)
    if cursor_screen:
        logger.debug("Using cursor monitor fallback: %s", cursor_screen.name())
        return cursor_screen.availableGeometry()

    # 3. Primary monitor fallback
    primary = QGuiApplication.primaryScreen()
    if primary:
        logger.debug("Using primary monitor fallback: %s", primary.name())
        return primary.availableGeometry()

    # Ultimate default safety
    return QRect(0, 0, 1536, 864)


def compute_launcher_position(window_width: int, window_height: int) -> QPoint:
    """Compute optimal upper-middle centered coordinates on the active monitor."""
    avail = get_target_screen_geometry()
    x = avail.x() + (avail.width() - window_width) // 2
    y = avail.y() + int(avail.height() * 0.28)
    return QPoint(x, y)
