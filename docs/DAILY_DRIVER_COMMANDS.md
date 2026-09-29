# DAILY_DRIVER_COMMANDS.md — Daily Driver Command Catalog

> **Milestone**: AstraRun v0.11 (Dynamic Workstation Agent Runtime: Closed-Loop Planning & HUD V2)  
> **Status**: VERIFIED & BENCHMARKED  
> **Target Audience**: AstraRun Users, Systems Engineers, and Workstation Operators  
> **Last Updated**: 2026-09-29  

---

## 1. Overview & Invocation Model

AstraRun v0.11 functions as an ambient, resident workstation assistant and autonomous agent runtime. It is invoked via:
1. **Global Hotkey**: `Alt+Space` (captures foreground origin window and toggles launcher overlay).
2. **System Tray Icon**: Context menu (Restart AstraRun, Exit AstraRun) or click.
3. **Headless / CLI Mode**: `python src/astrarun/main.py --run-command "<utterance>"`
4. **PowerShell Service Wrapper**: `.\start-astrarun.ps1 -Restart` / `.\start-astrarun.ps1 -Status` / `.\start-astrarun.ps1 -Stop`
5. **Cross-Process Summon**: Executing `python src/astrarun/main.py` summons the active resident instance instantly in <1s and exits 0.

All commands are processed through the canonical `AstraApplication.handle_request()` pipeline:
- **Fast-Path Launcher**: Sub-15ms pure deterministic routing for direct application launching, folder navigation, and system status queries.
- **Direct Navigation Commands**: Sub-millisecond instant switching to dedicated workstation views (History, Memory, Skills, Settings, Diagnostics).
- **Dynamic Agent Runtime Loop**: Autonomous goal understanding, DAG plan composition, closed-loop execution, machine observation, empirical verification (`FILE_NON_EMPTY`, `NETWORK_SSID`, `WINDOW_READY`), resource locking, and real-time Live Task HUD V2 tracking with reduced-motion compliance.
- **Neural NLP Sandwich Pipeline**: Multi-clause NLP parsing via spaCy dependency engine embedded between semantic Laya stages with 0 duplicate model weights, 100% literal preservation, and automatic 4-step execution expansion.


---

## 2. Fast-Path Application Launchers (Sub-15ms)

| Command | Route Type | Executed Tool | Description |
| :--- | :--- | :--- | :--- |
| `notepad` | Fast-Path | `open_application` | Launches Windows Notepad instantly. |
| `calc` | Fast-Path | `open_application` | Launches Windows Calculator. |
| `code` | Fast-Path | `open_application` | Launches Visual Studio Code. |
| `cmd` | Fast-Path | `open_application` | Launches Command Prompt. |
| `terminal` | Fast-Path | `open_application` | Launches Windows Terminal. |
| `explorer` | Fast-Path | `open_application` | Launches Windows File Explorer. |
| `edge` | Fast-Path | `open_application` | Launches Microsoft Edge browser. |
| `chrome` | Fast-Path | `open_application` | Launches Google Chrome browser. |
| `open vivaldi` | Fast-Path | `open_application` | Launches Vivaldi browser. |
| `launch taskmgr` | Fast-Path | `open_application` | Launches Windows Task Manager. |
| `start regedit` | Fast-Path | `open_application` | Launches Windows Registry Editor. |
| `go powershell` | Fast-Path | `open_application` | Launches PowerShell. |

---

## 3. Direct Navigation & Platform Views (< 1ms)

| Command | Action / Event | Target View | Description |
| :--- | :--- | :--- | :--- |
| `history` | `open_history` | History / Timeline UI | Displays the persistent SQLite Task Ledger, audit timeline, and conversation history. |
| `show history` | `open_history` | History / Timeline UI | Synonym for history view. |
| `memory` | `open_memory` | Memory & Learning View | Inspects learned user aliases, explicit teachings, preferences, and corrections. |
| `what have you learned?`| `open_memory` | Memory & Learning View | Natural language query opening the memory inspection view. |
| `skills` | `open_skills` | Skill Review View | Opens interactive UI to review, approve, reject, or pin mined workflow skills. |
| `settings` | `open_settings` | Settings Dialog | Configuration dialog for theme, hotkey bindings, search index, and startup settings. |
| `preferences` | `open_settings` | Settings Dialog | Synonym for settings dialog. |
| `diagnostics` | `open_diagnostics` | Diagnostics Dialog | Real-time platform telemetry: hardware specs, active monitors, capability count, hotkey status. |
| `what can you do?` | `list_result` | Capability Catalog | Displays all 77 registered workstation capabilities across 10 categories. |
| `capabilities` | `list_result` | Capability Catalog | Synonym for workstation capabilities query. |

---

## 4. Window Intelligence & Snapping Commands

All commands implicitly target the **origin window** (the window that had focus when `Alt+Space` was pressed) unless an explicit window title is specified.

| Command | Resolved Capability | Bounds / Target Geometry | Reversible |
| :--- | :--- | :--- | :--- |
| `snap left` | `snap_window_left` | Left 50% of current monitor work area | Yes (`undo`) |
| `snap right` | `snap_window_right` | Right 50% of current monitor work area | Yes (`undo`) |
| `snap this window left` | `snap_window_left` | Left 50% via explicit pronoun resolution | Yes (`undo`) |
| `maximize window` | `maximize_window` | Maximized state (`SW_MAXIMIZE`) | Yes (`undo`) |
| `minimize window` | `minimize_window` | Minimized state (`SW_MINIMIZE`) | Yes (`undo`) |
| `restore window` | `restore_window` | Restored normal state (`SW_RESTORE`) | Yes (`undo`) |
| `snap to top left` | `snap_window` (`TOP_LEFT`) | Upper-left quadrant (50% W x 50% H) | Yes (`undo`) |
| `snap to top right` | `snap_window` (`TOP_RIGHT`) | Upper-right quadrant (50% W x 50% H) | Yes (`undo`) |
| `snap to bottom left` | `snap_window` (`BOTTOM_LEFT`) | Lower-left quadrant (50% W x 50% H) | Yes (`undo`) |
| `snap to bottom right`| `snap_window` (`BOTTOM_RIGHT`)| Lower-right quadrant (50% W x 50% H) | Yes (`undo`) |
| `snap left two thirds`| `snap_window` (`LEFT_TWO_THIRDS`)| Left 66.6% width split | Yes (`undo`) |
| `snap right one third`| `snap_window` (`RIGHT_ONE_THIRD`)| Right 33.3% width split | Yes (`undo`) |
| `snap top half` | `snap_window` (`TOP_HALF`) | Top 50% horizontal split | Yes (`undo`) |
| `snap bottom half` | `snap_window` (`BOTTOM_HALF`) | Bottom 50% horizontal split | Yes (`undo`) |
| `focus chrome` | `focus_window` | Switches focus to Chrome window | N/A |
| `close window` | `close_window` | Sends graceful `WM_CLOSE` to origin window | No |
| `undo` | `undo_last_window_move` | Restores previous geometry from LIFO stack | N/A |
| `undo last window move`| `undo_last_window_move` | Restores previous geometry from LIFO stack | N/A |

---

## 5. Multi-Monitor & Desktop Arrangement

| Command | Capability | Description |
| :--- | :--- | :--- |
| `move to monitor 1` | `move_window_to_monitor` | Relocates window to primary display work area. |
| `move to monitor 2` | `move_window_to_monitor` | Relocates window to secondary display work area. |
| `move window to next screen` | `move_window_to_monitor` | Moves active window to adjacent display monitor. |
| `tile windows` | `arrange_desktop` | Tiles all visible desktop windows side-by-side. |
| `arrange desktop split horizontal` | `arrange_desktop` | Horizontally splits visible windows. |
| `arrange desktop split vertical` | `arrange_desktop` | Vertically splits visible windows. |
| `arrange desktop quad` | `arrange_desktop` | Arranges 4 primary windows into a 2x2 grid. |

---

## 6. Synchronized Compound Natural-Language Commands (v0.10.2)

Compound queries containing conjunctions (`and`, `then`, `&`, `;`) are decomposed by `ClauseDecomposer`, compiled into synchronized multi-step execution plans by `WorkflowCompiler`, and bound with implicit context by `WorkflowContext`. Suggestion popups are automatically suppressed to allow full sentence submission.

| Command | Decomposed Steps | Synchronized Plan | Telemetry & Result |
| :--- | :--- | :--- | :--- |
| `open notepad and type pqr` | Launch App + Type Text | `open_application` -> `wait_for_window` -> `resolve_editable_element` -> `type_text` | Launches Notepad, waits for HWND, resolves `RichEditD2DPT`, types `"pqr"` via `SendInput`. |
| `launch notepad and type meeting notes` | Launch App + Type Text | `open_application` -> `wait_for_window` -> `resolve_editable_element` -> `type_text` | Injects literal string `"meeting notes"` into document. |
| `open notepad and maximize window` | Launch App + Layout | `open_application` -> `wait_for_window` -> `maximize_window` | Launches Notepad, awaits ready state, then maximizes window. |
| `launch terminal and snap left` | Launch App + Layout | `open_application` -> `wait_for_window` -> `snap_window_left` | Launches Terminal, awaits ready state, snaps to left half. |
| `open code and snap right` | Launch App + Layout | `open_application` -> `wait_for_window` -> `snap_window_right` | Launches VS Code, awaits ready state, snaps to right half. |
| `snap window left and maximize` | Window Chaining | `snap_window_left` -> `maximize_window` | Chains window operations on origin window. |
| `press ctrl+a and copy` | Shortcut Chaining | `press_keyboard_shortcut(Ctrl+A)` -> `press_keyboard_shortcut(Ctrl+C)` | Selects all text and copies to system clipboard. |
| `copy and paste here` | Shortcut Chaining | `press_keyboard_shortcut(Ctrl+C)` -> `press_keyboard_shortcut(Ctrl+V)` | Replicates standard copy-paste pipeline. |
| `select all and press delete` | Shortcut Chaining | `press_keyboard_shortcut(Ctrl+A)` -> `press_keyboard_shortcut(Delete)` | Selects all and deletes in active control. |
| `press enter and type confirmed` | Shortcut + Typing | `press_keyboard_shortcut(Enter)` -> `type_text(confirmed)` | Dispatches Enter key and types `"confirmed"`. |

---

## 7. Dynamic Workstation Agent Goals (v0.11)

AstraRun v0.11 executes natural language goals via autonomous closed-loop planning:
$$\text{UNDERSTAND GOAL} \longrightarrow \text{PLAN (DAG)} \longrightarrow \text{ACT} \longrightarrow \text{OBSERVE} \longrightarrow \text{VERIFY} \longrightarrow \text{COMPLETED}$$

Goals execute through structured interaction surfaces (Tier A Native Win32/WLAN > Tier B Structured CLI > Tier C UI Automation) with empirical verification and live Task HUD V2 tracking:

| Natural Language Goal | Intent / Capability | Interaction Tier | Verifier Strategy | Description & Output |
| :--- | :--- | :--- | :--- | :--- |
| `run a battery report and save it in Downloads as astra-battery.html` | `generate_battery_report` | Tier B (Structured CLI) | `FILE_NON_EMPTY` | Generates official Windows battery report via `powercfg /batteryreport`, normalizes path to user Downloads folder, and verifies non-empty HTML output. |
| `scan wifi` / `list available wifi` | `wifi_scan` | Tier A (Native Win32) | `RETURN_CODE_ONLY` | Scans available 802.11 BSS networks directly in-process via `wlanapi.dll` with 0 subprocesses. Displays SSIDs and signal qualities. |
| `check wifi status` | `wifi_status` | Tier A (Native Win32) | `RETURN_CODE_ONLY` | Queries native WLAN interface state, active SSID connection, BSS type, and signal quality. |
| `connect to wifi <ssid>` | `wifi_connect` | Tier A (Native Win32) | `NETWORK_SSID` | Connects to targeted SSID using fuzzy/case-insensitive profile matching (`WiFiResolver`) with empirical network verification. |
| `disconnect wifi` | `wifi_disconnect` | Tier A (Native Win32) | `RETURN_CODE_ONLY` | Gracefully disconnects WLAN interface via native `WlanDisconnect`. |

---

## 8. Workstation Telemetry & System Status

| Command | Capability | Returned Telemetry |
| :--- | :--- | :--- |
| `system status` | `system_summary` | Aggregate CPU %, RAM usage, C: drive free space, GPU % and VRAM. |
| `cpu status` | `cpu_metrics` | Overall CPU utilization % and logical core count. |
| `memory status` | `memory_metrics` | Used RAM, Total RAM, and Available RAM in GB. |
| `disk status` | `disk_usage` | Total, used, and free disk space across primary storage. |
| `battery status` | `battery_status` | Battery percentage, charging status, and remaining time. |
| `audio status` | `audio_status` | Master audio volume %, mute state, and default endpoint. |
| `network connections` | `list_network_connections` | Active established and listening socket connections. |
| `listening ports` | `list_listening_ports` | Active TCP listening ports and owning PIDs. |
| `list windows` | `list_windows` | Enumeration of all visible top-level desktop windows. |
| `foreground window` | `foreground_window` | Inspects currently focused foreground HWND and title. |

---

## 9. Safety-Gated & Policy-Protected Operations

| Command | Safety Status | Triggered Gate | Safety Mechanism |
| :--- | :--- | :--- | :--- |
| `kill process 1234` | `confirm` | ActionGate (CONFIRM) | Requires explicit user confirmation card before terminating PID. |
| `stop process 5678` | `confirm` | ActionGate (CONFIRM) | Requires explicit user confirmation card. |
| `format c:` | `blocked` | ActionGate (BLOCK) | Hard-blocked: Dangerous destructive system command. |
| `reg delete hklm` | `blocked` | ActionGate (BLOCK) | Hard-blocked: Protected registry root key modification. |
| `del /f /q c:\` | `blocked` | ActionGate (BLOCK) | Hard-blocked: Mass filesystem wipe pattern. |
| `rmdir /s c:\windows` | `blocked` | ActionGate (BLOCK) | Hard-blocked: Critical Windows directory destruction. |
| `kill process csrss.exe` | `blocked` | ActionGate (BLOCK) | Hard-blocked: Critical Windows core process protection. |
| `kill process lsass.exe` | `blocked` | ActionGate (BLOCK) | Hard-blocked: Local Security Authority Subsystem protection. |
