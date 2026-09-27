"""Unit and integration tests for AstraRun v0.10 Application Interaction & Control Grounding."""

from __future__ import annotations

import os
import sys
import time
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from astrarun.app import AstraApplication, ExecutionResult
from astrarun.capabilities.models import CapabilityCategory, CapabilityErrorCode, CapabilityResult, WindowEntity
from astrarun.interaction.clipboard import get_clipboard_text, set_clipboard_text
from astrarun.interaction.controller import (
    focus_element,
    invoke_element,
    scroll_element,
    select_element,
    set_element_value,
    toggle_element,
)
from astrarun.interaction.discovery import inspect_window_ui, list_ui_elements
from astrarun.interaction.keyboard import KeyboardShortcut, dispatch_shortcut, parse_shortcut, type_text_into_active
from astrarun.interaction.models import (
    ControlPattern,
    ControlType,
    ResolutionCandidate,
    ResolutionResult,
    UIElementRef,
)
from astrarun.interaction.policy import (
    DESTRUCTIVE_KEYWORDS,
    is_destructive_action,
    is_password_element,
    is_simulated_interaction_validation,
    redact_sensitive_content,
    set_simulated_interaction_validation,
    validate_interaction_target,
)
from astrarun.interaction.resolver import UIElementResolver
from astrarun.interaction.service import (
    click_element,
    focus_control,
    get_clipboard,
    inspect_ui,
    press_shortcut,
    scroll_control,
    select_tab,
    set_clipboard,
    set_element_text,
    toggle_checkbox,
    type_literal_text,
)
from astrarun.windows.policy import register_astrarun_hwnd, set_simulated_window_validation, unregister_astrarun_hwnd


@pytest.fixture(autouse=True)
def setup_simulated_interaction():
    """Ensure tests run safely in simulated mode with clean mocks."""
    set_simulated_interaction_validation(True)
    set_simulated_window_validation(True)
    yield
    set_simulated_interaction_validation(False)
    set_simulated_window_validation(False)


# =========================================================================
# 1. Models & Serialization Tests
# =========================================================================

def test_uielementref_serialization():
    elem = UIElementRef(
        hwnd=12345,
        pid=54321,
        control_type=ControlType.BUTTON,
        automation_id="btn_submit",
        name="Submit Form",
        class_name="QPushButton",
        bounds=(10, 20, 100, 30),
        is_enabled=True,
        is_password=False,
        supported_patterns=[ControlPattern.INVOKE.value],
        depth=2,
    )
    d = elem.to_dict()
    assert d["hwnd"] == 12345
    assert d["pid"] == 54321
    assert d["control_type"] == "button"
    assert d["automation_id"] == "btn_submit"
    assert d["name"] == "Submit Form"
    assert d["bounds"] == [10, 20, 100, 30]
    assert d["is_enabled"] is True
    assert d["supported_patterns"] == ["invoke"]

    restored = UIElementRef.from_dict(d)
    assert restored.hwnd == elem.hwnd
    assert restored.control_type == ControlType.BUTTON
    assert restored.automation_id == elem.automation_id
    assert restored.name == elem.name
    assert restored.bounds == elem.bounds
    assert restored.supported_patterns == elem.supported_patterns


def test_control_types_and_patterns():
    assert ControlType("button") == ControlType.BUTTON
    assert ControlType("edit") == ControlType.EDIT
    assert ControlType("check_box") == ControlType.CHECK_BOX
    assert ControlType("tab_item") == ControlType.TAB_ITEM
    assert ControlType("combo_box") == ControlType.COMBO_BOX

    assert ControlPattern.INVOKE.value == "invoke"
    assert ControlPattern.VALUE.value == "value"
    assert ControlPattern.TOGGLE.value == "toggle"
    assert ControlPattern.SELECTION_ITEM.value == "selection_item"


def test_keyboard_shortcut_canonical():
    sc1 = KeyboardShortcut(modifiers=["ctrl", "shift"], key="p")
    assert sc1.canonical_string == "Ctrl+Shift+P"

    sc2 = KeyboardShortcut(modifiers=["alt"], key="f4")
    assert sc2.canonical_string == "Alt+F4"

    sc3 = KeyboardShortcut(modifiers=[], key="enter")
    assert sc3.canonical_string == "Enter"


# =========================================================================
# 2. Safety Policy & Password Protection Tests
# =========================================================================

def test_destructive_action_classification():
    # Destructive words must trigger is_destructive_action
    destructive_cases = [
        ("Delete All", "click"),
        ("delete account", "click"),
        ("Format C:", "invoke"),
        ("Drop Table", "click"),
        ("Clear All Data", "click"),
        ("Factory Reset", "click"),
        ("Purge Cache", "click"),
        ("Wipe Partition", "click"),
        ("Buy License", "click"),
        ("Purchase Now", "click"),
        ("Terminate Process", "click"),
        ("Empty Recycle Bin", "click"),
    ]
    for name, action in destructive_cases:
        is_destruct, reason = is_destructive_action(name, action)
        assert is_destruct is True, f"Expected '{name}' to be classified as destructive"
        assert len(reason) > 0


def test_safe_exceptions_in_destructive_action():
    # Non-destructive or safe navigation actions
    safe_cases = [
        ("Save", "click"),
        ("Cancel", "click"),
        ("Close", "click"),
        ("Dismiss", "click"),
        ("Back", "click"),
        ("Reset Zoom", "click"),
        ("Reset View", "click"),
        ("OK", "click"),
        ("Apply", "click"),
        ("Submit", "click"),
    ]
    for name, action in safe_cases:
        is_destruct, _ = is_destructive_action(name, action)
        assert is_destruct is False, f"Expected '{name}' to be safe"


def test_password_element_detection():
    # Explicit flag
    elem_pwd_flag = UIElementRef(hwnd=1, pid=1, control_type=ControlType.EDIT, is_password=True)
    assert is_password_element(elem_pwd_flag) is True

    # Heuristic detection from name / automation_id
    elem_pwd_name = UIElementRef(hwnd=1, pid=1, control_type=ControlType.EDIT, name="Enter Password")
    assert is_password_element(elem_pwd_name) is True

    elem_pin_id = UIElementRef(hwnd=1, pid=1, control_type=ControlType.EDIT, automation_id="user_pin_code")
    assert is_password_element(elem_pin_id) is True

    # Normal text field
    elem_normal = UIElementRef(hwnd=1, pid=1, control_type=ControlType.EDIT, name="Username", automation_id="txt_user")
    assert is_password_element(elem_normal) is False


def test_redact_sensitive_content():
    # Passwords always redacted to fixed token
    assert redact_sensitive_content("SuperSecret123!", is_password=True) == "[REDACTED_PASSWORD]"

    # API keys and bearer tokens redacted in general text
    text_with_token = "Connecting with Bearer abcdef1234567890xyz and status 200"
    redacted = redact_sensitive_content(text_with_token)
    assert "Bearer [REDACTED_TOKEN]" in redacted
    assert "abcdef1234567890xyz" not in redacted

    text_with_key = "api_key = AKIAIOSFODNN7EXAMPLE12345"
    redacted_key = redact_sensitive_content(text_with_key)
    assert "[REDACTED_API_KEY]" in redacted_key
    assert "AKIAIOSFODNN7EXAMPLE12345" not in redacted_key


def test_target_validation():
    # Simulated mode -> True
    valid, _, _ = validate_interaction_target(1002)
    assert valid is True

    # In live mode
    set_simulated_interaction_validation(False)
    # HWND 0 -> False
    valid, msg, err = validate_interaction_target(0)
    assert valid is False
    assert err == CapabilityErrorCode.NOT_FOUND

    # AstraRun HWND -> BLOCKED
    register_astrarun_hwnd(99999)
    valid, msg, err = validate_interaction_target(99999)
    assert valid is False
    assert err == CapabilityErrorCode.BLOCKED
    unregister_astrarun_hwnd(99999)

    set_simulated_interaction_validation(True)


# =========================================================================
# 3. Element Resolver Tests
# =========================================================================

def test_element_resolver_exact_automation_id():
    elements = [
        UIElementRef(hwnd=1, pid=1, control_type=ControlType.BUTTON, automation_id="btn_submit", name="OK"),
        UIElementRef(hwnd=1, pid=1, control_type=ControlType.BUTTON, automation_id="btn_cancel", name="Cancel"),
    ]
    res = UIElementResolver.resolve("btn_submit", elements)
    assert res.element is not None
    assert res.element.automation_id == "btn_submit"
    assert res.confidence >= 0.95
    assert not res.ambiguous


def test_element_resolver_exact_name():
    elements = [
        UIElementRef(hwnd=1, pid=1, control_type=ControlType.BUTTON, automation_id="b1", name="Save Changes"),
        UIElementRef(hwnd=1, pid=1, control_type=ControlType.BUTTON, automation_id="b2", name="Discard"),
    ]
    res = UIElementResolver.resolve("Save Changes", elements)
    assert res.element is not None
    assert res.element.name == "Save Changes"
    assert res.confidence >= 0.90
    assert not res.ambiguous


def test_element_resolver_control_type_boost():
    elements = [
        UIElementRef(hwnd=1, pid=1, control_type=ControlType.PANE, automation_id="pane_search", name="Search"),
        UIElementRef(hwnd=1, pid=1, control_type=ControlType.EDIT, automation_id="txt_search", name="Search"),
    ]
    # Resolving for edit control type should favor edit over label
    res = UIElementResolver.resolve("Search", elements, expected_type=ControlType.EDIT)
    assert res.element is not None
    assert res.element.control_type == ControlType.EDIT
    assert res.element.automation_id == "txt_search"


def test_element_resolver_synonyms():
    elements = [
        UIElementRef(hwnd=1, pid=1, control_type=ControlType.BUTTON, automation_id="btn_ok", name="Submit"),
    ]
    # "ok" is a registered synonym for "submit"
    res = UIElementResolver.resolve("ok", elements)
    assert res.element is not None
    assert res.element.name == "Submit"


def test_element_resolver_ambiguity_detection():
    # Two buttons with almost identical names and same type
    elements = [
        UIElementRef(hwnd=1, pid=1, control_type=ControlType.BUTTON, automation_id="btn_del1", name="Delete Item"),
        UIElementRef(hwnd=1, pid=1, control_type=ControlType.BUTTON, automation_id="btn_del2", name="Delete File"),
    ]
    # Ambiguous query "delete" matches both with near identical score
    res = UIElementResolver.resolve("delete", elements)
    assert res.ambiguous is True
    assert len(res.candidates) >= 2


def test_element_resolver_not_found():
    elements = [
        UIElementRef(hwnd=1, pid=1, control_type=ControlType.BUTTON, automation_id="b1", name="Submit"),
    ]
    res = UIElementResolver.resolve("Supercalifragilistic", elements)
    assert res.element is None
    assert not res.ambiguous


# =========================================================================
# 4. Keyboard Shortcut Parsing & Dispatch Tests
# =========================================================================

def test_keyboard_parse_valid():
    sc = parse_shortcut("ctrl+shift+p")
    assert sc is not None
    assert sc.modifiers == ["ctrl", "shift"]
    assert sc.key == "p"
    assert sc.canonical_string == "Ctrl+Shift+P"

    sc2 = parse_shortcut("Alt + F4")
    assert sc2 is not None
    assert sc2.modifiers == ["alt"]
    assert sc2.key == "f4"
    assert sc2.canonical_string == "Alt+F4"

    sc3 = parse_shortcut("enter")
    assert sc3 is not None
    assert sc3.modifiers == []
    assert sc3.key == "enter"


def test_keyboard_parse_invalid():
    # Multiple primary keys
    assert parse_shortcut("ctrl+a+b") is None

    # Unrecognized key
    assert parse_shortcut("ctrl+superfoobar") is None

    # Empty string
    assert parse_shortcut("") is None
    assert parse_shortcut("   ") is None


def test_keyboard_dispatch_simulated():
    sc = parse_shortcut("Ctrl+C")
    assert sc is not None
    ok, msg, err = dispatch_shortcut(sc, target_hwnd=1002)
    assert ok is True
    assert "simulated" in msg.lower()
    assert err is None


def test_type_text_simulated():
    ok, msg, err = type_text_into_active("Hello, World!")
    assert ok is True
    assert "simulated" in msg.lower()
    assert err is None


# =========================================================================
# 5. Controller Functions (Simulated)
# =========================================================================

def test_controller_invoke_element():
    elem = UIElementRef(hwnd=1002, pid=1, control_type=ControlType.BUTTON, name="Save", automation_id="btn_save")
    ok, msg, err = invoke_element(elem)
    assert ok is True
    assert "simulated" in msg.lower()
    assert err is None


def test_controller_invoke_destructive_element_blocked():
    elem = UIElementRef(hwnd=1002, pid=1, control_type=ControlType.BUTTON, name="Delete All", automation_id="btn_delete")
    # Without force -> PERMISSION_DENIED
    ok, msg, err = invoke_element(elem, force=False)
    assert ok is False
    assert err == CapabilityErrorCode.PERMISSION_DENIED

    # With force=True -> succeeds
    ok, msg, err = invoke_element(elem, force=True)
    assert ok is True


def test_controller_set_element_value():
    elem = UIElementRef(hwnd=1002, pid=1, control_type=ControlType.EDIT, name="Search Query", automation_id="edit_search")
    ok, msg, err = set_element_value(elem, "test query")
    assert ok is True
    assert "simulated" in msg.lower()


def test_controller_toggle_element():
    elem = UIElementRef(hwnd=1002, pid=1, control_type=ControlType.CHECK_BOX, name="Dark Mode", automation_id="chk_dark")
    ok, msg, err = toggle_element(elem)
    assert ok is True
    assert "simulated" in msg.lower()


def test_controller_select_element():
    elem = UIElementRef(hwnd=1002, pid=1, control_type=ControlType.TAB_ITEM, name="Advanced", automation_id="tab_adv")
    ok, msg, err = select_element(elem)
    assert ok is True
    assert "simulated" in msg.lower()


def test_controller_focus_element():
    elem = UIElementRef(hwnd=1002, pid=1, control_type=ControlType.EDIT, name="Search", automation_id="edit_search")
    ok, msg, err = focus_element(elem)
    assert ok is True
    assert "simulated" in msg.lower()


def test_controller_scroll_element():
    elem = UIElementRef(hwnd=1002, pid=1, control_type=ControlType.PANE, name="Document", automation_id="pane_doc")
    ok, msg, err = scroll_element(elem, direction="down")
    assert ok is True
    assert "simulated" in msg.lower()


# =========================================================================
# 6. High-Level Service & Capability Handlers (Simulated)
# =========================================================================

def test_service_inspect_ui():
    res = inspect_ui(hwnd=1002)
    assert res.success is True
    assert res.data["count"] > 0
    assert len(res.data["elements"]) > 0


def test_service_click_element_safe():
    res = click_element("Save", hwnd=1002)
    assert res.success is True
    assert res.data["target"] == "Save"


def test_service_click_element_destructive_gated():
    # Destructive click without force must return PERMISSION_DENIED
    res = click_element("Delete All", hwnd=1002, force=False)
    assert res.success is False
    assert res.error_code == CapabilityErrorCode.PERMISSION_DENIED

    # With force=True
    res_forced = click_element("Delete All", hwnd=1002, force=True)
    assert res_forced.success is True


def test_service_set_element_text():
    res = set_element_text("Search", "astrarun unit test", hwnd=1002)
    assert res.success is True
    assert res.data["target"] == "Search"


def test_service_toggle_checkbox():
    res = toggle_checkbox("dark mode", hwnd=1002)
    assert res.success is True


def test_service_select_tab():
    res = select_tab("Advanced", hwnd=1002)
    assert res.success is True


def test_service_focus_control():
    res = focus_control("Search", hwnd=1002)
    assert res.success is True


def test_service_scroll_control():
    res = scroll_control(direction="down", hwnd=1002)
    assert res.success is True


def test_service_press_shortcut():
    res = press_shortcut("Ctrl+Shift+P", hwnd=1002)
    assert res.success is True
    assert res.data["shortcut"] == "Ctrl+Shift+P"


def test_service_type_literal_text_payload_as_data():
    # Verifies payload is treated as literal data, not command
    res = type_literal_text("format c: /q", hwnd=1002)
    assert res.success is True
    assert res.data["length"] == len("format c: /q")


# =========================================================================
# 7. Canonical Pipeline Integration (`AstraApplication.handle_request`)
# =========================================================================

def test_app_pipeline_ui_click():
    app = AstraApplication()
    mock_origin = WindowEntity(hwnd=1002, title="TestApp", pid=1, app_id="test.exe")

    res = app.handle_request("click Save", origin_window=mock_origin, dry_run=True)
    assert res.success is True
    assert res.type == "capability_result"


def test_app_pipeline_ui_destructive_click_confirmation():
    app = AstraApplication()
    mock_origin = WindowEntity(hwnd=1002, title="TestApp", pid=1, app_id="test.exe")

    res = app.handle_request("click Delete All", origin_window=mock_origin, dry_run=True)
    assert res.success is False
    assert res.type == "confirm"
    assert "confirm destructive click" in res.prompt.lower()


def test_app_pipeline_ui_type_into():
    app = AstraApplication()
    mock_origin = WindowEntity(hwnd=1002, title="TestApp", pid=1, app_id="test.exe")

    res = app.handle_request("type test into search", origin_window=mock_origin, dry_run=True)
    assert res.success is True
    assert res.type == "capability_result"


def test_app_pipeline_ui_toggle():
    app = AstraApplication()
    mock_origin = WindowEntity(hwnd=1002, title="TestApp", pid=1, app_id="test.exe")

    res = app.handle_request("toggle dark mode", origin_window=mock_origin, dry_run=True)
    assert res.success is True
    assert res.type == "capability_result"


def test_app_pipeline_ui_shortcuts():
    app = AstraApplication()
    mock_origin = WindowEntity(hwnd=1002, title="TestApp", pid=1, app_id="test.exe")

    for sc in ("press ctrl+c", "press alt+f4", "copy", "paste", "select all"):
        res = app.handle_request(sc, origin_window=mock_origin, dry_run=True)
        assert res.success is True
        assert res.type == "capability_result"


# =========================================================================
# 8. Live Fixture Subprocess Integration Tests (LIVE_FIXTURE)
# =========================================================================

def test_live_ui_fixture_roundtrip():
    """Verify live UI Automation against an isolated out-of-process PySide6 window."""
    if sys.platform != "win32":
        pytest.skip("Live UI Automation tests require Windows platform.")

    from pathlib import Path
    test_dir = str(Path(__file__).parent)
    if test_dir not in sys.path:
        sys.path.insert(0, test_dir)

    from fixtures.ui_fixture import spawn_ui_fixture

    # Run in live mode for real COM UIA traversal
    set_simulated_interaction_validation(False)
    try:
        with spawn_ui_fixture(timeout=15.0) as (hwnd, pid):
            assert hwnd > 0
            assert pid > 0

            # 1. Discover live elements
            elements = inspect_window_ui(hwnd, max_elements=50)
            assert len(elements) >= 5, f"Expected at least 5 controls in live fixture, got {len(elements)}"

            names = {e.name for e in elements}
            assert "Save" in names or any("save" in e.automation_id.lower() for e in elements)
            assert "Cancel" in names or any("cancel" in e.automation_id.lower() for e in elements)

            # 2. Click Save
            click_res = click_element("Save", hwnd=hwnd)
            assert click_res.success is True

            # 3. Enter Text
            set_res = set_element_text("Search", "Live Test Query", hwnd=hwnd)
            assert set_res.success is True

            # 4. Toggle Checkbox
            tog_res = toggle_checkbox("Feature", hwnd=hwnd)
            assert tog_res.success is True

            # 5. Select Tab
            tab_res = select_tab("Advanced", hwnd=hwnd)
            assert tab_res.success is True
    finally:
        set_simulated_interaction_validation(True)

