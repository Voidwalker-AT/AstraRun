# Process Capabilities — AstraRun v0.7

> **Scope**: Process inspection, resource profiling, tree relationships, and TOCTOU-safe termination  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. Subsystem Architecture

The Process Capability Subsystem (`src/astrarun/processes/service.py`) provides deep, real-time inspection of running operating system processes on the Windows host.

### Key Capabilities:
- `list_processes`: List active processes with deterministic sorting (`memory`, `cpu`, `name`).
- `find_process`: Query active processes by name or command line substring.
- `inspect_process`: Comprehensive inspection including CPU%, memory RSS, parent/child relationships, and listening ports.
- `process_resource_usage`: Lightweight CPU%, memory RSS in MB, and thread count.
- `process_ports`: List local listening and remote ports bound to a specific process PID.
- `process_children`: Enumerate child processes spawned by a parent PID.
- `process_parent`: Identify the parent process of a given PID.
- `terminate_process`: High-risk, confirmation-gated, TOCTOU-safe termination.

---

## 2. Process Inspection & Metric Accuracy

### 2.1 Deterministic Sorting
To provide consistent, reproducible outputs for both user queries and benchmark harnesses, `list_processes` supports strict sorting:
- `sort_by="memory"`: Sort descending by Resident Set Size (RSS).
- `sort_by="cpu"`: Sort descending by instantaneous CPU percent.
- `sort_by="name"`: Sort alphabetically by executable name.
Results are bounded by a `limit` parameter (default: 10, max: 100).

### 2.2 Command Line Sanitization
Workstation processes often carry sensitive tokens, API keys, or passwords in their command-line arguments (e.g. `python server.py --api-key sk-xxxx`).
When returning process metadata, AstraRun automatically sanitizes command lines:
- Tokens matching patterns like `--api-key`, `--token`, `--password`, `SECRET=...` are masked with `[REDACTED]`.
- Long command lines are truncated to avoid UI buffer overflows.

---

## 3. TOCTOU-Safe Process Termination

Process termination is the highest-risk mutating capability in the workstation environment. A naive `os.kill(pid)` is vulnerable to **Time-Of-Check to Time-Of-Use (TOCTOU)** race conditions: if a process exits and Windows recycles its PID before the kill signal arrives, AstraRun could accidentally terminate an innocent or critical process that acquired the reused PID.

### 3.1 The TOCTOU Protection Protocol
1. **Pre-Check**: When an inspection or termination request is initiated, AstraRun records:
   - Target PID
   - Process Creation Timestamp (`create_time`)
   - Process Executable Name (`name`)
2. **Re-Validation Immediately Before Signal Dispatch**:
   ```python
   target_proc = psutil.Process(pid)
   if abs(target_proc.create_time() - expected_create_time) > 1.0:
       raise ProcessLookupError("PID has been recycled by another process. Aborting.")
   if expected_name and target_proc.name().lower() != expected_name.lower():
       raise ProcessLookupError("Process name mismatch. Aborting.")
   ```
3. **Graceful Escalation**:
   - AstraRun first issues `proc.terminate()` (`SIGTERM`).
   - It waits up to 2.0 seconds for clean exit.
   - Only if `force=True` and the process fails to exit does it escalate to `proc.kill()` (`SIGKILL`).

---

## 4. Protected System Process Invariant

AstraRun enforces a hardcoded, non-overridable blocklist of critical operating system processes. Attempts to inspect or kill these processes with `terminate_process` are rejected immediately with `PERMISSION_DENIED`:

### Protected Process List:
- `system`, `system idle process`
- `registry`
- `smss.exe` (Session Manager)
- `csrss.exe` (Client Server Runtime)
- `wininit.exe` (Windows Initialization)
- `services.exe` (Service Control Manager)
- `lsass.exe` (Local Security Authority)
- `winlogon.exe` (Windows Logon)
- `dwm.exe` (Desktop Window Manager)
- `explorer.exe` (Windows Shell)
- `svchost.exe` (Generic Service Host)
- `astrarun.exe`, `python.exe` (Self-preservation)

Attempts to terminate any process in this list return:
```json
{
  "success": false,
  "capability": "terminate_process",
  "message": "Process 'explorer.exe' is a protected system process and cannot be terminated.",
  "error_code": "PERMISSION_DENIED"
}
```
This hard policy block can **never** be bypassed by user prompt engineering or model suggestion.
