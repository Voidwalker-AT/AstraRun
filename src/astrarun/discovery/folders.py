"""Known folders discovery and resolution for Windows environments."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from astrarun.core.logging import get_logger
from astrarun.core.models import FolderInfo

logger = get_logger("astrarun.discovery.folders")


class FolderResolver:
    """Resolves Windows known folders and platform workspace paths."""

    def __init__(self, workspace_root: Path | str | None = None):
        if workspace_root:
            self.workspace_root = Path(workspace_root).resolve()
        else:
            from astrarun.core.paths import AstraPaths
            self.workspace_root = AstraPaths.workspace_root()

        self._folders: dict[str, FolderInfo] = {}
        self.refresh()

    @property
    def folders(self) -> dict[str, FolderInfo]:
        """Return the dictionary of recognized folders."""
        return self._folders

    def get(self, key: str) -> FolderInfo | None:
        """Get folder info by normalized alias or key."""
        return self._folders.get(key.lower())

    def refresh(self) -> None:
        """Discover and resolve all known directories."""
        user_home = Path.home()
        raw_folders: dict[str, Path] = {
            "downloads": user_home / "Downloads",
            "documents": user_home / "Documents",
            "desktop": user_home / "Desktop",
            "pictures": user_home / "Pictures",
            "videos": user_home / "Videos",
            "music": user_home / "Music",
            "workspace": self.workspace_root,
            "active": self.workspace_root / "Active",
            "active projects": self.workspace_root / "Active",
        }

        # Query Windows Registry for user shell folders if on Windows
        if sys.platform == "win32":
            registry_folders = self._query_user_shell_folders()
            for k, p in registry_folders.items():
                if p.exists():
                    raw_folders[k] = p

        resolved: dict[str, FolderInfo] = {}
        for key, folder_path in raw_folders.items():
            if folder_path.exists():
                resolved[key] = FolderInfo(
                    key=key,
                    name=folder_path.name or key.title(),
                    path=str(folder_path.resolve()),
                    description=f"Directory at {folder_path.resolve()}"
                )

        self._folders = resolved
        logger.info("Folder discovery completed: %d folders resolved.", len(self._folders))

    def _query_user_shell_folders(self) -> dict[str, Path]:
        """Query User Shell Folders from HKCU."""
        results: dict[str, Path] = {}
        import winreg

        guid_map = {
            "{374DE290-123F-4565-9164-39C4925E467B}": "downloads",
            "Personal": "documents",
            "Desktop": "desktop",
            "My Pictures": "pictures",
            "My Video": "videos",
            "My Music": "music",
        }

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            ) as key:
                for reg_value_name, folder_key in guid_map.items():
                    try:
                        val, _ = winreg.QueryValueEx(key, reg_value_name)
                        if val:
                            expanded = os.path.expandvars(str(val))
                            results[folder_key] = Path(expanded)
                    except OSError:
                        continue
        except OSError as err:
            logger.debug("Failed reading User Shell Folders from registry: %s", err)

        return results
