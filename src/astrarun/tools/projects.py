"""Project-related workstation execution tools for AstraRun v0.6."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult
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
        creationflags = 0x08000008 if os.name == "nt" else 0
        subprocess.Popen(
            [code_bin, str(path)],
            shell=False,
            close_fds=True,
            creationflags=creationflags,
        )
        return True
    except Exception as err:
        logger.error("Failed to launch VS Code for project %s: %s", project_id, err)
        return False


def run_project_command(project_id: str, command_name: str = "test") -> CapabilityResult:
    """
    Execute an approved safe project command within verified project workspace.
    Bounded and isolated with CREATE_NO_WINDOW (0x08000000).
    """
    reg = get_project_registry()
    proj = reg.get_project(project_id)
    if not proj:
        matches = reg.find_projects(project_id)
        if matches:
            proj = matches[0]

    if not proj:
        return CapabilityResult.fail(
            capability="run_project_command",
            message=f"Project '{project_id}' not found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    proj_dir = Path(proj.absolute_path)
    if not proj_dir.exists():
        return CapabilityResult.fail(
            capability="run_project_command",
            message=f"Project directory does not exist: {proj_dir}",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    # Safe bounded command execution
    raw_cmd = proj.commands.get(command_name)
    if not raw_cmd:
        return CapabilityResult.fail(
            capability="run_project_command",
            message=f"PROJECT_COMMAND_UNRESOLVED: Command '{command_name}' not defined for project '{proj.id}'",
            error_code=CapabilityErrorCode.NOT_FOUND,
            data={"reason_code": "PROJECT_COMMAND_UNRESOLVED", "project_id": proj.id, "command": command_name},
        )
    import shlex
    cmd = shlex.split(raw_cmd)

    logger.info("Executing safe project command in %s: %s", proj_dir, cmd)
    flags = 0x08000000 if os.name == "nt" else 0
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(proj_dir),
            capture_output=True,
            text=True,
            timeout=15.0,
            creationflags=flags,
        )
        first_line = proc.stdout.strip().split("\n")[0] if proc.stdout else "Command completed."
        return CapabilityResult.ok(
            capability="run_project_command",
            message=f"Safe test command executed for '{proj.name}': {first_line}",
            data={
                "project_id": proj.id,
                "command": command_name,
                "returncode": proc.returncode,
                "stdout": proc.stdout[:500],
                "stderr": proc.stderr[:500],
            },
        )
    except Exception as err:
        return CapabilityResult.fail(
            capability="run_project_command",
            message=f"Execution error: {err}",
            error_code=CapabilityErrorCode.EXECUTION_ERROR,
        )
