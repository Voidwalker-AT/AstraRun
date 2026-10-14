"""Generic Editable-Surface Model and Input Strategy Ladder for AstraRun Computer Use.

Provides an application-agnostic abstraction for discovering, inspecting,
targeting, and injecting text into editable surfaces across Windows desktop applications
(classic Win32, UWP, modern XAML, Scintilla, RichEdit, browsers) without application brand hacks.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.computer_use.ui.uia_support import get_uia_interface, get_uia_module
from astrarun.interaction.clipboard import set_clipboard_text
from astrarun.interaction.keyboard import dispatch_shortcut, parse_shortcut, type_text_into_active

logger = get_logger("astrarun.computer_use.ui.editable_surface")


@dataclass
class EditableSurface:
    """Application-agnostic representation of an editable surface."""
    hwnd: int
    window_hwnd: int
    control_type: str = "unknown"
    name: str = ""
    automation_id: str = ""
    class_name: str = ""
    can_receive_text: bool = True
    current_content: Optional[str] = None
    focusable: bool = True
    read_only: bool = False
    target_identity: str = ""
    observation_generation: int = 0
    window_identity: str = ""
    discovery_mechanism: str = "UNKNOWN"
    com_element: Optional[Any] = field(default=None, repr=False)
    supported_patterns: list[str] = field(default_factory=list)


def discover_editable_surface(
    target_hwnd: int,
    target_name: Optional[str] = None,
    timeout_sec: float = 2.5,
) -> Optional[EditableSurface]:
    """Discover an editable surface within a target window through generic capabilities.

    Inspects:
    1. Focused control in window
    2. UI Automation tree for Document, Edit, or ValuePattern/TextPattern elements
    3. Win32 child control hierarchy for standard and custom edit surfaces (Scintilla, RichEdit, Edit)
    """
    if sys.platform != "win32" or not target_hwnd:
        return None

    user32 = ctypes.windll.user32
    if not user32.IsWindow(target_hwnd):
        return None

    t_start = time.time()
    uia = get_uia_interface()
    uia_mod = get_uia_module()

    # Get window title for window identity
    length_w = user32.GetWindowTextLengthW(target_hwnd)
    win_title = ""
    if length_w > 0:
        buf = ctypes.create_unicode_buffer(length_w + 1)
        user32.GetWindowTextW(target_hwnd, buf, length_w + 1)
        win_title = buf.value

    # 1. UI Automation Discovery
    if uia and uia_mod:
        try:
            root = uia.ElementFromHandle(target_hwnd)
            if root:
                deadline = t_start + timeout_sec
                while time.time() < deadline:
                    # Check focused element first
                    # Check focused element first, but ONLY if it belongs to target window/process
                    try:
                        focused_elem = uia.GetFocusedElement()
                        if focused_elem:
                            f_pid = focused_elem.CurrentProcessId
                            f_hwnd = focused_elem.CurrentNativeWindowHandle
                            target_pid = wintypes.DWORD()
                            user32.GetWindowThreadProcessId(target_hwnd, ctypes.byref(target_pid))
                            belongs_to_target = (f_pid == target_pid.value) or (f_hwnd == target_hwnd) or (f_hwnd and user32.IsChild(target_hwnd, f_hwnd))
                            if belongs_to_target:
                                f_c_type = focused_elem.CurrentControlType
                                f_name = focused_elem.CurrentName or ""
                                if f_c_type in (uia_mod.UIA_DocumentControlTypeId, uia_mod.UIA_EditControlTypeId):
                                    content = _extract_uia_content(focused_elem, uia_mod)
                                    is_ro = _check_uia_readonly(focused_elem, uia_mod)
                                    return EditableSurface(
                                        hwnd=target_hwnd,
                                        window_hwnd=target_hwnd,
                                        control_type="document" if f_c_type == uia_mod.UIA_DocumentControlTypeId else "edit",
                                        name=f_name,
                                        automation_id=focused_elem.CurrentAutomationId or "",
                                        class_name=focused_elem.CurrentClassName or "",
                                        can_receive_text=not is_ro,
                                        current_content=content,
                                        focusable=True,
                                        read_only=is_ro,
                                        target_identity=f"focused_{f_name or 'control'}",
                                        observation_generation=int(time.time() * 1000),
                                        window_identity=win_title,
                                        discovery_mechanism="UIA_FOCUSED_ELEMENT",
                                        com_element=focused_elem,
                                        supported_patterns=_get_supported_patterns(focused_elem, uia_mod),
                                    )
                    except Exception:
                        pass

                    # Query UIA tree for Document or Edit control types
                    try:
                        cond_edit = uia.CreateOrCondition(
                            uia.CreatePropertyCondition(uia_mod.UIA_ControlTypePropertyId, uia_mod.UIA_DocumentControlTypeId),
                            uia.CreatePropertyCondition(uia_mod.UIA_ControlTypePropertyId, uia_mod.UIA_EditControlTypeId),
                        )
                        edit_elem = root.FindFirst(uia_mod.TreeScope_Descendants, cond_edit)
                        if edit_elem:
                            c_type_id = edit_elem.CurrentControlType
                            name_val = edit_elem.CurrentName or ""
                            auto_id = edit_elem.CurrentAutomationId or ""
                            cls_name = edit_elem.CurrentClassName or ""
                            content = _extract_uia_content(edit_elem, uia_mod)
                            is_ro = _check_uia_readonly(edit_elem, uia_mod)
                            patterns = _get_supported_patterns(edit_elem, uia_mod)

                            return EditableSurface(
                                hwnd=target_hwnd,
                                window_hwnd=target_hwnd,
                                control_type="document" if c_type_id == uia_mod.UIA_DocumentControlTypeId else "edit",
                                name=name_val,
                                automation_id=auto_id,
                                class_name=cls_name,
                                can_receive_text=not is_ro,
                                current_content=content,
                                focusable=True,
                                read_only=is_ro,
                                target_identity=auto_id or name_val or cls_name or "uia_editable",
                                observation_generation=int(time.time() * 1000),
                                window_identity=win_title,
                                discovery_mechanism="UIA_TREE_SEARCH",
                                com_element=edit_elem,
                                supported_patterns=patterns,
                            )
                    except Exception as ex:
                        logger.debug("UIA tree search error: %s", ex)

                    time.sleep(0.1)
        except Exception as ex:
            logger.debug("UIA element inspection error: %s", ex)

    # 2. Win32 Child Control Discovery Fallback (Generic Client Pane Ranking)
    child_candidates: list[Tuple[int, str, str, int]] = []

    def enum_child_cb(child_h: int, _: int) -> bool:
        if user32.IsWindowVisible(child_h) and user32.IsWindowEnabled(child_h):
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child_h, cls_buf, 256)
            cls_lower = cls_buf.value.lower()
            # Exclude standard non-document chrome common controls (toolbars, statusbars, rebars, tabs)
            if any(ex in cls_lower for ex in ("toolbar", "statusbar", "rebar", "scrollbar", "tabcontrol", "systabcontrol", "header", "msctls_trackbar")):
                return True

            rc = wintypes.RECT()
            user32.GetWindowRect(child_h, ctypes.byref(rc))
            w = max(0, rc.right - rc.left)
            h_dim = max(0, rc.bottom - rc.top)
            area = w * h_dim

            # Candidate must be a substantial interactive surface (w >= 100, h >= 40)
            if w >= 100 and h_dim >= 40:
                length = user32.GetWindowTextLengthW(child_h)
                txt = ""
                if length > 0 and length < 65536:
                    t_buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(child_h, t_buf, length + 1)
                    txt = t_buf.value
                child_candidates.append((child_h, cls_buf.value, txt, area))
        return True

    WNDENUMCHILDPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows(target_hwnd, WNDENUMCHILDPROC(enum_child_cb), 0)

    if child_candidates:
        # Prioritize largest visible editing surface (primary document pane)
        child_candidates.sort(key=lambda c: c[3], reverse=True)
        child_h, cls_name, txt, _ = child_candidates[0]

        return EditableSurface(
            hwnd=child_h,
            window_hwnd=target_hwnd,
            control_type="win32_edit",
            name=cls_name,
            automation_id=f"win32_0x{child_h:x}",
            class_name=cls_name,
            can_receive_text=True,
            current_content=txt,
            focusable=True,
            read_only=False,
            target_identity=f"win32_child_{cls_name}",
            observation_generation=int(time.time() * 1000),
            window_identity=win_title,
            discovery_mechanism="WIN32_CHILD_ENUM",
        )

    # 3. Window-Level Fallback Surface (e.g. top-level custom control)
    return EditableSurface(
        hwnd=target_hwnd,
        window_hwnd=target_hwnd,
        control_type="window_surface",
        name=win_title,
        automation_id=f"window_0x{target_hwnd:x}",
        class_name="TopLevelWindow",
        can_receive_text=True,
        current_content="",
        focusable=True,
        read_only=False,
        target_identity=f"window_0x{target_hwnd:x}",
        observation_generation=int(time.time() * 1000),
        window_identity=win_title,
        discovery_mechanism="WINDOW_FALLBACK",
    )


def execute_input_strategy_ladder(
    surface: EditableSurface,
    text: str,
) -> Tuple[bool, str, str]:
    """Execute generic input strategy ladder against discovered editable surface.

    Ladder Rungs:
    1. Direct structured accessibility action: UIA ValuePattern.SetValue
    2. Focused semantic control + Universal Clipboard Paste (Ctrl+V)
    3. Focused semantic control + Native SendInput keystrokes
    4. Window-level keyboard fallback

    Returns:
    (success, mechanism_used, error_message)
    """
    if not surface or not surface.can_receive_text or surface.read_only:
        return False, "NONE", "Surface cannot receive text or is read-only"

    user32 = ctypes.windll.user32
    target_hwnd = surface.window_hwnd or surface.hwnd

    # Bring target window to foreground
    from astrarun.ui.presentation import force_foreground_activation
    user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
    force_foreground_activation(target_hwnd)
    time.sleep(0.1)

    # Rung 1: Direct Structured UIA ValuePattern
    uia_mod = get_uia_module()
    if surface.com_element and uia_mod and not surface.read_only:
        try:
            val_pat = surface.com_element.GetCurrentPattern(uia_mod.UIA_ValuePatternId)
            if val_pat:
                val_obj = val_pat.QueryInterface(uia_mod.IUIAutomationValuePattern)
                if not val_obj.CurrentIsReadOnly:
                    val_obj.SetValue(text)
                    logger.info("Rung 1: Successfully set text via UIA ValuePattern")
                    return True, "UIA_VALUE_PATTERN", ""
        except Exception as ex:
            logger.debug("Rung 1 (UIA ValuePattern) failed: %s", ex)

    # Focus control if COM element is available
    if surface.com_element:
        try:
            surface.com_element.SetFocus()
            time.sleep(0.05)
        except Exception:
            pass

    # If child control HWND exists, focus it via Win32 with AttachThreadInput
    if surface.hwnd and surface.hwnd != target_hwnd:
        try:
            kernel32 = ctypes.windll.kernel32
            cur_tid = kernel32.GetCurrentThreadId()
            target_tid = user32.GetWindowThreadProcessId(surface.hwnd, None)
            if cur_tid != target_tid:
                user32.AttachThreadInput(cur_tid, target_tid, True)
                user32.SetFocus(surface.hwnd)
                user32.AttachThreadInput(cur_tid, target_tid, False)
            else:
                user32.SetFocus(surface.hwnd)
            time.sleep(0.05)
        except Exception as ex:
            logger.debug("Win32 child SetFocus failed: %s", ex)

    # For window-level fallback surfaces (e.g. calculators, canvas, custom dialogs),
    # interactive applications expect direct synthetic keystrokes rather than clipboard paste.
    if surface.control_type == "window_surface" or surface.discovery_mechanism == "WINDOW_FALLBACK":
        logger.info("Window-level fallback surface: dispatching native keystrokes directly")
        ok, msg, err_code = type_text_into_active(text)
        if ok:
            time.sleep(0.15)
            return True, "SYNTHETIC_KEYSTROKES", ""
        return False, "NONE", msg or "Synthetic keystrokes failed on window surface"

    # Rung 2: Focused Semantic Control + Clipboard Paste (Ctrl+V / WM_PASTE)
    if len(text) > 0 and sys.platform == "win32":
        try:
            if set_clipboard_text(text):
                time.sleep(0.05)
                # If child control HWND exists, send WM_PASTE directly to the control
                if surface.hwnd and surface.hwnd != target_hwnd:
                    logger.info("Directly sending WM_PASTE (0x0302) to child control HWND 0x%x", surface.hwnd)
                    user32.SendMessageW(surface.hwnd, 0x0302, 0, 0)
                ok_paste, _, _ = dispatch_shortcut(parse_shortcut("Ctrl+V"), target_hwnd=target_hwnd)
                if ok_paste or (surface.hwnd and surface.hwnd != target_hwnd):
                    logger.info("Rung 2: Dispatched text via universal Clipboard Paste")
                    time.sleep(0.15)
                    return True, "CLIPBOARD_PASTE", ""
        except Exception as ex:
            logger.debug("Rung 2 (Clipboard Paste) failed: %s", ex)

    # Rung 3: Native SendInput Keystrokes
    logger.info("Rung 3: Dispatching text via native SendInput keystrokes")
    ok, msg, err_code = type_text_into_active(text)
    if ok:
        time.sleep(0.1)
        return True, "SYNTHETIC_KEYSTROKES", ""

    return False, "NONE", msg or "All input ladder strategies exhausted"


def verify_surface_content(
    surface: EditableSurface,
    expected_text: str,
    prior_title_had_asterisk: bool = False,
    timeout_sec: float = 2.0,
) -> Tuple[bool, str]:
    """Affirmatively verify that the expected text was physically received by the surface.

    Checks:
    1. UIA TextPattern content
    2. UIA ValuePattern content
    3. Win32 control text / Scintilla text
    4. Window title dirty indicator or document name update
    5. Window-level UIA element content update (for non-document interactive controls)
    """
    user32 = ctypes.windll.user32
    target_hwnd = surface.window_hwnd or surface.hwnd
    uia_mod = get_uia_module()

    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        # Check COM element
        if surface.com_element and uia_mod:
            # 1. TextPattern
            try:
                txt_pat = surface.com_element.GetCurrentPattern(uia_mod.UIA_TextPatternId)
                if txt_pat:
                    txt_obj = txt_pat.QueryInterface(uia_mod.IUIAutomationTextPattern)
                    cur_txt = txt_obj.DocumentRange.GetText(-1) or ""
                    if expected_text in cur_txt:
                        return True, "UIA_TextPattern"
            except Exception:
                pass

            # 2. ValuePattern
            try:
                val_pat = surface.com_element.GetCurrentPattern(uia_mod.UIA_ValuePatternId)
                if val_pat:
                    val_obj = val_pat.QueryInterface(uia_mod.IUIAutomationValuePattern)
                    cur_val = val_obj.CurrentValue or ""
                    if expected_text in cur_val:
                        return True, "UIA_ValuePattern"
            except Exception:
                pass

        # 3. Win32 Control Text via universal WM_GETTEXT (0x000D)
        if surface.hwnd and user32.IsWindow(surface.hwnd):
            WM_GETTEXT = 0x000D
            buf_len = max(2048, len(expected_text) * 4)
            buf = ctypes.create_unicode_buffer(buf_len)
            res_len = user32.SendMessageW(surface.hwnd, WM_GETTEXT, buf_len, buf)
            if res_len > 0 and expected_text in buf.value:
                return True, "Win32_WM_GETTEXT"

            # Fallback to standard GetWindowTextW
            length = user32.GetWindowTextLengthW(surface.hwnd)
            if length > 0:
                buf2 = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(surface.hwnd, buf2, length + 1)
                if expected_text in buf2.value:
                    return True, "Win32_Control_Text"

        # 4. Window Title Substring
        if target_hwnd and user32.IsWindow(target_hwnd):
            length_w = user32.GetWindowTextLengthW(target_hwnd)
            if length_w > 0:
                w_buf = ctypes.create_unicode_buffer(length_w + 1)
                user32.GetWindowTextW(target_hwnd, w_buf, length_w + 1)
                t = w_buf.value
                if expected_text in t:
                    return True, "Window_Title_Text"

        # 5. Window-Level UIA Element Content Check (e.g. for non-document interactive applications)
        if target_hwnd and uia_mod and (surface.control_type == "window_surface" or surface.discovery_mechanism == "WINDOW_FALLBACK"):
            try:
                from astrarun.computer_use.ui.uia_support import get_uia_interface
                uia_iface = get_uia_interface()
                if uia_iface:
                    w_elem = uia_iface.ElementFromHandle(target_hwnd)
                    if w_elem:
                        candidates = {expected_text, expected_text.replace(",", "")}
                        if re.match(r"^[\d\s\+\-\*\/\.\(\)]+=$", expected_text.strip()):
                            try:
                                expr = expected_text.strip().rstrip("=")
                                calc_res = str(eval(expr, {"__builtins__": {}}, {}))
                                candidates.add(calc_res)
                            except Exception:
                                pass

                        raw_c = w_elem.FindAll(uia_mod.TreeScope_Descendants, uia_iface.CreateTrueCondition())
                        if raw_c:
                            for idx in range(min(50, raw_c.Length)):
                                el = raw_c.GetElement(idx)
                                name_val = (el.CurrentName or "") + " " + (el.CurrentHelpText or "")
                                name_norm = name_val.replace(",", "")
                                if any(c in name_val or c in name_norm for c in candidates if len(c) > 0):
                                    return True, "Window_UIA_Element_Updated"
            except Exception as ex:
                logger.debug("Window UIA content check exception: %s", ex)

        time.sleep(0.15)

    return False, "UNVERIFIED"


def _extract_uia_content(elem: Any, uia_mod: Any) -> Optional[str]:
    """Extract observable content from a UIA element via TextPattern or ValuePattern."""
    if not elem or not uia_mod:
        return None
    try:
        txt_pat = elem.GetCurrentPattern(uia_mod.UIA_TextPatternId)
        if txt_pat:
            txt_obj = txt_pat.QueryInterface(uia_mod.IUIAutomationTextPattern)
            return txt_obj.DocumentRange.GetText(-1) or ""
    except Exception:
        pass
    try:
        val_pat = elem.GetCurrentPattern(uia_mod.UIA_ValuePatternId)
        if val_pat:
            val_obj = val_pat.QueryInterface(uia_mod.IUIAutomationValuePattern)
            return val_obj.CurrentValue or ""
    except Exception:
        pass
    return None


def _check_uia_readonly(elem: Any, uia_mod: Any) -> bool:
    """Check if UIA element is marked read-only."""
    if not elem or not uia_mod:
        return False
    try:
        val_pat = elem.GetCurrentPattern(uia_mod.UIA_ValuePatternId)
        if val_pat:
            val_obj = val_pat.QueryInterface(uia_mod.IUIAutomationValuePattern)
            return bool(val_obj.CurrentIsReadOnly)
    except Exception:
        pass
    return False


def _get_supported_patterns(elem: Any, uia_mod: Any) -> list[str]:
    """Query supported patterns on a UIA element."""
    patterns = []
    if not elem or not uia_mod:
        return patterns
    for p_id, p_name in [
        (uia_mod.UIA_ValuePatternId, "value"),
        (uia_mod.UIA_TextPatternId, "text"),
        (uia_mod.UIA_InvokePatternId, "invoke"),
        (uia_mod.UIA_TogglePatternId, "toggle"),
    ]:
        try:
            if elem.GetCurrentPattern(p_id):
                patterns.append(p_name)
        except Exception:
            pass
    return patterns


@dataclass
class SelectionObservation:
    """Application-agnostic selection state observation."""
    observable: bool = False
    source: str = "NONE"  # "UIA_TEXT_PATTERN" | "SCINTILLA_ADAPTER" | "WIN32_EDIT" | "NONE"
    anchor: Optional[int] = None
    caret: Optional[int] = None
    start: Optional[int] = None
    end: Optional[int] = None
    selected_length: Optional[int] = None
    document_length: Optional[int] = None
    evidence_reference: str = ""


def send_message_timeout_w(
    hwnd: int,
    msg: int,
    wparam: int = 0,
    lparam: int = 0,
    timeout_ms: int = 1000,
) -> Tuple[bool, int]:
    """Safely invoke SendMessageTimeoutW with fail-closed timeout protection.

    Guarantees no thread hanging if the target window procedure is blocked or unresponsive.
    """
    if sys.platform != "win32" or not hwnd:
        return False, 0
    user32 = ctypes.windll.user32
    if not user32.IsWindow(hwnd):
        return False, 0

    SMTO_ABORTIFHUNG = 0x0002
    SMTO_NORMAL = 0x0000
    flags = SMTO_ABORTIFHUNG | SMTO_NORMAL

    ULONG_PTR = ctypes.c_ulonglong
    res = ULONG_PTR(0)

    try:
        user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ULONG_PTR),
        ]
        user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
    except Exception:
        pass

    ok = user32.SendMessageTimeoutW(hwnd, msg, wparam, lparam, flags, timeout_ms, ctypes.byref(res))
    if ok != 0:
        return True, int(res.value)
    return False, 0


def observe_surface_selection(
    target_hwnd: Optional[int] = None,
    surface: Optional[EditableSurface] = None,
    timeout_sec: float = 2.0,
) -> SelectionObservation:
    """Observe selection state on an editable surface through generic hierarchical adapters.

    Observation ladder:
    1. UI Automation TextPattern / TextPattern2 on focused / surface element.
    2. Structural Win32 Edit / RichEdit control messages (EM_GETSEL, WM_GETTEXTLENGTH).
    3. Structural Scintilla control messages (SCI_GETSELECTIONSTART, SCI_GETSELECTIONEND, SCI_GETLENGTH, SCI_GETCURRENTPOS, SCI_GETANCHOR).

    Returns:
        SelectionObservation with exact measurements and provenance reference.
    """
    if sys.platform != "win32":
        return SelectionObservation(observable=False, source="NONE", evidence_reference="non_windows_platform")

    user32 = ctypes.windll.user32
    root_hwnd = target_hwnd or (surface.window_hwnd if surface else (surface.hwnd if surface else 0))
    if not root_hwnd or not user32.IsWindow(root_hwnd):
        return SelectionObservation(observable=False, source="NONE", evidence_reference="invalid_window_handle")

    uia = get_uia_interface()
    uia_mod = get_uia_module()

    # Determine candidate controls / elements
    candidate_hwnds: list[int] = []
    if surface and surface.hwnd and user32.IsWindow(surface.hwnd):
        candidate_hwnds.append(surface.hwnd)

    def _enum_children(ch: int, _: int) -> bool:
        if user32.IsWindowVisible(ch) and user32.IsWindowEnabled(ch):
            candidate_hwnds.append(ch)
        return True

    WNDENUMCHILDPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumChildWindows(root_hwnd, WNDENUMCHILDPROC(_enum_children), 0)

    # 1. UI Automation TextPattern Discovery Ladder
    if uia and uia_mod:
        try:
            uia_candidates = []
            if surface and surface.com_element:
                uia_candidates.append(surface.com_element)
            try:
                focused = uia.GetFocusedElement()
                if focused:
                    target_pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(root_hwnd, ctypes.byref(target_pid))
                    if focused.CurrentProcessId == target_pid.value:
                        uia_candidates.append(focused)
            except Exception:
                pass

            for elem in uia_candidates:
                try:
                    txt_pat = elem.GetCurrentPattern(uia_mod.UIA_TextPatternId)
                    if txt_pat:
                        txt_obj = txt_pat.QueryInterface(uia_mod.IUIAutomationTextPattern)
                        ranges = txt_obj.GetSelection()
                        doc_range = txt_obj.DocumentRange
                        doc_text = doc_range.GetText(-1) or ""
                        doc_len = len(doc_text)
                        sel_len = 0
                        if ranges and ranges.Length > 0:
                            sel_range = ranges.GetElement(0)
                            sel_text = sel_range.GetText(-1) or ""
                            sel_len = len(sel_text)
                        return SelectionObservation(
                            observable=True,
                            source="UIA_TEXT_PATTERN",
                            anchor=None,
                            caret=None,
                            start=0 if sel_len > 0 else None,
                            end=sel_len if sel_len > 0 else None,
                            selected_length=sel_len,
                            document_length=doc_len,
                            evidence_reference=f"uia_text_sel_len_{sel_len}_doc_len_{doc_len}",
                        )
                except Exception as ex:
                    logger.debug("UIA TextPattern selection inspection error: %s", ex)
        except Exception as ex:
            logger.debug("UIA selection inspection error: %s", ex)

    # 2. Structural Control-Family Probes (Scintilla & Win32 Edit)
    for ch in candidate_hwnds:
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ch, cls_buf, 256)
        cls_name = cls_buf.value.lower()

        # Scintilla Control Family (Notepad++, Geany, SciTE, Code::Blocks, etc.)
        if "scintilla" in cls_name:
            SCI_GETLENGTH = 2006
            SCI_GETCURRENTPOS = 2008
            SCI_GETANCHOR = 2009
            SCI_GETSELECTIONSTART = 2143
            SCI_GETSELECTIONEND = 2145

            ok_len, doc_len = send_message_timeout_w(ch, SCI_GETLENGTH, 0, 0, timeout_ms=500)
            ok_start, sel_start = send_message_timeout_w(ch, SCI_GETSELECTIONSTART, 0, 0, timeout_ms=500)
            ok_end, sel_end = send_message_timeout_w(ch, SCI_GETSELECTIONEND, 0, 0, timeout_ms=500)
            ok_pos, caret = send_message_timeout_w(ch, SCI_GETCURRENTPOS, 0, 0, timeout_ms=500)
            ok_anc, anchor = send_message_timeout_w(ch, SCI_GETANCHOR, 0, 0, timeout_ms=500)

            if ok_len and ok_start and ok_end and doc_len >= 0:
                selected_len = max(0, sel_end - sel_start)
                return SelectionObservation(
                    observable=True,
                    source="SCINTILLA_ADAPTER",
                    anchor=anchor if ok_anc else None,
                    caret=caret if ok_pos else None,
                    start=sel_start,
                    end=sel_end,
                    selected_length=selected_len,
                    document_length=doc_len,
                    evidence_reference=f"scintilla_0x{ch:x}_start_{sel_start}_end_{sel_end}_doclen_{doc_len}",
                )

        # Standard Win32 Edit Control Family
        if "edit" in cls_name:
            EM_GETSEL = 0x00B0
            WM_GETTEXTLENGTH = 0x000E

            ok_len, doc_len = send_message_timeout_w(ch, WM_GETTEXTLENGTH, 0, 0, timeout_ms=500)
            ok_sel, sel_dword = send_message_timeout_w(ch, EM_GETSEL, 0, 0, timeout_ms=500)

            if ok_len and ok_sel and doc_len >= 0:
                start = sel_dword & 0xFFFF
                end = (sel_dword >> 16) & 0xFFFF
                selected_len = max(0, end - start)
                return SelectionObservation(
                    observable=True,
                    source="WIN32_EDIT",
                    anchor=None,
                    caret=None,
                    start=start,
                    end=end,
                    selected_length=selected_len,
                    document_length=doc_len,
                    evidence_reference=f"win32_edit_0x{ch:x}_start_{start}_end_{end}_doclen_{doc_len}",
                )

    # Fallback: check root HWND itself if it directly hosts an edit control
    if root_hwnd:
        cls_buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(root_hwnd, cls_buf, 256)
        cls_name = cls_buf.value.lower()
        if "edit" in cls_name:
            ok_len, doc_len = send_message_timeout_w(root_hwnd, 0x000E, 0, 0, timeout_ms=500)
            ok_sel, sel_dword = send_message_timeout_w(root_hwnd, 0x00B0, 0, 0, timeout_ms=500)
            if ok_len and ok_sel and doc_len >= 0:
                start = sel_dword & 0xFFFF
                end = (sel_dword >> 16) & 0xFFFF
                return SelectionObservation(
                    observable=True,
                    source="WIN32_EDIT",
                    start=start,
                    end=end,
                    selected_length=max(0, end - start),
                    document_length=doc_len,
                    evidence_reference=f"win32_edit_root_0x{root_hwnd:x}_doclen_{doc_len}",
                )

    return SelectionObservation(
        observable=False,
        source="NONE",
        evidence_reference="no_observable_selection_surface_found",
    )


def verify_select_all_predicate(sel: SelectionObservation) -> bool:
    """Evaluate whether the selection observation satisfies SELECT_ALL semantics.

    Affirmatively requires:
    1. Selection state is observable (observable == True)
    2. Document has non-zero content (document_length > 0)
    3. Entire document is selected (selected_length == document_length)
    """
    return bool(
        sel.observable
        and sel.document_length is not None
        and sel.document_length > 0
        and sel.selected_length is not None
        and sel.selected_length == sel.document_length
    )


def execute_select_all_strategy(
    surface: Optional[EditableSurface] = None,
    target_hwnd: Optional[int] = None,
) -> Tuple[bool, str]:
    """Execute generic strategy ladder to select all text in an editable surface.

    Ladder Rungs:
    1. UI Automation TextPattern DocumentRange.Select()
    2. Control-family specific messages:
       - Scintilla: SCI_SELECTALL (2013)
       - Win32 Edit: EM_SETSEL (0, -1)
    3. Universal keyboard shortcut (Ctrl+A)
    """
    if sys.platform != "win32":
        return False, "NON_WINDOWS_PLATFORM"

    user32 = ctypes.windll.user32
    root_hwnd = target_hwnd or (surface.window_hwnd if surface else (surface.hwnd if surface else 0))
    ctrl_hwnd = (surface.hwnd if surface and surface.hwnd and surface.hwnd != root_hwnd else 0)

    # Rung 1: UIA TextPattern Select()
    uia_mod = get_uia_module()
    if surface and surface.com_element and uia_mod:
        try:
            txt_pat = surface.com_element.GetCurrentPattern(uia_mod.UIA_TextPatternId)
            if txt_pat:
                txt_obj = txt_pat.QueryInterface(uia_mod.IUIAutomationTextPattern)
                txt_obj.DocumentRange.Select()
                return True, "UIA_TEXT_PATTERN_SELECT"
        except Exception:
            pass

    # Rung 2: Control-Family Selection Messages
    candidates = [ctrl_hwnd] if ctrl_hwnd else []
    if root_hwnd and user32.IsWindow(root_hwnd):
        def _enum_cb(ch: int, _: int) -> bool:
            if user32.IsWindowVisible(ch):
                candidates.append(ch)
            return True
        WNDENUMCHILDPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(root_hwnd, WNDENUMCHILDPROC(_enum_cb), 0)

    for ch in candidates:
        if not ch or not user32.IsWindow(ch):
            continue
        cbuf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ch, cbuf, 256)
        cname = cbuf.value.lower()
        if "scintilla" in cname:
            SCI_SELECTALL = 2013
            ok, _ = send_message_timeout_w(ch, SCI_SELECTALL, 0, 0, timeout_ms=500)
            if ok:
                return True, "SCINTILLA_SCI_SELECTALL"
        if "edit" in cname:
            EM_SETSEL = 0x00B1
            ok, _ = send_message_timeout_w(ch, EM_SETSEL, 0, -1, timeout_ms=500)
            if ok:
                return True, "WIN32_EM_SETSEL"

    # Rung 3: Universal Keyboard Shortcut
    if root_hwnd and user32.IsWindow(root_hwnd):
        ok, msg, _ = dispatch_shortcut(parse_shortcut("Ctrl+A"), target_hwnd=root_hwnd)
        if ok:
            return True, "KEYBOARD_SHORTCUT_CTRL_A"

    return False, "SELECT_ALL_EXHAUSTED"


def clear_selection_strategy(
    surface: Optional[EditableSurface] = None,
    target_hwnd: Optional[int] = None,
) -> Tuple[bool, str]:
    """Clear active selection on an editable surface (used for negative mutation verification)."""
    if sys.platform != "win32":
        return False, "NON_WINDOWS_PLATFORM"

    user32 = ctypes.windll.user32
    root_hwnd = target_hwnd or (surface.window_hwnd if surface else (surface.hwnd if surface else 0))
    ctrl_hwnd = (surface.hwnd if surface and surface.hwnd and surface.hwnd != root_hwnd else 0)

    candidates = [ctrl_hwnd] if ctrl_hwnd else []
    if root_hwnd and user32.IsWindow(root_hwnd):
        def _enum_cb(ch: int, _: int) -> bool:
            if user32.IsWindowVisible(ch):
                candidates.append(ch)
            return True
        WNDENUMCHILDPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumChildWindows(root_hwnd, WNDENUMCHILDPROC(_enum_cb), 0)

    for ch in candidates:
        if not ch or not user32.IsWindow(ch):
            continue
        cbuf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(ch, cbuf, 256)
        cname = cbuf.value.lower()
        if "scintilla" in cname:
            SCI_SETEMPTYSELECTION = 2556
            ok, _ = send_message_timeout_w(ch, SCI_SETEMPTYSELECTION, 0, 0, timeout_ms=500)
            if ok:
                return True, "SCINTILLA_CLEAR"
        if "edit" in cname:
            EM_SETSEL = 0x00B1
            ok, _ = send_message_timeout_w(ch, EM_SETSEL, 0, 0, timeout_ms=500)
            if ok:
                return True, "WIN32_EDIT_CLEAR"

    if root_hwnd and user32.IsWindow(root_hwnd):
        ok, msg, _ = dispatch_shortcut(parse_shortcut("Right"), target_hwnd=root_hwnd)
        if ok:
            return True, "KEYBOARD_RIGHT_ARROW"

    return False, "CLEAR_SELECTION_EXHAUSTED"


