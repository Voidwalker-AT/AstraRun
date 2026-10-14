"""Centralized, resilient Windows UI Automation COM loader for AstraRun.

Guarantees UIAutomationCore.dll type library generation with comtypes,
preventing module generation races and import errors across threads and processes.
"""

from __future__ import annotations

import sys
import threading
from typing import Any, Optional

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.computer_use.ui.uia_support")

_lock = threading.Lock()
_uia_module: Optional[Any] = None


def get_uia_module() -> Any:
    """Return the generated or loaded comtypes UIAutomationClient module safely."""
    global _uia_module
    if _uia_module is not None:
        return _uia_module

    with _lock:
        if _uia_module is not None:
            return _uia_module

        if sys.platform != "win32":
            return None

        import comtypes.client

        try:
            from comtypes.gen import UIAutomationClient
            _uia_module = UIAutomationClient
            return _uia_module
        except (ImportError, AttributeError):
            pass

        try:
            # Force generation of UIAutomationClient COM wrapper
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient
            _uia_module = UIAutomationClient
            return _uia_module
        except Exception as ex:
            logger.error("Failed to load UIAutomationCore.dll COM module: %s", ex)
            return None


def get_uia_interface() -> Optional[Any]:
    """Create and return a CUIAutomation COM client instance."""
    mod = get_uia_module()
    if not mod:
        return None
    try:
        import comtypes.client
        return comtypes.client.CreateObject(
            mod.CUIAutomation,
            interface=mod.IUIAutomation,
        )
    except Exception as ex:
        logger.error("Failed to instantiate IUIAutomation COM object: %s", ex)
        return None
