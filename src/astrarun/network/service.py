"""Network capability services: listening port discovery and connection inspection."""

from __future__ import annotations

import time
from typing import Any, List, Optional

import psutil

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult, PortInfo
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.network.service")


def list_listening_ports(limit: int = 20) -> CapabilityResult:
    """List active TCP listening ports and owning processes."""
    t0 = time.perf_counter()
    ports: list[PortInfo] = []
    seen: set[int] = set()

    try:
        for c in psutil.net_connections(kind="inet"):
            if c.status == "LISTEN" and c.laddr:
                p = c.laddr.port
                if p not in seen:
                    seen.add(p)
                    pid = c.pid
                    pname = None
                    if pid:
                        try:
                            pname = psutil.Process(pid).name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pname = "unknown"

                    ports.append(
                        PortInfo(
                            port=p,
                            protocol="tcp",
                            address=c.laddr.ip,
                            state="LISTEN",
                            pid=pid,
                            process_name=pname,
                        )
                    )
    except Exception as err:
        logger.error("Error querying listening ports: %s", err)

    ports.sort(key=lambda x: x.port)
    res_ports = ports[:limit]
    latency = (time.perf_counter() - t0) * 1000

    return CapabilityResult.ok(
        capability="list_listening_ports",
        message=f"Found {len(res_ports)} listening port(s).",
        data={"ports": [p.to_dict() for p in res_ports], "count": len(res_ports)},
        context_updates=[{"type": "ports_listed", "count": len(res_ports)}],
        latency_ms=latency,
    )


def inspect_port(port: int) -> CapabilityResult:
    """
    Inspect a specific port (read-only).
    Allows inspection of privileged ports (e.g. 80, 443, 22) in read-only mode.
    """
    t0 = time.perf_counter()
    match = None

    try:
        for c in psutil.net_connections(kind="inet"):
            if c.laddr and c.laddr.port == port:
                pid = c.pid
                pname = None
                if pid:
                    try:
                        pname = psutil.Process(pid).name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pname = "unknown"

                match = PortInfo(
                    port=port,
                    protocol="tcp",
                    address=c.laddr.ip,
                    state=c.status,
                    pid=pid,
                    process_name=pname,
                )
                break
    except Exception as err:
        return CapabilityResult.fail(
            capability="inspect_port",
            message=f"Error inspecting port {port}: {err}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )

    latency = (time.perf_counter() - t0) * 1000
    if not match:
        return CapabilityResult.ok(
            capability="inspect_port",
            message=f"Port {port} is NOT currently listening.",
            data={"port": port, "status": "NOT_LISTENING", "listening": False},
            latency_ms=latency,
        )

    return CapabilityResult.ok(
        capability="inspect_port",
        message=f"Port {port} is {match.state} by {match.process_name or 'unknown'} (PID {match.pid}).",
        data=match.to_dict(),
        context_updates=[{"type": "port_inspected", "port": port, "pid": match.pid, "process_name": match.process_name}],
        latency_ms=latency,
    )


def find_process_on_port(port: int) -> CapabilityResult:
    """Find the process listening on a specific network port."""
    res = inspect_port(port)
    if not res.success:
        return res

    d = res.data
    if not d.get("pid"):
        return CapabilityResult.fail(
            capability="find_process_on_port",
            message=f"No process currently listening on port {port}.",
            error_code=CapabilityErrorCode.NOT_FOUND,
            latency_ms=res.latency_ms,
        )

    return CapabilityResult.ok(
        capability="find_process_on_port",
        message=f"Process on port {port}: {d.get('process_name')} (PID {d.get('pid')})",
        data={"port": port, "pid": d.get("pid"), "process_name": d.get("process_name")},
        latency_ms=res.latency_ms,
    )


def list_network_connections(limit: int = 20) -> CapabilityResult:
    """List active internet socket connections across the machine."""
    t0 = time.perf_counter()
    conns: list[dict[str, Any]] = []

    try:
        for c in psutil.net_connections(kind="inet"):
            if not c.laddr:
                continue
            laddr_str = f"{c.laddr.ip}:{c.laddr.port}"
            raddr_str = f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "0.0.0.0:0"
            pname = None
            if c.pid:
                try:
                    pname = psutil.Process(c.pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pname = "unknown"

            conns.append({
                "local_address": laddr_str,
                "remote_address": raddr_str,
                "status": c.status,
                "pid": c.pid,
                "process_name": pname,
            })
            if len(conns) >= limit:
                break
    except Exception as err:
        logger.error("Error inspecting network connections: %s", err)

    latency = (time.perf_counter() - t0) * 1000
    return CapabilityResult.ok(
        capability="list_network_connections",
        message=f"Retrieved {len(conns)} network connection(s).",
        data={"connections": conns, "count": len(conns)},
        latency_ms=latency,
    )
