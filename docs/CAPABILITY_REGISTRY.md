# Capability Registry — AstraRun v0.7

> **Scope**: Catalog of all 47 registered workstation capabilities  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. Registry Overview

The `CapabilityRegistry` (`src/astrarun/capabilities/registry.py`) is the central authority for typed OS operations in AstraRun. It registers, validates, secures, and dispatches all 47 workstation capabilities.

### Summary Metrics:
- **Total Registered Capabilities**: 47
- **Read-Only Capabilities**: 37 (78.7%)
- **Mutating / Action Capabilities**: 10 (21.3%)
- **Automatic Execution (`AUTO`)**: 40 (85.1%)
- **Confirmation Required (`CONFIRM`)**: 3 (6.4%)
- **Hard Blocked by Policy (`BLOCK`)**: 4 (8.5%)
- **Mean Dispatch Latency**: 0.590 ms

---

## 2. Complete Capability Catalog

### 2.1 Application Capabilities (`APPLICATION`)

| Capability ID | Risk | Read-Only | Permission | Arguments | Description | Context Effects |
|---|---|---|---|---|---|---|
| `list_running_applications` | LOW | Yes | AUTO | `{}` | List user-facing applications based on visible top-level windows | None |
| `is_application_running` | LOW | Yes | AUTO | `app: str` | Check if a specific desktop application is running | None |
| `find_application` | LOW | Yes | AUTO | `name: str` | Find application executable metadata from Start Menu and paths | None |
| `open_application` | LOW | No | AUTO | `app: str, path?: str` | Launch a verified desktop application executable | `application_opened` |
| `focus_application` | LOW | No | AUTO | `app: str` | Bring application window to foreground (disambiguates multiples) | `application_focused` |
| `close_application` | MEDIUM | No | AUTO | `app: str` | Gracefully close application window via `WM_CLOSE` | `application_closed` |

### 2.2 File Capabilities (`FILE`)

| Capability ID | Risk | Read-Only | Permission | Arguments | Description | Context Effects |
|---|---|---|---|---|---|---|
| `find_file` | LOW | Yes | AUTO | `pattern: str, root?: str, limit?: int` | Search user files within bounded workspace/user roots | None |
| `find_latest_file` | LOW | Yes | AUTO | `pattern?: str, root?: str` | Find most recently modified file in bounded folders | None |
| `list_recent_files` | LOW | Yes | AUTO | `limit?: int, root?: str` | List recently modified user files (default: 10) | None |
| `open_file` | LOW | No | AUTO | `path: str` | Open non-executable document file with default handler (blocks scripts) | `file_opened` |
| `reveal_file` | LOW | No | AUTO | `path: str` | Highlight file in Windows File Explorer via `/select` | `file_revealed` |
| `file_metadata` | LOW | Yes | AUTO | `path: str` | Query size, timestamps, extension, and attributes | None |

### 2.3 Process Capabilities (`PROCESS`)

| Capability ID | Risk | Read-Only | Permission | Arguments | Description | Context Effects |
|---|---|---|---|---|---|---|
| `list_processes` | LOW | Yes | AUTO | `sort_by?: str, limit?: int` | List processes sorted deterministically by memory/CPU | None |
| `find_process` | LOW | Yes | AUTO | `name: str` | Find active processes matching name substring | None |
| `inspect_process` | LOW | Yes | AUTO | `pid?: int, name?: str` | Detailed metrics, CPU%, memory RSS, ports, sanitised cmdline | None |
| `process_resource_usage` | LOW | Yes | AUTO | `pid: int` | Current memory RSS, CPU percent, and thread count | None |
| `process_ports` | LOW | Yes | AUTO | `pid: int` | Network ports currently bound by process | None |
| `process_children` | LOW | Yes | AUTO | `pid: int` | Child processes spawned by target PID | None |
| `process_parent` | LOW | Yes | AUTO | `pid: int` | Parent process information for target PID | None |
| `terminate_process` | HIGH | No | CONFIRM | `pid: int, name?: str, force?: bool` | Terminate process with TOCTOU revalidation & protected list block | `process_terminated` |

### 2.4 Network Capabilities (`NETWORK`)

| Capability ID | Risk | Read-Only | Permission | Arguments | Description | Context Effects |
|---|---|---|---|---|---|---|
| `list_listening_ports` | LOW | Yes | AUTO | `limit?: int` | List local TCP listening ports and owning PIDs/names | None |
| `inspect_port` | LOW | Yes | AUTO | `port: int` | Query status and owning process for a specific port | None |
| `find_process_on_port` | LOW | Yes | AUTO | `port: int` | Resolve process entity currently bound to port | None |
| `list_network_connections` | LOW | Yes | AUTO | `kind?: str, limit?: int` | List active TCP connections (ESTABLISHED, LISTEN) | None |

### 2.5 System Capabilities (`SYSTEM`)

| Capability ID | Risk | Read-Only | Permission | Arguments | Description | Context Effects |
|---|---|---|---|---|---|---|
| `system_summary` | LOW | Yes | AUTO | `{}` | Summary of OS, CPU, RAM, disk, battery, and GPU | None |
| `cpu_status` | LOW | Yes | AUTO | `{}` | CPU model, core count, frequency, and current utilization | None |
| `memory_status` | LOW | Yes | AUTO | `{}` | Total, used, available RAM and swap metrics | None |
| `disk_status` | LOW | Yes | AUTO | `path?: str` | Total, used, free disk space and percentage on primary drive | None |
| `battery_status` | LOW | Yes | AUTO | `{}` | Battery percent, power plugged status, remaining time | None |
| `gpu_status` | LOW | Yes | AUTO | `{}` | GPU name, VRAM usage, utilization (NVIDIA SMI fallback) | None |
| `audio_status` | LOW | Yes | AUTO | `{}` | Master volume percentage and mute status | None |
| `lock_workstation` | MEDIUM | No | AUTO | `{}` | Lock the Windows workstation via `LockWorkStation` API | None |
| `shutdown_system` | HIGH | No | BLOCK | `{}` | Hard blocked by security policy | None |
| `restart_system` | HIGH | No | BLOCK | `{}` | Hard blocked by security policy | None |

### 2.6 Project Capabilities (`PROJECT`)

| Capability ID | Risk | Read-Only | Permission | Arguments | Description | Context Effects |
|---|---|---|---|---|---|---|
| `project_status` | LOW | Yes | AUTO | `project_id: str` | High-level status of a registered workspace project | None |
| `project_git_status` | LOW | Yes | AUTO | `project_id: str` | Git branch, uncommitted modified files, untracked files | None |
| `project_running_processes` | LOW | Yes | AUTO | `project_id: str` | Detect active processes executing in project root | None |
| `project_ports` | LOW | Yes | AUTO | `project_id: str` | Detect listening ports owned by project processes | None |
| `open_project_folder` | LOW | No | AUTO | `project_id: str` | Open project root in Windows File Explorer | `folder_opened` |
| `open_project_in_vscode` | LOW | No | AUTO | `project_id: str` | Open project directory in Visual Studio Code | `project_opened` |

### 2.7 Window Capabilities (`WINDOW`)

| Capability ID | Risk | Read-Only | Permission | Arguments | Description | Context Effects |
|---|---|---|---|---|---|---|
| `list_windows` | LOW | Yes | AUTO | `{}` | List visible desktop application windows with titles & bounds | None |
| `foreground_window` | LOW | Yes | AUTO | `{}` | Inspect the currently focused desktop window | None |
| `find_window` | LOW | Yes | AUTO | `title_query: str` | Find window by title substring match | None |
| `windows_for_application` | LOW | Yes | AUTO | `app_name: str` | Find all visible windows belonging to an application | None |

### 2.8 Legacy & Web Tools (`WORKFLOW` / `LEGACY`)

| Capability ID | Risk | Read-Only | Permission | Arguments | Description | Context Effects |
|---|---|---|---|---|---|---|
| `open_folder` | LOW | No | AUTO | `path: str` | Open local folder in Explorer | `folder_opened` |
| `open_url` | LOW | No | AUTO | `url: str` | Open sanitized web URL in default browser | `url_opened` |
| `execute_shell` | HIGH | No | BLOCK | `{}` | Hard blocked: zero raw shell execution invariant | None |
| `delete_system_path` | HIGH | No | BLOCK | `{}` | Hard blocked: destructive file operation invariant | None |
| `open_executable_script` | HIGH | No | BLOCK | `{}` | Hard blocked: direct execution of script files invariant | None |

---

## 3. Invocation Contract

Capabilities are dispatched via `CapabilityRegistry.execute(capability_id, arguments)`:

```python
registry = CapabilityRegistry()
result = registry.execute("inspect_port", {"port": 8000})

if result.success:
    print(f"Port 8000 is owned by PID {result.data['pid']} ({result.data['name']})")
else:
    print(f"Failed: {result.message} [{result.error_code}]")
```
