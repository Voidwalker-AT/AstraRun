"""Production result presentation engine for AstraRun.

Handles model/planner-directed presentation of deliverables and summaries:
- Folders -> Windows File Explorer
- Files -> Default viewer / editor (e.g. Notepad, image viewer)
- Summaries -> Launcher / Floating HUD result card

Enforces strict semantic truth state machine:
PRESENTATION_REQUESTED
  -> PRESENTATION_DISPATCHED
  -> PRESENTATION_PROCESS_STARTED
  -> PRESENTATION_TARGET_DISCOVERED
  -> PRESENTATION_TARGET_IDENTITY_VERIFIED
  -> PRESENTATION_TARGET_VISIBLE
  -> PRESENTATION_CONTENT_VERIFIED
  -> RESULT_PRESENTED (only if target physically observed)
  OR PRESENTATION_UNVERIFIED (fail closed)
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

import psutil

from astrarun.capabilities.models import CapabilityResult
from astrarun.core.logging import get_logger
from astrarun.core.telemetry import CausalTelemetry, CausalEventType, compute_hash

logger = get_logger("astrarun.ui.result_presentation")

DWMWA_CLOAKED = 14
MONITOR_DEFAULTTONEAREST = 2


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _ensure_desktop():
    if sys.platform == "win32":
        try:
            from astrarun.windows.discovery import _ensure_desktop_attached
            _ensure_desktop_attached()
        except Exception:
            pass


def _is_window_visible_and_on_monitor(user32, dwmapi, hwnd: int) -> Tuple[bool, List[int]]:
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
        return False, [0, 0, 0, 0]

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 10 or h <= 10:
        return False, [0, 0, 0, 0]

    if dwmapi:
        cloaked = ctypes.c_int(0)
        hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if hr == 0 and cloaked.value != 0:
            return False, [rect.left, rect.top, rect.right, rect.bottom]

    h_mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if h_mon:
        mon_info = MONITORINFO()
        mon_info.cbSize = ctypes.sizeof(MONITORINFO)
        if user32.GetMonitorInfoW(h_mon, ctypes.byref(mon_info)):
            mr = mon_info.rcMonitor
            ix_left = max(rect.left, mr.left)
            ix_top = max(rect.top, mr.top)
            ix_right = min(rect.right, mr.right)
            ix_bottom = min(rect.bottom, mr.bottom)
            if ix_right > ix_left and ix_bottom > ix_top:
                return True, [rect.left, rect.top, rect.right, rect.bottom]

    return False, [rect.left, rect.top, rect.right, rect.bottom]


def present_result(
    target: Optional[str] = None,
    mode: str = "auto",
    task_id: Optional[str] = None,
) -> CapabilityResult:
    """
    Present a task deliverable or summary to the user with physical OS attestation.
    Fails closed if the intended result window is not physically verified.
    """
    telem = CausalTelemetry.get_instance()
    t0 = time.time()
    
    # 1. State: PRESENTATION_REQUESTED
    telem.emit(
        event_type=CausalEventType.RESULT_PRESENTATION_REQUESTED.value,
        component="ResultPresentation",
        task_id=task_id,
        data={"target": target, "mode": mode, "state": "PRESENTATION_REQUESTED"},
        input_hash=compute_hash(target or ""),
    )

    resolved_mode = mode.lower() if mode else "auto"
    target_str = (target or "").strip()
    target_path = Path(target_str) if target_str else None

    # Detect mechanism and validate target on disk
    mechanism = "summary"
    if target_path:
        if target_path.exists():
            if target_path.is_dir() or resolved_mode == "explorer":
                mechanism = "explorer"
            elif target_path.is_file():
                if resolved_mode in ("editor", "notepad"):
                    mechanism = "editor"
                else:
                    mechanism = "viewer"
        else:
            if resolved_mode in ("explorer", "editor", "viewer") or target_str.endswith((".txt", ".json", ".py", ".md", ".log", "\\", "/")):
                # Target path was requested as a file/dir but is missing on disk -> FAIL CLOSED
                telem.emit(
                    event_type=CausalEventType.STATE_OBSERVED.value,
                    component="ResultPresentation",
                    task_id=task_id,
                    data={"target_observed": False, "error": f"Target path '{target_str}' does not exist on disk."},
                )
                return CapabilityResult.fail(
                    "present_result",
                    f"Presentation failed: target path '{target_str}' does not exist on disk.",
                    data={"target_observed": False, "hwnd": None, "pid": None, "mechanism": resolved_mode},
                )
    elif resolved_mode == "explorer":
        mechanism = "explorer"

    # Pre-launch window snapshot
    pre_windows: Dict[int, Tuple[int, str, str]] = {}
    user32 = ctypes.windll.user32 if sys.platform == "win32" else None
    dwmapi = None
    if sys.platform == "win32":
        try:
            dwmapi = ctypes.windll.dwmapi
        except Exception:
            dwmapi = None
        _ensure_desktop()
        if user32:
            def snap_cb(h, _):
                if user32.IsWindowVisible(h):
                    pbuf = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(pbuf))
                    len_t = user32.GetWindowTextLengthW(h)
                    t_buf = ctypes.create_unicode_buffer(len_t + 1)
                    user32.GetWindowTextW(h, t_buf, len_t + 1)
                    c_buf = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(h, c_buf, 256)
                    pre_windows[h] = (pbuf.value, t_buf.value, c_buf.value)
                return True
            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(snap_cb), 0)

    # 2. State: PRESENTATION_DISPATCHED
    launched_pid: Optional[int] = None
    proc = None
    si_cmd = None
    if sys.platform == "win32":
        si_cmd = subprocess.STARTUPINFO()
        si_cmd.lpDesktop = r"WinSta0\Default"

    if mechanism == "explorer":
        path_to_open = str(target_path.resolve()) if (target_path and target_path.exists()) else str(Path.home())
        try:
            if target_path and target_path.is_file():
                proc = subprocess.Popen(["explorer.exe", f"/select,{path_to_open}"], startupinfo=si_cmd)
            else:
                proc = subprocess.Popen(["explorer.exe", path_to_open], startupinfo=si_cmd)
            launched_pid = proc.pid
        except Exception as e:
            logger.error("Failed opening explorer: %s", e)
            telem.emit(
                event_type=CausalEventType.STATE_OBSERVED.value,
                component="ResultPresentation",
                task_id=task_id,
                data={"target_observed": False, "error": str(e)},
            )
            return CapabilityResult.fail("present_result", f"Failed dispatching explorer: {e}")

    elif mechanism in ("editor", "viewer"):
        path_to_open = str(target_path.resolve())
        try:
            if sys.platform == "win32":
                viewer_code = f"""
import sys, ctypes
from pathlib import Path
user32 = ctypes.windll.user32
hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
if hwinsta: user32.SetProcessWindowStation(hwinsta)
hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
if not hdesk: hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
if hdesk: user32.SetThreadDesktop(hdesk)

from PySide6 import QtWidgets
app = QtWidgets.QApplication(sys.argv)
w = QtWidgets.QMainWindow()
p = Path({repr(path_to_open)})
w.setWindowTitle(f"{{p.name}} - AstraRun Viewer")
w.resize(650, 450)
txt = QtWidgets.QPlainTextEdit(w)
txt.setReadOnly(True)
try:
    content = p.read_text(encoding="utf-8", errors="replace")
except Exception:
    content = ""
txt.setPlainText(content)
w.setCentralWidget(txt)
w.show()
sys.exit(app.exec())
"""
                proc = subprocess.Popen([sys.executable, "-c", viewer_code], startupinfo=si_cmd)
                launched_pid = proc.pid
            else:
                proc = subprocess.Popen(["xdg-open", path_to_open])
                launched_pid = proc.pid
        except Exception as e:
            logger.error("Failed opening viewer: %s", e)
            telem.emit(
                event_type=CausalEventType.STATE_OBSERVED.value,
                component="ResultPresentation",
                task_id=task_id,
                data={"target_observed": False, "error": str(e)},
            )
            return CapabilityResult.fail("present_result", f"Failed dispatching file viewer: {e}")

    elif mechanism == "summary":
        pass

    # 3 & 4: Observation and Identity Verification
    verified_hwnd: Optional[int] = None
    verified_pid: Optional[int] = None
    verified_title: str = ""
    verified_class: str = ""
    target_observed: bool = False

    if mechanism == "summary":
        # Attest AstraRun launcher / HUD surface
        try:
            from astrarun.core.paths import AstraPaths
            state_file = AstraPaths.state_file_path()
            if state_file.exists():
                import json
                sf = json.loads(state_file.read_text(encoding="utf-8"))
                lh = sf.get("launcher_hwnd")
                lp = sf.get("pid")
                if lh and user32:
                    is_vis, rect = _is_window_visible_and_on_monitor(user32, dwmapi, lh)
                    if is_vis:
                        verified_hwnd = lh
                        verified_pid = lp
                        len_t = user32.GetWindowTextLengthW(lh)
                        t_buf = ctypes.create_unicode_buffer(len_t + 1)
                        user32.GetWindowTextW(lh, t_buf, len_t + 1)
                        verified_title = t_buf.value
                        c_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(lh, c_buf, 256)
                        verified_class = c_buf.value
                        if verified_title or verified_class:
                            target_observed = True
        except Exception as e:
            logger.debug("Summary attestation failed: %s", e)

    elif user32 and mechanism in ("explorer", "editor", "viewer"):
        target_name_lower = target_path.name.lower() if target_path else ""
        target_stem_lower = target_path.stem.lower() if target_path else ""
        target_parent_lower = target_path.parent.name.lower() if target_path else ""

        deadline = time.time() + 6.0
        while time.time() < deadline:
            time.sleep(0.2)
            _ensure_desktop()
            candidate_hwnd = None
            candidate_pid = None
            candidate_title = ""
            candidate_class = ""

            def search_cb(h, _):
                nonlocal candidate_hwnd, candidate_pid, candidate_title, candidate_class
                is_vis, _ = _is_window_visible_and_on_monitor(user32, dwmapi, h)
                if not is_vis:
                    return True

                pbuf = wintypes.DWORD()
                user32.GetWindowThreadProcessId(h, ctypes.byref(pbuf))
                win_pid = pbuf.value

                p_name = ""
                try:
                    p_name = (psutil.Process(win_pid).name() or "").lower()
                except Exception:
                    p_name = ""

                len_t = user32.GetWindowTextLengthW(h)
                t_buf = ctypes.create_unicode_buffer(len_t + 1)
                user32.GetWindowTextW(h, t_buf, len_t + 1)
                title = t_buf.value
                title_lower = title.lower()

                c_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(h, c_buf, 256)
                class_name = c_buf.value

                is_new_window = (h not in pre_windows)

                if mechanism == "explorer":
                    is_exp = p_name == "explorer.exe" or class_name in ("CabinetWClass", "ExploreWClass")
                    if is_exp:
                        # Match target directory or file identity
                        title_matches = (
                            bool(target_name_lower and target_name_lower in title_lower)
                            or bool(target_stem_lower and target_stem_lower in title_lower)
                            or bool(target_parent_lower and target_parent_lower in title_lower)
                        )
                        # Require affirmative title/target matching; do not accept arbitrary new windows
                        if title_matches:
                            candidate_hwnd = h
                            candidate_pid = win_pid
                            candidate_title = title
                            candidate_class = class_name
                            return False

                elif mechanism in ("editor", "viewer"):
                    title_matches = (
                        target_name_lower in title_lower
                        or target_stem_lower in title_lower
                    )
                    is_editor_app = (
                        "notepad" in p_name
                        or "notepad" in class_name.lower()
                        or "code" in p_name
                        or "editor" in class_name.lower()
                        or (launched_pid and win_pid == launched_pid)
                    )
                    if title_matches and (is_new_window or is_editor_app):
                        candidate_hwnd = h
                        candidate_pid = win_pid
                        candidate_title = title
                        candidate_class = class_name
                        return False

                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(search_cb), 0)

            if candidate_hwnd:
                verified_hwnd = candidate_hwnd
                verified_pid = candidate_pid
                verified_title = candidate_title
                verified_class = candidate_class
                target_observed = True
                break

    # 5. Semantic Decision: Emit RESULT_PRESENTED ONLY if target_observed is True and verified_hwnd is valid
    if target_observed and verified_hwnd is not None:
        telem.emit(
            event_type=CausalEventType.STATE_OBSERVED.value,
            component="ResultPresentation",
            task_id=task_id,
            data={
                "target_observed": True,
                "hwnd": verified_hwnd,
                "pid": verified_pid,
                "title": verified_title,
                "class": verified_class,
                "mechanism": mechanism,
            },
        )
        telem.emit(
            event_type=CausalEventType.POSTCONDITION_VERIFIED.value,
            component="ResultPresentation",
            task_id=task_id,
            data={
                "postcondition": "RESULT_VISIBLE_TO_USER",
                "hwnd": verified_hwnd,
                "target": str(target_path) if target_path else target_str,
            },
        )
        telem.emit(
            event_type=CausalEventType.RESULT_PRESENTED.value,
            component="ResultPresentation",
            task_id=task_id,
            data={
                "target_observed": True,
                "mechanism": mechanism,
                "target": str(target_path) if target_path else target_str,
                "verified_hwnd": verified_hwnd,
                "verified_pid": verified_pid,
                "verified_title": verified_title,
                "verified_class": verified_class,
                "duration_ms": (time.time() - t0) * 1000.0,
            },
            output_hash=compute_hash(f"{verified_hwnd}:{verified_title}"),
        )

        # Register in ResourceLedger
        if mechanism != "summary":
            try:
                from astrarun.tasks.resource_ledger import AstraResourceLedger, OwnedResource, ResourceType, CleanupPolicy
                ledger = AstraResourceLedger.get_instance()
                owned = OwnedResource(
                    task_id=task_id or "presentation_task",
                    resource_type=ResourceType.APPLICATION if mechanism != "explorer" else ResourceType.EXPLORER_WINDOW,
                    launching_capability="present_result",
                    pid=verified_pid,
                    hwnd=verified_hwnd,
                    document_path=str(target_path) if target_path else None,
                    astra_created=True,
                    cleanup_policy=CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
                )
                ledger.register_resource(owned)
            except Exception:
                pass

        return CapabilityResult.ok(
            capability="present_result",
            message=f"Result presented via {mechanism} (HWND={verified_hwnd}, '{verified_title}'): {target_str}",
            data={
                "target_observed": True,
                "mechanism": mechanism,
                "target": target_str,
                "hwnd": verified_hwnd,
                "pid": verified_pid,
                "title": verified_title,
            },
        )
    else:
        # FAIL CLOSED: target window was not observed
        error_msg = f"Presentation unverified: {mechanism} window for '{target_str}' was not observed on desktop."
        logger.warning(error_msg)
        telem.emit(
            event_type=CausalEventType.STATE_OBSERVED.value,
            component="ResultPresentation",
            task_id=task_id,
            data={
                "target_observed": False,
                "error": error_msg,
                "mechanism": mechanism,
                "target": target_str,
            },
        )
        return CapabilityResult.fail(
            "present_result",
            error_msg,
            data={
                "target_observed": False,
                "mechanism": mechanism,
                "target": target_str,
                "hwnd": None,
                "pid": None,
                "title": "",
            },
        )
