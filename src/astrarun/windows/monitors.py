"""Physical and logical display monitor enumeration and natural language resolution."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import re
import sys
from typing import Optional

from astrarun.core.logging import get_logger
from astrarun.windows.models import MonitorEntity

logger = get_logger("astrarun.windows.monitors")

# Allow overriding monitor list for offline testing / deterministic benchmarks
_MOCK_MONITORS: list[MonitorEntity] | None = None


def set_mock_monitors(monitors: list[MonitorEntity] | None) -> None:
    """Set mock monitors for unit tests or multi-monitor simulation."""
    global _MOCK_MONITORS
    _MOCK_MONITORS = monitors


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
        ("szDevice", ctypes.c_wchar * 32),
    ]


MONITORINFOF_PRIMARY = 0x00000001
MONITOR_DEFAULTTONEAREST = 0x00000002


def enumerate_monitors() -> list[MonitorEntity]:
    """Enumerate all active physical and virtual displays on the workstation."""
    global _MOCK_MONITORS
    if _MOCK_MONITORS is not None:
        return list(_MOCK_MONITORS)

    if sys.platform != "win32":
        # Fallback simulated standard 1080p display for non-Windows test environments
        return [
            MonitorEntity(
                monitor_id=1,
                device_name="SIMULATED_DISPLAY",
                work_area=(0, 0, 1920, 1032),
                full_bounds=(0, 0, 1920, 1080),
                is_primary=True,
                dpi=96,
            )
        ]

    user32 = ctypes.windll.user32
    shcore = getattr(ctypes.windll, "shcore", None)

    monitors: list[MonitorEntity] = []
    raw_monitors: list[tuple[int, _MONITORINFOEXW, int]] = []

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(_RECT),
        ctypes.c_long,
    )

    def _callback(hmonitor: int, hdc: int, lprect: Any, lparam: int) -> int:
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            dpi = 96
            if shcore and hasattr(shcore, "GetDpiForMonitor"):
                dpi_x = ctypes.c_uint()
                dpi_y = ctypes.c_uint()
                # MDT_EFFECTIVE_DPI = 0
                if shcore.GetDpiForMonitor(hmonitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)) == 0:
                    dpi = dpi_x.value
            raw_monitors.append((hmonitor, info, dpi))
        return 1

    cb = MONITORENUMPROC(_callback)
    user32.EnumDisplayMonitors(0, 0, cb, 0)

    # Sort geometrically from left to right by rcMonitor.left, then rcMonitor.top
    raw_monitors.sort(key=lambda item: (item[1].rcMonitor.left, item[1].rcMonitor.top))

    for idx, (_, info, dpi) in enumerate(raw_monitors, start=1):
        work_w = info.rcWork.right - info.rcWork.left
        work_h = info.rcWork.bottom - info.rcWork.top
        full_w = info.rcMonitor.right - info.rcMonitor.left
        full_h = info.rcMonitor.bottom - info.rcMonitor.top
        is_pri = bool(info.dwFlags & MONITORINFOF_PRIMARY)

        monitors.append(
            MonitorEntity(
                monitor_id=idx,
                device_name=str(info.szDevice),
                work_area=(info.rcWork.left, info.rcWork.top, work_w, work_h),
                full_bounds=(info.rcMonitor.left, info.rcMonitor.top, full_w, full_h),
                is_primary=is_pri,
                dpi=dpi,
            )
        )

    if not monitors:
        # Fallback to single primary desktop bounds if enum returned empty
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        monitors.append(
            MonitorEntity(
                monitor_id=1,
                device_name="DEFAULT_PRIMARY",
                work_area=(0, 0, screen_w, screen_h - 48),
                full_bounds=(0, 0, screen_w, screen_h),
                is_primary=True,
                dpi=96,
            )
        )

    return monitors


def get_primary_monitor() -> MonitorEntity:
    """Retrieve the primary monitor."""
    monitors = enumerate_monitors()
    for m in monitors:
        if m.is_primary:
            return m
    return monitors[0]


def monitor_from_window(hwnd: int) -> MonitorEntity:
    """Find the monitor holding the largest area of the specified window."""
    monitors = enumerate_monitors()
    if len(monitors) == 1 or sys.platform != "win32":
        return monitors[0]

    user32 = ctypes.windll.user32
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not hmon:
        return get_primary_monitor()

    info = _MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
    if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        target_name = str(info.szDevice)
        for m in monitors:
            if m.device_name == target_name:
                return m
    return get_primary_monitor()


def resolve_monitor(spec: str | int, current_monitor_id: Optional[int] = None) -> Optional[MonitorEntity]:
    """
    Resolve natural language or index-based monitor specification to a concrete MonitorEntity.
    
    Supported specifications:
      - 1, 2, "1", "2"
      - "monitor 1", "monitor 2", "screen 1", "display 2"
      - "primary", "main", "default"
      - "secondary", "second"
      - "left", "left monitor", "leftmost"
      - "right", "right monitor", "rightmost"
      - "other", "next", "alternate"
    """
    monitors = enumerate_monitors()
    if not monitors:
        return None

    if isinstance(spec, int):
        for m in monitors:
            if m.monitor_id == spec:
                return m
        return monitors[-1] if spec > len(monitors) else monitors[0]

    clean = str(spec).strip().lower()

    # Direct integer or "monitor N" / "display N"
    digit_match = re.search(r"\b(\d+)\b", clean)
    if digit_match:
        idx = int(digit_match.group(1))
        for m in monitors:
            if m.monitor_id == idx:
                return m
        # If requested index out of range, clamp safely to highest available
        return monitors[-1] if idx > len(monitors) else monitors[0]

    # Primary / Main
    if clean in ("primary", "main", "primary monitor", "main monitor", "default"):
        return get_primary_monitor()

    # Secondary / Second
    if clean in ("secondary", "second", "secondary monitor", "second monitor"):
        non_primaries = [m for m in monitors if not m.is_primary]
        if non_primaries:
            return non_primaries[0]
        return monitors[1] if len(monitors) > 1 else monitors[0]

    # Leftmost / Left
    if clean in ("left", "left monitor", "leftmost", "left screen"):
        # Monitors are already sorted by X coordinate
        return monitors[0]

    # Rightmost / Right
    if clean in ("right", "right monitor", "rightmost", "right screen"):
        return monitors[-1]

    # Other / Next / Alternate
    if clean in ("other", "next", "other monitor", "alternate", "the other monitor"):
        if len(monitors) == 1:
            return monitors[0]
        cur_id = current_monitor_id or get_primary_monitor().monitor_id
        # Pick the first monitor that is not the current one
        for m in monitors:
            if m.monitor_id != cur_id:
                return m
        return monitors[0]

    # Fallback to primary
    return get_primary_monitor()
