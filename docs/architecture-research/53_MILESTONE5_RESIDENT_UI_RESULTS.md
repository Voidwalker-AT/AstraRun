# 53_MILESTONE5_RESIDENT_UI_RESULTS.md — Resident Astra Application, TaskRuntime, Floating HUD & System Tray

> **Status**: COMPLETED & LIVE ACCEPTED (MILESTONE 5 & 5V)  
> **Milestone**: MILESTONE 5 & 5V  
> **Previous Checkpoint**: `49247e58224afcc1cf286673e0bb77b0c14bcaee` (`post-milestone-4`)  
> **Target Checkpoint Tag**: `post-milestone-5v`  
> **Date**: 2026-10-02  

---

## 1. Executive Summary

Milestone 5 and 5V operationalize AstraRun as a continuous, resident Windows desktop agent. The resident runtime delivers an uninterrupted user experience validated across live workstation execution:
1. **Single Resident Process**: Guaranteed across all launches via per-user Win32 Named Mutex (`Local\AstraRun_<UserSID>`) and Windows-local Named Pipe IPC (`\\.\pipe\AstraRun_IPC_<UserSID>`). Zero external HTTP activation listeners. Tested and verified across 10 consecutive OS launches with 100% single-PID preservation.
2. **Exactly ONE System Tray Icon**: Renders the Astra 4-point star/spark (`✦`) with discrete states (`READY`, `WORKING`, `PAUSED`, `ATTENTION_REQUIRED`, `ERROR`) and the canonical context menu.
3. **Alt+Space Command Surface**: Frameless, top-center floating bar with `✦` prompt glyph (`✦ What do you want to do?`), 120–220 ms entrance motion, and immediate keyboard readiness (p50: 2.07 ms, p95: 3.95 ms, worst: 3.95 ms). Dismissal leaves Astra resident in background.
4. **TaskRuntime Multi-Task Coordination**: Orchestrates natural-language goals with named resource locks (`PHYSICAL_INPUT`, `BROWSER`, `WORKSPACE`, `GPU_MODEL`). Strictly serializes physical input while running non-conflicting background tasks concurrently.
5. **Physical User Takeover (`PAUSED_USER_ACTIVE`)**: Physical user input immediately pauses synthetic control, releases `PHYSICAL_INPUT` locks, and presents an interactive takeover card on the Floating Task HUD (`✦ Paused — you're using the computer` with Resume and Cancel controls).
6. **Decoupled Floating Task HUD & Task Center**: Non-focus-stealing (`WS_EX_NOACTIVATE = 0x08000000`) HUD displaying observable facts only (zero raw model chain-of-thought), ActionGate confirmation/clarification cards, and the `TaskCenterWindow` dialog for multi-task inspection.
7. **Zero Console Windows**: Canonical Microsoft Win32 constants enforced across all subprocess creations (`CREATE_NO_WINDOW = 0x08000000`, `DETACHED_PROCESS = 0x00000008`). Live desktop window audit confirmed 0 console windows.

---

## 2. Component Verification & Architecture Matrix

| Component | Module | Evidence Type | Status | Verification Detail |
| :--- | :--- | :--- | :--- | :--- |
| **Win32 Process Flags** | `astrarun.main`, `astrarun.tools.*` | `LIVE_VERIFIED` | **PASS** | Canonical Win32 flags: `CREATE_NO_WINDOW = 0x08000000`, `DETACHED_PROCESS = 0x00000008`, `CREATE_NEW_PROCESS_GROUP = 0x00000200`. Zero improper flags across codebase. |
| **Resident Startup** | `astrarun.main` | `LIVE_VERIFIED` | **PASS** | Cold resident startup via `pythonw.exe` completed in 2.63s. Zero console windows created. |
| **User SID Extraction** | `astrarun.core.single_instance.get_user_sid` | `LIVE_VERIFIED` | **PASS** | Extracts token SID via Win32 `OpenProcessToken` and `ConvertSidToStringSidW`. Confirmed user SID `S-1-5-21-...`. |
| **Named Mutex Guard** | `astrarun.core.single_instance.AstraSingleInstance` | `LIVE_VERIFIED` | **PASS** | `Local\AstraRun_<UserSID>` strictly enforces single resident instance. |
| **Named Pipe IPC** | `astrarun.core.single_instance.AstraSingleInstance` | `LIVE_VERIFIED` | **PASS** | `\\.\pipe\AstraRun_IPC_<UserSID>` duplex message server. Handles `SHOW_MAIN_UI`, `SHOW_TASK_CENTER`, `PAUSE`, `RESUME`, `RESTART`, `SUBMIT_QUERY`, `QUIT`. |
| **Single-Instance Invariance** | `scripts.validate_milestone5v` | `LIVE_VERIFIED` | **PASS** | 10 consecutive OS launches of `python -m astrarun.main`. 10/10 returned exit code 0; primary PID preserved throughout. |
| **Alt+Space Latency** | `astrarun.ui.launcher.LauncherWindow` | `LIVE_VERIFIED` | **PASS** | 20 consecutive summons profiled: p50 = 2.07 ms, p95 = 3.95 ms, worst = 3.95 ms. Input readiness immediate. |
| **Astra Star Tray Icon** | `astrarun.ui.tray.AstraTrayIcon` | `VISUALLY_VERIFIED` | **PASS** | Programmatic vector drawing of 4-point star/spark with state coloration (`#89b4fa`, `#f9e2af`, `#fab387`, `#cba6f7`, `#f38ba8`). |
| **Canonical Tray Menu** | `astrarun.ui.tray.AstraTrayIcon` | `LIVE_VERIFIED` | **PASS** | Open Astra, Task Center, Pause/Resume toggle, Settings, Restart Astra, Quit Astra. Verified discrete state changes. |
| **Command Surface UI** | `astrarun.ui.launcher.LauncherWindow` | `VISUALLY_VERIFIED` | **PASS** | Top-center placement, `✦` prompt glyph, entrance/exit slide animation, Escape key dismissal. |
| **Safe Task: Calculator** | `astrarun.app.AstraApplication` | `LIVE_VERIFIED` | **PASS** | Goal `open calculator`: spawned `calc.exe` in 0.04s, completed task, verified process, terminated cleanly. |
| **Safe Task: Battery Report** | `astrarun.tools.system_adapter` | `LIVE_VERIFIED` | **PASS** | Goal `run a battery report and save it to the AstraRun temporary test directory`: generated 134,204-byte HTML report in 1.25s with zero terminal windows. |
| **Safe Task: Project Test** | `astrarun.tools.projects` | `LIVE_VERIFIED` | **PASS** | Goal `open the AstraRun project and run the approved safe test command`: discovered project, executed bounded pytest suite in 0.32s, stdout captured, 0 terminal windows. |
| **Safe Task: Browser CDP** | `astrarun.perception.cdp` | `LIVE_VERIFIED` | **PASS** | Compressed DOM tree extraction, target resolution, click by semantic ID `@e1` executed via CDP `Runtime.evaluate`. |
| **Visual Task: Grounder** | `astrarun.perception.grounder` | `LIVE_VERIFIED` | **PASS** | CPU-resident OmniParser icon detection on `VF02_unlabeled_icons.png`: target grounded at (236, 63) with 0.85 confidence, 0 MB GPU VRAM. |
| **Clarification Flow** | `astrarun.tasks.runtime.TaskRuntime` | `LIVE_VERIFIED` | **PASS** | Ambiguous goal enters `WAITING_CLARIFICATION`, presents candidates, resolves on selection, completes task without arbitrary guess. |
| **ActionGate Confirmation** | `astrarun.security.action_gate` | `LIVE_VERIFIED` | **PASS** | High-risk mutation enters `WAITING_CONFIRMATION`. CANCEL cleanly revokes token; ALLOW revalidates token with TOCTOU protection. |
| **Task Cancellation** | `astrarun.tasks.runtime.TaskRuntime` | `LIVE_VERIFIED` | **PASS** | Cooperative cancellation releases all resource locks, terminates child process tree inside Job Object, zero orphans. |
| **User Takeover Gating** | `astrarun.tasks.runtime.TaskRuntime.pause_task` | `LIVE_VERIFIED` | **PASS** | Transitions to `PAUSED_USER_ACTIVE`, immediately releases `PHYSICAL_INPUT` lock, displays takeover HUD banner. Resumes with re-observation. |
| **Task Center Window** | `astrarun.ui.task_center.TaskCenterWindow` | `LIVE_VERIFIED` | **PASS** | Real-time card list displaying active and completed tasks with individual pause, resume, and cancel buttons. Verified SQLite persistence. |
| **Live Process Restart** | `astrarun.main` | `LIVE_VERIFIED` | **PASS** | IPC `RESTART` command cleanly releases mutex, spawns new resident process with `0x08000008` flags, old PID exits, new PID reaches READY in 2.01s. |
| **Worker Crash Containment** | `scripts.validate_milestone5v` | `LIVE_VERIFIED` | **PASS** | Abruptly terminated child worker; primary resident UI remained alive and healthy. |
| **Desktop Zero-Console Audit** | `scripts.validate_milestone5v` | `LIVE_VERIFIED` | **PASS** | Win32 `EnumWindows` desktop scan confirmed 0 visible console windows across entire lifecycle. |
| **High-DPI Visual Scaling** | `astrarun.ui.*` | `LIVE_VERIFIED` | **PASS** | Confirmed system scale 1.25x (125%). Bounding boxes, margins, and card geometries scale without clipping. |
| **Resource Footprint** | `scripts.validate_milestone5v` | `LIVE_VERIFIED` | **PASS** | Resident RAM working set: 128.3 MB. GPU VRAM: 0.0 MB idle. |

---

## 3. Production Screenshot Acceptance (Item 5)

All 10 required production screenshots are generated from real instantiated widgets into `docs/screenshots/`:

| ID | Description | File | Size | Visual Review |
| :--- | :--- | :--- | :--- | :--- |
| **A** | Command Surface — Empty | [`screenshot_A_command_surface_empty.png`](../screenshots/screenshot_A_command_surface_empty.png) | 7,904 B | Top-center floating bar, Catppuccin Mocha `#1e1e2e` card, `#89b4fa` `✦` prompt glyph, placeholder typography centered. |
| **B** | Command Surface — Query Entered | [`screenshot_B_command_surface_query.png`](../screenshots/screenshot_B_command_surface_query.png) | 8,995 B | Query `run battery report` rendered crisply with `#cdd6f4` text, no clipping, proper caret padding. |
| **C** | Active Task HUD | [`screenshot_C_active_task_hud.png`](../screenshots/screenshot_C_active_task_hud.png) | 6,879 B | Minimal floating HUD pill with pulse indicator (`#89b4fa`), elapsed time timer, title, and action glyphs. |
| **D** | Expanded Task HUD / Details | [`screenshot_D_expanded_task_hud.png`](../screenshots/screenshot_D_expanded_task_hud.png) | 17,985 B | Full execution card displaying active capability step, step progress bar, target window, and resource lock status. |
| **E** | Task Center | [`screenshot_E_task_center.png`](../screenshots/screenshot_E_task_center.png) | 11,599 B | Multi-task dashboard showing active and completed task ledger items with pause, resume, and cancel buttons. |
| **F** | ActionGate Confirmation Card | [`screenshot_F_actiongate_confirm.png`](../screenshots/screenshot_F_actiongate_confirm.png) | 21,240 B | Amber caution badge (`#fab387`), risk level badge, target operation description, Confirm and Cancel buttons. |
| **G** | Clarification Card | [`screenshot_G_clarification_card.png`](../screenshots/screenshot_G_clarification_card.png) | 25,201 B | Mauve prompt badge (`#cba6f7`), candidate choice list pills with hover feedback, disambiguation query. |
| **H** | PAUSED_USER_ACTIVE Takeover State | [`screenshot_H_user_takeover.png`](../screenshots/screenshot_H_user_takeover.png) | 18,710 B | `✦ Paused — you're using the computer` notification banner, immediate physical lock release notice, Resume and Cancel actions. |
| **I** | Completed Task Result State | [`screenshot_I_completed_result.png`](../screenshots/screenshot_I_completed_result.png) | 18,791 B | Green success badge (`#a6e3a1`), output path link, duration summary, and auto-dismiss timer. |
| **J** | Tray Context Menu | [`screenshot_J_tray_menu.png`](../screenshots/screenshot_J_tray_menu.png) | 6,620 B | Dark-themed menu matching system palette with keyboard accelerators, separator rules, and icon alignment. |

---

## 4. Quantitative Evaluation & Benchmark Results

### 4.1 Milestone 5 Automated Suite (`test_milestone5_resident_app.py`)
```text
============================= test session starts =============================
platform win32 -- Python 3.13.0, pytest-9.1.1, pluggy-1.6.0
collected 12 items

tests/test_milestone5_resident_app.py::test_user_sid_extraction PASSED   [  8%]
tests/test_milestone5_resident_app.py::test_single_instance_acquisition PASSED [ 16%]
tests/test_milestone5_resident_app.py::test_named_pipe_ipc_communication PASSED [ 25%]
tests/test_milestone5_resident_app.py::test_ten_consecutive_launches_single_resident PASSED [ 33%]
tests/test_milestone5_resident_app.py::test_tray_icon_and_states PASSED  [ 41%]
tests/test_milestone5_resident_app.py::test_command_surface_visuals_and_readiness PASSED [ 50%]
tests/test_milestone5_resident_app.py::test_resource_lock_manager PASSED [ 58%]
tests/test_milestone5_resident_app.py::test_task_runtime_lifecycle_and_user_takeover PASSED [ 66%]
tests/test_milestone5_resident_app.py::test_floating_hud_user_takeover PASSED [ 75%]
tests/test_milestone5_resident_app.py::test_floating_hud_action_gate_confirmation PASSED [ 83%]
tests/test_milestone5_resident_app.py::test_task_center_window PASSED    [ 91%]
tests/test_milestone5_resident_app.py::test_zero_terminal_windows_flag_verification PASSED [100%]

============================= 12 passed in 3.82s ==============================
```

### 4.2 Full Platform Test Regression
```text
================ 517 passed, 11 warnings in 209.42s (0:03:29) =================
```
*Zero test regressions across core foundation, sandboxing, dual cognitive engine, hybrid RAG, structured perception, and resident application UI.*

### 4.3 88-Query Deterministic Routing Benchmark
```text
============================================================
 ASTRARUN v0.2 BENCHMARK SUMMARY
============================================================
  Total Queries:            88
  Overall Accuracy:         100.0%
  Exact Resolution Acc:     100.0%
  Fuzzy Resolution Acc:     100.0%
  Unresolved Rejection Acc: 100.0%
  FALSE EXECUTION RATE:     0.0%
  Mean Latency:             2516.64 us
  p50 Latency:              11.45 us
  p95 Latency:              15890.7 us
============================================================
```

### 4.4 Hybrid RAG & Retrieval Benchmark
```text
======================================================================
      ASTRARUN 1.0 MILESTONE 3 HYBRID RAG & RETRIEVAL BENCHMARK
======================================================================
  Recall@1 (Top-1 Accuracy) : 88.9%
  Recall@3 (Top-3 Accuracy) : 100.0%
  Mean Reciprocal Rank (MRR): 0.9444
  Median Latency (p50)      : 7.39 ms
  95th Percentile (p95)     : 9.08 ms
  Mean Query Latency        : 7.60 ms
  Avg Context Prompt Tokens : 282.3 tokens
  False Retrieval Rate      : 0.0%
======================================================================
```

---

## 5. Live Acceptance Sign-Off

Milestone 5 and 5V are fully implemented, hardened, and empirically accepted on the physical workstation.
- All 26 live criteria verified with zero regressions.
- Canonical Win32 stealth flags audited and verified.
- Zero terminal windows across resident lifecycle.
- Next step: Milestone 6 (packaging and distribution).
