"""Project capability services: status, git status, file listing, process association, and ports."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, List, Optional

import psutil

from astrarun.capabilities.models import (
    CapabilityErrorCode,
    CapabilityResult,
    GitStatus,
)
from astrarun.core.logging import get_logger
from astrarun.projects.registry import ProjectRegistry

logger = get_logger("astrarun.projects.service")

_global_project_registry: Optional[ProjectRegistry] = None


def get_project_registry() -> ProjectRegistry:
    """Retrieve or initialize singleton ProjectRegistry."""
    global _global_project_registry
    if _global_project_registry is None:
        _global_project_registry = ProjectRegistry()
    return _global_project_registry


def _get_proj_path(proj: Any) -> Path:
    """Safely retrieve absolute path from project metadata."""
    if hasattr(proj, "absolute_path") and proj.absolute_path:
        return Path(proj.absolute_path).resolve()
    elif hasattr(proj, "path") and proj.path:
        return Path(proj.path).resolve()
    from astrarun.core.paths import AstraPaths
    return AstraPaths.workspace_root()


def project_git_status(project_id: str) -> CapabilityResult:
    """
    Query Git status of a verified project directory using structured argument lists.
    Guarantees no raw text interpolation into Git command line.
    """
    t0 = time.perf_counter()
    reg = get_project_registry()
    proj = reg.get_project(project_id)
    if not proj:
        matches = reg.find_projects(project_id)
        if matches:
            proj = matches[0]

    if not proj:
        return CapabilityResult.fail(
            capability="project_git_status",
            message=f"Project '{project_id}' not found in registry.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    proj_dir = _get_proj_path(proj)
    if not proj_dir.exists() or not (proj_dir / ".git").exists():
        return CapabilityResult.fail(
            capability="project_git_status",
            message=f"Project '{proj.id}' has no Git repository at {proj_dir}.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    try:
        flags = 0x08000000 if os.name == "nt" else 0
        branch_res = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=str(proj_dir),
            capture_output=True,
            text=True,
            timeout=2.0,
            creationflags=flags,
        )
        branch = branch_res.stdout.strip() or "HEAD"

        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(proj_dir),
            capture_output=True,
            text=True,
            timeout=2.0,
            creationflags=flags,
        )
        lines = status_res.stdout.splitlines()
        modified = []
        untracked = []
        for line in lines:
            line_str = line.strip()
            if line_str.startswith("??"):
                untracked.append(line_str[3:].strip())
            else:
                modified.append(line_str[3:].strip())

        is_dirty = len(modified) > 0 or len(untracked) > 0
        git_status = GitStatus(
            branch=branch,
            modified=modified,
            untracked=untracked,
            is_dirty=is_dirty,
        )
        latency = (time.perf_counter() - t0) * 1000

        msg = f"{proj.name} on branch '{branch}' | {'DIRTY (' + str(len(modified) + len(untracked)) + ' changes)' if is_dirty else 'CLEAN'}"
        return CapabilityResult.ok(
            capability="project_git_status",
            message=msg,
            data=git_status.to_dict(),
            context_updates=[{"type": "project_git_inspected", "project_id": proj.id, "branch": branch, "is_dirty": is_dirty}],
            latency_ms=latency,
        )
    except Exception as err:
        return CapabilityResult.fail(
            capability="project_git_status",
            message=f"Error running git status on '{proj.id}': {err}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )


def project_running_processes(project_id: str) -> CapabilityResult:
    """Find running processes associated with a project directory via cwd or cmdline."""
    t0 = time.perf_counter()
    reg = get_project_registry()
    proj = reg.get_project(project_id)
    if not proj:
        matches = reg.find_projects(project_id)
        if matches:
            proj = matches[0]

    if not proj:
        return CapabilityResult.fail(
            capability="project_running_processes",
            message=f"Project '{project_id}' not found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    proj_path_lower = str(_get_proj_path(proj)).lower()
    associated: list[dict[str, Any]] = []

    for p in psutil.process_iter(["pid", "name"]):
        try:
            cwd_match = False
            cmd_match = False
            try:
                proc_cwd = p.cwd().lower()
                if proj_path_lower in proc_cwd:
                    cwd_match = True
            except (psutil.AccessDenied, psutil.ZombieProcess):
                pass

            try:
                cmd_line = " ".join(p.cmdline()).lower()
                if proj_path_lower in cmd_line:
                    cmd_match = True
            except (psutil.AccessDenied, psutil.ZombieProcess):
                pass

            if cwd_match or cmd_match:
                evidence = "cwd" if cwd_match else "cmdline"
                associated.append({
                    "pid": p.info["pid"],
                    "name": p.info["name"],
                    "evidence": evidence,
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="project_running_processes",
        message=f"Found {len(associated)} process(es) associated with '{proj.name}'.",
        data={"project_id": proj.id, "processes": associated, "count": len(associated)},
        latency_ms=latency,
    )


def project_ports(project_id: str) -> CapabilityResult:
    """Find listening ports associated with running project processes."""
    t0 = time.perf_counter()
    proc_res = project_running_processes(project_id)
    if not proc_res.success:
        return proc_res

    pids = {p["pid"] for p in proc_res.data.get("processes", [])}
    ports: list[int] = []

    if pids:
        try:
            for c in psutil.net_connections(kind="inet"):
                if c.pid in pids and c.status == "LISTEN" and c.laddr:
                    ports.append(c.laddr.port)
        except Exception:
            pass

    ports.sort()
    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="project_ports",
        message=f"Project '{project_id}' listening ports: {ports or 'None'}",
        data={"project_id": project_id, "ports": ports},
        latency_ms=latency,
    )


def project_status(project_id: str) -> CapabilityResult:
    """Comprehensive status summary of a workspace project."""
    t0 = time.perf_counter()
    reg = get_project_registry()
    proj = reg.get_project(project_id)
    if not proj:
        matches = reg.find_projects(project_id)
        if matches:
            proj = matches[0]

    if not proj:
        return CapabilityResult.fail(
            capability="project_status",
            message=f"Project '{project_id}' not found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    git_res = project_git_status(proj.id)
    proc_res = project_running_processes(proj.id)
    port_res = project_ports(proj.id)

    status_data = {
        "id": proj.id,
        "name": proj.name,
        "path": str(_get_proj_path(proj)),
        "category": proj.category,
        "git": git_res.data if git_res.success else {"available": False},
        "running_processes": proc_res.data.get("processes", []) if proc_res.success else [],
        "listening_ports": port_res.data.get("ports", []) if port_res.success else [],
    }

    branch_str = git_res.data.get("branch", "unknown") if git_res.success else "no git"
    dirty_str = "dirty" if git_res.success and git_res.data.get("is_dirty") else "clean"
    procs_cnt = len(status_data["running_processes"])
    ports_str = ", ".join(map(str, status_data["listening_ports"])) if status_data["listening_ports"] else "none"

    msg = f"{proj.name} ({proj.id}) | Branch: {branch_str} ({dirty_str}) | Active Processes: {procs_cnt} | Ports: {ports_str}"
    latency = (time.perf_counter() - t0) * 1000

    return CapabilityResult.ok(
        capability="project_status",
        message=msg,
        data=status_data,
        context_updates=[{"type": "project_status_inspected", "project_id": proj.id}],
        latency_ms=latency,
    )
