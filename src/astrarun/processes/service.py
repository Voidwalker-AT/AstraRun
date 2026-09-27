"""Process capability services: listing, sorting, resource metrics, relationships, and safe termination."""

from __future__ import annotations

import time
from typing import Any, List, Optional

import psutil

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult
from astrarun.core.logging import get_logger
from astrarun.telemetry.redactor import redact_sensitive_text

logger = get_logger("astrarun.processes.service")

# Critical Windows processes that may NEVER be terminated under any circumstances
PROTECTED_PROCESS_NAMES = {
    "system", "system idle process", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe",
    "explorer.exe", "dwm.exe", "spoolsv.exe", "fontdrvhost.exe"
}


def list_processes(
    limit: int = 10,
    sort_by: Optional[str] = "memory",
    filter_name: Optional[str] = None,
) -> CapabilityResult:
    """
    List running processes with structured resource metrics and deterministic sorting.
    
    Args:
        limit: Maximum number of processes to return.
        sort_by: Metric to sort by ('memory', 'cpu', 'newest'/'start_time').
        filter_name: Optional process name substring (e.g. 'node', 'python').
    """
    t0 = time.perf_counter()
    procs: list[dict[str, Any]] = []
    clean_filter = filter_name.strip().lower() if filter_name else None

    for p in psutil.process_iter(["pid", "name", "memory_info", "cpu_percent", "create_time"]):
        try:
            info = p.info
            name = info.get("name") or "unknown"
            if clean_filter and clean_filter not in name.lower():
                continue

            mem_info = info.get("memory_info")
            rss_bytes = mem_info.rss if mem_info else 0
            rss_mb = round(rss_bytes / (1024 * 1024), 2)
            cpu_pct = info.get("cpu_percent") or 0.0
            create_time = info.get("create_time") or 0.0

            procs.append({
                "pid": info["pid"],
                "name": name,
                "memory_mb": rss_mb,
                "cpu_percent": cpu_pct,
                "create_time": create_time,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Deterministic sorting
    if sort_by == "cpu":
        procs.sort(key=lambda x: x["cpu_percent"], reverse=True)
    elif sort_by in ("newest", "start_time"):
        procs.sort(key=lambda x: x["create_time"], reverse=True)
    else:  # default: memory
        procs.sort(key=lambda x: x["memory_mb"], reverse=True)

    result_procs = procs[:limit]
    latency = (time.perf_counter() - t0) * 1000

    msg = f"Retrieved {len(result_procs)} processes (sorted by {sort_by})."
    if clean_filter:
        msg = f"Retrieved {len(result_procs)} '{clean_filter}' processes (sorted by {sort_by})."

    return CapabilityResult.ok(
        capability="list_processes",
        message=msg,
        data={"processes": result_procs, "count": len(result_procs), "sorted_by": sort_by},
        context_updates=[{"type": "processes_listed", "count": len(result_procs)}],
        latency_ms=latency,
    )


def find_process(query: str) -> CapabilityResult:
    """Find running process by name or PID."""
    t0 = time.perf_counter()
    clean = query.strip().lower()
    matches: list[dict[str, Any]] = []

    # Check if query is an explicit PID
    is_pid = clean.isdigit()
    target_pid = int(clean) if is_pid else None

    for p in psutil.process_iter(["pid", "name", "memory_info", "status"]):
        try:
            if target_pid and p.info["pid"] == target_pid:
                matches.append({
                    "pid": p.info["pid"],
                    "name": p.info["name"],
                    "memory_mb": round((p.info["memory_info"].rss if p.info["memory_info"] else 0) / (1024 * 1024), 2),
                    "status": p.info.get("status", "running"),
                })
                break
            elif clean in (p.info["name"] or "").lower():
                matches.append({
                    "pid": p.info["pid"],
                    "name": p.info["name"],
                    "memory_mb": round((p.info["memory_info"].rss if p.info["memory_info"] else 0) / (1024 * 1024), 2),
                    "status": p.info.get("status", "running"),
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    latency = (time.perf_counter() - t0) * 1000
    if not matches:
        return CapabilityResult.fail(
            capability="find_process",
            message=f"No process matching '{query}' found.",
            error_code=CapabilityErrorCode.NOT_FOUND,
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="find_process",
        message=f"Found {len(matches)} matching process(es).",
        data={"processes": matches[:10], "count": len(matches)},
        latency_ms=latency,
    )


def inspect_process(pid: int) -> CapabilityResult:
    """Inspect detailed runtime metrics, relationships, and ports for a specific PID."""
    t0 = time.perf_counter()
    if not psutil.pid_exists(pid):
        return CapabilityResult.fail(
            capability="inspect_process",
            message=f"Process PID {pid} does not exist.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    try:
        p = psutil.Process(pid)
        name = p.name()
        create_time = p.create_time()
        status = p.status()

        # Memory & CPU
        mem = p.memory_info()
        rss_mb = round(mem.rss / (1024 * 1024), 2)
        mem_pct = round(p.memory_percent(), 2)
        try:
            cpu_pct = p.cpu_percent(interval=0.0)
        except Exception:
            cpu_pct = 0.0

        # Thread count
        num_threads = p.num_threads()

        # Executable & Sanitized Command Line
        try:
            exe = p.exe()
        except (psutil.AccessDenied, psutil.ZombieProcess):
            exe = "<access_denied>"

        try:
            cmdline_raw = " ".join(p.cmdline()[:10])
            cmdline = redact_sensitive_text(cmdline_raw)
        except (psutil.AccessDenied, psutil.ZombieProcess):
            cmdline = "<access_denied>"

        # Parent & Children
        try:
            parent = p.parent()
            parent_info = {"pid": parent.pid, "name": parent.name()} if parent else None
        except Exception:
            parent_info = None

        children_info = []
        try:
            for ch in p.children(recursive=False):
                children_info.append({"pid": ch.pid, "name": ch.name()})
        except Exception:
            pass

        # Listening ports
        ports: list[int] = []
        try:
            for c in psutil.net_connections(kind="inet"):
                if c.pid == pid and c.status == "LISTEN" and c.laddr:
                    ports.append(c.laddr.port)
        except Exception:
            pass

        data = {
            "pid": pid,
            "name": name,
            "exe": exe,
            "cmdline": cmdline,
            "status": status,
            "create_time": create_time,
            "memory_mb": rss_mb,
            "memory_percent": mem_pct,
            "cpu_percent": cpu_pct,
            "threads": num_threads,
            "parent": parent_info,
            "children": children_info,
            "listening_ports": ports,
        }
        latency = (time.perf_counter() - t0) * 1000

        return CapabilityResult.ok(
            capability="inspect_process",
            message=f"{name} (PID {pid}) | Memory: {rss_mb} MB ({mem_pct}%) | CPU: {cpu_pct}% | Threads: {num_threads}",
            data=data,
            context_updates=[{"type": "process_inspected", "pid": pid, "name": name, "create_time": create_time}],
            latency_ms=latency,
        )
    except (psutil.NoSuchProcess, psutil.AccessDenied) as err:
        return CapabilityResult.fail(
            capability="inspect_process",
            message=f"Failed to inspect process PID {pid}: {err}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )


def process_resource_usage(pid: int) -> CapabilityResult:
    """Return lightweight CPU and RAM usage metrics for a process."""
    res = inspect_process(pid)
    if not res.success:
        return res
    d = res.data
    return CapabilityResult.ok(
        capability="process_resource_usage",
        message=f"{d['name']} (PID {pid}): RAM {d['memory_mb']} MB, CPU {d['cpu_percent']}%, Threads {d['threads']}",
        data={
            "pid": pid,
            "name": d["name"],
            "memory_mb": d["memory_mb"],
            "memory_percent": d["memory_percent"],
            "cpu_percent": d["cpu_percent"],
            "threads": d["threads"],
        },
        latency_ms=res.latency_ms,
    )


def process_ports(pid: int) -> CapabilityResult:
    """Return listening ports associated with a process."""
    res = inspect_process(pid)
    if not res.success:
        return res
    ports = res.data.get("listening_ports", [])
    return CapabilityResult.ok(
        capability="process_ports",
        message=f"Process PID {pid} ({res.data['name']}) is listening on ports: {ports or 'None'}",
        data={"pid": pid, "name": res.data["name"], "ports": ports},
        latency_ms=res.latency_ms,
    )


def process_children(pid: int) -> CapabilityResult:
    """List child processes of a process."""
    res = inspect_process(pid)
    if not res.success:
        return res
    children = res.data.get("children", [])
    return CapabilityResult.ok(
        capability="process_children",
        message=f"Process PID {pid} has {len(children)} child process(es).",
        data={"pid": pid, "children": children},
        latency_ms=res.latency_ms,
    )


def process_parent(pid: int) -> CapabilityResult:
    """Get parent process of a process."""
    res = inspect_process(pid)
    if not res.success:
        return res
    parent = res.data.get("parent")
    return CapabilityResult.ok(
        capability="process_parent",
        message=f"Process PID {pid} parent: {parent['name'] if parent else 'None'} (PID {parent['pid'] if parent else 'N/A'})",
        data={"pid": pid, "parent": parent},
        latency_ms=res.latency_ms,
    )


def terminate_process(
    pid: int,
    expected_create_time: float = 0.0,
    expected_name: str = "",
) -> CapabilityResult:
    """
    Terminate a process with Time-of-Check/Time-of-Use (TOCTOU) and policy validation.
    Confirmation-gated action. Protected processes are strictly blocked.
    """
    t0 = time.perf_counter()
    if pid <= 4:
        return CapabilityResult.fail(
            capability="terminate_process",
            message=f"Termination of critical system PID {pid} is unconditionally blocked.",
            error_code=CapabilityErrorCode.BLOCKED,
        )

    if not psutil.pid_exists(pid):
        return CapabilityResult.fail(
            capability="terminate_process",
            message=f"Process PID {pid} no longer exists.",
            error_code=CapabilityErrorCode.NOT_FOUND,
        )

    try:
        proc = psutil.Process(pid)
        name = proc.name().lower()
        if name in PROTECTED_PROCESS_NAMES or name.replace(".exe", "") in PROTECTED_PROCESS_NAMES:
            return CapabilityResult.fail(
                capability="terminate_process",
                message=f"Termination of protected system process '{name}' (PID {pid}) is BLOCKED.",
                error_code=CapabilityErrorCode.BLOCKED,
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    from astrarun.tools.processes import terminate_process as raw_terminate_process

    success = raw_terminate_process(
        pid=pid,
        expected_create_time=expected_create_time,
        expected_name=expected_name,
    )
    latency = (time.perf_counter() - t0) * 1000

    if success:
        return CapabilityResult.ok(
            capability="terminate_process",
            message=f"Process PID {pid} terminated successfully.",
            data={"pid": pid},
            context_updates=[{"type": "process_terminated", "pid": pid}],
            latency_ms=latency,
        )
    return CapabilityResult.fail(
        capability="terminate_process",
        message=f"Failed to terminate PID {pid} (TOCTOU revalidation failure or access denied).",
        error_code=CapabilityErrorCode.PERMISSION_DENIED,
        latency_ms=latency,
    )
