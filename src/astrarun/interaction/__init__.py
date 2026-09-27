"""AstraRun UI Automation, Control Grounding & Application Interaction (v0.10)."""

from __future__ import annotations

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
from astrarun.interaction.keyboard import dispatch_shortcut, parse_shortcut, type_text_into_active
from astrarun.interaction.models import (
    ControlPattern,
    ControlType,
    KeyboardShortcut,
    ResolutionCandidate,
    ResolutionResult,
    UIElementRef,
)
from astrarun.interaction.policy import (
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
from astrarun.interaction.worker import UIAutomationWorker, get_ui_worker

__all__ = [
    # Models
    "ControlType",
    "ControlPattern",
    "UIElementRef",
    "KeyboardShortcut",
    "ResolutionCandidate",
    "ResolutionResult",
    # Policies
    "is_destructive_action",
    "is_password_element",
    "redact_sensitive_content",
    "validate_interaction_target",
    "set_simulated_interaction_validation",
    "is_simulated_interaction_validation",
    # Discovery & Resolution
    "inspect_window_ui",
    "list_ui_elements",
    "UIElementResolver",
    # Controllers & Keyboard & Clipboard
    "invoke_element",
    "set_element_value",
    "toggle_element",
    "select_element",
    "focus_element",
    "scroll_element",
    "parse_shortcut",
    "dispatch_shortcut",
    "type_text_into_active",
    "get_clipboard_text",
    "set_clipboard_text",
    # Capabilities & Services
    "inspect_ui",
    "click_element",
    "set_element_text",
    "toggle_checkbox",
    "select_tab",
    "focus_control",
    "scroll_control",
    "press_shortcut",
    "type_literal_text",
    "get_clipboard",
    "set_clipboard",
    # Worker
    "UIAutomationWorker",
    "get_ui_worker",
]
