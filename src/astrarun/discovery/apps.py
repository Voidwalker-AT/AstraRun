"""Application discovery engine for Windows environments."""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

from astrarun.core.logging import get_logger
from astrarun.core.models import AppInfo

logger = get_logger("astrarun.discovery.apps")

# Standard executable keys to prioritize and discover
STANDARD_APPS = [
    ("notepad", "Notepad", "notepad.exe"),
    ("calc", "Calculator", "calc.exe"),
    ("wt", "Windows Terminal", "wt.exe"),
    ("pwsh", "PowerShell 7", "pwsh.exe"),
    ("powershell", "Windows PowerShell", "powershell.exe"),
    ("cmd", "Command Prompt", "cmd.exe"),
    ("explorer", "File Explorer", "explorer.exe"),
    ("code", "Visual Studio Code", "code.exe"),
    ("vivaldi", "Vivaldi Browser", "vivaldi.exe"),
]


class AppDiscoveryCache:
    """Discovers and caches local executable applications."""

    def __init__(self, configured_apps: dict[str, AppInfo] | None = None):
        self._apps: dict[str, AppInfo] = {}
        self._configured_apps = configured_apps or {}
        self.refresh()

    @property
    def apps(self) -> dict[str, AppInfo]:
        """Return the dictionary of discovered applications."""
        return self._apps

    def get(self, key: str) -> AppInfo | None:
        """Get application info by key."""
        return self._apps.get(key.lower())

    def refresh(self) -> None:
        """Scan system and build application cache."""
        discovered: dict[str, AppInfo] = {}

        # 1. Discover via Windows App Paths Registry
        app_paths = self._scan_app_paths_registry()
        for key, path in app_paths.items():
            if Path(path).exists():
                discovered[key] = AppInfo(
                    key=key,
                    name=Path(path).stem.title(),
                    path=path,
                    description=f"Discovered via App Paths: {Path(path).name}"
                )

        # 2. Discover via PATH
        for key, display_name, exe_name in STANDARD_APPS:
            if key not in discovered or not Path(discovered[key].path).exists():
                resolved = shutil.which(exe_name) or shutil.which(key)
                if resolved and Path(resolved).exists():
                    discovered[key] = AppInfo(
                        key=key,
                        name=display_name,
                        path=resolved,
                        description=f"Discovered via PATH: {exe_name}"
                    )

        # 3. Check Known Installation Fallbacks (especially for WindowsApps and Vivaldi)
        self._scan_known_fallback_locations(discovered)

        # 4. Scan Start Menu Shortcuts (.lnk)
        self._scan_start_menu_shortcuts(discovered)

        # 5. Apply configured apps (highest precedence)
        for key, app_info in self._configured_apps.items():
            discovered[key] = app_info

        self._apps = discovered
        logger.info("Application discovery completed: %d apps cached.", len(self._apps))

    def _scan_app_paths_registry(self) -> dict[str, str]:
        """Scan Windows App Paths registry keys in HKLM and HKCU."""
        results: dict[str, str] = {}
        if sys.platform != "win32":
            return results

        import winreg

        subkeys = [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        ]

        for hkey, subkey_path in subkeys:
            try:
                with winreg.OpenKey(hkey, subkey_path) as root_key:
                    num_subkeys = winreg.QueryInfoKey(root_key)[0]
                    for i in range(num_subkeys):
                        try:
                            app_subkey_name = winreg.EnumKey(root_key, i)
                            with winreg.OpenKey(root_key, app_subkey_name) as app_key:
                                try:
                                    app_path, _ = winreg.QueryValueEx(app_key, "")
                                    if app_path:
                                        # Clean quotes and strip whitespace
                                        clean_path = str(app_path).strip().strip('"')
                                        stem = Path(app_subkey_name).stem.lower()
                                        if Path(clean_path).exists():
                                            results[stem] = clean_path
                                            # Also store full name if distinct
                                            results[app_subkey_name.lower()] = clean_path
                                except OSError:
                                    continue
                        except OSError:
                            continue
            except OSError as err:
                logger.debug("Could not open App Paths registry key %s: %s", subkey_path, err)
                continue

        return results

    def _scan_known_fallback_locations(self, discovered: dict[str, AppInfo]) -> None:
        """Scan common local app paths if not already resolved."""
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        system_root = os.environ.get("SystemRoot", r"C:\Windows")

        candidates = {
            "wt": [
                Path(local_app_data) / "Microsoft" / "WindowsApps" / "wt.exe",
            ],
            "code": [
                Path(local_app_data) / "Programs" / "Microsoft VS Code" / "Code.exe",
                Path(program_files) / "Microsoft VS Code" / "Code.exe",
            ],
            "vivaldi": [
                Path("E:/vivaldi/Application/vivaldi.exe"),
                Path(local_app_data) / "Vivaldi" / "Application" / "vivaldi.exe",
                Path(program_files) / "Vivaldi" / "Application" / "vivaldi.exe",
            ],
            "notepad": [
                Path(system_root) / "System32" / "notepad.exe",
            ],
            "calc": [
                Path(system_root) / "System32" / "calc.exe",
            ],
            "explorer": [
                Path(system_root) / "explorer.exe",
            ],
            "cmd": [
                Path(system_root) / "System32" / "cmd.exe",
            ],
            "powershell": [
                Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe",
            ]
        }

        for key, paths in candidates.items():
            if key not in discovered or not Path(discovered[key].path).exists():
                for p in paths:
                    if p.exists():
                        discovered[key] = AppInfo(
                            key=key,
                            name=p.stem.title(),
                            path=str(p),
                            description=f"Discovered via fallback path: {p}"
                        )
                        break

    def _scan_start_menu_shortcuts(self, discovered: dict[str, AppInfo]) -> None:
        """Scan Start Menu Programs directories for application shortcuts (.lnk)."""
        if sys.platform != "win32":
            return

        start_menu_dirs = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            start_menu_dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        programdata = os.environ.get("PROGRAMDATA")
        if programdata:
            start_menu_dirs.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

        exclude_words = {"uninstall", "help", "documentation", "readme", "website", "remove", "setup", "license"}

        for menu_dir in start_menu_dirs:
            if not menu_dir.exists():
                continue
            try:
                for lnk in menu_dir.rglob("*.lnk"):
                    stem_clean = lnk.stem.strip()
                    lower_stem = stem_clean.lower()

                    # Filter out uninstaller/help shortcuts
                    if any(w in lower_stem for w in exclude_words):
                        continue

                    norm_key = re.sub(r"[^a-zA-Z0-9]+", "", lower_stem)
                    if not norm_key:
                        continue

                    app_info = AppInfo(
                        key=lower_stem,
                        name=stem_clean,
                        path=str(lnk.resolve()),
                        description=f"Start Menu Shortcut: {stem_clean}"
                    )

                    if lower_stem not in discovered:
                        discovered[lower_stem] = app_info
                    if norm_key not in discovered:
                        discovered[norm_key] = app_info
            except Exception as err:
                logger.debug("Error scanning Start Menu at %s: %s", menu_dir, err)

        self._apps = discovered


def discover_all_apps() -> dict[str, AppInfo]:
    """Helper to discover all local applications via AppDiscoveryCache."""
    return AppDiscoveryCache().apps
