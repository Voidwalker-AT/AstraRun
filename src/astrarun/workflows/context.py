"""WorkflowContext: Typed execution state and discourse binding for multi-step workflows.

Enforces:
1. Implicit target propagation: results from preceding steps automatically bind to subsequent steps.
2. Discourse state retention: tracks last opened app, window, UI root, and UI element.
3. Origin window preservation: maintains user's starting workstation context.
4. Zero global guessing: cross-step bindings are deterministic within the same compound workflow.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from astrarun.capabilities.models import CapabilityResult, WindowEntity
from astrarun.interaction.models import UIElementRef
from astrarun.workflows.models import WorkflowStep

logger = logging.getLogger(__name__)


@dataclass
class WorkflowContext:
    """Typed execution state for chained capability execution in a compound task."""
    origin_window: Optional[WindowEntity] = None
    last_opened_application: Optional[str] = None
    last_opened_window: Optional[WindowEntity] = None
    last_resolved_ui_root: Optional[int] = None  # HWND
    last_ui_element: Optional[UIElementRef] = None
    step_outputs: dict[str, Any] = field(default_factory=dict)

    def record_step_result(self, step: WorkflowStep, result: CapabilityResult) -> None:
        """Update context with outputs and semantic side-effects of an executed step."""
        self.step_outputs[step.step_id] = result.data or {}

        # 1. Application open
        if step.tool == "open_application":
            app_arg = step.arguments.get("app")
            if app_arg:
                self.last_opened_application = str(app_arg).lower()
                logger.debug("WorkflowContext: last_opened_application = %s", self.last_opened_application)

        # 2. Window wait or discovery
        elif step.tool in ("wait_for_window", "foreground_window", "find_window", "focus_application"):
            if result.success and isinstance(result.data, dict):
                hwnd = result.data.get("hwnd")
                if hwnd:
                    self.last_resolved_ui_root = int(hwnd)
                    self.last_opened_window = WindowEntity(
                        hwnd=int(hwnd),
                        title=result.data.get("title", ""),
                        pid=result.data.get("pid", 0),
                        app_id=result.data.get("app", self.last_opened_application or ""),
                    )
                    logger.debug("WorkflowContext: last_opened_window = HWND %d ('%s')", hwnd, self.last_opened_window.title)

        # 3. Editable UI element resolution
        elif step.tool in ("resolve_editable_element", "focus_ui_element", "inspect_window_ui"):
            if result.success and isinstance(result.data, dict):
                elem_dict = result.data.get("element")
                if isinstance(elem_dict, dict):
                    self.last_ui_element = UIElementRef.from_dict(elem_dict)
                hwnd = result.data.get("hwnd")
                if hwnd:
                    self.last_resolved_ui_root = int(hwnd)
                logger.debug("WorkflowContext: last_ui_element resolved in HWND %s", self.last_resolved_ui_root)

        # 4. Window mutation / layout
        elif "window" in step.tool:
            hwnd = step.arguments.get("hwnd") or (result.data.get("hwnd") if isinstance(result.data, dict) else None)
            if hwnd:
                self.last_resolved_ui_root = int(hwnd)

    def bind_step_arguments(self, step: WorkflowStep) -> dict[str, Any]:
        """
        Enrich step arguments with implicit target context where not explicitly specified.
        Mutates step.arguments in place and returns the bound arguments dictionary.
        """
        bound = step.arguments

        # A. Bind 'app' target for wait_for_window
        if step.tool == "wait_for_window":
            if not bound.get("app") and self.last_opened_application:
                bound["app"] = self.last_opened_application

        # B. Bind 'hwnd' target for UI inspection and editable control resolution
        elif step.tool == "resolve_editable_element":
            if not bound.get("hwnd"):
                if self.last_resolved_ui_root:
                    bound["hwnd"] = self.last_resolved_ui_root
                elif self.last_opened_window:
                    bound["hwnd"] = self.last_opened_window.hwnd
                elif self.origin_window:
                    bound["hwnd"] = self.origin_window.hwnd

        # C. Bind target HWND for text typing
        elif step.tool == "type_text":
            if not bound.get("hwnd"):
                if self.last_resolved_ui_root:
                    bound["hwnd"] = self.last_resolved_ui_root
                elif self.last_opened_window:
                    bound["hwnd"] = self.last_opened_window.hwnd
                elif self.origin_window:
                    bound["hwnd"] = self.origin_window.hwnd

            if not bound.get("target") and self.last_ui_element:
                bound["target"] = self.last_ui_element.name or self.last_ui_element.automation_id
            if not bound.get("target_element") and self.last_ui_element:
                bound["target_element"] = self.last_ui_element.to_dict()

        # D. Bind target HWND for shortcuts, clicks, value setting, and element actions
        elif step.tool in ("press_keyboard_shortcut", "click_ui_element", "set_ui_element_value", "focus_ui_element", "toggle_ui_element", "select_ui_element"):
            if not bound.get("hwnd"):
                if self.last_resolved_ui_root:
                    bound["hwnd"] = self.last_resolved_ui_root
                elif self.last_opened_window:
                    bound["hwnd"] = self.last_opened_window.hwnd
                elif self.origin_window:
                    bound["hwnd"] = self.origin_window.hwnd

        # E. Bind target HWND for window manipulation (maximize, snap, move, close, focus)
        elif step.tool in ("maximize_window", "minimize_window", "restore_window", "snap_window_left", "snap_window_right", "move_window", "close_window", "move_window_to_monitor", "focus_window"):
            if not bound.get("hwnd"):
                if self.last_resolved_ui_root:
                    bound["hwnd"] = self.last_resolved_ui_root
                elif self.last_opened_window:
                    bound["hwnd"] = self.last_opened_window.hwnd
                elif self.origin_window:
                    bound["hwnd"] = self.origin_window.hwnd

        return bound

    def to_dict(self) -> dict[str, Any]:
        """Serialize context for task telemetry and logging."""
        return {
            "origin_window": self.origin_window.to_dict() if self.origin_window else None,
            "last_opened_application": self.last_opened_application,
            "last_opened_window": self.last_opened_window.to_dict() if self.last_opened_window else None,
            "last_resolved_ui_root": self.last_resolved_ui_root,
            "last_ui_element": self.last_ui_element.to_dict() if self.last_ui_element else None,
        }
