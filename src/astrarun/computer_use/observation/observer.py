"""Hierarchical Desktop Observer for AstraRun ComputerUse."""

from __future__ import annotations

import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

from astrarun.computer_use.hooks.desktop_attach import ensure_desktop_attached
from astrarun.computer_use.ui.dialogs import DialogDetector
from astrarun.computer_use.world.desktop_state import (
    DesktopWorldState,
    DialogObservation,
    ProcessObservation,
    WindowObservation,
)
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.computer_use.observation.observer")


class DesktopObserver:
    """
    Hierarchical multi-tier desktop observer implementing F0-20 perception contracts.
    Maintains live desktop world state without high CPU/GPU overhead.
    """

    _instance: Optional[DesktopObserver] = None

    def __init__(self) -> None:
        self._last_state: Optional[DesktopWorldState] = None
        self._process_cache: Dict[int, Tuple[float, str, str]] = {}  # pid -> (create_time, name, exe)

    @classmethod
    def get_instance(cls) -> DesktopObserver:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def observe(
        self,
        target_hwnd: Optional[int] = None,
        include_uia: bool = True,
        include_dialogs: bool = True,
        task_id: Optional[str] = None,
    ) -> DesktopWorldState:
        """
        Produce a live DesktopWorldState observation across Tier 0 (Win32),
        Tier 1 (UIA / Dialogs), and ambient ownership.
        """
        t0 = time.perf_counter()
        ensure_desktop_attached()

        fg_hwnd = 0
        cursor_pos: Optional[Tuple[int, int]] = None
        visible_windows: List[WindowObservation] = []
        dialogs: List[DialogObservation] = []
        processes: List[ProcessObservation] = []
        astra_resources: List[Dict[str, Any]] = []
        user_resources: List[Dict[str, Any]] = []
        focused_ctrl: Optional[Dict[str, Any]] = None
        user_takeover = False

        # 1. User takeover check
        try:
            from astrarun.perception.input import PhysicalInputController
            pic = PhysicalInputController.get_instance()
            user_takeover = pic.check_user_takeover()
        except Exception:
            pass

        # 2. Resource ledger lookup
        ledger = None
        try:
            from astrarun.tasks.resource_ledger import AstraResourceLedger
            ledger = AstraResourceLedger.get_instance()
        except Exception:
            pass

        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            # Foreground window
            fg_hwnd = user32.GetForegroundWindow()

            # Cursor position
            pt = wintypes.POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                cursor_pos = (pt.x, pt.y)

            # Enumerate visible top-level windows
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            GWL_STYLE = -16
            WS_MINIMIZE = 0x20000000
            WS_MAXIMIZE = 0x01000000
            GW_OWNER = 4

            def enum_cb(hwnd: int, lparam: int) -> bool:
                if not user32.IsWindowVisible(hwnd):
                    return True

                length = user32.GetWindowTextLengthW(hwnd)
                title = ""
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value

                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                cls_name = cls_buf.value

                # Filter out invisible or tool utility shells unless titled
                if not title and cls_name in ["DummyDWMListenerWindow", "EdgeUiInputTopWndClass", "ThumbnailDeviceHelperWnd"]:
                    return True

                rect = wintypes.RECT()
                bounds = (0, 0, 0, 0)
                if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    bounds = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                p_info = self._get_proc_info(pid.value)

                style = user32.GetWindowLongW(hwnd, GWL_STYLE)
                is_min = bool(style & WS_MINIMIZE)
                is_max = bool(style & WS_MAXIMIZE)
                owner = user32.GetWindow(hwnd, GW_OWNER)

                is_dialog = cls_name == "#32770" or owner != 0

                # Check Astra ownership
                is_astra = False
                res_task_id = None
                if ledger:
                    res = ledger.get_resource_for_hwnd(hwnd)
                    if res:
                        is_astra = True
                        res_task_id = res.task_id

                w_obs = WindowObservation(
                    hwnd=hwnd,
                    pid=pid.value,
                    process_creation_time=p_info[0],
                    application_identity=p_info[1],
                    title=title,
                    bounds=bounds,
                    is_visible=True,
                    is_minimized=is_min,
                    is_maximized=is_max,
                    is_foreground=(hwnd == fg_hwnd),
                    owner_hwnd=owner,
                    is_modal=is_dialog and owner != 0,
                    is_dialog=is_dialog,
                    dialog_type=cls_name if is_dialog else "",
                    astra_owned=is_astra,
                    task_id=res_task_id or (task_id if is_astra else None),
                    uia_available=True,
                    last_observed=time.time(),
                )
                visible_windows.append(w_obs)
                if is_astra:
                    astra_resources.append({"type": "window", "hwnd": hwnd, "title": title})
                else:
                    user_resources.append({"type": "window", "hwnd": hwnd, "title": title})
                return True

            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        # 3. Dialogs detection
        if include_dialogs:
            dialogs = DialogDetector.detect_dialogs(task_id=task_id)

        # 4. Foreground window observation
        fg_obs = None
        for w in visible_windows:
            if w.hwnd == fg_hwnd:
                fg_obs = w
                break

        # 5. UIA structured controls if requested
        active_target = target_hwnd or fg_hwnd
        if include_uia and active_target:
            try:
                from astrarun.interaction.discovery import enumerate_window_controls
                raw = enumerate_window_controls(active_target, max_elements=20)
                for c in raw:
                    if getattr(c, "is_focused", False):
                        focused_ctrl = {
                            "name": c.name,
                            "automation_id": c.automation_id,
                            "control_type": getattr(c.control_type, "value", str(c.control_type)),
                            "bounds": c.bounds,
                        }
                        break
            except Exception as ex:
                logger.debug("Focused control UIA scan omitted: %s", ex)

        # 6. Browser sessions
        browser_tabs: List[Dict[str, Any]] = []
        try:
            from astrarun.computer_use.browser.cdp import BrowserCDPDriver
            driver = BrowserCDPDriver()
            browser_tabs = driver.get_open_tabs()
        except Exception:
            pass

        t_end = time.perf_counter()
        latency_ms = round((t_end - t0) * 1000.0, 2)

        state = DesktopWorldState(
            timestamp=time.time(),
            foreground_window=fg_obs,
            cursor_position=cursor_pos,
            monitors=[],
            visible_windows=visible_windows,
            dialogs=dialogs,
            processes=processes,
            astra_owned_resources=astra_resources,
            user_owned_resources=user_resources,
            focused_control=focused_ctrl,
            browser_sessions=browser_tabs,
            user_takeover_active=user_takeover,
            observation_freshness=time.time(),
            observation_latency_ms=latency_ms,
        )

        self._last_state = state
        if task_id:
            try:
                from astrarun.core.telemetry import CausalTelemetry, CausalEventType
                telem = CausalTelemetry.get_instance()
                telem.emit(
                    event_type=CausalEventType.STATE_OBSERVED.value,
                    component="DesktopObserver",
                    task_id=task_id,
                    data={
                        "foreground_title": fg_obs.title if fg_obs else None,
                        "visible_window_count": len(visible_windows),
                        "dialog_count": len(dialogs),
                        "observation_latency_ms": latency_ms,
                    },
                )
            except Exception:
                pass
        return state

    def _get_proc_info(self, pid: int) -> Tuple[float, str, str]:
        """Cached lookup of process create time and name."""
        if pid in self._process_cache:
            return self._process_cache[pid]
        try:
            p = psutil.Process(pid)
            info = (p.create_time(), p.name(), p.exe() if hasattr(p, "exe") else "")
            self._process_cache[pid] = info
            return info
        except Exception:
            return (0.0, "", "")

    def get_last_state(self) -> Optional[DesktopWorldState]:
        return self._last_state

    # Alias for API compatibility
    observe_state = observe
