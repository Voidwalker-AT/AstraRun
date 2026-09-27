"""Process and network port inspection routines for AstraRun context."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import psutil

from astrarun.context.models import DevPortInfo
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.context.processes")


def get_listening_dev_ports(min_port: int = 1024, max_port: int = 65535) -> list[DevPortInfo]:
    """
    List all developer processes listening on TCP ports >= min_port.
    Read-only diagnostic inspection.
    """
    results: list[DevPortInfo] = []
    try:
        connections = psutil.net_connections(kind="inet")
        seen_ports: set[int] = set()

        for c in connections:
            if c.status == "LISTEN" and c.laddr:
                port = c.laddr.port
                if min_port <= port <= max_port and port not in seen_ports:
                    seen_ports.add(port)
                    pid = c.pid or 0
                    pname = ""
                    ctime = 0.0
                    if pid:
                        try:
                            p = psutil.Process(pid)
                            pname = p.name()
                            ctime = p.create_time()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pname = "unknown"

                    results.append(
                        DevPortInfo(
                            port=port,
                            pid=pid,
                            process_name=pname,
                            create_time=ctime,
                            status="LISTEN",
                        )
                    )
    except Exception as err:
        logger.debug("Error querying listening ports: %s", err)

    results.sort(key=lambda x: x.port)
    return results


def inspect_port_details(port: int) -> dict[str, Any]:
    """
    Inspect a specific port (read-only).
    Works on all ports (including privileged <= 1023) for read-only inspection.
    """
    try:
        connections = psutil.net_connections(kind="inet")
        matches = [c for c in connections if c.laddr and c.laddr.port == port]

        if not matches:
            return {
                "port": port,
                "status": "NOT_LISTENING",
                "pid": None,
                "process_name": None,
                "message": f"No process currently listening on port {port}",
            }

        conn = matches[0]
        pid = conn.pid
        proc_name = None
        cmdline = []
        create_time = 0.0
        memory_mb = 0.0

        if pid:
            try:
                p = psutil.Process(pid)
                proc_name = p.name()
                create_time = p.create_time()
                try:
                    cmdline = p.cmdline()
                except (psutil.AccessDenied, psutil.ZombieProcess):
                    cmdline = []
                try:
                    memory_mb = round(p.memory_info().rss / (1024 * 1024), 2)
                except (psutil.AccessDenied, psutil.ZombieProcess):
                    memory_mb = 0.0
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                proc_name = "unknown"

        return {
            "port": port,
            "status": conn.status,
            "pid": pid,
            "process_name": proc_name,
            "create_time": create_time,
            "cmdline": " ".join(cmdline[:5]) if cmdline else "",
            "memory_mb": memory_mb,
            "message": f"Port {port} is {conn.status} by {proc_name or 'unknown'} (PID {pid})",
        }
    except Exception as err:
        return {
            "port": port,
            "status": "ERROR",
            "pid": None,
            "process_name": None,
            "message": f"Error inspecting port {port}: {err}",
        }


def inspect_process_details(pid: int) -> dict[str, Any]:
    """
    Inspect process by PID (read-only).
    Handles permission-denied gracefully.
    """
    try:
        if not psutil.pid_exists(pid):
            return {
                "pid": pid,
                "exists": False,
                "message": f"Process PID {pid} does not exist",
            }

        p = psutil.Process(pid)
        name = p.name()
        create_time = p.create_time()
        exe = ""
        cmdline = ""
        memory_mb = 0.0
        cpu_percent = 0.0
        status = p.status()

        try:
            exe = p.exe()
        except (psutil.AccessDenied, psutil.ZombieProcess):
            exe = "<access_denied>"

        try:
            cmd = p.cmdline()
            cmdline = " ".join(cmd) if cmd else ""
        except (psutil.AccessDenied, psutil.ZombieProcess):
            cmdline = "<access_denied>"

        try:
            memory_mb = round(p.memory_info().rss / (1024 * 1024), 2)
        except (psutil.AccessDenied, psutil.ZombieProcess):
            memory_mb = 0.0

        try:
            cpu_percent = p.cpu_percent(interval=0.0)
        except Exception:
            cpu_percent = 0.0

        # Find listening ports for this pid
        ports: list[int] = []
        try:
            for c in psutil.net_connections(kind="inet"):
                if c.pid == pid and c.status == "LISTEN" and c.laddr:
                    ports.append(c.laddr.port)
        except Exception:
            pass

        return {
            "pid": pid,
            "exists": True,
            "name": name,
            "exe": exe,
            "cmdline": cmdline[:200],
            "create_time": create_time,
            "status": status,
            "memory_mb": memory_mb,
            "cpu_percent": cpu_percent,
            "listening_ports": ports,
            "message": f"{name} (PID {pid}) | Memory: {memory_mb} MB | Status: {status}",
        }
    except Exception as err:
        return {
            "pid": pid,
            "exists": False,
            "message": f"Error inspecting PID {pid}: {err}",
        }
