"""High-level workstation capabilities for UI interaction and control grounding."""

from __future__ import annotations

import sys
import time
from typing import Any, Dict, List, Optional

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult, WindowEntity
from astrarun.core.logging import get_logger
from astrarun.interaction.clipboard import get_clipboard_text, set_clipboard_text
from astrarun.interaction.controller import (
    focus_element,
    invoke_element,
    scroll_element,
    select_element,
    set_element_value,
    toggle_element,
)
from astrarun.interaction.discovery import inspect_window_ui
from astrarun.interaction.keyboard import dispatch_shortcut, parse_shortcut, type_text_into_active
from astrarun.interaction.models import ControlType, UIElementRef
from astrarun.interaction.policy import is_destructive_action, is_password_element, redact_sensitive_content
from astrarun.interaction.resolver import UIElementResolver
from astrarun.windows.discovery import foreground_window
from astrarun.windows.resolver import WindowResolver

logger = get_logger("astrarun.interaction.service")


def _resolve_target_hwnd(
    hwnd: Optional[int] = None,
    window_query: Optional[str] = None,
    origin_window: Optional[WindowEntity | int] = None,
) -> Optional[int]:
    """Resolve the target window HWND from explicit hwnd, window name, or origin/foreground window."""
    if hwnd and hwnd > 0:
        return hwnd

    origin_entity: Optional[WindowEntity] = None
    if isinstance(origin_window, WindowEntity):
        origin_entity = origin_window

    if window_query:
        # Use WindowResolver to resolve window by name
        res = WindowResolver().resolve(window_query, origin_window=origin_entity)
        if res.window:
            return res.window.hwnd

    # Fallback to origin_window if supplied
    if origin_window:
        if isinstance(origin_window, int) and origin_window > 0:
            return origin_window
        if isinstance(origin_window, WindowEntity) and origin_window.hwnd > 0:
            return origin_window.hwnd

    # Fallback to current foreground window
    fg = foreground_window()
    if fg.success and fg.data.get("hwnd"):
        return fg.data["hwnd"]

    return None


def inspect_ui(
    hwnd: Optional[int] = None,
    window: Optional[str] = None,
    max_elements: int = 50,
    filter_type: Optional[str] = None,
    origin_window: Optional[WindowEntity | int] = None,
) -> CapabilityResult:
    """Enumerate accessible controls within a target or active window."""
    t0 = time.perf_counter()
    target_hwnd = _resolve_target_hwnd(hwnd, window, origin_window)
    if not target_hwnd:
        return CapabilityResult.fail(
            capability="inspect_window_ui",
            message="No active or matching window found to inspect.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    expected_types = None
    if filter_type:
        try:
            expected_types = [ControlType(filter_type.lower())]
        except ValueError:
            return CapabilityResult.fail(
                capability="inspect_window_ui",
                message=f"Unknown control filter type '{filter_type}'.",
                error_code=CapabilityErrorCode.INVALID_ARGUMENT,
            )

    elements = inspect_window_ui(target_hwnd, max_elements=max_elements, control_types=expected_types)
    latency = (time.perf_counter() - t0) * 1000

    return CapabilityResult.ok(
        capability="inspect_window_ui",
        message=f"Discovered {len(elements)} accessible UI element(s) in window {target_hwnd}.",
        data={
            "hwnd": target_hwnd,
            "count": len(elements),
            "elements": [e.to_dict() for e in elements],
        },
        context_updates=[{"type": "ui_inspected", "hwnd": target_hwnd, "count": len(elements)}],
        latency_ms=latency,
    )


def click_element(
    target: str,
    hwnd: Optional[int] = None,
    window: Optional[str] = None,
    force: bool = False,
    origin_window: Optional[WindowEntity | int] = None,
) -> CapabilityResult:
    """Find and click a semantic button, menu item, or interactive control."""
    t0 = time.perf_counter()

    # 0. Upfront destructive action policy check
    is_destruct, reason = is_destructive_action(target, "click")
    if is_destruct and not force:
        logger.warning("Invocation of destructive control '%s' blocked: %s", target, reason)
        return CapabilityResult.fail(
            capability="click_ui_element",
            message=f"Action is destructive: {reason}",
            error_code=CapabilityErrorCode.PERMISSION_DENIED,
        )

    target_hwnd = _resolve_target_hwnd(hwnd, window, origin_window)
    if not target_hwnd:
        return CapabilityResult.fail(
            capability="click_ui_element",
            message="No active or matching window found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    # 1. Discover elements in target window
    elements = inspect_window_ui(target_hwnd, max_elements=100)
    if not elements:
        return CapabilityResult.fail(
            capability="click_ui_element",
            message=f"No accessible UI elements found in window {target_hwnd}.",
            error_code=CapabilityErrorCode.UNAVAILABLE,
        )

    # 2. Resolve target element
    res = UIElementResolver.resolve(target, elements, expected_type=ControlType.BUTTON)
    if res.ambiguous:
        return CapabilityResult.fail(
            capability="click_ui_element",
            message=res.clarification_prompt or "Multiple ambiguous UI controls match query.",
            error_code=CapabilityErrorCode.AMBIGUOUS,
            data={"candidates": [c.element.to_dict() for c in res.candidates[:5]]},
        )

    if not res.element:
        return CapabilityResult.fail(
            capability="click_ui_element",
            message=f"Could not find UI control matching '{target}' in window {target_hwnd}.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    # 3. Invoke element
    ok, msg, err_code = invoke_element(res.element, force=force)
    latency = (time.perf_counter() - t0) * 1000

    if not ok:
        return CapabilityResult.fail(
            capability="click_ui_element",
            message=msg,
            error_code=err_code or CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="click_ui_element",
        message=msg,
        data={
            "hwnd": target_hwnd,
            "target": target,
            "element": res.element.to_dict(),
            "confidence": res.confidence,
            "match_reason": res.match_reason,
        },
        context_updates=[{"type": "ui_clicked", "hwnd": target_hwnd, "element": res.element.name}],
        latency_ms=latency,
    )


def set_element_text(
    target: str,
    value: str,
    hwnd: Optional[int] = None,
    window: Optional[str] = None,
    origin_window: Optional[WindowEntity | int] = None,
) -> CapabilityResult:
    """Find an editable field and set its text content."""
    t0 = time.perf_counter()
    target_hwnd = _resolve_target_hwnd(hwnd, window, origin_window)
    if not target_hwnd:
        return CapabilityResult.fail(
            capability="set_ui_element_value",
            message="No active or matching window found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    elements = inspect_window_ui(target_hwnd, max_elements=100)
    res = UIElementResolver.resolve(target, elements, expected_type=ControlType.EDIT)

    if res.ambiguous:
        return CapabilityResult.fail(
            capability="set_ui_element_value",
            message=res.clarification_prompt or "Multiple ambiguous input fields match query.",
            error_code=CapabilityErrorCode.AMBIGUOUS,
        )

    if not res.element:
        return CapabilityResult.fail(
            capability="set_ui_element_value",
            message=f"Could not find input field matching '{target}' in window {target_hwnd}.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    ok, msg, err_code = set_element_value(res.element, value)
    latency = (time.perf_counter() - t0) * 1000

    if not ok:
        return CapabilityResult.fail(
            capability="set_ui_element_value",
            message=msg,
            error_code=err_code or CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    is_pwd = is_password_element(res.element)
    display_val = redact_sensitive_content(value, is_password=is_pwd)

    return CapabilityResult.ok(
        capability="set_ui_element_value",
        message=msg,
        data={
            "hwnd": target_hwnd,
            "target": target,
            "element": res.element.to_dict(),
            "value_preview": display_val,
            "is_password": is_pwd,
        },
        context_updates=[{"type": "ui_value_set", "hwnd": target_hwnd, "element": res.element.name}],
        latency_ms=latency,
    )


def toggle_checkbox(
    target: str,
    hwnd: Optional[int] = None,
    window: Optional[str] = None,
    origin_window: Optional[WindowEntity | int] = None,
) -> CapabilityResult:
    """Find and toggle a checkbox or switch."""
    t0 = time.perf_counter()
    target_hwnd = _resolve_target_hwnd(hwnd, window, origin_window)
    if not target_hwnd:
        return CapabilityResult.fail(
            capability="toggle_ui_element",
            message="No active or matching window found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    elements = inspect_window_ui(target_hwnd, max_elements=100)
    res = UIElementResolver.resolve(target, elements, expected_type=ControlType.CHECK_BOX)

    if not res.element:
        return CapabilityResult.fail(
            capability="toggle_ui_element",
            message=f"Could not find checkbox matching '{target}' in window {target_hwnd}.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    ok, msg, err_code = toggle_element(res.element)
    latency = (time.perf_counter() - t0) * 1000

    if not ok:
        return CapabilityResult.fail(
            capability="toggle_ui_element",
            message=msg,
            error_code=err_code or CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="toggle_ui_element",
        message=msg,
        data={"hwnd": target_hwnd, "target": target, "element": res.element.to_dict()},
        context_updates=[{"type": "ui_toggled", "hwnd": target_hwnd, "element": res.element.name}],
        latency_ms=latency,
    )


def select_tab(
    target: str,
    hwnd: Optional[int] = None,
    window: Optional[str] = None,
    origin_window: Optional[WindowEntity | int] = None,
) -> CapabilityResult:
    """Find and select a tab item, radio button, or list row."""
    t0 = time.perf_counter()
    target_hwnd = _resolve_target_hwnd(hwnd, window, origin_window)
    if not target_hwnd:
        return CapabilityResult.fail(
            capability="select_ui_element",
            message="No active or matching window found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    elements = inspect_window_ui(target_hwnd, max_elements=100)
    res = UIElementResolver.resolve(target, elements, expected_type=ControlType.TAB_ITEM)

    if not res.element:
        return CapabilityResult.fail(
            capability="select_ui_element",
            message=f"Could not find selectable item matching '{target}' in window {target_hwnd}.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    ok, msg, err_code = select_element(res.element)
    latency = (time.perf_counter() - t0) * 1000

    if not ok:
        return CapabilityResult.fail(
            capability="select_ui_element",
            message=msg,
            error_code=err_code or CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="select_ui_element",
        message=msg,
        data={"hwnd": target_hwnd, "target": target, "element": res.element.to_dict()},
        context_updates=[{"type": "ui_tab_selected", "hwnd": target_hwnd, "element": res.element.name}],
        latency_ms=latency,
    )


def focus_control(
    target: str,
    hwnd: Optional[int] = None,
    window: Optional[str] = None,
    origin_window: Optional[WindowEntity | int] = None,
) -> CapabilityResult:
    """Assign native keyboard focus to a target UI control."""
    t0 = time.perf_counter()
    target_hwnd = _resolve_target_hwnd(hwnd, window, origin_window)
    if not target_hwnd:
        return CapabilityResult.fail(
            capability="focus_ui_element",
            message="No active or matching window found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    elements = inspect_window_ui(target_hwnd, max_elements=100)
    res = UIElementResolver.resolve(target, elements)

    if not res.element:
        return CapabilityResult.fail(
            capability="focus_ui_element",
            message=f"Could not find UI control matching '{target}' to focus.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    ok, msg, err_code = focus_element(res.element)
    latency = (time.perf_counter() - t0) * 1000

    if not ok:
        return CapabilityResult.fail(
            capability="focus_ui_element",
            message=msg,
            error_code=err_code or CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="focus_ui_element",
        message=msg,
        data={"hwnd": target_hwnd, "target": target, "element": res.element.to_dict()},
        context_updates=[{"type": "ui_focused", "hwnd": target_hwnd, "element": res.element.name}],
        latency_ms=latency,
    )


def scroll_control(
    direction: str = "down",
    target: Optional[str] = None,
    hwnd: Optional[int] = None,
    window: Optional[str] = None,
    origin_window: Optional[WindowEntity | int] = None,
) -> CapabilityResult:
    """Scroll a container or active window logically."""
    t0 = time.perf_counter()
    target_hwnd = _resolve_target_hwnd(hwnd, window, origin_window)
    if not target_hwnd:
        return CapabilityResult.fail(
            capability="scroll_ui_element",
            message="No active or matching window found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    elements = inspect_window_ui(target_hwnd, max_elements=100)
    if target:
        res = UIElementResolver.resolve(target, elements)
        target_el = res.element
    else:
        # Pick the largest pane/container or the first scroll-supporting element
        target_el = next((e for e in elements if "scroll" in e.supported_patterns), None)
        if not target_el and elements:
            target_el = elements[0]

    if not target_el:
        return CapabilityResult.fail(
            capability="scroll_ui_element",
            message="No scrollable container found in window.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    ok, msg, err_code = scroll_element(target_el, direction=direction)
    latency = (time.perf_counter() - t0) * 1000

    if not ok:
        return CapabilityResult.fail(
            capability="scroll_ui_element",
            message=msg,
            error_code=err_code or CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="scroll_ui_element",
        message=msg,
        data={"hwnd": target_hwnd, "direction": direction, "element": target_el.to_dict()},
        context_updates=[{"type": "ui_scrolled", "hwnd": target_hwnd, "direction": direction}],
        latency_ms=latency,
    )


def press_shortcut(
    shortcut: str,
    hwnd: Optional[int] = None,
    window: Optional[str] = None,
    origin_window: Optional[WindowEntity | int] = None,
) -> CapabilityResult:
    """Dispatch a validated keyboard shortcut (e.g. Ctrl+Shift+P, Alt+F4) to the target or foreground window."""
    t0 = time.perf_counter()
    parsed = parse_shortcut(shortcut)
    if not parsed:
        return CapabilityResult.fail(
            capability="press_keyboard_shortcut",
            message=f"Invalid or unrecognized keyboard shortcut '{shortcut}'.",
            error_code=CapabilityErrorCode.INVALID_ARGUMENT,
        )

    target_hwnd = _resolve_target_hwnd(hwnd, window, origin_window)
    ok, msg, err_code = dispatch_shortcut(parsed, target_hwnd=target_hwnd)
    latency = (time.perf_counter() - t0) * 1000

    if not ok:
        return CapabilityResult.fail(
            capability="press_keyboard_shortcut",
            message=msg,
            error_code=err_code or CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="press_keyboard_shortcut",
        message=msg,
        data={"shortcut": parsed.canonical_string, "hwnd": target_hwnd},
        context_updates=[{"type": "shortcut_dispatched", "shortcut": parsed.canonical_string}],
        latency_ms=latency,
    )


def type_literal_text(
    text: str,
    hwnd: Optional[int] = None,
    window: Optional[str] = None,
    origin_window: Optional[WindowEntity | int] = None,
) -> CapabilityResult:
    """
    Type literal text into the active/focused control without shell evaluation.
    Payload is treated strictly as data.
    """
    t0 = time.perf_counter()
    target_hwnd = _resolve_target_hwnd(hwnd, window, origin_window)
    if target_hwnd and sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(target_hwnd)
            time.sleep(0.05)
        except Exception:
            pass

    ok, msg, err_code = type_text_into_active(text)
    latency = (time.perf_counter() - t0) * 1000

    if not ok:
        return CapabilityResult.fail(
            capability="type_text",
            message=msg,
            error_code=err_code or CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="type_text",
        message=msg,
        data={"length": len(text), "hwnd": target_hwnd},
        context_updates=[{"type": "text_typed", "length": len(text)}],
        latency_ms=latency,
    )


def get_clipboard() -> CapabilityResult:
    """Read text content from the system clipboard."""
    t0 = time.perf_counter()
    ok, text, err_code = get_clipboard_text()
    latency = (time.perf_counter() - t0) * 1000

    if not ok:
        return CapabilityResult.fail(
            capability="get_clipboard_content",
            message="Failed to read system clipboard.",
            error_code=err_code or CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    redacted_preview = redact_sensitive_content(text[:50])
    return CapabilityResult.ok(
        capability="get_clipboard_content",
        message=f"Clipboard read successfully ({len(text)} chars).",
        data={"content": text, "preview": redacted_preview, "length": len(text)},
        latency_ms=latency,
    )


def set_clipboard(text: str) -> CapabilityResult:
    """Write text content to the system clipboard."""
    t0 = time.perf_counter()
    ok, msg, err_code = set_clipboard_text(text)
    latency = (time.perf_counter() - t0) * 1000

    if not ok:
        return CapabilityResult.fail(
            capability="set_clipboard_content",
            message=msg,
            error_code=err_code or CapabilityErrorCode.OS_ERROR,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="set_clipboard_content",
        message=msg,
        data={"length": len(text)},
        context_updates=[{"type": "clipboard_set", "length": len(text)}],
        latency_ms=latency,
    )
