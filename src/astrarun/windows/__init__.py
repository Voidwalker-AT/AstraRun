"""Window Intelligence and Desktop Composition subsystem for AstraRun v0.9."""

from __future__ import annotations

from astrarun.windows.controller import (
    arrange_desktop,
    close_window,
    focus_window,
    maximize_window,
    minimize_window,
    move_window,
    move_window_to_monitor,
    resize_window,
    restore_window,
    snap_window,
    snap_window_left,
    snap_window_right,
    undo_last_window_move,
)
from astrarun.windows.discovery import (
    find_window,
    foreground_window,
    list_windows,
    windows_for_application,
)
from astrarun.windows.layouts import DesktopLayoutEngine
from astrarun.windows.models import (
    LayoutType,
    MonitorEntity,
    WindowBounds,
    WindowLayoutSnapshot,
    WindowState,
)
from astrarun.windows.monitors import (
    enumerate_monitors,
    get_primary_monitor,
    monitor_from_window,
    resolve_monitor,
    set_mock_monitors,
)
from astrarun.windows.policy import (
    clamp_geometry,
    is_astrarun_window,
    register_astrarun_hwnd,
    unregister_astrarun_hwnd,
    validate_window_identity,
)
from astrarun.windows.resolver import WindowResolution, WindowResolver
from astrarun.windows.undo import WindowRestoreStack, restore_stack

__all__ = [
    # Models
    "WindowState",
    "LayoutType",
    "WindowBounds",
    "MonitorEntity",
    "WindowLayoutSnapshot",
    # Discovery
    "list_windows",
    "foreground_window",
    "find_window",
    "windows_for_application",
    # Controller
    "focus_window",
    "minimize_window",
    "maximize_window",
    "restore_window",
    "move_window",
    "resize_window",
    "move_window_to_monitor",
    "snap_window",
    "snap_window_left",
    "snap_window_right",
    "close_window",
    "undo_last_window_move",
    "arrange_desktop",
    # Monitors
    "enumerate_monitors",
    "get_primary_monitor",
    "monitor_from_window",
    "resolve_monitor",
    "set_mock_monitors",
    # Layouts
    "DesktopLayoutEngine",
    # Policy
    "register_astrarun_hwnd",
    "unregister_astrarun_hwnd",
    "is_astrarun_window",
    "validate_window_identity",
    "clamp_geometry",
    # Resolver
    "WindowResolver",
    "WindowResolution",
    # Undo
    "WindowRestoreStack",
    "restore_stack",
]
