"""Semantic UI control mutation controller using UI Automation patterns."""

from __future__ import annotations

import sys
import time
from typing import Optional, Tuple

from astrarun.capabilities.models import CapabilityErrorCode
from astrarun.core.logging import get_logger
from astrarun.interaction.discovery import _ensure_desktop_attached
from astrarun.interaction.models import ControlPattern, UIElementRef
from astrarun.interaction.policy import (
    is_destructive_action,
    is_password_element,
    is_simulated_interaction_validation,
    redact_sensitive_content,
    validate_interaction_target,
)

logger = get_logger("astrarun.interaction.controller")


_CONTROL_TYPE_TO_UIA = {
    "button": 50000,
    "check_box": 50002,
    "combo_box": 50003,
    "edit": 50004,
    "hyperlink": 50005,
    "list_item": 50007,
    "list": 50008,
    "menu_bar": 50010,
    "menu_item": 50011,
    "radio_button": 50013,
    "tab": 50018,
    "tab_item": 50019,
    "window": 50032,
    "pane": 50033,
}


def _get_com_element(element: UIElementRef):
    """Retrieve the native COM IUIAutomationElement for a UIElementRef."""
    if sys.platform != "win32":
        return None

    _ensure_desktop_attached()

    import comtypes.client
    from comtypes.gen import UIAutomationClient

    uia = comtypes.client.CreateObject(
        UIAutomationClient.CUIAutomation,
        interface=UIAutomationClient.IUIAutomation,
    )
    root = uia.ElementFromHandle(element.hwnd)
    if not root:
        return None

    # 1. Try compound AutomationId AND Name condition if both present
    if element.automation_id and element.name:
        cond_both = uia.CreateAndCondition(
            uia.CreatePropertyCondition(UIAutomationClient.UIA_AutomationIdPropertyId, element.automation_id),
            uia.CreatePropertyCondition(UIAutomationClient.UIA_NamePropertyId, element.name),
        )
        found = root.FindFirst(UIAutomationClient.TreeScope_Descendants, cond_both)
        if found:
            return found

    # 2. Try compound Name AND ControlType condition if type mapped
    c_type_val = element.control_type.value if hasattr(element.control_type, "value") else str(element.control_type)
    if element.name and c_type_val in _CONTROL_TYPE_TO_UIA:
        cond_type = uia.CreateAndCondition(
            uia.CreatePropertyCondition(UIAutomationClient.UIA_NamePropertyId, element.name),
            uia.CreatePropertyCondition(UIAutomationClient.UIA_ControlTypePropertyId, _CONTROL_TYPE_TO_UIA[c_type_val]),
        )
        found = root.FindFirst(UIAutomationClient.TreeScope_Descendants, cond_type)
        if found:
            return found

    # 3. Try exact AutomationId condition
    if element.automation_id:
        cond_id = uia.CreatePropertyCondition(
            UIAutomationClient.UIA_AutomationIdPropertyId,
            element.automation_id,
        )
        found = root.FindFirst(UIAutomationClient.TreeScope_Descendants, cond_id)
        if found:
            return found

    # 4. Try exact Name condition
    if element.name:
        cond_name = uia.CreatePropertyCondition(
            UIAutomationClient.UIA_NamePropertyId,
            element.name,
        )
        found = root.FindFirst(UIAutomationClient.TreeScope_Descendants, cond_name)
        if found:
            return found

    return root


def invoke_element(element: UIElementRef, force: bool = False) -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """
    Trigger the primary action of a button, menu item, or clickable UI element.
    Enforces destructive confirmation gates and uses semantic InvokePattern.
    """
    is_destruct, reason = is_destructive_action(element.name, "click", element.control_type)
    if is_destruct and not force:
        logger.warning("Invocation of destructive control '%s' blocked: %s", element.name, reason)
        return False, f"Action is destructive: {reason}", CapabilityErrorCode.PERMISSION_DENIED

    if sys.platform != "win32" or is_simulated_interaction_validation():
        logger.info("Simulated invocation of UI element '%s' (%s)", element.name, element.automation_id)
        return True, f"Successfully invoked '{element.name or element.automation_id}' (simulated).", None

    valid, err_msg, err_code = validate_interaction_target(element.hwnd)
    if not valid:
        return False, err_msg, err_code

    try:
        from comtypes.gen import UIAutomationClient

        com_elem = _get_com_element(element)
        if not com_elem:
            return False, f"Could not find live UI element '{element.name}'.", CapabilityErrorCode.NOT_FOUND

        # Attempt InvokePattern
        try:
            pattern = com_elem.GetCurrentPattern(UIAutomationClient.UIA_InvokePatternId)
            if pattern:
                inv = pattern.QueryInterface(UIAutomationClient.IUIAutomationInvokePattern)
                inv.Invoke()
                logger.info("Invoked element '%s' via IUIAutomationInvokePattern", element.name)
                return True, f"Successfully clicked '{element.name or element.automation_id}'.", None
        except Exception as ex:
            logger.debug("InvokePattern failed on '%s': %s", element.name, ex)

        # Fallback 1: TogglePattern if checkbox/toggle
        try:
            pattern = com_elem.GetCurrentPattern(UIAutomationClient.UIA_TogglePatternId)
            if pattern:
                tog = pattern.QueryInterface(UIAutomationClient.IUIAutomationTogglePattern)
                tog.Toggle()
                return True, f"Successfully toggled '{element.name or element.automation_id}'.", None
        except Exception:
            pass

        # Fallback 2: Win32 BM_CLICK if it's a native button control
        import ctypes
        BM_CLICK = 0x00F5
        user32 = ctypes.windll.user32
        res = user32.SendMessageW(element.hwnd, BM_CLICK, 0, 0)
        logger.info("Dispatched BM_CLICK to HWND %d (result: %s)", element.hwnd, res)
        return True, f"Successfully clicked '{element.name}' via Win32 message.", None

    except Exception as e:
        logger.error("Exception invoking element '%s': %s", element.name, e)
        return False, f"Error invoking element: {e}", CapabilityErrorCode.OS_ERROR


def set_element_value(element: UIElementRef, text: str) -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """
    Set text content into an editable UI field.
    Uses atomic ValuePattern.SetValue without clipboard or keystroke races.
    """
    is_pwd = is_password_element(element)
    redacted_preview = redact_sensitive_content(text, is_password=is_pwd)

    if sys.platform != "win32" or is_simulated_interaction_validation():
        logger.info("Simulated text entry into '%s': %s", element.name, redacted_preview)
        return True, f"Set text in '{element.name or element.automation_id}' (simulated).", None

    valid, err_msg, err_code = validate_interaction_target(element.hwnd)
    if not valid:
        return False, err_msg, err_code

    try:
        from comtypes.gen import UIAutomationClient

        com_elem = _get_com_element(element)
        if not com_elem:
            return False, f"Could not find editable UI element '{element.name}'.", CapabilityErrorCode.NOT_FOUND

        # Attempt ValuePattern
        try:
            pattern = com_elem.GetCurrentPattern(UIAutomationClient.UIA_ValuePatternId)
            if pattern:
                val = pattern.QueryInterface(UIAutomationClient.IUIAutomationValuePattern)
                val.SetValue(text)
                logger.info("Set value on '%s' via IUIAutomationValuePattern", element.name)
                return True, f"Successfully set text in '{element.name or element.automation_id}'.", None
        except Exception as ex:
            logger.debug("ValuePattern failed on '%s': %s", element.name, ex)

        # Fallback: Focus element + SendKeys via Win32 SendInput
        try:
            com_elem.SetFocus()
            time.sleep(0.05)
            from astrarun.interaction.keyboard import type_text_into_active
            type_text_into_active(text)
            return True, f"Typed text into '{element.name}' via focus dispatch.", None
        except Exception as ex:
            logger.error("Fallback typing failed: %s", ex)

        return False, f"Element '{element.name}' does not support ValuePattern or text entry.", CapabilityErrorCode.UNAVAILABLE

    except Exception as e:
        logger.error("Exception setting value on element '%s': %s", element.name, e)
        return False, f"Error setting value: {e}", CapabilityErrorCode.OS_ERROR


def toggle_element(element: UIElementRef) -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """Toggle a checkbox, switch, or toggle button state."""
    if sys.platform != "win32" or is_simulated_interaction_validation():
        return True, f"Toggled '{element.name or element.automation_id}' (simulated).", None

    valid, err_msg, err_code = validate_interaction_target(element.hwnd)
    if not valid:
        return False, err_msg, err_code

    try:
        from comtypes.gen import UIAutomationClient

        com_elem = _get_com_element(element)
        if not com_elem:
            return False, f"Could not find toggleable UI element '{element.name}'.", CapabilityErrorCode.NOT_FOUND

        pattern = com_elem.GetCurrentPattern(UIAutomationClient.UIA_TogglePatternId)
        if not pattern:
            return False, f"Element '{element.name}' does not support TogglePattern.", CapabilityErrorCode.UNAVAILABLE

        tog = pattern.QueryInterface(UIAutomationClient.IUIAutomationTogglePattern)
        tog.Toggle()
        return True, f"Successfully toggled '{element.name or element.automation_id}'.", None
    except Exception as e:
        logger.error("Exception toggling element '%s': %s", element.name, e)
        return False, f"Error toggling element: {e}", CapabilityErrorCode.OS_ERROR


def select_element(element: UIElementRef) -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """Select a tab item, radio button, or list row."""
    if sys.platform != "win32" or is_simulated_interaction_validation():
        return True, f"Selected '{element.name or element.automation_id}' (simulated).", None

    valid, err_msg, err_code = validate_interaction_target(element.hwnd)
    if not valid:
        return False, err_msg, err_code

    try:
        from comtypes.gen import UIAutomationClient

        com_elem = _get_com_element(element)
        if not com_elem:
            return False, f"Could not find selectable UI element '{element.name}'.", CapabilityErrorCode.NOT_FOUND

        pattern = com_elem.GetCurrentPattern(UIAutomationClient.UIA_SelectionItemPatternId)
        if not pattern:
            return False, f"Element '{element.name}' does not support SelectionItemPattern.", CapabilityErrorCode.UNAVAILABLE

        sel = pattern.QueryInterface(UIAutomationClient.IUIAutomationSelectionItemPattern)
        sel.Select()
        return True, f"Successfully selected '{element.name or element.automation_id}'.", None
    except Exception as e:
        logger.error("Exception selecting element '%s': %s", element.name, e)
        return False, f"Error selecting element: {e}", CapabilityErrorCode.OS_ERROR


def focus_element(element: UIElementRef) -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """Directly assign native Windows keyboard focus to an element."""
    if sys.platform != "win32" or is_simulated_interaction_validation():
        return True, f"Focused '{element.name or element.automation_id}' (simulated).", None

    valid, err_msg, err_code = validate_interaction_target(element.hwnd)
    if not valid:
        return False, err_msg, err_code

    try:
        com_elem = _get_com_element(element)
        if not com_elem:
            return False, f"Could not find UI element '{element.name}'.", CapabilityErrorCode.NOT_FOUND

        com_elem.SetFocus()
        return True, f"Successfully focused '{element.name or element.automation_id}'.", None
    except Exception as e:
        logger.error("Exception focusing element '%s': %s", element.name, e)
        return False, f"Error focusing element: {e}", CapabilityErrorCode.OS_ERROR


def scroll_element(element: UIElementRef, direction: str = "down") -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """Scroll a scrollable container logically."""
    if sys.platform != "win32" or is_simulated_interaction_validation():
        return True, f"Scrolled '{element.name or element.automation_id}' {direction} (simulated).", None

    valid, err_msg, err_code = validate_interaction_target(element.hwnd)
    if not valid:
        return False, err_msg, err_code

    try:
        from comtypes.gen import UIAutomationClient

        com_elem = _get_com_element(element)
        if not com_elem:
            return False, f"Could not find scrollable element '{element.name}'.", CapabilityErrorCode.NOT_FOUND

        pattern = com_elem.GetCurrentPattern(UIAutomationClient.UIA_ScrollPatternId)
        if not pattern:
            return False, f"Element '{element.name}' does not support ScrollPattern.", CapabilityErrorCode.UNAVAILABLE

        scr = pattern.QueryInterface(UIAutomationClient.IUIAutomationScrollPattern)
        # ScrollAmount_LargeIncrement = 2, ScrollAmount_LargeDecrement = 1, ScrollAmount_NoAmount = 0
        h_amt = 0
        v_amt = 0
        d_lower = direction.lower()
        if "down" in d_lower:
            v_amt = 2
        elif "up" in d_lower:
            v_amt = 1
        elif "right" in d_lower:
            h_amt = 2
        elif "left" in d_lower:
            h_amt = 1

        scr.Scroll(h_amt, v_amt)
        return True, f"Successfully scrolled '{element.name or element.automation_id}' {direction}.", None
    except Exception as e:
        logger.error("Exception scrolling element '%s': %s", element.name, e)
        return False, f"Error scrolling element: {e}", CapabilityErrorCode.OS_ERROR
