"""Browser CDP automation driver for AstraRun ComputerUse."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from astrarun.capabilities.models import CapabilityResult
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.computer_use.browser.cdp")


class BrowserCDPDriver:
    """
    Manages browser automation sessions via Chrome DevTools Protocol / WebDriver.
    """

    def __init__(self, browser_service: Optional[Any] = None) -> None:
        self.service = browser_service

    def get_open_tabs(self) -> List[Dict[str, Any]]:
        """List open browser tabs."""
        if self.service and hasattr(self.service, "get_open_tabs"):
            try:
                return self.service.get_open_tabs()
            except Exception:
                pass
        return []

    def navigate(self, url: str) -> CapabilityResult:
        """Navigate active browser session to URL."""
        if self.service and hasattr(self.service, "navigate"):
            try:
                ok = self.service.navigate(url)
                return CapabilityResult(success=ok, capability="open_url", message=f"Navigated to {url}")
            except Exception as e:
                return CapabilityResult.error(f"Browser navigation failed: {e}")
        from astrarun.tools.browser import open_url
        ok = open_url(url)
        return CapabilityResult(success=ok, capability="open_url", message=f"Opened URL {url}")
