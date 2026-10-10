"""Application capability services: discovery, running check, safe focus, and graceful close."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

import psutil

from astrarun.capabilities.models import (
    ApplicationEntity,
    CapabilityErrorCode,
    CapabilityResult,
    WindowEntity,
)
from astrarun.core.logging import get_logger
from astrarun.discovery.apps import discover_all_apps
from astrarun.tasks.resource_ledger import (
    AstraResourceLedger,
    CleanupPolicy,
    ContentClassification,
    ResourceType,
)
from astrarun.tools.apps import open_app

logger = get_logger("astrarun.applications.service")

SW_RESTORE = 9
WM_CLOSE = 0x0010


def _ensure_desktop_attached() -> None:
    """Ensure current thread is attached to the interactive input desktop."""
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        user32.OpenInputDesktop.restype = ctypes.c_void_p
        user32.OpenDesktopW.restype = ctypes.c_void_p
        user32.SetThreadDesktop.argtypes = [ctypes.c_void_p]
        user32.SetThreadDesktop.restype = ctypes.wintypes.BOOL
        DESKTOP_ALL = 0x01FF
        hdesk = user32.OpenInputDesktop(0, False, DESKTOP_ALL)
        if not hdesk:
            hdesk = user32.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def _get_top_level_windows() -> list[WindowEntity]:
    """Enumerate visible top-level desktop windows."""
    if sys.platform != "win32":
        return []

    _ensure_desktop_attached()
    windows: list[WindowEntity] = []
    user32 = ctypes.windll.user32

    # EnumWindows callback definition
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

        # Ignore tiny or invisible utility windows
        if bounds[2] <= 50 or bounds[3] <= 50:
            return True

        app_name = "unknown"
        if pid:
            try:
                proc = psutil.Process(pid)
                app_name = proc.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                app_name = "unknown"

        windows.append(
            WindowEntity(
                hwnd=hwnd,
                title=title,
                pid=pid,
                app_id=app_name.lower().replace(".exe", ""),
                bounds=bounds,
                state="normal",
                visible=True,
            )
        )
        return True

    cb = WNDENUMPROC(enum_callback)
    user32.EnumWindows(cb, 0)
    return windows


def list_running_applications() -> CapabilityResult:
    """List running user-facing desktop applications based on visible top-level windows."""
    t0 = time.perf_counter()
    windows = _get_top_level_windows()

    # Aggregate by app_id
    apps_map: dict[str, ApplicationEntity] = {}
    for win in windows:
        aid = win.app_id
        if aid in ("explorer", "dwm", "shellexperiencehost", "applicationframehost", "systemsettings"):
            # skip standard Windows shell wrappers if they lack distinct titles
            if win.title in ("Program Manager", "Windows Shell Experience Host"):
                continue

        if aid not in apps_map:
            apps_map[aid] = ApplicationEntity(
                app_id=aid,
                display_name=win.title.split(" - ")[-1] if " - " in win.title else aid.title(),
                executable=f"{aid}.exe",
                pid=win.pid,
                windows=[win.hwnd],
                running=True,
            )
        else:
            apps_map[aid].windows.append(win.hwnd)

    app_list = list(apps_map.values())
    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="list_running_applications",
        message=f"Found {len(app_list)} running applications.",
        data={"applications": [a.to_dict() for a in app_list], "count": len(app_list)},
        context_updates=[{"type": "running_apps_listed", "count": len(app_list)}],
        latency_ms=latency,
    )


def is_application_running(app: str) -> CapabilityResult:
    """Check if a specific application is currently running."""
    t0 = time.perf_counter()
    app_clean = app.strip().lower().replace(".exe", "")
    windows = _get_top_level_windows()

    matches = [
        w for w in windows
        if app_clean in w.app_id or app_clean in w.title.lower()
    ]
    is_running = len(matches) > 0
    latency = (time.perf_counter() - t0) * 1000

    if is_running:
        return CapabilityResult.ok(
            capability="is_application_running",
            message=f"Application '{app}' is running with {len(matches)} window(s).",
            data={"running": True, "app": app_clean, "windows": [w.to_dict() for w in matches]},
            latency_ms=latency,
        )
    else:
        return CapabilityResult.ok(
            capability="is_application_running",
            message=f"Application '{app}' is not currently running.",
            data={"running": False, "app": app_clean, "windows": []},
            latency_ms=latency,
        )


def find_application(name: str) -> CapabilityResult:
    """Find installed application metadata from system and start menu."""
    t0 = time.perf_counter()
    clean_name = name.strip().lower()
    apps = discover_all_apps()

    # Search exact then fuzzy
    matched = None
    for k, info in apps.items():
        if k == clean_name or info.name.lower() == clean_name:
            matched = info
            break

    if not matched:
        for k, info in apps.items():
            if clean_name in k or clean_name in info.name.lower():
                matched = info
                break

    latency = (time.perf_counter() - t0) * 1000
    if matched:
        return CapabilityResult.ok(
            capability="find_application",
            message=f"Found application: {matched.name}",
            data={"app_id": matched.key, "name": matched.name, "path": matched.path},
            latency_ms=latency,
        )
    return CapabilityResult.fail(
        capability="find_application",
        message=f"Application '{name}' not found.",
        error_code=CapabilityErrorCode.NOT_FOUND,
        latency_ms=latency,
    )


def open_application(
    app: str = "",
    path: Optional[str] = None,
    target: Optional[str] = None,
    task_id: Optional[str] = None,
    cleanup_policy: Optional[CleanupPolicy | str] = None,
    content_classification: Optional[ContentClassification | str] = None,
    app_name: Optional[str] = None,
    application: Optional[str] = None,
) -> CapabilityResult:
    """Launch a verified local application with task-scoped resource ownership."""
    t0 = time.perf_counter()
    app = app or app_name or application or ""
    if not app and target:
        app = target
    resolved_path = path
    resolved_target = target

    # If path is provided but represents a document rather than an executable, use it as target
    if resolved_path:
        p = Path(resolved_path)
        if not p.exists() or p.suffix.lower() not in (".exe", ".lnk", ".bat", ".cmd"):
            if not resolved_target:
                resolved_target = resolved_path
            resolved_path = None

    if not resolved_path:
        find_res = find_application(app)
        if find_res.success and find_res.data and find_res.data.get("path"):
            resolved_path = find_res.data["path"]
        else:
            import shutil
            which_path = shutil.which(app) or shutil.which(f"{app}.exe")
            if which_path:
                resolved_path = which_path

    # Pre-launch resource snapshotting for unambiguous ownership
    ledger = AstraResourceLedger.get_instance()
    pre_snap = ledger.capture_pre_launch_snapshot()

    success = open_app(app=app, path=resolved_path or "", target=resolved_target)
    latency = (time.perf_counter() - t0) * 1000

    if success:
        # Determine policies
        pol = CleanupPolicy(cleanup_policy) if cleanup_policy else CleanupPolicy.AUTO_CLOSE_ON_COMPLETION
        clsf = ContentClassification(content_classification) if content_classification else ContentClassification.NONE

        owned_res = ledger.identify_and_register_launched_resource(
            task_id=task_id or "default_task",
            capability="open_application",
            pre_snapshot=pre_snap,
            expected_name_or_class=app,
            cleanup_policy=pol,
            content_classification=clsf,
            document_path=resolved_target or resolved_path,
            resource_type=ResourceType.APPLICATION,
        )

        # Declarative Tabbed application adapter (Windows 11 Notepad, Windows Terminal, etc.):
        # If pre-existing instances absorbed the launch into a tab, spawn a distinct window for task isolation
        TABBED_APPLICATION_ADAPTERS = {
            "notepad": {"hotkey": "ctrl+shift+n", "title_token": "notepad"},
            "windowsterminal": {"hotkey": "ctrl+shift+n", "title_token": "terminal"},
            "terminal": {"hotkey": "ctrl+shift+n", "title_token": "terminal"},
            "wt": {"hotkey": "ctrl+shift+n", "title_token": "terminal"},
        }
        app_clean = app.lower().replace(".exe", "").replace(" ", "")
        if not owned_res.hwnd and app_clean in TABBED_APPLICATION_ADAPTERS:
            adapter = TABBED_APPLICATION_ADAPTERS[app_clean]
            for h, (w_pid, w_title, _) in pre_snap.hwnds.items():
                if adapter["title_token"] in w_title.lower():
                    logger.info("[TABBED_APP_SEPARATION] Pre-existing tabbed app %s detected; spawning isolated task window via %s.", app, adapter["hotkey"])
                    from astrarun.interaction.keyboard import dispatch_shortcut, parse_shortcut
                    sc = parse_shortcut(adapter["hotkey"])
                    dispatch_shortcut(sc, target_hwnd=h)
                    time.sleep(0.8)
                    owned_res = ledger.identify_and_register_launched_resource(
                        task_id=task_id or "default_task",
                        capability="open_application",
                        pre_snapshot=pre_snap,
                        expected_name_or_class=app,
                        cleanup_policy=pol,
                        content_classification=clsf,
                        document_path=resolved_target or resolved_path,
                        resource_type=ResourceType.APPLICATION,
                    )
                    break

        # Document session cleanliness invariant:
        # If a document application is launched fresh without an explicit file path target,
        # ensure the initial active document is clean and unpolluted by OS session restore.
        if owned_res.hwnd and sys.platform == "win32" and not resolved_target and not resolved_path:
            app_clean = app.lower().replace(".exe", "").replace(" ", "")
            if app_clean in ("notepad", "texteditor"):
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(owned_res.hwnd, buf, 512)
                    if buf.value.startswith("*"):
                        logger.info("[SESSION_RESTORE_ISOLATION] Restored dirty buffer detected in %s; dispatching Ctrl+N for clean document.", app)
                        from astrarun.interaction.keyboard import dispatch_shortcut, parse_shortcut
                        dispatch_shortcut(parse_shortcut("Ctrl+N"), target_hwnd=owned_res.hwnd)
                        time.sleep(0.3)
                except Exception as ex:
                    logger.debug("Session restore isolation check error: %s", ex)

        res_data = {
            "app": app,
            "path": resolved_path,
            "resource_id": owned_res.resource_id,
            "pid": owned_res.pid,
            "hwnd": owned_res.hwnd,
            "astra_created": owned_res.astra_created,
            "process_creation_time": owned_res.process_creation_time,
        }
        return CapabilityResult.ok(
            capability="open_application",
            message=f"Application '{app}' launched successfully (PID={owned_res.pid}, HWND={owned_res.hwnd}).",
            data=res_data,
            context_updates=[{"type": "application_opened", "app": app, "hwnd": owned_res.hwnd or 0, "pid": owned_res.pid or 0}],
            latency_ms=(time.perf_counter() - t0) * 1000,
        )
    return CapabilityResult.fail(
        capability="open_application",
        message=f"Failed to launch application '{app}'.",
        error_code=CapabilityErrorCode.OS_ERROR,
        latency_ms=latency,
    )


def focus_application(app: str) -> CapabilityResult:
    """
    Focus a running application's window.
    If multiple plausible windows exist, returns AMBIGUOUS error with candidates.
    """
    t0 = time.perf_counter()
    if sys.platform != "win32":
        return CapabilityResult.fail(
            capability="focus_application",
            message="Window focus is only supported on Windows.",
            error_code=CapabilityErrorCode.UNAVAILABLE,
        )

    clean_app = app.strip().lower().replace(".exe", "")
    windows = _get_top_level_windows()

    matches = [
        w for w in windows
        if clean_app in w.app_id or clean_app in w.title.lower()
    ]

    latency = (time.perf_counter() - t0) * 1000
    if not matches:
        return CapabilityResult.fail(
            capability="focus_application",
            message=f"No running window found for '{app}'.",
            error_code=CapabilityErrorCode.NOT_FOUND,
            latency_ms=latency,
        )

    if len(matches) > 1:
        # Multiple windows: requires disambiguation
        candidates = [{"hwnd": w.hwnd, "title": w.title, "pid": w.pid} for w in matches]
        return CapabilityResult.fail(
            capability="focus_application",
            message=f"Multiple windows found for '{app}' ({len(matches)} matches). Disambiguation required.",
            error_code=CapabilityErrorCode.AMBIGUOUS,
            data={"candidates": candidates},
            latency_ms=latency,
        )

    # Exactly 1 match: Focus safely
    target = matches[0]
    user32 = ctypes.windll.user32
    user32.ShowWindow(target.hwnd, SW_RESTORE)
    user32.SetForegroundWindow(target.hwnd)

    return CapabilityResult.ok(
        capability="focus_application",
        message=f"Focused '{target.title}'.",
        data={"hwnd": target.hwnd, "title": target.title, "pid": target.pid},
        context_updates=[{"type": "application_focused", "app": clean_app, "hwnd": target.hwnd, "title": target.title}],
        latency_ms=latency,
    )


def close_application(
    app: str = "",
    task_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    app_name: Optional[str] = None,
    application: Optional[str] = None,
) -> CapabilityResult:
    """
    Gracefully close ONLY Astra-owned application windows and processes.
    Strict Invariant: NEVER terminates pre-existing user windows.
    """
    t0 = time.perf_counter()
    app = app or app_name or application or ""
    if sys.platform != "win32":
        return CapabilityResult.fail(
            capability="close_application",
            message="Window closing is only supported on Windows.",
            error_code=CapabilityErrorCode.UNAVAILABLE,
        )

    clean_app = app.strip().lower().replace(".exe", "")
    ledger = AstraResourceLedger.get_instance()

    from astrarun.discovery.entity_resolver import SemanticEntityResolver
    resolver = SemanticEntityResolver.get_instance()
    resolved = resolver.resolve_application(app)
    target_names = {clean_app, app.strip().lower()}
    if resolved:
        target_names.add(resolved.name.lower())
        target_names.add(Path(resolved.target_path).stem.lower())
        target_names.add(Path(resolved.target_path).name.lower())

    def _matches_resource(res: Any) -> bool:
        meta_str = str(res.metadata).lower()
        cap_str = (res.launching_capability or "").lower()
        doc_str = (res.document_path or "").lower()
        if any(name in cap_str or name in doc_str or name in meta_str for name in target_names):
            return True
        if res.pid:
            try:
                pname = psutil.Process(res.pid).name().lower()
                pstem = pname.replace(".exe", "")
                if any(name == pstem or name == pname or name in pname or pname in name for name in target_names):
                    return True
            except Exception:
                pass
        if res.hwnd and sys.platform == "win32":
            try:
                import win32gui
                title = win32gui.GetWindowText(res.hwnd).lower()
                if any(name in title for name in target_names):
                    return True
            except Exception:
                pass
        return False

    target_resources = []
    if resource_id:
        res = ledger.get_resource(resource_id)
        if res:
            target_resources.append(res)
    elif task_id:
        for res in ledger.list_resources_for_task(task_id):
            if _matches_resource(res):
                target_resources.append(res)

    # If no resources found for specific task_id, check across all active Astra-owned resources
    if not target_resources:
        for res in ledger.list_active_astra_resources():
            if _matches_resource(res):
                target_resources.append(res)

    latency = (time.perf_counter() - t0) * 1000
    if not target_resources:
        return CapabilityResult.fail(
            capability="close_application",
            message=f"No Astra-owned running instance found for '{app}'. Pre-existing user windows were safely preserved.",
            error_code=CapabilityErrorCode.NOT_FOUND,
            latency_ms=latency,
        )

    closed_count = 0
    for res in target_resources:
        if ledger.close_owned_resource(res):
            closed_count += 1

    return CapabilityResult.ok(
        capability="close_application",
        message=f"Closed {closed_count} Astra-owned instance(s) of '{app}'.",
        data={"app": clean_app, "windows_closed": closed_count},
        context_updates=[{"type": "application_closed", "app": clean_app, "windows_count": closed_count}],
        latency_ms=latency,
    )
