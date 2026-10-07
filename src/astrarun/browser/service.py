"""Canonical Managed Browser Service for AstraRun.

Provides managed browser navigation, semantic DOM extraction, and element interaction
governed strictly under ExecutionBroker and ActionGate policies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.perception.cdp import CDPProvider, DOMCompressor
from astrarun.perception.models import DOMElementObservation

logger = logging.getLogger("astrarun.browser.service")


@dataclass
class BrowserPageSnapshot:
    url: str
    title: str
    interactive_elements: List[Dict[str, Any]] = field(default_factory=list)
    compressed_text: str = ""
    element_count: int = 0


class BrowserService:
    """Canonical browser automation and inspection service."""

    _instance: Optional[BrowserService] = None

    def __init__(self, cdp_provider: Optional[CDPProvider] = None) -> None:
        self.cdp = cdp_provider or CDPProvider()
        self.compressor = DOMCompressor()
        self._current_page: Optional[BrowserPageSnapshot] = None

    @classmethod
    def get_instance(cls) -> BrowserService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def inspect_html(self, raw_html: str, url: str = "about:blank", title: str = "") -> BrowserPageSnapshot:
        """Parse raw HTML content into a semantic, token-compressed DOM snapshot."""
        compressed_text, elements = self.compressor.compress_html(raw_html)
        elem_dicts = [
            {
                "id": el.element_id,
                "tag": el.tag_name,
                "role": el.role,
                "text": el.text,
                "attributes": el.attributes,
            }
            for el in elements
        ]
        snapshot = BrowserPageSnapshot(
            url=url,
            title=title or url,
            interactive_elements=elem_dicts,
            compressed_text=compressed_text,
            element_count=len(elements),
        )
        self._current_page = snapshot
        logger.debug("Inspected HTML for %s: %d interactive elements", url, len(elements))
        return snapshot

    def get_current_page(self) -> Optional[BrowserPageSnapshot]:
        return self._current_page

    def open_local_fixture(self, fixture_path: Path | str) -> BrowserPageSnapshot:
        """Open and parse a local HTML fixture file into a DOM snapshot."""
        p = Path(fixture_path)
        if not p.exists():
            raise FileNotFoundError(f"Fixture not found at {fixture_path}")
        html_content = p.read_text(encoding="utf-8")
        title = p.stem.replace("_", " ").title()
        return self.inspect_html(raw_html=html_content, url=p.resolve().as_uri(), title=title)

    def launch_managed_browser(self, url: str = "about:blank", headless: bool = True, port: int = 9222) -> bool:
        """Launch an isolated browser instance with remote debugging."""
        import subprocess
        import sys
        from astrarun.core.paths import AstraPaths

        edge_paths = [
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        ]
        browser_exe = next((p for p in edge_paths if p.exists()), None)
        if not browser_exe:
            logger.warning("No managed browser binary found.")
            return False

        profile_dir = AstraPaths.temp_dir() / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(browser_exe),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
        ]
        if headless:
            cmd.append("--headless=new")
        cmd.append(url)

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )
            logger.info("Launched managed browser PID %d (%s)", self._proc.pid, browser_exe.name)
            return True
        except Exception as err:
            logger.error("Failed to launch managed browser: %s", err)
            return False

    def close_managed_browser(self) -> None:
        """Cleanly terminate managed browser process."""
        if hasattr(self, "_proc") and self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None

    def click_element_by_id(self, element_id: str) -> bool:
        """Simulate clicking an interactive element from the compressed DOM snapshot."""
        if not self._current_page:
            return False
        for el in self._current_page.interactive_elements:
            if el["id"] == element_id:
                logger.info("BrowserService clicked element %s (%s)", element_id, el.get("text", ""))
                return True
        return False

