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


def get_screen_for_hwnd(origin_hwnd: int | None = None) -> Any:
    """
    Resolve the QScreen hosting the given window HWND, taking high-DPI scaling into account.
    Falls back to cursor screen or primary screen.
    """
    screens = QGuiApplication.screens()
    if not screens:
        return None

    if origin_hwnd and sys.platform == "win32":
        try:
            user32 = ctypes.windll.user32
            rect = wintypes.RECT()
            if user32.GetWindowRect(origin_hwnd, ctypes.byref(rect)):
                # Center of the origin window in physical coordinates
                cx = (rect.left + rect.right) // 2
                cy = (rect.top + rect.bottom) // 2

                for screen in screens:
                    dpr = screen.devicePixelRatio()
                    sg = screen.geometry()
                    phys_left = sg.left() * dpr
                    phys_top = sg.top() * dpr
                    phys_right = sg.right() * dpr
                    phys_bottom = sg.bottom() * dpr
                    if phys_left <= cx <= phys_right and phys_top <= cy <= phys_bottom:
                        logger.debug("Resolved screen '%s' for HWND %d via physical geometry", screen.name(), origin_hwnd)
                        return screen
        except Exception as err:
            logger.debug("Could not resolve screen from HWND %d: %s", origin_hwnd, err)

    # Fallback to screen under cursor
    cursor_pos = QCursor.pos()
    cursor_screen = QGuiApplication.screenAt(cursor_pos)
    if cursor_screen:
        return cursor_screen

    # Fallback to primary screen
    primary = QGuiApplication.primaryScreen()
    if primary:
        return primary

    return screens[0] if screens else None


def compute_top_center_launcher_position(
    window_width: int,
    window_height: int,
    target_screen: Any = None,
    origin_hwnd: int | None = None,
    top_margin: int = 48,
) -> tuple[QPoint, QRect]:
    """
    Compute optimal top-center coordinates on the monitor containing the origin window.
    Returns (position, available_work_area) in Qt logical coordinates.
    """
    screen = target_screen or get_screen_for_hwnd(origin_hwnd)
    if screen:
        avail = screen.availableGeometry()
    else:
        avail = get_target_screen_geometry()

    width = min(window_width, avail.width() - 32)
    x = avail.x() + (avail.width() - width) // 2
    y = avail.y() + top_margin
    return QPoint(x, y), avail


def compute_task_hud_position(
    hud_width: int,
    hud_height: int,
    target_screen: Any = None,
    origin_hwnd: int | None = None,
    margin_right: int = 24,
    margin_top: int = 24,
) -> tuple[QPoint, QRect]:
    """
    Compute optimal top-right coordinates for the Floating Task HUD on the target monitor.
    Returns (position, available_work_area) in Qt logical coordinates.
    """
    screen = target_screen or get_screen_for_hwnd(origin_hwnd)
    if screen:
        avail = screen.availableGeometry()
    else:
        avail = get_target_screen_geometry()

    width = min(hud_width, avail.width() - 32)
    x = avail.x() + avail.width() - width - margin_right
    y = avail.y() + margin_top
    return QPoint(x, y), avail


def compute_launcher_position(window_width: int, window_height: int) -> QPoint:
    """Compute optimal upper-middle centered coordinates on the active monitor."""
    pos, _ = compute_top_center_launcher_position(window_width, window_height)
    return pos

