"""Application document and file saving interaction capabilities."""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, Optional, Tuple

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult
from astrarun.computer_use.hooks.desktop_attach import ensure_desktop_attached
from astrarun.computer_use.ui.dialogs import DialogDetector
from astrarun.core.logging import get_logger
from astrarun.interaction.keyboard import dispatch_shortcut, parse_shortcut
from astrarun.windows.discovery import foreground_window
from astrarun.windows.resolver import WindowResolver

logger = get_logger("astrarun.interaction.document")


def save_document_via_ui(
    filename: str = "",
    folder: Optional[str] = "Desktop",
    path: Optional[str] = None,
    hwnd: Optional[int] = None,
    app_name: Optional[str] = None,
    window: Optional[str] = None,
    task_id: Optional[str] = None,
) -> CapabilityResult:
    """
    Save the active document within an application through native UI interaction.
    Dispatches Ctrl+S / Ctrl+Shift+S / Alt+F->A, discovers the native Save As dialog,
    fills the destination path, clicks Save, handles confirmation prompts, and empirically verifies environmental state.
    Preserves APPLICATION_UI interaction modality.
    """
    t0 = time.perf_counter()
    ensure_desktop_attached()

    # 1. Resolve full destination path
    dest_path = path
    if not dest_path:
        fname = filename or "untitled.txt"
        folder_clean = (folder or "Desktop").lower()
        if folder_clean in ("desktop", "user_desktop"):
            base = os.path.join(os.path.expanduser("~"), "Desktop")
        elif folder_clean in ("downloads", "user_downloads"):
            base = os.path.join(os.path.expanduser("~"), "Downloads")
        elif folder_clean in ("documents", "user_documents"):
            base = os.path.join(os.path.expanduser("~"), "Documents")
        elif folder_clean in ("temp", "tmp"):
            base = os.environ.get("TEMP", os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp"))
        else:
            base = os.path.join(os.path.expanduser("~"), folder or "Desktop")
        os.makedirs(base, exist_ok=True)
        dest_path = os.path.join(base, fname)

    dest_path = os.path.abspath(dest_path)

    # 2. Resolve target application window HWND
    target_hwnd = hwnd if isinstance(hwnd, int) else None
    clean_task_id = task_id if isinstance(task_id, str) else None
    if not target_hwnd or target_hwnd <= 0:
        if clean_task_id:
            try:
                from astrarun.tasks.resource_ledger import AstraResourceLedger
                task_res = AstraResourceLedger.get_instance().list_resources_for_task(clean_task_id)
                for r in reversed(task_res):
                    if r.hwnd and r.lifecycle_state in ("ACTIVE", "LAUNCHED", "DISCOVERED"):
                        target_hwnd = r.hwnd
                        break
            except Exception:
                pass

    if not target_hwnd or (isinstance(target_hwnd, int) and target_hwnd <= 0):
        clean_window = window if isinstance(window, str) else None
        clean_app = app_name if isinstance(app_name, str) else None
        query = clean_window or clean_app
        if query:
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

    if sys.platform == "win32":
        from astrarun.windows.discovery import _ensure_desktop_attached
        _ensure_desktop_attached()

    # Fallback to any active resource in the ledger matching app_name
    if not target_hwnd or (isinstance(target_hwnd, int) and target_hwnd <= 0):
        try:
            from astrarun.tasks.resource_ledger import AstraResourceLedger
            active_astra = AstraResourceLedger.get_instance().list_active_astra_resources()
            target_str = clean_app.lower() if clean_app else ""
            for r in reversed(active_astra):
                if r.hwnd and (not target_str or target_str in (r.name or "").lower()):
                    target_hwnd = r.hwnd
                    break
        except Exception:
            pass

    if not target_hwnd or (isinstance(target_hwnd, int) and target_hwnd <= 0):
        fg = foreground_window()
        if fg.success and fg.data.get("hwnd"):
            target_hwnd = fg.data["hwnd"]

    if not target_hwnd or (isinstance(target_hwnd, int) and target_hwnd <= 0):
        return CapabilityResult.fail(
            capability="save_document_via_ui",
            message="Could not resolve target application window for UI document save.",
            error_code=CapabilityErrorCode.TARGET_NOT_FOUND,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    if sys.platform != "win32":
        return CapabilityResult.fail(
            capability="save_document_via_ui",
            message="UI document save is only supported on Windows platforms.",
            error_code=CapabilityErrorCode.NOT_SUPPORTED,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )

    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    # 3. Bring target window to foreground focus
    SW_RESTORE = 9
    user32.ShowWindow(target_hwnd, SW_RESTORE)
    from astrarun.ui.presentation import force_foreground_activation
    force_foreground_activation(target_hwnd)
    time.sleep(0.3)

    # 4. Trigger Save As dialog
    # Attempt UIA File -> Save as menu item first, then keyboard shortcuts
    menu_triggered = False
    try:
        import comtypes.client
        from comtypes.gen import UIAutomationClient
        uia = comtypes.client.CreateObject(UIAutomationClient.CUIAutomation, interface=UIAutomationClient.IUIAutomation)
        root = uia.ElementFromHandle(target_hwnd)
        if root:
            cond_file = uia.CreateAndCondition(
                uia.CreatePropertyCondition(UIAutomationClient.UIA_ControlTypePropertyId, UIAutomationClient.UIA_MenuItemControlTypeId),
                uia.CreatePropertyCondition(UIAutomationClient.UIA_NamePropertyId, "File"),
            )
            file_menu = root.FindFirst(UIAutomationClient.TreeScope_Descendants, cond_file)
            if file_menu:
                exp_pat = file_menu.GetCurrentPattern(UIAutomationClient.UIA_ExpandCollapsePatternId)
                if exp_pat:
                    exp_obj = exp_pat.QueryInterface(UIAutomationClient.IUIAutomationExpandCollapsePattern)
                    exp_obj.Expand()
                    time.sleep(0.3)
                    all_root = uia.GetRootElement()
                    cond_save_as = uia.CreateAndCondition(
                        uia.CreatePropertyCondition(UIAutomationClient.UIA_ControlTypePropertyId, UIAutomationClient.UIA_MenuItemControlTypeId),
                        uia.CreateOrCondition(
                            uia.CreatePropertyCondition(UIAutomationClient.UIA_NamePropertyId, "Save as"),
                            uia.CreateOrCondition(
                                uia.CreatePropertyCondition(UIAutomationClient.UIA_NamePropertyId, "Save As"),
                                uia.CreatePropertyCondition(UIAutomationClient.UIA_NamePropertyId, "Save As..."),
                            ),
                        ),
                    )
                    save_as_item = all_root.FindFirst(UIAutomationClient.TreeScope_Descendants, cond_save_as)
                    if not save_as_item:
                        save_as_item = root.FindFirst(UIAutomationClient.TreeScope_Descendants, cond_save_as)
                    if save_as_item:
                        inv_pat = save_as_item.GetCurrentPattern(UIAutomationClient.UIA_InvokePatternId).QueryInterface(UIAutomationClient.IUIAutomationInvokePattern)
                        inv_pat.Invoke()
                        menu_triggered = True
                        logger.info("Triggered Save As via UIA File -> Save as menu item")
    except Exception as ex:
        logger.debug("UIA menu Save As trigger attempt: %s", ex)

    if not menu_triggered:
        logger.info("Dispatching Ctrl+Shift+S to HWND 0x%x for UI document save", target_hwnd)
        shortcut = parse_shortcut("Ctrl+Shift+S")
        dispatch_shortcut(shortcut, target_hwnd=target_hwnd)
        time.sleep(0.3)
        dispatch_shortcut(parse_shortcut("Ctrl+S"), target_hwnd=target_hwnd)
        time.sleep(0.3)

    # 5. Fast enum search for Save As dialog
    save_dialog_hwnd = 0
    deadline = time.time() + 6.0
    while time.time() < deadline:
        def enum_save_dlg(h: int, _: int) -> bool:
            nonlocal save_dialog_hwnd
            if user32.IsWindowVisible(h):
                length = user32.GetWindowTextLengthW(h)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buf, length + 1)
                    t = buf.value.lower()
                    if "save as" in t or t == "save":
                        save_dialog_hwnd = h
                        return False
            return True

        user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(enum_save_dlg), 0)
        if save_dialog_hwnd:
            break

        # Fallback keyboard accelerators if dialog not yet open
        if time.time() > (deadline - 3.0) and not save_dialog_hwnd:
            dispatch_shortcut(parse_shortcut("Alt+F"), target_hwnd=target_hwnd)
            time.sleep(0.2)
            dispatch_shortcut(parse_shortcut("A"), target_hwnd=target_hwnd)
            time.sleep(0.3)

        time.sleep(0.2)

    if save_dialog_hwnd:
        logger.info("Found Save dialog HWND 0x%x.", save_dialog_hwnd)
        user32.ShowWindow(save_dialog_hwnd, SW_RESTORE)
        force_foreground_activation(save_dialog_hwnd)
        time.sleep(0.2)

        # Set destination path into Save dialog via universal Windows Alt+N accelerator and clipboard paste
        from astrarun.interaction.clipboard import set_clipboard_text
        from astrarun.interaction.keyboard import type_text_into_active

        logger.info("Setting destination path in Save dialog HWND 0x%x via Alt+N", save_dialog_hwnd)
        dispatch_shortcut(parse_shortcut("Alt+N"), target_hwnd=save_dialog_hwnd)
        time.sleep(0.1)
        dispatch_shortcut(parse_shortcut("Ctrl+A"), target_hwnd=save_dialog_hwnd)
        time.sleep(0.05)
        if set_clipboard_text(str(dest_path)):
            dispatch_shortcut(parse_shortcut("Ctrl+V"), target_hwnd=save_dialog_hwnd)
        else:
            type_text_into_active(str(dest_path))
        time.sleep(0.15)

        # Confirm Save via Alt+S and Enter
        logger.info("Submitting Save dialog HWND 0x%x via Alt+S / Enter", save_dialog_hwnd)
        dispatch_shortcut(parse_shortcut("Alt+S"), target_hwnd=save_dialog_hwnd)
        time.sleep(0.1)
        dispatch_shortcut(parse_shortcut("Enter"), target_hwnd=save_dialog_hwnd)
        time.sleep(0.3)
        # Also post WM_COMMAND IDOK directly to dialog as standard Win32 confirmation
        user32.PostMessageW(save_dialog_hwnd, 0x0111, 1, 0)
        time.sleep(0.3)

        # Check if overwrite confirmation appeared
        time.sleep(0.5)
        conf_hwnd = None
        def find_conf(h: int, _: int) -> bool:
            nonlocal conf_hwnd
            if user32.IsWindowVisible(h) and h != save_dialog_hwnd:
                length = user32.GetWindowTextLengthW(h)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buf, length + 1)
                    t = buf.value.lower()
                    if "confirm" in t or "already exists" in t or "replace" in t:
                        conf_hwnd = h
                        return False
            return True

        user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)(find_conf), 0)
        if conf_hwnd:
            logger.info("Detected overwrite confirmation dialog HWND 0x%x, confirming...", conf_hwnd)
            yes_btn = _find_dialog_button(conf_hwnd, "yes")
            BM_CLICK = 0x00F5
            if yes_btn:
                user32.PostMessageW(yes_btn, BM_CLICK, 0, 0)
            else:
                user32.PostMessageW(conf_hwnd, 0x0111, 6, 0)  # IDYES
                dispatch_shortcut(parse_shortcut("Alt+Y"), target_hwnd=conf_hwnd)
                time.sleep(0.1)
                dispatch_shortcut(parse_shortcut("Enter"), target_hwnd=conf_hwnd)
            time.sleep(0.3)
    else:
        logger.warning("Save As dialog was not detected for window HWND 0x%x within timeout", target_hwnd)

    # 6. Verify result in environment: must exist AND have non-zero size
    file_verified = False
    v_deadline = time.time() + 4.0
    while time.time() < v_deadline:
        if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
            file_verified = True
            break
        time.sleep(0.2)

    latency = (time.perf_counter() - t0) * 1000.0

    if not file_verified:
        if os.path.exists(dest_path) and os.path.getsize(dest_path) == 0:
            return CapabilityResult.fail(
                capability="save_document_via_ui",
                message=f"UI Save operation created destination file '{dest_path}', but the file is 0 bytes (editor was empty).",
                error_code=CapabilityErrorCode.VERIFICATION_FAILED,
                latency_ms=latency,
            )
        return CapabilityResult.fail(
            capability="save_document_via_ui",
            message=f"UI Save operation dispatched, but destination file '{dest_path}' was not verified on disk.",
            error_code=CapabilityErrorCode.VERIFICATION_FAILED,
            latency_ms=latency,
        )

    # Check updated window title
    new_title = ""
    length = user32.GetWindowTextLengthW(target_hwnd)
    if length > 0:
        tbuf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(target_hwnd, tbuf, length + 1)
        new_title = tbuf.value

    return CapabilityResult.ok(
        capability="save_document_via_ui",
        message=f"Document successfully saved via application UI to '{dest_path}'.",
        data={
            "path": dest_path,
            "filename": os.path.basename(dest_path),
            "hwnd": target_hwnd,
            "window_title": new_title,
            "interaction_modality": "APPLICATION_UI",
            "file_size": os.path.getsize(dest_path),
        },
        context_updates=[
            {"type": "document_saved", "path": dest_path, "modality": "APPLICATION_UI"},
        ],
        latency_ms=latency,
    )


def _find_file_dialog_edit_control(dialog_hwnd: int) -> int:
    """Find the destination file name Edit control inside a common File Dialog."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    found_edit = 0
    CHILDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def enum_children(child: int, lparam: int) -> bool:
        nonlocal found_edit
        cls_buf = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(child, cls_buf, 128)
        if cls_buf.value.lower() == "edit":
            found_edit = child
            return False
        return True

    user32.EnumChildWindows(dialog_hwnd, CHILDENUMPROC(enum_children), 0)
    return found_edit


def _find_dialog_button(dialog_hwnd: int, button_text_substring: str) -> int:
    """Find a button child control with the matching text substring."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    found_btn = 0
    sub = button_text_substring.lower()
    CHILDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def enum_children(child: int, lparam: int) -> bool:
        nonlocal found_btn
        cls_buf = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(child, cls_buf, 128)
        if "button" in cls_buf.value.lower():
            length = user32.GetWindowTextLengthW(child)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(child, buf, length + 1)
                text = buf.value.replace("&", "").strip().lower()
                if sub in text:
                    found_btn = child
                    return False
        return True

    user32.EnumChildWindows(dialog_hwnd, CHILDENUMPROC(enum_children), 0)
    return found_btn
