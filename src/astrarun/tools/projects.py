"""Project-related workstation execution tools for AstraRun v0.6."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from astrarun.core.logging import get_logger
from astrarun.projects.registry import ProjectRegistry

logger = get_logger("astrarun.tools.projects")

_registry: Optional[ProjectRegistry] = None


def get_project_registry() -> ProjectRegistry:
    global _registry
    if _registry is None:
        _registry = ProjectRegistry()
    return _registry


def open_project_folder(project_id: str) -> bool:
    """
    Open the verified filesystem directory for a project in Windows File Explorer.
    Consumes a verified project ID, never arbitrary user paths.
    """
    reg = get_project_registry()
    path = reg.project_path(project_id)
    if not path or not path.exists():
        logger.error("Project folder not found on disk for project ID: %s", project_id)
        return False

    try:
        logger.info("Opening project folder: %s", path)
        os.startfile(str(path))
        return True
    except Exception as err:
        logger.error("Failed to open project folder %s: %s", path, err)
        return False


def open_project_in_vscode(project_id: str) -> bool:
    """
    Open the verified project in Visual Studio Code.
    Dispatches 'code <project_path>' via safe argv subprocess.
    """
    reg = get_project_registry()
    path = reg.project_path(project_id)
    if not path or not path.exists():
        logger.error("Project path not found on disk for project ID: %s", project_id)
        return False

    code_bin = shutil.which("code") or shutil.which("code.cmd")
    if not code_bin:
        # Fallback to default user install path if not directly on PATH
        local_code = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd"
        if local_code.exists():
            code_bin = str(local_code)

    if not code_bin:
        logger.error("VS Code ('code') executable not found on system PATH")
        return False

    try:
        logger.info("Launching VS Code for project: %s (%s)", project_id, path)
        subprocess.Popen(
            [code_bin, str(path)],
            shell=False,
            close_fds=True,
        )
        return True
    except Exception as err:
        logger.error("Failed to launch VS Code for project %s: %s", project_id, err)
        return False
