"""Windows UI Automation driver for AstraRun ComputerUse."""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional, Tuple

from astrarun.capabilities.models import CapabilityResult
from astrarun.computer_use.models import ControlType, UIElement, ActionBackend
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.computer_use.ui.automation")


class UIAutomationDriver:
    """
    Direct interface to Windows UI Automation accessibility tree and control patterns.
    """

    def enumerate_elements(self, hwnd: int, max_elements: int = 50) -> List[UIElement]:
        """Enumerate interactive UI elements within a window."""
        if sys.platform != "win32" or not hwnd:
            return []

        try:
            from astrarun.interaction.discovery import inspect_window_ui
            raw_controls = inspect_window_ui(hwnd, max_elements=max_elements)
            result = []
            for c in raw_controls:
                c_type = ControlType.UNKNOWN
                try:
                    c_type = ControlType(c.control_type.value)
                except Exception:
                    pass
                result.append(
                    UIElement(
                        automation_id=c.automation_id,
                        name=c.name,
                        control_type=c_type,
                        hwnd=c.hwnd,
                        bounds=c.bounds,
                        is_enabled=getattr(c, "is_enabled", True),
                        is_focused=getattr(c, "is_focused", False),
                        backend=ActionBackend.UIA,
                    )
                )
            return result
        except Exception as ex:
            logger.debug("Failed enumerating UI elements: %s", ex)
            return []

    def invoke(self, element: UIElement) -> CapabilityResult:
        """Invoke element via InvokePattern."""
        from astrarun.interaction.controller import invoke_element
        from astrarun.interaction.models import UIElementRef

        ref = UIElementRef(
            name=element.name,
            automation_id=element.automation_id,
            control_type=element.control_type.value,
            hwnd=element.hwnd,
            bounds=element.bounds,
        )
        ok, msg, err = invoke_element(ref)
        return CapabilityResult(success=ok, capability="invoke_ui_element", message=msg)

    def set_value(self, element: UIElement, value: str) -> CapabilityResult:
        """Set value via ValuePattern."""
        from astrarun.interaction.controller import set_element_value
        from astrarun.interaction.models import UIElementRef

        ref = UIElementRef(
            name=element.name,
            automation_id=element.automation_id,
            control_type=element.control_type.value,
            hwnd=element.hwnd,
            bounds=element.bounds,
        )
        ok, msg, err = set_element_value(ref, value)
        return CapabilityResult(success=ok, capability="set_element_value", message=msg)
