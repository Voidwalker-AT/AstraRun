"""Bounded UI tree traversal and element discovery using Microsoft UI Automation."""

from __future__ import annotations

import sys
import time
from typing import List, Optional

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult
from astrarun.core.logging import get_logger
from astrarun.interaction.models import ControlPattern, ControlType, UIElementRef
from astrarun.interaction.policy import is_simulated_interaction_validation, validate_interaction_target

logger = get_logger("astrarun.interaction.discovery")


def _ensure_desktop_attached() -> None:
    """Ensure current thread is attached to the interactive Default desktop if needed."""
    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            # Check desktop name
            h_desk = user32.GetThreadDesktop(ctypes.windll.kernel32.GetCurrentThreadId())
            buf_desk = ctypes.create_unicode_buffer(256)
            user32.GetUserObjectInformationW(h_desk, 2, buf_desk, 256, None)
            if buf_desk.value.lower() != "default":
                h_default = user32.OpenDesktopW("Default", 0, False, 0x01FF)
                if h_default:
                    user32.SetThreadDesktop(h_default)
        except Exception as e:
            logger.debug("Desktop attachment check failed or not required: %s", e)


def _get_simulated_elements(hwnd: int) -> list[UIElementRef]:
    """Provide deterministic mock UI elements for headless testing and benchmarking."""
    return [
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_save",
            name="Save",
            class_name="QPushButton",
            bounds=(10, 10, 80, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_cancel",
            name="Cancel",
            class_name="QPushButton",
            bounds=(100, 10, 80, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_delete_all",
            name="Delete All",
            class_name="QPushButton",
            bounds=(190, 10, 100, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.EDIT,
            automation_id="edit_search",
            name="Search Query",
            class_name="QLineEdit",
            bounds=(10, 50, 200, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.VALUE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.EDIT,
            automation_id="edit_password",
            name="Password",
            class_name="QLineEdit",
            bounds=(10, 90, 200, 30),
            is_enabled=True,
            is_password=True,
            supported_patterns=[ControlPattern.VALUE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.CHECK_BOX,
            automation_id="chk_dark_mode",
            name="Enable Dark Mode",
            class_name="QCheckBox",
            bounds=(10, 130, 150, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.TOGGLE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.TAB_ITEM,
            automation_id="tab_general",
            name="General",
            class_name="QTabBarItem",
            bounds=(10, 170, 70, 25),
            is_enabled=True,
            supported_patterns=[ControlPattern.SELECTION_ITEM.value],
            depth=2,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.TAB_ITEM,
            automation_id="tab_advanced",
            name="Advanced",
            class_name="QTabBarItem",
            bounds=(85, 170, 70, 25),
            is_enabled=True,
            supported_patterns=[ControlPattern.SELECTION_ITEM.value],
            depth=2,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_submit",
            name="Submit",
            class_name="QPushButton",
            bounds=(10, 250, 80, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_apply",
            name="Apply",
            class_name="QPushButton",
            bounds=(100, 250, 80, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_ok",
            name="OK",
            class_name="QPushButton",
            bounds=(190, 250, 80, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_continue",
            name="Continue",
            class_name="QPushButton",
            bounds=(280, 250, 80, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_next",
            name="Next",
            class_name="QPushButton",
            bounds=(370, 250, 80, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_refresh",
            name="Refresh",
            class_name="QPushButton",
            bounds=(460, 250, 80, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_download",
            name="Download",
            class_name="QPushButton",
            bounds=(550, 250, 80, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.BUTTON,
            automation_id="btn_export",
            name="Export",
            class_name="QPushButton",
            bounds=(640, 250, 80, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.INVOKE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.CHECK_BOX,
            automation_id="chk_feature",
            name="Enable Feature",
            class_name="QCheckBox",
            bounds=(170, 130, 150, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.TOGGLE.value],
            depth=1,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.TAB_ITEM,
            automation_id="tab_settings",
            name="Settings",
            class_name="QTabBarItem",
            bounds=(160, 170, 70, 25),
            is_enabled=True,
            supported_patterns=[ControlPattern.SELECTION_ITEM.value],
            depth=2,
        ),
        UIElementRef(
            hwnd=hwnd,
            pid=1000,
            control_type=ControlType.COMBO_BOX,
            automation_id="combo_quality",
            name="Quality",
            class_name="QComboBox",
            bounds=(10, 210, 120, 30),
            is_enabled=True,
            supported_patterns=[ControlPattern.EXPAND_COLLAPSE.value, ControlPattern.VALUE.value],
            depth=1,
        ),
    ]


def inspect_window_ui(
    hwnd: int,
    max_depth: int = 5,
    max_elements: int = 100,
    control_types: Optional[list[ControlType]] = None,
    timeout_sec: float = 2.0,
) -> list[UIElementRef]:
    """
    Perform a bounded traversal of the target window's UI element tree.
    Enforces depth, element count, and timeout limits to avoid freezing on massive trees.
    """
    if sys.platform != "win32" or is_simulated_interaction_validation():
        elements = _get_simulated_elements(hwnd)
        if control_types:
            elements = [e for e in elements if e.control_type in control_types]
        return elements[:max_elements]

    valid, err_msg, _ = validate_interaction_target(hwnd)
    if not valid:
        logger.warning("Target window HWND %s failed validation: %s", hwnd, err_msg)
        return []

    _ensure_desktop_attached()

    import comtypes.client
    from comtypes.gen import UIAutomationClient

    elements: list[UIElementRef] = []
    t_start = time.perf_counter()

    try:
        uia = comtypes.client.CreateObject(
            UIAutomationClient.CUIAutomation,
            interface=UIAutomationClient.IUIAutomation,
        )
        root_element = uia.ElementFromHandle(hwnd)
        if not root_element:
            return []

        cond_true = uia.CreateTrueCondition()
        walker = uia.CreateTreeWalker(cond_true)

        def walk(current, depth: int) -> None:
            if depth > max_depth or len(elements) >= max_elements:
                return
            if (time.perf_counter() - t_start) > timeout_sec:
                logger.warning("UI inspection reached timeout of %.2fs", timeout_sec)
                return

            child = walker.GetFirstChildElement(current)
            while child and len(elements) < max_elements:
                if (time.perf_counter() - t_start) > timeout_sec:
                    break

                try:
                    c_type_id = child.CurrentControlType
                    c_type = ControlType.from_uia_type_id(c_type_id)

                    # Only record interactive or named controls
                    name = child.CurrentName or ""
                    auto_id = child.CurrentAutomationId or ""
                    class_name = child.CurrentClassName or ""
                    is_enabled = bool(child.CurrentIsEnabled)
                    is_offscreen = bool(child.CurrentIsOffscreen)
                    is_password = bool(child.CurrentIsPassword)
                    has_focus = bool(child.CurrentHasKeyboardFocus)
                    pid = child.CurrentProcessId

                    rect = child.CurrentBoundingRectangle
                    bounds = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

                    # Determine supported patterns
                    patterns = []
                    # Check InvokePattern (10000)
                    try:
                        if child.GetCurrentPattern(UIAutomationClient.UIA_InvokePatternId):
                            patterns.append(ControlPattern.INVOKE.value)
                    except Exception:
                        pass
                    # Check ValuePattern (10002)
                    try:
                        if child.GetCurrentPattern(UIAutomationClient.UIA_ValuePatternId):
                            patterns.append(ControlPattern.VALUE.value)
                    except Exception:
                        pass
                    # Check TogglePattern (10015)
                    try:
                        if child.GetCurrentPattern(UIAutomationClient.UIA_TogglePatternId):
                            patterns.append(ControlPattern.TOGGLE.value)
                    except Exception:
                        pass
                    # Check SelectionItemPattern (10010)
                    try:
                        if child.GetCurrentPattern(UIAutomationClient.UIA_SelectionItemPatternId):
                            patterns.append(ControlPattern.SELECTION_ITEM.value)
                    except Exception:
                        pass
                    # Check ScrollPattern (10004)
                    try:
                        if child.GetCurrentPattern(UIAutomationClient.UIA_ScrollPatternId):
                            patterns.append(ControlPattern.SCROLL.value)
                    except Exception:
                        pass
                    # Check ExpandCollapsePattern (10005)
                    try:
                        if child.GetCurrentPattern(UIAutomationClient.UIA_ExpandCollapsePatternId):
                            patterns.append(ControlPattern.EXPAND_COLLAPSE.value)
                    except Exception:
                        pass

                    if name or auto_id or patterns or c_type in (
                        ControlType.BUTTON,
                        ControlType.EDIT,
                        ControlType.CHECK_BOX,
                        ControlType.TAB_ITEM,
                        ControlType.COMBO_BOX,
                    ):
                        ref = UIElementRef(
                            hwnd=hwnd,
                            pid=pid,
                            control_type=c_type,
                            automation_id=auto_id,
                            name=name,
                            class_name=class_name,
                            bounds=bounds,
                            is_enabled=is_enabled,
                            is_offscreen=is_offscreen,
                            is_password=is_password,
                            has_keyboard_focus=has_focus,
                            supported_patterns=patterns,
                            depth=depth,
                        )

                        if not control_types or c_type in control_types:
                            elements.append(ref)

                    # Recursively walk children
                    walk(child, depth + 1)

                except Exception as ex:
                    logger.debug("Skipping UI element due to access error: %s", ex)

                child = walker.GetNextSiblingElement(child)

        walk(root_element, 1)

    except Exception as e:
        logger.error("Error during UI tree traversal on HWND %d: %s", hwnd, e)

    return elements


def list_ui_elements(hwnd: int, filter_type: Optional[str] = None, max_elements: int = 50) -> CapabilityResult:
    """
    Enumerate accessible controls within a desktop window.
    Supports optional control type filtering (e.g. 'button', 'edit', 'check_box').
    """
    t0 = time.perf_counter()

    expected_types = None
    if filter_type:
        try:
            expected_types = [ControlType(filter_type.lower())]
        except ValueError:
            return CapabilityResult.fail(
                capability="list_ui_elements",
                message=f"Unknown control filter type '{filter_type}'.",
                error_code=CapabilityErrorCode.INVALID_ARGUMENT,
            )

    elements = inspect_window_ui(hwnd, max_elements=max_elements, control_types=expected_types)
    latency = (time.perf_counter() - t0) * 1000

    return CapabilityResult.ok(
        capability="list_ui_elements",
        message=f"Discovered {len(elements)} UI element(s) in window {hwnd}.",
        data={
            "hwnd": hwnd,
            "count": len(elements),
            "elements": [e.to_dict() for e in elements],
        },
        context_updates=[{"type": "ui_elements_listed", "hwnd": hwnd, "count": len(elements)}],
        latency_ms=latency,
    )
