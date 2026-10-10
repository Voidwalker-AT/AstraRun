"""Unified ComputerUseController orchestrating desktop, ui, browser, input, and perception."""

from __future__ import annotations

import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

from astrarun.capabilities.models import CapabilityResult
from astrarun.computer_use.browser import BrowserCDPDriver
from astrarun.computer_use.desktop import DesktopLifecycle
from astrarun.computer_use.input import PhysicalInputDriver
from astrarun.computer_use.models import (
    ActionBackend,
    ComputerUseObservation,
    ControlType,
    RecoveryAction,
    UIAction,
    UIElement,
    VerificationCondition,
    VerificationResult,
)
from astrarun.computer_use.perception import ScreenPerception
from astrarun.computer_use.session import ApplicationSession, SessionState
from astrarun.computer_use.ui import UIAutomationDriver
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.computer_use.controller")


class ComputerUseController:
    """
    Unified Computer-Use controller providing universal Observe, Act, Verify, Recover primitives
    across Windows desktop, UI automation, browser tabs, and perception.
    Does NOT contain semantic intent logic (which is owned by Brain).
    """

    def __init__(
        self,
        desktop: Optional[DesktopLifecycle] = None,
        ui: Optional[UIAutomationDriver] = None,
        browser: Optional[BrowserCDPDriver] = None,
        physical_input: Optional[PhysicalInputDriver] = None,
        perception: Optional[ScreenPerception] = None,
    ) -> None:
        self.desktop = desktop or DesktopLifecycle()
        self.ui = ui or UIAutomationDriver()
        self.browser = browser or BrowserCDPDriver()
        self.physical_input = physical_input or PhysicalInputDriver()
        self.perception = perception or ScreenPerception()
        self._sessions: Dict[str, ApplicationSession] = {}

    # -------------------------------------------------------------------------
    # 1. OBSERVE: Multi-modal desktop and window observation
    # -------------------------------------------------------------------------
    def observe(self, window_target: Optional[int | str] = None) -> ComputerUseObservation:
        """Capture normalized state: active window, interactable elements, browser tabs, takeover."""
        t_start = time.perf_counter()
        active_hwnd = 0
        window_title = ""
        app_name = ""

        # 1. Physical user takeover check
        user_intervening = self.physical_input.check_user_takeover()

        # 2. Window observation via Win32
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            active_hwnd = user32.GetForegroundWindow()
            if active_hwnd:
                length = user32.GetWindowTextLengthW(active_hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(active_hwnd, buf, length + 1)
                window_title = buf.value

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(active_hwnd, ctypes.byref(pid))
                try:
                    p = psutil.Process(pid.value)
                    app_name = p.name()
                except Exception:
                    pass

        # 3. UIA interactable elements scan
        target_hwnd = int(window_target) if isinstance(window_target, int) else active_hwnd
        elements_list: List[Dict[str, Any]] = []
        focused_dict: Optional[Dict[str, Any]] = None

        if target_hwnd:
            ui_elements = self.ui.enumerate_elements(target_hwnd, max_elements=25)
            for el in ui_elements:
                d = {
                    "name": el.name,
                    "automation_id": el.automation_id,
                    "control_type": el.control_type.value,
                    "bounds": el.bounds,
                    "is_enabled": el.is_enabled,
                }
                elements_list.append(d)
                if el.is_focused:
                    focused_dict = d

        # 4. Browser tabs scan
        browser_tabs = self.browser.get_open_tabs()

        return ComputerUseObservation(
            timestamp=time.time(),
            application_identity=app_name or None,
            window_identity=active_hwnd or None,
            window_title=window_title,
            focused_element=focused_dict,
            interactable_elements=elements_list,
            available_actions=["click", "type", "shortcut", "scroll", "close"],
            browser_sessions=browser_tabs,
            user_taking_over=user_intervening,
            source_backend=ActionBackend.UIA,
            confidence=1.0,
            provenance={"latency_ms": round((time.perf_counter() - t_start) * 1000, 2)},
        )

    # -------------------------------------------------------------------------
    # 2. FIND: Control and Element Targeting
    # -------------------------------------------------------------------------
    def find_element(self, target: str, hwnd: Optional[int] = None) -> Optional[UIElement]:
        """Find accessible UI control via AutomationId, Name, or ControlType."""
        target_hwnd = hwnd or self.observe().window_identity
        if not target_hwnd:
            return None

        elements = self.ui.enumerate_elements(target_hwnd, max_elements=50)
        target_l = target.lower()
        for el in elements:
            if target_l == el.name.lower() or target_l == el.automation_id.lower():
                return el
        for el in elements:
            if target_l in el.name.lower() or target_l in el.automation_id.lower():
                return el
        return None

    # -------------------------------------------------------------------------
    # 3. INTERACT: Execution with UIA & Physical Fallback
    # -------------------------------------------------------------------------
    def interact(self, action: UIAction) -> CapabilityResult:
        """Execute interaction governed by ActionGate and physical takeover checks."""
        if self.physical_input.check_user_takeover():
            logger.warning("Interaction blocked: physical user takeover active.")
            return CapabilityResult.error("Interaction paused: user physical activity detected.")

        if action.action_type == "click":
            if action.element:
                return self.ui.invoke(action.element)
            elif action.target and action.hwnd:
                elem = self.find_element(action.target, action.hwnd)
                if elem:
                    return self.ui.invoke(elem)
            elif action.coordinates:
                cx, cy = action.coordinates
                return self.physical_input.click_at(cx, cy)
            return CapabilityResult.error(f"Could not resolve target '{action.target}' to click.")

        elif action.action_type == "type":
            text = action.text or ""
            return self.physical_input.type_text(text=text, hwnd=action.hwnd)

        elif action.action_type == "shortcut":
            from astrarun.interaction.keyboard import dispatch_shortcut, parse_shortcut
            sc = parse_shortcut(action.shortcut or "")
            ok = dispatch_shortcut(sc, target_hwnd=action.hwnd)
            return CapabilityResult(
                success=ok,
                capability="press_keyboard_shortcut",
                message=f"Dispatched shortcut {action.shortcut}",
            )

        return CapabilityResult.error(f"Unsupported action type: {action.action_type}")

    # -------------------------------------------------------------------------
    # 4. VERIFY: Environmental Ground-Truth Verification
    # -------------------------------------------------------------------------
    def verify(self, condition: VerificationCondition) -> VerificationResult:
        """Verify environmental side-effects."""
        t0 = time.perf_counter()
        deadline = time.time() + condition.timeout_seconds

        while time.time() <= deadline:
            if condition.condition_type == "window_visible":
                obs = self.observe()
                if condition.target and condition.target.lower() in obs.window_title.lower():
                    return VerificationResult(
                        verified=True,
                        condition_type=condition.condition_type,
                        observed_value=obs.window_title,
                        message=f"Verified window visible matching '{condition.target}'.",
                        latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                    )
            elif condition.condition_type == "process_running":
                target_stem = (condition.target or "").lower().replace(".exe", "")
                for p in psutil.process_iter(["name"]):
                    try:
                        p_stem = (p.info["name"] or "").lower().replace(".exe", "")
                        if p_stem == target_stem:
                            return VerificationResult(
                                verified=True,
                                condition_type=condition.condition_type,
                                observed_value=p.info["name"],
                                message=f"Verified process '{condition.target}' running.",
                                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
                            )
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            time.sleep(0.1)

        return VerificationResult(
            verified=False,
            condition_type=condition.condition_type,
            observed_value=None,
            message=f"Verification timed out for condition '{condition.condition_type}'.",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )

    # -------------------------------------------------------------------------
    # 5. RECOVER: Bounded Recovery & Re-observation
    # -------------------------------------------------------------------------
    def recover(self, error_message: str, attempt: int = 1, max_attempts: int = 3) -> RecoveryAction:
        """Provide bounded recovery recommendation."""
        if attempt >= max_attempts:
            return RecoveryAction(
                action="fail",
                reason=f"Recovery budget exceeded ({attempt}/{max_attempts}): {error_message}",
                attempt_number=attempt,
                max_attempts=max_attempts,
            )

        if "stale" in error_message.lower() or "not available" in error_message.lower():
            return RecoveryAction(
                action="reobserve",
                reason="Element handle is stale. Re-observing current window state.",
                attempt_number=attempt + 1,
                max_attempts=max_attempts,
            )

        if "dialog" in error_message.lower() or "modal" in error_message.lower():
            return RecoveryAction(
                action="dismiss_dialog",
                reason="Modal dialog detected blocking target. Attempting Escape dismiss.",
                attempt_number=attempt + 1,
                max_attempts=max_attempts,
            )

        return RecoveryAction(
            action="retry",
            reason=f"Transient failure detected: {error_message}. Retrying step.",
            attempt_number=attempt + 1,
            max_attempts=max_attempts,
        )
