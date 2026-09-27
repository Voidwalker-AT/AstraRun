# AstraRun v0.7 Status Report

> **Date**: 2026-09-27  
> **Status**: STABLE / VERIFIED / MILESTONE COMPLETE  
> **Milestone**: v0.7 Complete (Workstation Capability Expansion)  
> **Prior Milestone**: v0.6.5 Complete (`95b79f3`)  

---

## 1. What Works Completely

1. **Central Capability Registry (`astrarun.capabilities.registry`)**:
   - Universal operating boundary maintaining **47 typed capabilities** across 9 OS categories (`APPLICATION`, `FILE`, `PROCESS`, `NETWORK`, `SYSTEM`, `PROJECT`, `WINDOW`, `AUDIO`, `WORKFLOW`).
   - Standardized return contract: `CapabilityResult` with latency profiling and strongly typed error codes (`NOT_FOUND`, `PERMISSION_DENIED`, `INVALID_ARGUMENT`, `AMBIGUOUS`, `OS_ERROR`).
   - Explicit permission gating: `AUTO` (40 capabilities), `CONFIRM` (3 capabilities), and `BLOCK` (4 capabilities).
   - Mean execution latency: **0.590 ms**.

2. **Application Capabilities (`astrarun.applications`)**:
   - Real desktop application discovery via Win32 User32 top-level window filtering (`EnumWindows`, `IsWindowVisible`, `GetWindowTextLengthW`, and window bounds checks).
   - Window restoration and foreground focusing (`focus_application`) with automatic `AMBIGUOUS` candidate return when multiple windows match.
   - Non-destructive graceful closing (`close_application`) via native `WM_CLOSE` messages, preserving user work and prompting native save dialogs.
   - Launching verified application binaries via `App Paths` and discovery cache.

3. **File Capabilities (`astrarun.files`)**:
   - Bounded metadata indexing over safe user roots (`E:\Workspace`, `Downloads`, `Documents`, `Desktop`, `Pictures`).
   - Reparse point and junction traversal protection (`follow_symlinks=False`).
   - Recent files, latest screenshot discovery, and document search.
   - Hardened `open_file` strictly prohibiting executable scripts (`.bat`, `.cmd`, `.ps1`, `.vbs`, `.exe`) with `PERMISSION_DENIED`.
   - Safe `reveal_file` alternative opening Windows File Explorer with `/select`.

4. **Process Capabilities (`astrarun.processes`)**:
   - Deterministic sorting by memory (RSS), CPU%, and name.
   - Comprehensive inspection: CPU%, memory RSS, thread count, bound ports, and parent/child process relationships.
   - Automated command-line sanitization masking passwords, tokens, and API keys.
   - TOCTOU-safe process termination revalidating target PID, creation timestamp, and process name before signal delivery.
   - Hardcoded protected process defense immune to termination (`explorer.exe`, `system`, `lsass.exe`, `csrss.exe`, `services.exe`, etc.).

5. **Network Capabilities (`astrarun.network`)**:
   - Real-time listening port queries and process-to-port mapping (`find_process_on_port`).
   - 100% read-only socket diagnostics across all port ranges (including privileged system ports `<= 1023`).
   - Active TCP connection monitoring with zero packet inspection.

6. **System Capabilities (`astrarun.system`)**:
   - Workstation health summary: OS, CPU cores, RAM total/used, disk utilization, battery percentage, and audio volume.
   - Dedicated GPU telemetry via `nvidia-smi` (NVIDIA RTX 2050) with graceful fallback.
   - Native Windows desktop locking (`LockWorkStation`).
   - Hard policy blocking of system shutdown and reboot (`shutdown_system`, `restart_system`).

7. **Project Capabilities (`astrarun.projects`)**:
   - Integration with `ProjectRegistry` and `E:\Workspace\workspace.json`.
   - Injection-proof Git status inspection using structured subprocess calls (`git branch --show-current` and `git status --porcelain`).
   - Project-bound process and listening port detection based on process working directories.

8. **Window Discovery Subsystem (`astrarun.windows`)**:
   - Sensory discovery foundation for desktop windows (`list_windows`, `foreground_window`, `find_window`, `windows_for_application`).
   - Strongly-typed `WindowEntity` tracking HWND, caption, geometry, and owning process.
   - Prepares clean integration for active window manipulation in v0.8.

9. **Structured UI Presentation Cards (`astrarun.ui.cards`)**:
   - Modern dark Catppuccin Mocha visual cards:
     - `ResultCard`: Key-value diagnostic summaries with status badges and safe action buttons.
     - `ListResultCard`: Keyboard-navigable selectable lists with `Up`/`Down`, `Enter`, and `Esc` dismissal.

10. **Structured Observation Store (`astrarun.capabilities.store`)**:
    - Ephemeral, in-memory bounded ring buffer (200 facts) capturing sensory OS facts.
    - Zero disk I/O overhead and minimal memory footprint (<150 KB RAM).
    - Prepares verified fact context for future System-2 reasoning handoffs (v0.12).

11. **Decoupled Reasoning Provider Architecture**:
    - Generic `ReasoningProvider` interface and `ReasoningRequired` escalation boundary remain unconfigured in v0.7.
    - The user's external `AI-Bridge` project remains untouched and decoupled.

---

## 2. Verification & Benchmark Results

### 2.1 Automated Unit & Integration Tests
- **Status**: **169 / 169 PASSED** in **9.03s**
- **Regressions**: **0**
- Test suites: Config, Routing, UI, Telemetry, Action Gate, Ensemble, NLP Engine, and v0.7 Capabilities.

### 2.2 Standard Benchmark Suites

| Benchmark Suite | Case Count | Target Dataset SHA256 | Primary Accuracy Metric | Key Safety Metric | Mean Latency |
|---|---|---|---|---|---|
| **Action Benchmark V1** | 330 | `d73ac62ab9...` | **100.0%** Intent Acc | **0.00%** FER | **0.051 ms** |
| **NLP Benchmark V1 (Test)** | 310 | `41f1ad1b6a...` | **100.0%** Intent Acc | **0.00%** Negated Leakage | **5.796 ms** |
| **Capability Benchmark V1** | 520 | `32ca0f2946...` | **100.0%** Cap Acc | **100.0%** Block Recall | **0.590 ms** |

### 2.3 Platform Health Diagnostic (`wsctl doctor`)
- **Status**: **EXCELLENT (39 / 39 OK)**
- 0 errors, 0 warnings.
