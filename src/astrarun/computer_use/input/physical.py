"""Physical input and user takeover controller for AstraRun ComputerUse."""

from __future__ import annotations

from typing import Optional, Tuple
from astrarun.capabilities.models import CapabilityResult
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.computer_use.input.physical")


class PhysicalInputDriver:
    """
    Direct physical mouse and keyboard driver with mandatory user takeover detection.
    """

    def __init__(self) -> None:
        pass

    def check_user_takeover(self) -> bool:
        """Check whether physical human user is currently intervening on input devices."""
        try:
            from astrarun.perception.input import PhysicalInputController
            pic = PhysicalInputController.get_instance()
            return pic.check_user_takeover()
        except Exception:
            return False

    def click_at(self, x: int, y: int, button: str = "left") -> CapabilityResult:
        """Inject physical mouse click at screen coordinates with takeover guard."""
        if self.check_user_takeover():
            return CapabilityResult.error("Interaction aborted: user physical input detected.")

        try:
            from astrarun.perception.input import PhysicalInputController
            pic = PhysicalInputController.get_instance()
            ok, msg = pic.click_at(x, y, button=button)
            return CapabilityResult(success=ok, capability="click_coordinates", message=msg)
        except Exception as e:
            return CapabilityResult.error(f"Click failed: {e}")

    def type_text(self, text: str, hwnd: Optional[int] = None) -> CapabilityResult:
        """Inject keystrokes into target window."""
        if self.check_user_takeover():
            return CapabilityResult.error("Typing aborted: user physical input detected.")

        from astrarun.interaction.controller import type_into_window
        ok, msg, err = type_into_window(text=text, hwnd=hwnd)
        return CapabilityResult(success=ok, capability="type_into_window", message=msg)
