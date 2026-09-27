# Network Capabilities — AstraRun v0.7

> **Scope**: Network port discovery, port inspection, process-to-port mapping, and connection monitoring  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. Subsystem Architecture

The Network Capability Subsystem (`src/astrarun/network/service.py`) provides real-time visibility into local network ports, active sockets, and TCP connections.

### Key Capabilities:
- `list_listening_ports`: List all local TCP listening ports along with their bound IP and owning process.
- `inspect_port`: Check whether a specific port is active, whether it is listening, and which PID owns it.
- `find_process_on_port`: Resolve the exact process name, PID, and executable path bound to a port.
- `list_network_connections`: List active network sockets (`ESTABLISHED`, `LISTEN`, `TIME_WAIT`).

---

## 2. Process-to-Port Resolution

Software developers constantly encounter conflicts where a development server fails to bind:
```text
Error: listen EADDRINUSE: address already in use :::3000
```
AstraRun provides instant, typed port-to-process resolution:

```python
result = registry.execute("find_process_on_port", {"port": 3000})
# Output:
# {
#   "success": true,
#   "data": {
#     "port": 3000,
#     "pid": 14592,
#     "name": "node.exe",
#     "status": "LISTEN"
#   }
# }
```
This enables zero-friction diagnosis without requiring the developer to remember arcane netstat commands (`netstat -ano | findstr :3000`).

---

## 3. Privileged vs Non-Privileged Port Queries

In operating systems, ports `<= 1023` are privileged system ports (e.g. 80 HTTP, 443 HTTPS, 22 SSH).
- **AstraRun Network Operations are 100% Read-Only**: The network subsystem only queries socket status via `psutil.net_connections()`.
- **Zero Socket Mutation**: AstraRun does not bind, inject, redirect, or open network sockets.
- **Safe Across All Port Ranges**: Querying port 80 or 443 is completely safe and permitted as an `AUTO` read-only operation because no system state or firewall rules are altered.

---

## 4. Connection State Filtering

`list_network_connections(kind="tcp", limit=20)` inspects network sockets while masking sensitive payload content:
- Tracks connection state: `LISTEN`, `ESTABLISHED`, `CLOSE_WAIT`.
- Reports local endpoint (`127.0.0.1:5432`) and remote endpoint (`192.168.1.50:62100`).
- Does **not** inspect or capture packet payloads, ensuring privacy and zero data leakage.
