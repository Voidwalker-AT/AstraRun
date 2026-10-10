"""Generic dialog and modal window discovery for AstraRun ComputerUse."""

from __future__ import annotations

import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

from astrarun.computer_use.hooks.desktop_attach import ensure_desktop_attached
from astrarun.computer_use.world.desktop_state import DialogObservation
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.computer_use.ui.dialogs")


class DialogDetector:
    """
    Generic discovery and interaction handler for Windows dialogs, modals, and message boxes.
    Detects standard Win32 dialogs (#32770), modern XAML popups, File Open/Save dialogs,
    and unhandled application error alerts.
    """

    @classmethod
    def detect_dialogs(
        cls,
        owner_hwnd: Optional[int] = None,
        task_id: Optional[str] = None,
    ) -> List[DialogObservation]:
        """
        Scan desktop for active dialogs and modal windows.
        If owner_hwnd is specified, filters for dialogs owned by that specific window.
        """
        if sys.platform != "win32":
            return []

        ensure_desktop_attached()

        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        GWL_STYLE = -16
        GWL_EXSTYLE = -20
        GW_OWNER = 4
        WS_POPUP = 0x80000000
        WS_EX_DLGMODALFRAME = 0x00000001

        dialogs: List[DialogObservation] = []

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def enum_cb(hwnd: int, lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True

            owner = user32.GetWindow(hwnd, GW_OWNER)
            if owner_hwnd is not None and owner != owner_hwnd and hwnd != owner_hwnd:
                return True

            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            cls_name = cls_buf.value

            length = user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value

            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

            # Heuristic for dialog:
            # 1. Native dialog class (#32770)
            # 2. Owned window with WS_POPUP or WS_EX_DLGMODALFRAME
            # 3. Known title keywords (Save As, Open, Error, Warning, Confirm)
            is_dialog_class = cls_name == "#32770"
            is_modal_popup = (owner != 0) and (bool(style & WS_POPUP) or bool(ex_style & WS_EX_DLGMODALFRAME))
            is_common_dialog = any(k in title.lower() for k in ["save as", "open", "cannot find", "confirm save", "error", "warning"])

            if is_dialog_class or is_modal_popup or is_common_dialog:
                # Classify type
                t_lower = title.lower()
                if "save as" in t_lower or "save" in t_lower:
                    d_type = "file_save"
                elif "open" in t_lower:
                    d_type = "file_open"
                elif any(k in t_lower for k in ["error", "cannot find", "failed", "warning"]):
                    d_type = "error"
                elif any(k in t_lower for k in ["confirm", "do you want", "save changes"]):
                    d_type = "confirmation"
                else:
                    d_type = "custom"

                # Discover child buttons and prompt text
                buttons, prompt = cls._inspect_dialog_children(hwnd)

                # Check Astra ownership if ledger is available
                astra_owned = False
                try:
                    from astrarun.tasks.resource_ledger import AstraResourceLedger
                    ledger = AstraResourceLedger.get_instance()
                    res = ledger.get_resource_for_hwnd(owner or hwnd)
                    if res:
                        astra_owned = True
                except Exception:
                    pass

                obs = DialogObservation(
                    hwnd=hwnd,
                    owner_hwnd=owner,
                    title=title,
                    dialog_class=cls_name,
                    dialog_type=d_type,
                    prompt_text=prompt,
                    buttons=buttons,
                    astra_owned=astra_owned,
                    task_id=task_id,
                    last_observed=time.time(),
                )
                dialogs.append(obs)

            return True

        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        return dialogs

    @classmethod
    def _inspect_dialog_children(cls, dialog_hwnd: int) -> Tuple[List[str], str]:
        """Inspect child controls of a dialog to extract button names and static prompt text."""
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        buttons: List[str] = []
        prompt_parts: List[str] = []

        CHILDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def child_cb(child_hwnd: int, lparam: int) -> bool:
            cls_buf = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(child_hwnd, cls_buf, 128)
            cls_name = cls_buf.value.lower()

            length = user32.GetWindowTextLengthW(child_hwnd)
            text = ""
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(child_hwnd, buf, length + 1)
                text = buf.value.strip()

            if "button" in cls_name and text:
                # Filter out accelerators like '&Save' -> 'Save'
                clean_btn = text.replace("&", "")
                buttons.append(clean_btn)
            elif "static" in cls_name and text:
                prompt_parts.append(text)

            return True

        user32.EnumChildWindows(dialog_hwnd, CHILDENUMPROC(child_cb), 0)
        prompt = "\n".join(prompt_parts)
        return buttons, prompt

    @classmethod
    def dismiss_dialog(cls, dialog_hwnd: int, button_preference: str = "cancel") -> bool:
        """
        Safely dismiss a dialog window.
        Attempts to click the preferred button (Cancel, Close, OK), or sends WM_CLOSE / ESC.
        """
        if sys.platform != "win32" or not dialog_hwnd:
            return False

        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        # 1. Search for preferred button child HWND
        target_btn_hwnd = 0
        pref = button_preference.lower()

        CHILDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def child_cb(child_hwnd: int, lparam: int) -> bool:
            nonlocal target_btn_hwnd
            cls_buf = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(child_hwnd, cls_buf, 128)
            if "button" in cls_buf.value.lower():
                length = user32.GetWindowTextLengthW(child_hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(child_hwnd, buf, length + 1)
                    text = buf.value.replace("&", "").strip().lower()
                    if pref in text:
                        target_btn_hwnd = child_hwnd
                        return False
            return True

        user32.EnumChildWindows(dialog_hwnd, CHILDENUMPROC(child_cb), 0)

        BM_CLICK = 0x00F5
        WM_CLOSE = 0x0010
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        VK_ESCAPE = 0x1B

        if target_btn_hwnd:
            logger.info("Dismissing dialog 0x%x via BM_CLICK on button 0x%x", dialog_hwnd, target_btn_hwnd)
            user32.SendMessageW(target_btn_hwnd, BM_CLICK, 0, 0)
            time.sleep(0.2)
            if not user32.IsWindow(dialog_hwnd):
                return True

        # 2. Try sending Escape keystroke to dialog
        logger.info("Dismissing dialog 0x%x via Escape key", dialog_hwnd)
        user32.PostMessageW(dialog_hwnd, WM_KEYDOWN, VK_ESCAPE, 0)
        user32.PostMessageW(dialog_hwnd, WM_KEYUP, VK_ESCAPE, 0)
        time.sleep(0.2)
        if not user32.IsWindow(dialog_hwnd):
            return True

        # 3. Post WM_CLOSE
        logger.info("Dismissing dialog 0x%x via WM_CLOSE", dialog_hwnd)
        user32.PostMessageW(dialog_hwnd, WM_CLOSE, 0, 0)
        time.sleep(0.2)
        return not bool(user32.IsWindow(dialog_hwnd))
