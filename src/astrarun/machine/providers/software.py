"""Scoped software and developer toolchain discovery for AstraRun 1.0.

Discovers relevant developer runtimes and desktop applications without
indiscriminate registry or filesystem crawling.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.machine.fact import FactAuthority, FreshnessClass, MachineFact
from astrarun.machine.providers.base import BaseMachineProvider

logger = get_logger("astrarun.machine.providers.software")

CREATE_NO_WINDOW = 0x08000000


class SoftwareProvider(BaseMachineProvider):
    """Scoped application and developer toolchain inventory provider."""

    name = "software"

    # Important development and system tools to probe
    TOOL_DEFINITIONS = {
        "git": {"cmd": "git", "version_arg": "--version"},
        "node": {"cmd": "node", "version_arg": "--version"},
        "npm": {"cmd": "npm", "version_arg": "--version"},
        "java": {"cmd": "javac", "version_arg": "-version"},
        "cl": {"cmd": "cl", "version_arg": None},
        "gcc": {"cmd": "gcc", "version_arg": "--version"},
        "docker": {"cmd": "docker", "version_arg": "--version"},
        "wsl": {"cmd": "wsl", "version_arg": "--status"},
        "nvcc": {"cmd": "nvcc", "version_arg": "--version"},
        "ffmpeg": {"cmd": "ffmpeg", "version_arg": "-version"},
        "7zip": {"cmd": "7z", "version_arg": None},
        "pwsh": {"cmd": "pwsh", "version_arg": "--version"},
        "powershell": {"cmd": "powershell", "version_arg": "$PSVersionTable.PSVersion.ToString()"},
    }

    # Browser discovery paths (LocalAppData, ProgramFiles, Scoop)
    BROWSER_SEARCH_PATHS = {
        "vivaldi": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Vivaldi" / "Application" / "vivaldi.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Vivaldi" / "Application" / "vivaldi.exe",
            Path.home() / "scoop" / "shims" / "vivaldi.exe",
        ],
        "chrome": [
            Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        ],
        "edge": [
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ],
        "firefox": [
            Path(os.environ.get("PROGRAMFILES", "")) / "Mozilla Firefox" / "firefox.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Mozilla Firefox" / "firefox.exe",
        ],
    }

    # Editor discovery
    EDITOR_SEARCH_PATHS = {
        "vscode": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd",
            Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft VS Code" / "bin" / "code.cmd",
            Path.home() / "scoop" / "shims" / "code.cmd",
        ],
        "cursor": [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "cursor" / "Cursor.exe",
        ],
    }

    def discover(self) -> List[MachineFact]:
        facts: List[MachineFact] = []
        now = time.time()

        # 1. Probe Developer Tools on PATH
        for tool_name, conf in self.TOOL_DEFINITIONS.items():
            installed, path, ver = self._probe_tool(conf["cmd"], conf["version_arg"])
            facts.append(MachineFact(
                key=f"software.tool.{tool_name}.installed",
                value=installed,
                source=FactAuthority.APPLICATION_PROBE,
                freshness_class=FreshnessClass.SESSION,
                observed_at=now,
            ))
            if installed and path:
                facts.append(MachineFact(
                    key=f"software.tool.{tool_name}.path",
                    value=str(path),
                    source=FactAuthority.APPLICATION_PROBE,
                    freshness_class=FreshnessClass.SESSION,
                    observed_at=now,
                ))
            if installed and ver:
                facts.append(MachineFact(
                    key=f"software.tool.{tool_name}.version",
                    value=ver,
                    source=FactAuthority.APPLICATION_PROBE,
                    freshness_class=FreshnessClass.SESSION,
                    observed_at=now,
                ))

        # 2. Probe Desktop Browsers
        for b_name, search_list in self.BROWSER_SEARCH_PATHS.items():
            b_path = self._find_first_existing(search_list) or shutil.which(b_name)
            installed = b_path is not None
            facts.append(MachineFact(
                key=f"software.app.{b_name}.installed",
                value=installed,
                source=FactAuthority.FILESYSTEM,
                freshness_class=FreshnessClass.SESSION,
                observed_at=now,
            ))
            if installed:
                facts.append(MachineFact(
                    key=f"software.app.{b_name}.path",
                    value=str(b_path),
                    source=FactAuthority.FILESYSTEM,
                    freshness_class=FreshnessClass.SESSION,
                    observed_at=now,
                ))
                # Capability flags
                facts.append(MachineFact(
                    key=f"software.app.{b_name}.automation_cdp",
                    value=True if b_name in {"vivaldi", "chrome", "edge"} else False,
                    source=FactAuthority.INFERRED,
                    freshness_class=FreshnessClass.STABLE,
                    observed_at=now,
                ))
                facts.append(MachineFact(
                    key=f"software.app.{b_name}.automation_uia",
                    value=True,
                    source=FactAuthority.INFERRED,
                    freshness_class=FreshnessClass.STABLE,
                    observed_at=now,
                ))

        # 3. Probe Editors / IDEs
        for e_name, search_list in self.EDITOR_SEARCH_PATHS.items():
            e_path = self._find_first_existing(search_list) or shutil.which("code" if e_name == "vscode" else e_name)
            installed = e_path is not None
            facts.append(MachineFact(
                key=f"software.app.{e_name}.installed",
                value=installed,
                source=FactAuthority.FILESYSTEM,
                freshness_class=FreshnessClass.SESSION,
                observed_at=now,
            ))
            if installed:
                facts.append(MachineFact(
                    key=f"software.app.{e_name}.path",
                    value=str(e_path),
                    source=FactAuthority.FILESYSTEM,
                    freshness_class=FreshnessClass.SESSION,
                    observed_at=now,
                ))
                facts.append(MachineFact(
                    key=f"software.app.{e_name}.cli_available",
                    value=True,
                    source=FactAuthority.INFERRED,
                    freshness_class=FreshnessClass.SESSION,
                    observed_at=now,
                ))

        return facts

    def _probe_tool(self, cmd_name: str, version_arg: Optional[str]) -> Tuple[bool, Optional[str], Optional[str]]:
        """Safely probe if executable exists and read its version output headlessly."""
        exe_path = shutil.which(cmd_name)
        if not exe_path:
            return False, None, None

        if not version_arg:
            return True, exe_path, None

        version_str: Optional[str] = None
        try:
            full_cmd = [exe_path, version_arg]
            res = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=2.0,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            out = res.stdout.strip() or res.stderr.strip()
            if out:
                # Extract first informative line
                first_line = out.splitlines()[0].strip()
                version_str = first_line[:80]
        except Exception:
            pass

        return True, exe_path, version_str

    def _find_first_existing(self, paths: List[Path]) -> Optional[Path]:
        for p in paths:
            try:
                if p.exists() and p.is_file():
                    return p
            except Exception:
                continue
        return None
