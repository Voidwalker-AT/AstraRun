"""Machine and workstation environment observer for AstraRun v0.11 agent runtime."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import time
from typing import Any, Optional

from astrarun.agent.models import Observation
from astrarun.capabilities.schema import InteractionTier
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.agent.observer")


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_byte),
        ("BatteryFlag", ctypes.c_byte),
        ("BatteryLifePercent", ctypes.c_byte),
        ("SystemStatusFlag", ctypes.c_byte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


class MachineObserver:
    """Captures real-time workstation state: foreground window, power, Wi-Fi, and active processes."""

    def __init__(self):
        self._user32 = None
        self._kernel32 = None
        if sys.platform == "win32":
            try:
                self._user32 = ctypes.windll.user32
                self._kernel32 = ctypes.windll.kernel32
            except Exception as e:
                logger.warning("Failed to initialize Win32 libraries for observer: %s", e)

    def get_foreground_window_info(self) -> dict[str, Any]:
        """Query currently active foreground window details via Win32."""
        if not self._user32:
            return {"hwnd": 0, "title": "", "pid": 0}

        try:
            hwnd = self._user32.GetForegroundWindow()
            if not hwnd:
                return {"hwnd": 0, "title": "", "pid": 0}

            length = self._user32.GetWindowTextLengthW(hwnd)
            title = ""
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                self._user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value

            pid = ctypes.wintypes.DWORD()
            self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            return {
                "hwnd": hwnd,
                "title": title,
                "pid": pid.value,
            }
        except Exception as exc:
            logger.debug("Error getting foreground window info: %s", exc)
            return {"hwnd": 0, "title": "", "pid": 0}

    def get_power_status(self) -> dict[str, Any]:
        """Query battery percentage and AC power status via GetSystemPowerStatus (Tier A)."""
        if not self._kernel32:
            return {"available": False}

        try:
            status = SYSTEM_POWER_STATUS()
            if self._kernel32.GetSystemPowerStatus(ctypes.byref(status)):
                ac_connected = (status.ACLineStatus == 1)
                battery_pct = int(status.BatteryLifePercent) if status.BatteryLifePercent <= 100 else None
                return {
                    "available": True,
                    "ac_connected": ac_connected,
                    "battery_pct": battery_pct,
                    "battery_flag": int(status.BatteryFlag),
                }
        except Exception as exc:
            logger.debug("Error reading power status: %s", exc)

        return {"available": False}

    def get_machine_state(self) -> dict[str, Any]:
        """Capture comprehensive snapshot of current machine state."""
        state: dict[str, Any] = {
            "timestamp": time.time(),
            "foreground": self.get_foreground_window_info(),
            "power": self.get_power_status(),
        }

        # Query native Wi-Fi connection if available
        try:
            from astrarun.tools.wifi import _wifi_client
            if _wifi_client.is_available:
                networks = _wifi_client.get_networks()
                active = next((n for n in networks if n.connected), None)
                if active:
                    state["wifi"] = {
                        "connected": True,
                        "ssid": active.ssid,
                        "signal_quality": active.signal_quality,
                    }
                else:
                    state["wifi"] = {"connected": False}
        except Exception:
            state["wifi"] = {"connected": False}

        return state

    def capture_observation(
        self,
        step_id: str,
        raw_output: Any = None,
        extracted_facts: Optional[dict[str, Any]] = None,
        tier: InteractionTier = InteractionTier.TIER_A_NATIVE,
    ) -> Observation:
        """Construct a structured Observation with machine state snapshot."""
        machine_state = self.get_machine_state()
        facts = extracted_facts.copy() if extracted_facts else {}

        # Augment facts with machine state context
        if "foreground_window" not in facts:
            facts["foreground_window"] = machine_state["foreground"].get("title", "")
        if "foreground_hwnd" not in facts:
            facts["foreground_hwnd"] = machine_state["foreground"].get("hwnd", 0)

        return Observation(
            step_id=step_id,
            timestamp=time.time(),
            machine_state=machine_state,
            raw_output=raw_output,
            extracted_facts=facts,
            tier=tier,
        )


# Global observer instance
global_observer = MachineObserver()
