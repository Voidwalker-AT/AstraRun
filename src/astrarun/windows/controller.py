"""Win32 window mutation controller and safe desktop manipulation."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import time
from typing import Any, Dict, List, Optional, Union

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult
from astrarun.core.logging import get_logger
from astrarun.windows.layouts import DesktopLayoutEngine
from astrarun.windows.models import LayoutType, MonitorEntity, WindowBounds, WindowLayoutSnapshot, WindowState
from astrarun.windows.monitors import enumerate_monitors, get_primary_monitor, monitor_from_window, resolve_monitor
from astrarun.windows.policy import (
    clamp_geometry,
    is_simulated_window_validation,
    validate_window_identity,
)
from astrarun.windows.undo import restore_stack

logger = get_logger("astrarun.windows.controller")

# Win32 Constants
SW_HIDE = 0
SW_NORMAL = 1
SW_SHOWMINIMIZED = 2
SW_MAXIMIZE = 3
SW_SHOWMAXIMIZED = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
SW_SHOWNA = 8
SW_RESTORE = 9

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOREDRAW = 0x0008
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

WM_CLOSE = 0x0010


def _get_window_current_snapshot(hwnd: int, pid: int | None = None) -> WindowLayoutSnapshot:
    """Read current window bounds and state for the undo stack."""
    if sys.platform != "win32" or is_simulated_window_validation():
        return WindowLayoutSnapshot(
            hwnd=hwnd,
            pid=pid or 1000,
            title="Simulated Window",
            bounds=(100, 100, 800, 600),
            state="normal",
            monitor_id=1,
        )

    user32 = ctypes.windll.user32
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    bounds = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    len_title = user32.GetWindowTextLengthW(hwnd)
    title = ""
    if len_title > 0:
        buf = ctypes.create_unicode_buffer(len_title + 1)
        user32.GetWindowTextW(hwnd, buf, len_title + 1)
        title = buf.value.strip()

    pid_actual = pid or 0
    if not pid_actual:
        pid_buf = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
        pid_actual = pid_buf.value

    # Determine state via placement
    class _WINDOWPLACEMENT(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_uint),
            ("flags", ctypes.c_uint),
            ("showCmd", ctypes.c_uint),
            ("ptMinPosition", ctypes.wintypes.POINT),
            ("ptMaxPosition", ctypes.wintypes.POINT),
            ("rcNormalPosition", ctypes.wintypes.RECT),
        ]

    wp = _WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(_WINDOWPLACEMENT)
    state = "normal"
    if user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        if wp.showCmd == SW_SHOWMAXIMIZED:
            state = "maximized"
        elif wp.showCmd in (SW_SHOWMINIMIZED, SW_MINIMIZE):
            state = "minimized"

    mon = monitor_from_window(hwnd)
    return WindowLayoutSnapshot(
        hwnd=hwnd,
        pid=pid_actual,
        title=title,
        bounds=bounds,
        state=state,
        monitor_id=mon.monitor_id,
    )


def focus_window(
    hwnd: Optional[int] = None,
    pid: int | None = None,
    window: Optional[str] = None,
    window_name: Optional[str] = None,
    app_name: Optional[str] = None,
    task_id: Optional[str] = None,
) -> CapabilityResult:
    """Safely bring a window to foreground focus and restore if minimized."""
    t0 = time.perf_counter()

    # Resolve HWND if query passed by name
    target_hwnd = hwnd
    if not target_hwnd or target_hwnd <= 0:
        if task_id:
            try:
                from astrarun.tasks.resource_ledger import AstraResourceLedger
                task_res = AstraResourceLedger.get_instance().list_resources_for_task(task_id)
                for r in reversed(task_res):
                    if r.hwnd and r.lifecycle_state in ("ACTIVE", "LAUNCHED", "DISCOVERED"):
                        target_hwnd = r.hwnd
                        break
            except Exception:
                pass

    if not target_hwnd or target_hwnd <= 0:
        query = window or window_name or app_name
        if query:
            try:
                from astrarun.windows.resolver import WindowResolver
                res = WindowResolver().resolve(query)
                if res.window and res.window.hwnd:
                    target_hwnd = res.window.hwnd
                elif res.candidates:
                    try:
                        from astrarun.tasks.resource_ledger import AstraResourceLedger
                        active_astra = AstraResourceLedger.get_instance().list_active_astra_resources()
                        active_hwnds = {r.hwnd for r in active_astra if r.hwnd}
                        astra_matches = [c for c in res.candidates if c.hwnd in active_hwnds]
                        if astra_matches:
                            target_hwnd = astra_matches[0].hwnd
                        else:
                            target_hwnd = res.candidates[0].hwnd
                    except Exception:
                        target_hwnd = res.candidates[0].hwnd
            except Exception:
                pass
        if not target_hwnd or target_hwnd <= 0:
            try:
                from astrarun.computer_use.observation import DesktopObserver
                st = DesktopObserver.get_instance().observe()
                if query:
                    w = st.find_window_by_app(query)
                    if w:
                        target_hwnd = w.hwnd
            except Exception:
                pass

    if not target_hwnd or target_hwnd <= 0:
        return CapabilityResult.fail(
            "focus_window",
            f"Could not resolve target window for focus (hwnd={hwnd}, window={window or window_name or app_name}).",
            error_code=CapabilityErrorCode.TARGET_NOT_FOUND if hasattr(CapabilityErrorCode, 'TARGET_NOT_FOUND') else CapabilityErrorCode.NOT_FOUND,
        )

    hwnd = target_hwnd
    valid, msg, code = validate_window_identity(hwnd, expected_pid=pid)
    if not valid:
        return CapabilityResult.fail("focus_window", msg, error_code=code)

    if sys.platform != "win32" or is_simulated_window_validation():
        return CapabilityResult.ok("focus_window", f"Focused window {hwnd} (simulated).", latency_ms=1.0)

    user32 = ctypes.windll.user32
    # Restore if minimized
    user32.ShowWindow(hwnd, SW_RESTORE)

    # Attach thread input to bypass Windows foreground activation lock
    cur_thread = ctypes.windll.kernel32.GetCurrentThreadId()
    target_thread = user32.GetWindowThreadProcessId(hwnd, None)
    if cur_thread != target_thread:
        user32.AttachThreadInput(cur_thread, target_thread, True)

    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)

    if cur_thread != target_thread:
        user32.AttachThreadInput(cur_thread, target_thread, False)

    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="focus_window",
        message=f"Brought window {hwnd} to foreground focus.",
        data={"hwnd": hwnd, "action": "focus"},
        context_updates=[{"type": "window_focused", "hwnd": hwnd}],
        latency_ms=latency,
    )


def minimize_window(hwnd: int, pid: int | None = None) -> CapabilityResult:
    """Minimize a window."""
    t0 = time.perf_counter()
    valid, msg, code = validate_window_identity(hwnd, expected_pid=pid)
    if not valid:
        return CapabilityResult.fail("minimize_window", msg, error_code=code)

    if sys.platform != "win32" or is_simulated_window_validation():
        return CapabilityResult.ok("minimize_window", f"Minimized window {hwnd} (simulated).", latency_ms=1.0)

    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, SW_MINIMIZE)
    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="minimize_window",
        message=f"Minimized window {hwnd}.",
        data={"hwnd": hwnd, "action": "minimize"},
        latency_ms=latency,
    )


def maximize_window(hwnd: int, pid: int | None = None) -> CapabilityResult:
    """Maximize a window after capturing snapshot for undo."""
    t0 = time.perf_counter()
    valid, msg, code = validate_window_identity(hwnd, expected_pid=pid)
    if not valid:
        return CapabilityResult.fail("maximize_window", msg, error_code=code)

    # Record snapshot before maximizing
    snap = _get_window_current_snapshot(hwnd, pid)
    restore_stack.push(snap)

    if sys.platform != "win32" or is_simulated_window_validation():
        return CapabilityResult.ok("maximize_window", f"Maximized window {hwnd} (simulated).", latency_ms=1.0)

    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, SW_MAXIMIZE)
    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="maximize_window",
        message=f"Maximized window {hwnd}.",
        data={"hwnd": hwnd, "action": "maximize"},
        latency_ms=latency,
    )


def restore_window(hwnd: int, pid: int | None = None) -> CapabilityResult:
    """Restore a minimized or maximized window to normal size."""
    t0 = time.perf_counter()
    valid, msg, code = validate_window_identity(hwnd, expected_pid=pid)
    if not valid:
        return CapabilityResult.fail("restore_window", msg, error_code=code)

    if sys.platform != "win32" or is_simulated_window_validation():
        return CapabilityResult.ok("restore_window", f"Restored window {hwnd} (simulated).", latency_ms=1.0)

    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, SW_RESTORE)
    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="restore_window",
        message=f"Restored window {hwnd}.",
        data={"hwnd": hwnd, "action": "restore"},
        latency_ms=latency,
    )


def move_window(
    hwnd: int,
    x: int,
    y: int,
    width: Optional[int] = None,
    height: Optional[int] = None,
    pid: Optional[int] = None,
) -> CapabilityResult:
    """Move and optionally resize a window, saving undo snapshot."""
    t0 = time.perf_counter()
    valid, msg, code = validate_window_identity(hwnd, expected_pid=pid)
    if not valid:
        return CapabilityResult.fail("move_window", msg, error_code=code)

    snap = _get_window_current_snapshot(hwnd, pid)
    restore_stack.push(snap)

    cur_w = width if width is not None and width > 0 else snap.bounds[2]
    cur_h = height if height is not None and height > 0 else snap.bounds[3]
    cx, cy, cw, ch = clamp_geometry(x, y, cur_w, cur_h)

    if sys.platform != "win32" or is_simulated_window_validation():
        return CapabilityResult.ok(
            capability="move_window",
            message=f"Moved window {hwnd} to ({cx}, {cy}, {cw}, {ch}) (simulated).",
            data={"hwnd": hwnd, "bounds": (cx, cy, cw, ch)},
            latency_ms=1.0,
        )

    user32 = ctypes.windll.user32
    # Restore first if maximized
    if snap.state == "maximized":
        user32.ShowWindow(hwnd, SW_RESTORE)

    flags = SWP_NOACTIVATE | SWP_NOZORDER | SWP_FRAMECHANGED
    res = user32.SetWindowPos(hwnd, 0, cx, cy, cw, ch, flags)
    latency = (time.perf_counter() - t0) * 1000

    if not res:
        err = ctypes.GetLastError()
        return CapabilityResult.fail(
            "move_window",
            f"Failed to reposition window {hwnd} (Win32 Error: {err}).",
            error_code=CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="move_window",
        message=f"Moved window {hwnd} to ({cx}, {cy}, {cw}, {ch}).",
        data={"hwnd": hwnd, "bounds": (cx, cy, cw, ch)},
        context_updates=[{"type": "window_moved", "hwnd": hwnd, "bounds": (cx, cy, cw, ch)}],
        latency_ms=latency,
    )


def resize_window(hwnd: int, width: int, height: int, pid: Optional[int] = None) -> CapabilityResult:
    """Resize a window while preserving its current top-left position."""
    snap = _get_window_current_snapshot(hwnd, pid)
    return move_window(hwnd, x=snap.bounds[0], y=snap.bounds[1], width=width, height=height, pid=pid)


def move_window_to_monitor(hwnd: int, monitor_spec: str | int, pid: Optional[int] = None) -> CapabilityResult:
    """Move a window to a target display monitor while preserving its relative size."""
    t0 = time.perf_counter()
    valid, msg, code = validate_window_identity(hwnd, expected_pid=pid)
    if not valid:
        return CapabilityResult.fail("move_window_to_monitor", msg, error_code=code)

    snap = _get_window_current_snapshot(hwnd, pid)
    target_mon = resolve_monitor(monitor_spec, current_monitor_id=snap.monitor_id)
    if not target_mon:
        return CapabilityResult.fail(
            "move_window_to_monitor",
            f"Could not resolve monitor matching '{monitor_spec}'.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    # Calculate target position inside target work area
    wx, wy, ww, wh = target_mon.work_area
    cur_w = min(ww, snap.bounds[2])
    cur_h = min(wh, snap.bounds[3])

    # Center or position neatly in target work area
    tx = wx + (ww - cur_w) // 2
    ty = wy + (wh - cur_h) // 2

    res = move_window(hwnd, x=tx, y=ty, width=cur_w, height=cur_h, pid=pid)
    if not res.success:
        return res

    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="move_window_to_monitor",
        message=f"Moved window '{snap.title}' to {target_mon.device_name} (Monitor {target_mon.monitor_id}).",
        data={"hwnd": hwnd, "monitor_id": target_mon.monitor_id, "bounds": (tx, ty, cur_w, cur_h)},
        latency_ms=latency,
    )


def snap_window(
    hwnd: int,
    layout: Union[str, LayoutType],
    monitor_spec: Optional[str | int] = None,
    pid: Optional[int] = None,
) -> CapabilityResult:
    """Snap a window into a standard tiling layout position on the target monitor."""
    t0 = time.perf_counter()
    valid, msg, code = validate_window_identity(hwnd, expected_pid=pid)
    if not valid:
        return CapabilityResult.fail("snap_window", msg, error_code=code)

    snap = _get_window_current_snapshot(hwnd, pid)
    if monitor_spec is not None:
        target_mon = resolve_monitor(monitor_spec, current_monitor_id=snap.monitor_id) or get_primary_monitor()
    else:
        target_mon = monitor_from_window(hwnd)

    bounds = DesktopLayoutEngine.compute_bounds(layout, target_mon.work_area)
    res = move_window(hwnd, x=bounds[0], y=bounds[1], width=bounds[2], height=bounds[3], pid=pid)
    if not res.success:
        return res

    latency = (time.perf_counter() - t0) * 1000
    lt_name = layout.value if isinstance(layout, LayoutType) else str(layout)
    return CapabilityResult.ok(
        capability="snap_window",
        message=f"Snapped window '{snap.title}' to {lt_name} on Monitor {target_mon.monitor_id}.",
        data={"hwnd": hwnd, "layout": lt_name, "bounds": bounds, "monitor_id": target_mon.monitor_id},
        latency_ms=latency,
    )


def snap_window_left(
    hwnd: int,
    monitor_spec: Optional[str | int] = None,
    pid: Optional[int] = None,
) -> CapabilityResult:
    """Snap a window to the left half of its monitor."""
    res = snap_window(hwnd=hwnd, layout=LayoutType.LEFT_HALF, monitor_spec=monitor_spec, pid=pid)
    res.capability = "snap_window_left"
    return res


def snap_window_right(
    hwnd: int,
    monitor_spec: Optional[str | int] = None,
    pid: Optional[int] = None,
) -> CapabilityResult:
    """Snap a window to the right half of its monitor."""
    res = snap_window(hwnd=hwnd, layout=LayoutType.RIGHT_HALF, monitor_spec=monitor_spec, pid=pid)
    res.capability = "snap_window_right"
    return res


def close_window(hwnd: int, pid: int | None = None) -> CapabilityResult:
    """
    Gracefully close a window via standard WM_CLOSE message.
    Strict Invariant: NEVER terminates process; allows app to prompt save dialog.
    """
    t0 = time.perf_counter()
    valid, msg, code = validate_window_identity(hwnd, expected_pid=pid)
    if not valid:
        return CapabilityResult.fail("close_window", msg, error_code=code)

    snap = _get_window_current_snapshot(hwnd, pid)

    if sys.platform != "win32" or is_simulated_window_validation():
        return CapabilityResult.ok(
            capability="close_window",
            message=f"Sent WM_CLOSE to window {hwnd} (simulated).",
            data={"hwnd": hwnd, "action": "close"},
            latency_ms=1.0,
        )

    try:
        from astrarun.tasks.resource_ledger import AstraResourceLedger
        ledger = AstraResourceLedger.get_instance()
        active_res = [r for r in ledger.list_active_astra_resources() if r.hwnd == hwnd]
        if active_res:
            res = active_res[0]
            ok = ledger.close_owned_resource(res)
            latency = (time.perf_counter() - t0) * 1000
            if ok:
                return CapabilityResult.ok(
                    capability="close_window",
                    message=f"Closed Astra-owned window '{snap.title}' (HWND {hwnd}).",
                    data={"hwnd": hwnd, "title": snap.title, "action": "close", "resource_id": res.resource_id},
                    context_updates=[{"type": "window_closed", "hwnd": hwnd, "title": snap.title}],
                    latency_ms=latency,
                )
    except Exception as err:
        logger.debug("Resource ledger check in close_window: %s", err)

    user32 = ctypes.windll.user32
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="close_window",
        message=f"Sent graceful close request (WM_CLOSE) to window '{snap.title}' (HWND {hwnd}).",
        data={"hwnd": hwnd, "title": snap.title, "action": "close"},
        context_updates=[{"type": "window_closed", "hwnd": hwnd, "title": snap.title}],
        latency_ms=latency,
    )


def undo_last_window_move() -> CapabilityResult:
    """Restore the most recently modified window geometry from the undo stack."""
    t0 = time.perf_counter()
    snap = restore_stack.pop()
    if not snap:
        return CapabilityResult.fail(
            "undo_last_window_move",
            "No recent window layout actions found to undo (stack empty or expired).",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    # Revalidate handle still exists and belongs to the same process
    valid, msg, code = validate_window_identity(snap.hwnd, expected_pid=snap.pid)
    if not valid:
        return CapabilityResult.fail(
            "undo_last_window_move",
            f"Cannot undo: target window {snap.hwnd} ('{snap.title}') has closed or recycled (STALE_ENTITY).",
            error_code=code,
        )

    if sys.platform != "win32" or is_simulated_window_validation():
        return CapabilityResult.ok(
            "undo_last_window_move",
            f"Restored window '{snap.title}' to {snap.bounds} (simulated).",
            data={"hwnd": snap.hwnd, "bounds": snap.bounds},
            latency_ms=1.0,
        )

    user32 = ctypes.windll.user32
    if snap.state == "maximized":
        user32.ShowWindow(snap.hwnd, SW_MAXIMIZE)
    elif snap.state == "minimized":
        user32.ShowWindow(snap.hwnd, SW_MINIMIZE)
    else:
        user32.ShowWindow(snap.hwnd, SW_RESTORE)
        user32.SetWindowPos(
            snap.hwnd,
            0,
            snap.bounds[0],
            snap.bounds[1],
            snap.bounds[2],
            snap.bounds[3],
            SWP_NOACTIVATE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )

    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="undo_last_window_move",
        message=f"Restored window '{snap.title}' to previous bounds {snap.bounds}.",
        data={"hwnd": snap.hwnd, "bounds": snap.bounds, "state": snap.state},
        context_updates=[{"type": "window_undo", "hwnd": snap.hwnd, "bounds": snap.bounds}],
        latency_ms=latency,
    )


def arrange_desktop(plan: list[dict[str, Any]]) -> CapabilityResult:
    """
    Arrange multiple windows simultaneously (e.g. VS Code left and Terminal right).
    Enforces atomic pre-validation: validates ALL targets before mutating any window.
    """
    t0 = time.perf_counter()
    if not plan:
        return CapabilityResult.fail(
            "arrange_desktop",
            "No window arrangement items provided in plan.",
            error_code=CapabilityErrorCode.INVALID_ARGUMENT,
        )

    # 1. Pre-validate every item in the plan
    for idx, item in enumerate(plan):
        hwnd = item.get("hwnd", 0)
        pid = item.get("pid")
        valid, msg, code = validate_window_identity(hwnd, expected_pid=pid)
        if not valid:
            return CapabilityResult.fail(
                "arrange_desktop",
                f"Aborted desktop arrangement: item #{idx+1} (HWND {hwnd}) failed validation: {msg}",
                error_code=code,
            )

    # 2. Execute moves sequentially
    executed: list[dict[str, Any]] = []
    for item in plan:
        hwnd = item["hwnd"]
        layout = item.get("layout", "full")
        mon_spec = item.get("monitor")
        pid = item.get("pid")

        res = snap_window(hwnd, layout=layout, monitor_spec=mon_spec, pid=pid)
        if not res.success:
            logger.warning("Step in arrange_desktop encountered issue: %s", res.message)
        executed.append({"hwnd": hwnd, "layout": layout, "success": res.success})

    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="arrange_desktop",
        message=f"Arranged {len(plan)} window(s) across the desktop.",
        data={"plan": executed, "count": len(executed)},
        latency_ms=latency,
    )


