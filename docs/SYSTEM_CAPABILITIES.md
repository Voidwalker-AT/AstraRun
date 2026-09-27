# System Capabilities — AstraRun v0.7

> **Scope**: Host machine diagnostics, resource health, GPU telemetry, and security policy boundaries  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. Subsystem Architecture

The System Capability Subsystem (`src/astrarun/system/service.py`) provides real-time health metrics, resource utilization, and host state inspection.

### Key Capabilities:
- `system_summary`: Unified overview of OS, CPU, RAM, disk, battery, and GPU.
- `cpu_status`: CPU model, physical/logical core counts, clock frequency, and per-core utilization.
- `memory_status`: Total, available, used physical RAM, and swap space.
- `disk_status`: Storage capacity, used space, free space, and mount points.
- `battery_status`: Battery charge percentage, AC power status, and remaining runtime.
- `gpu_status`: Dedicated GPU telemetry (NVIDIA SMI / Torch fallback).
- `audio_status`: Master audio volume percentage and mute status.
- `lock_workstation`: Immediately lock the desktop session.
- `shutdown_system`: **HARD BLOCKED BY SECURITY POLICY**.
- `restart_system`: **HARD BLOCKED BY SECURITY POLICY**.

---

## 2. Hardware Acceleration & Dedicated GPU Telemetry

AstraRun operates on developer workstations equipped with discrete GPUs (such as the NVIDIA GeForce RTX 2050 on this host).

### 2.1 NVIDIA SMI Query
The `gpu_status` capability queries real-time metrics using `nvidia-smi`:
```python
cmd = [
    "nvidia-smi",
    "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
    "--format=csv,noheader,nounits",
]
```
Returns:
- GPU Model Name (e.g. *NVIDIA GeForce RTX 2050*)
- Total and Used VRAM in MB
- GPU Core Utilization Percent
- Temperature in Celsius

### 2.2 Graceful Fallback
If the host lacks an NVIDIA GPU or if `nvidia-smi` is not installed on PATH:
- AstraRun does **not** crash or fail.
- It returns `success=True` with `{"available": False, "message": "No NVIDIA GPU detected or nvidia-smi unavailable"}`.
- All other system capabilities continue to operate normally.

---

## 3. Workstation Session Control & Hard Blocks

### 3.1 Safe Action: `lock_workstation`
When a developer commands *"lock the computer"* or *"lock screen"*:
AstraRun invokes the native Windows API:
```python
ctypes.windll.user32.LockWorkStation()
```
- **Permission**: `AUTO` (non-destructive, security-enhancing).
- Instantly locks the Windows user session without closing open applications or terminating running processes.

### 3.2 Hard Blocks: Shutdown and Reboot
System shutdown and reboot are **strictly prohibited**:
```python
# shutdown_system and restart_system
risk = ToolRisk.HIGH
permission = CapabilityPermission.BLOCK
```
Regardless of whether a user asks *"shut down the PC"* or an adversarial prompt attempts *"reboot my computer"*, the capability registry returns:
```json
{
  "success": false,
  "capability": "shutdown_system",
  "message": "System shutdown is blocked by security policy.",
  "error_code": "PERMISSION_DENIED"
}
```
AstraRun will never turn off or restart the developer's computer.
