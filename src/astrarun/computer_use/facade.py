"""Unified ComputerUse facade consolidating desktop, UI automation, browser, and perception."""

from __future__ import annotations

import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import psutil

from astrarun.core.logging import get_logger
from astrarun.core.models import AppInfo
from astrarun.capabilities.models import CapabilityResult
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
from astrarun.discovery.entity_resolver import ResolvedEntity, SemanticEntityResolver

logger = get_logger("astrarun.computer_use.facade")


class ComputerUse:
    """
    Unified facade for AstraRun computer-use capabilities.
    Consolidates existing Desktop, UIA, Browser, Physical Input, and Resource Lifecycle
    modules into a cohesive interface without redundant wrappers.
    """

    _instance: Optional[ComputerUse] = None

    def __init__(
        self,
        app_cache: Optional[Any] = None,
        entity_resolver: Optional[SemanticEntityResolver] = None,
        execution_broker: Optional[Any] = None,
        resource_ledger: Optional[Any] = None,
        browser_service: Optional[Any] = None,
    ) -> None:
        self.app_cache = app_cache
        self.entity_resolver = entity_resolver
        self.execution_broker = execution_broker
        self.resource_ledger = resource_ledger
        self.browser_service = browser_service

    @classmethod
    def get_instance(cls) -> ComputerUse:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -------------------------------------------------------------------------
    # 1. OBSERVE: Multi-modal desktop and window observation
    def observe_world_state(self, target_hwnd: Optional[int] = None, task_id: Optional[str] = None):
        """Capture live DesktopWorldState representation."""
        from astrarun.computer_use.observation import DesktopObserver
        return DesktopObserver.get_instance().observe(target_hwnd=target_hwnd, task_id=task_id)

    def observe(self, window_target: Optional[int | str] = None) -> ComputerUseObservation:
        """Capture normalized state: active window, interactable elements, browser tabs, takeover."""
        t_start = time.perf_counter()
        from astrarun.computer_use.hooks.desktop_attach import ensure_desktop_attached
        ensure_desktop_attached()

        active_hwnd = 0
        window_title = ""
        app_name = ""
        user_intervening = False

        # 1. Physical user takeover check
        try:
            from astrarun.perception.input import PhysicalInputController
            pic = PhysicalInputController.get_instance()
            user_intervening = pic.check_user_takeover()
        except Exception:
            pass

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

        # Resolve target HWND
        target_hwnd = 0
        if isinstance(window_target, int) and window_target > 0:
            target_hwnd = window_target
        elif isinstance(window_target, str) and window_target:
            try:
                from astrarun.windows.resolver import WindowResolver
                res = WindowResolver().resolve(window_target)
                if res.window and res.window.hwnd:
                    target_hwnd = res.window.hwnd
                elif res.candidates:
                    target_hwnd = res.candidates[0].hwnd
            except Exception:
                pass
        if not target_hwnd:
            target_hwnd = active_hwnd

        # If target window is specific and different from active_hwnd, query its title/app
        if target_hwnd and target_hwnd != active_hwnd and sys.platform == "win32":
            try:
                length = user32.GetWindowTextLengthW(target_hwnd)
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(target_hwnd, buf, length + 1)
                if buf.value:
                    window_title = buf.value
                t_pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(target_hwnd, ctypes.byref(t_pid))
                if t_pid.value:
                    p = psutil.Process(t_pid.value)
                    app_name = p.name()
            except Exception:
                pass

        # 3. UIA interactable elements scan
        elements: List[Dict[str, Any]] = []
        focused_dict: Optional[Dict[str, Any]] = None

        if target_hwnd and sys.platform == "win32":
            try:
                from astrarun.interaction.discovery import enumerate_window_controls
                raw_controls = enumerate_window_controls(target_hwnd, max_elements=25)
                for c in raw_controls:
                    c_dict = {
                        "name": c.name,
                        "automation_id": c.automation_id,
                        "control_type": getattr(c.control_type, "value", str(c.control_type)),
                        "bounds": c.bounds,
                        "is_enabled": getattr(c, "is_enabled", True),
                    }
                    elements.append(c_dict)
                    if getattr(c, "is_focused", False):
                        focused_dict = c_dict
            except Exception as ex:
                logger.debug("UIA controls enumeration omitted: %s", ex)

        # 4. Browser tabs scan
        browser_tabs: List[Dict[str, Any]] = []
        if self.browser_service:
            try:
                if hasattr(self.browser_service, "get_open_tabs"):
                    browser_tabs = self.browser_service.get_open_tabs()
            except Exception:
                pass

        obs = ComputerUseObservation(
            timestamp=time.time(),
            application_identity=app_name or None,
            window_identity=active_hwnd or None,
            window_title=window_title,
            focused_element=focused_dict,
            interactable_elements=elements,
            available_actions=["click", "type", "shortcut", "scroll", "close"],
            browser_sessions=browser_tabs,
            user_taking_over=user_intervening,
            source_backend=ActionBackend.UIA,
            confidence=1.0,
            provenance={"latency_ms": round((time.perf_counter() - t_start) * 1000, 2)},
        )
        return obs

    # -------------------------------------------------------------------------
    # 2. DISCOVER & RESOLVE: Dynamic Application Discovery
    # -------------------------------------------------------------------------
    def discover(self, query: str = "") -> List[AppInfo]:
        """Discover installed applications from AppDiscoveryCache."""
        if not self.app_cache and hasattr(self, "_get_default_cache"):
            self.app_cache = self._get_default_cache()
        if not self.app_cache:
            from astrarun.discovery.apps import AppDiscoveryCache
            self.app_cache = AppDiscoveryCache()
        all_apps = list(self.app_cache.apps.values())
        if not query:
            return all_apps
        q_lower = query.lower()
        return [a for a in all_apps if q_lower in a.name.lower() or q_lower in a.key.lower()]

    def resolve(self, query: str) -> Optional[ResolvedEntity]:
        """Resolve natural language query to canonical desktop application."""
        if not self.entity_resolver:
            from astrarun.discovery.entity_resolver import SemanticEntityResolver
            self.entity_resolver = SemanticEntityResolver(app_cache=self.app_cache)
        return self.entity_resolver.resolve_application(query)

    # -------------------------------------------------------------------------
    # 3. FIND: Control and Element Targeting
    # -------------------------------------------------------------------------
    def find_element(self, target: str, hwnd: Optional[int] = None) -> Optional[UIElement]:
        """Find accessible UI control via AutomationId, Name, or ControlType."""
        if sys.platform != "win32":
            return None
        target_hwnd = hwnd
        if not target_hwnd:
            obs = self.observe()
            target_hwnd = obs.window_identity
        if not target_hwnd:
            return None

        try:
            from astrarun.interaction.discovery import resolve_element_by_semantic_target
            elem_ref = resolve_element_by_semantic_target(target_hwnd, target)
            if elem_ref:
                c_type = ControlType.UNKNOWN
                try:
                    c_type = ControlType(elem_ref.control_type.value)
                except Exception:
                    pass
                return UIElement(
                    automation_id=elem_ref.automation_id,
                    name=elem_ref.name,
                    control_type=c_type,
                    hwnd=elem_ref.hwnd,
                    bounds=elem_ref.bounds,
                    backend=ActionBackend.UIA,
                )
        except Exception as err:
            logger.debug("Failed finding element '%s': %s", target, err)
        return None

    # -------------------------------------------------------------------------
    # 4. INTERACT: Execution with UIA & Governed Coordinate Fallback
    # -------------------------------------------------------------------------
    def interact(self, action: UIAction) -> CapabilityResult:
        """Execute interaction: UIA pattern invocation with physical coordinate click fallback."""
        # Check user takeover safety invariant
        try:
            from astrarun.perception.input import PhysicalInputController
            pic = PhysicalInputController.get_instance()
            if pic.check_user_takeover():
                logger.warning("Interaction blocked: physical user takeover active.")
                return CapabilityResult.error("Interaction paused: user physical activity detected.")
        except Exception:
            pass

        if action.action_type == "click":
            from astrarun.interaction.controller import invoke_element
            from astrarun.interaction.models import UIElementRef
            elem_ref = None
            if action.element:
                elem_ref = UIElementRef(
                    name=action.element.name,
                    automation_id=action.element.automation_id,
                    control_type=action.element.control_type.value,
                    hwnd=action.element.hwnd,
                    bounds=action.element.bounds,
                )
            elif action.target and action.hwnd:
                found = self.find_element(action.target, action.hwnd)
                if found:
                    elem_ref = UIElementRef(
                        name=found.name,
                        automation_id=found.automation_id,
                        control_type=found.control_type.value,
                        hwnd=found.hwnd,
                        bounds=found.bounds,
                    )

            if elem_ref:
                ok, msg, err_code = invoke_element(elem_ref, force=action.force)
                return CapabilityResult(success=ok, capability="click_ui_element", message=msg)
            elif action.coordinates:
                # Direct governed coordinate click fallback
                cx, cy = action.coordinates
                from astrarun.perception.input import PhysicalInputController
                pic = PhysicalInputController.get_instance()
                ok, msg = pic.click_at(cx, cy, button="left")
                return CapabilityResult(success=ok, capability="click_coordinates", message=msg)

            return CapabilityResult.error(f"Could not resolve target element '{action.target}' to click.")

        elif action.action_type == "type":
            text = action.text or ""
            try:
                from astrarun.perception.input import NativeInputController
                ok, msg = NativeInputController().type_text(text, target_hwnd=action.hwnd)
                return CapabilityResult(success=ok, capability="type_text", message=msg)
            except Exception:
                from astrarun.interaction.keyboard import type_text_into_active
                ok, msg, _ = type_text_into_active(text)
                return CapabilityResult(success=ok, capability="type_text", message=msg)

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
    # 5. VERIFY: Environmental Ground-Truth Verification
    # -------------------------------------------------------------------------
    def verify(self, condition: VerificationCondition) -> VerificationResult:
        """Verify environmental side-effects (never equate API success with goal completion)."""
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
    # 6. RECOVER: Bounded Recovery & Re-observation
    # -------------------------------------------------------------------------
    def recover(self, error_message: str, attempt: int = 1, max_attempts: int = 3) -> RecoveryAction:
        """Provide bounded recovery recommendation (retry, re-observe, dismiss modal, or fail)."""
        if attempt >= max_attempts:
            return RecoveryAction(
                action="fail",
                reason=f"Recovery budget exceeded ({attempt}/{max_attempts}): {error_message}",
                attempt_number=attempt,
                max_attempts=max_attempts,
            )

        # Detect stale handle / modal obstruction
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
