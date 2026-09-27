"""Window discovery foundation for AstraRun v0.7 (Read-Only).

Discovers top-level desktop windows, foreground window, and application-window associations.
Full window management (move, resize, snap, state mutation) is strictly deferred to v0.8.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import time
from typing import Any, List, Optional

import psutil

from astrarun.capabilities.models import (
    CapabilityErrorCode,
    CapabilityResult,
    WindowEntity,
)
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.windows.discovery")


def list_windows(limit: int = 30) -> CapabilityResult:
    """Enumerate visible top-level desktop windows."""
    t0 = time.perf_counter()
    if sys.platform != "win32":
        return CapabilityResult.fail(
            capability="list_windows",
            message="Window enumeration is only supported on Windows.",
            error_code=CapabilityErrorCode.UNAVAILABLE,
        )

    windows: list[WindowEntity] = []
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def enum_callback(hwnd: int, lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True

        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True

        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True

        pid_buf = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
        pid = pid_buf.value

        rect = ctypes.wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        bounds = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

        # Ignore zero-size or tiny offscreen windows
        if bounds[2] <= 50 or bounds[3] <= 50:
            return True

        app_name = "unknown"
        if pid:
            try:
                proc = psutil.Process(pid)
                app_name = proc.name().lower().replace(".exe", "")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                app_name = "unknown"

        windows.append(
            WindowEntity(
                hwnd=hwnd,
                title=title,
                pid=pid,
                app_id=app_name,
                bounds=bounds,
                state="normal",
                visible=True,
            )
        )
        return True

    cb = WNDENUMPROC(enum_callback)
    user32.EnumWindows(cb, 0)

    res_windows = windows[:limit]
    latency = (time.perf_counter() - t0) * 1000

    return CapabilityResult.ok(
        capability="list_windows",
        message=f"Discovered {len(res_windows)} visible top-level window(s).",
        data={"windows": [w.to_dict() for w in res_windows], "count": len(res_windows)},
        context_updates=[{"type": "windows_listed", "count": len(res_windows)}],
        latency_ms=latency,
    )


def foreground_window() -> CapabilityResult:
    """Retrieve the currently focused foreground window."""
    t0 = time.perf_counter()
    if sys.platform != "win32":
        return CapabilityResult.fail(
            capability="foreground_window",
            message="Foreground window query is only supported on Windows.",
            error_code=CapabilityErrorCode.UNAVAILABLE,
        )

    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return CapabilityResult.fail(
            capability="foreground_window",
            message="No foreground window currently active.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    length = user32.GetWindowTextLengthW(hwnd)
    title = ""
    if length > 0:
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()

    pid_buf = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
    pid = pid_buf.value

    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    bounds = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    app_name = "unknown"
    if pid:
        try:
            proc = psutil.Process(pid)
            app_name = proc.name().lower().replace(".exe", "")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            app_name = "unknown"

    win_entity = WindowEntity(
        hwnd=hwnd,
        title=title,
        pid=pid,
        app_id=app_name,
        bounds=bounds,
        state="normal",
        visible=True,
    )
    latency = (time.perf_counter() - t0) * 1000

    return CapabilityResult.ok(
        capability="foreground_window",
        message=f"Foreground window: '{title}' ({app_name}, PID {pid})",
        data=win_entity.to_dict(),
        context_updates=[{"type": "foreground_window_queried", "hwnd": hwnd, "title": title, "app_id": app_name}],
        latency_ms=latency,
    )


def find_window(query: str) -> CapabilityResult:
    """Find desktop windows matching title or application name."""
    t0 = time.perf_counter()
    clean = query.strip().lower()
    res = list_windows(limit=100)
    if not res.success:
        return res

    all_windows = res.data.get("windows", [])
    matches = [
        w for w in all_windows
        if clean in w["title"].lower() or clean in w["app_id"].lower()
    ]
    latency = (time.perf_counter() - t0) * 1000

    if not matches:
        return CapabilityResult.fail(
            capability="find_window",
            message=f"No window matching '{query}' found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="find_window",
        message=f"Found {len(matches)} matching window(s) for '{query}'.",
        data={"windows": matches, "count": len(matches)},
        latency_ms=latency,
    )


def windows_for_application(app: str) -> CapabilityResult:
    """Find all open top-level windows for an application."""
    clean = app.strip().lower().replace(".exe", "")
    return find_window(clean)
