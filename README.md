# AstraRun — Windows Intelligent Command Launcher & Workstation Control Plane (v0.10.1)

AstraRun is a local, lightweight, low-latency Windows command launcher and workstation orchestrator engineered as the foundational command interface for an evolving AI-assisted workstation control ecosystem.

AstraRun replaces fragile string-interpolated shell execution with a strictly typed pipeline:
`Natural Language -> NLP Engine -> StructuredUtterance -> Context Engine -> Entity Resolution -> ActionGate -> Task Runtime -> Capability Registry -> Windows OS`.

---

## Key Capabilities (v0.10.1)

- **Real Alt+Space Launcher & Win32 Presentation Pipeline (v0.10.1)**: Summoned reliably with `Alt+Space` in ~4.5ms from a pre-warmed resident background process. Uses `AttachThreadInput` to defeat Windows 11 `LockSetForegroundWindow` restrictions, captures origin window HWND synchronously before UI spawn, and drops in smoothly with 150ms `OutCubic` entrance and 110ms `InCubic` exit animations.
- **Decoupled Floating Task HUD & Non-Focus-Stealing Invariant (v0.10.1)**: Lightweight, frameless top-right HUD tracking asynchronous task progress (`PASSIVE_PROGRESS`, `SUCCESS`, `ERROR`, `WAITING_CONFIRMATION`). Enforces Win32 `WS_EX_NOACTIVATE (0x08000000)`, `Qt.WindowType.WindowDoesNotAcceptFocus`, and `Qt.WidgetAttribute.WA_ShowWithoutActivating` to ensure background tasks NEVER steal keyboard focus from active target applications (e.g. Notepad, VS Code, Browser).
- **Compound NLP & Multi-Step Workflows (v0.10.1)**: Clause decomposition and workflow compilation transforming multi-clause instructions (e.g. `open notepad and type hello from Astra`) into sequential execution pipelines with auto-resolved application paths.
- **Semantic UI Automation Subsystem (v0.10)**: 11 capabilities expanding the platform to **70 typed workstation capabilities** across 10 OS categories with direct Microsoft UI Automation (`IUIAutomation`) tree inspection and control manipulation.
- **Dedicated COM MTA Worker Thread (v0.10)**: Isolates heavy COM accessibility traversals onto a dedicated background thread, eliminating GUI thread deadlocks and message pump freezes.
- **Strict Control Mutation Invariant**:
  $$\text{UIA Semantic Pattern} > \text{Win32 Control Message} > \text{Keyboard Shortcut} > \text{Coordinate Interaction (PERMANENTLY PROHIBITED)}$$
  Zero blind coordinate clicking (`pyautogui.click(x, y)`). All control manipulations use strongly-typed UIA patterns (`InvokePattern`, `ValuePattern`, `TogglePattern`, `SelectionItemPattern`, `ScrollPattern`).
- **Safe 64-bit SendInput & Clipboard Memory ABI**: Full 40-byte union alignment (`sizeof(INPUT) == 40`) for reliable Unicode keystroke typing and shortcut dispatch (`Ctrl+C`, `Ctrl+V`, `Alt+F4`), plus safe 64-bit global memory handle copying for clipboard operations.
- **Text Payload as Data Invariant**: Text entry (`type "format c:" into notepad`) is treated strictly as literal data, never evaluated as shell commands.
- **Password Masking & Privacy Invariant**: Controls marked `IsPassword` or matching credential heuristics have their values completely masked; secrets are never logged, persisted in SQLite, or exported in telemetry.
- **Destructive Button Gating**: High-risk control actions (`delete`, `remove`, `format`, `drop`, `wipe`, `purge`, `reset`, `buy`, `terminate`) are gated behind `ActionGate` user confirmation prompts.
- **Window Intelligence & Native Win32 Subsystem (v0.9)**: Ground-truth window management with the Origin Window Invariant, 11 deterministic tiling layouts, bounded LIFO undo stack (0.06 ms restore), and multi-monitor DPI awareness.
- **Self-Targeting Window Immunity**: Process-wide `_ASTRARUN_HWNDS` registry unconditionally prevents AstraRun from modifying, snapping, or closing its own resident windows.
- **Canonical Composition Root (`AstraApplication`)**: Single pipeline unifying all 15 platform subsystems, enforcing direct navigation, sub-3ms fast-path launcher routing (0.47 ms measured), rich NLP, ActionGate safety, and background learning.
- **Ambient Resident UI & System Tray**: Windows named mutex single-instance lock (`Local\AstraRun_SingleInstance_Mutex`), programmatically rendered high-DPI Catppuccin Mocha tray icon, interactive Diagnostics Dialog, and Settings Dialog.
- **Memory, Learning & Skill Foundation (v0.8.5)**: Durable workstation semantic memory, natural language teaching parser, and candidate skill discovery operating strictly off the interactive hot path in background threads.
- **Task Runtime & Lifecycle Authority (v0.8)**: Centrally governed by `TaskManager` across a formal 14-state directed Finite State Machine (`TaskStatus`) with persistent SQLite Task Ledger.
- **Benchmark-Proven Performance**:
  - **Live UI Acceptance Suite (30 cases)**: **100.0% Pass Rate** (30 / 30), **0.00% Focus Theft**, **0.00% FER** (`docs/V0.10.1_LIVE_UI_ACCEPTANCE.md`).
  - **Interaction Benchmark V1 (405 cases)**: **100.0% Accuracy**, **0.00% WEAR**, **0 password leaks**, **100.0% destructive block recall**, **0.0621 ms mean latency**.
  - **Product Benchmark V2 (280 cases)**: **100.0% Accuracy**, **0.00% False Execution Rate**, **0.5983 ms fast-path routing latency** (< 3ms invariant verified).
  - **Window Benchmark V1 (330 cases)**: **100.0% Accuracy**, **0.00% Wrong Window Action Rate**, **0.0169 ms mean latency**.
  - **Learning Benchmark V1 (320 cases)**: **100.0% Accuracy**, **0.00% False Memory Activation Rate**, **100.0% Security Invariant Enforcement Rate**, **28.32 ms mean latency**.
  - **Task Benchmark V1 (300 cases)**: **100.0% Status Accuracy**, **100.0% Sequence Accuracy**, **100.0% Persistence Accuracy**, **79.58 ms mean latency**.
  - **Capability Benchmark V1 (520 cases)**: **100.0% Capability Accuracy**, **100.0% Permission Accuracy**, **100.0% Block Recall**, **0.624 ms mean latency**.
  - **Action Benchmark V1 (330 cases)**: **100.0% Intent Accuracy**, **100.0% Gate Accuracy**, **0.00% False Execution Rate (FER)**, **0.094 ms mean latency**.
  - **NLP Benchmark V1 (620 cases)**: **100.0% Intent Accuracy**, **95.2% Clause Acc**, **0.00% Negated Action Leakage Rate**, **7.275 ms mean latency**.
- **307 Passing Automated Tests**: 100% test pass rate across 22 test modules in ~32.46s.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Input ["User Input & Context"]
        User["User Typing / Hotkey (Alt+Space)"] --> UI["PySide6 Launcher Window"]
        CtxEngine["WorkstationContextEngine"] -.->|Foreground App, Ports, Recents| Resolver
    end

    subgraph Understanding ["Hybrid NLP & Planning Layer"]
        UI -->|Raw Query| NLP["Hybrid NLP Engine (v0.6.5)"]
        NLP -->|StructuredUtterance| Compiler["WorkflowCompiler"]
        Compiler -->|WorkflowProposal| Gate["ActionGate"]
    end

    subgraph Safety ["Action Gate & Policy Arbiter"]
        Gate -->|Tier 0 Hard Policy Check| PolicyBlock{"Violates Hard Policy?"}
        PolicyBlock -->|Yes| BlockOutcome["BLOCK (shutdown, format, lsass, script execution)"]
        PolicyBlock -->|No| AmbigCheck{"Ambiguous Target or Multiple Windows?"}
        AmbigCheck -->|Yes| ClarifyOutcome["CLARIFY (DisambiguationCard / ListResultCard)"]
        AmbigCheck -->|No| RiskCheck{"High Risk or Gated Action?"}
        RiskCheck -->|Yes| ConfirmOutcome["CONFIRM (ConfirmationCard + TOCTOU Token)"]
        RiskCheck -->|No| AllowOutcome["ALLOW (Auto-Execute via Capability Registry)"]
    end

    subgraph Runtime ["Task Runtime & Ledger (v0.8)"]
        AllowOutcome --> TM["TaskManager (14-State FSM)"]
        ConfirmOutcome -->|User Confirms Ctrl+Enter| TM
        TM --> Reg["CapabilityRegistry (70 Capabilities)"]
        TM -.->|Emit Events| Bus["TaskEventBus (31 Observable Events)"]
        Bus -.-> ActView["TaskActivityView (Live Timeline)"]
        TM -.->|Persist State| Ledger[("SQLite TaskLedger (WAL Mode)")]
        Ledger -.-> HistView["HistoryView (Split-View Audit)"]
    end

    subgraph Capabilities ["Workstation Capabilities"]
        Reg --> Apps["Applications (EnumWindows, WM_CLOSE, Focus)"]
        Reg --> Files["Files (Safe Index, Reveal, Metadata)"]
        Reg --> Procs["Processes (Inspect, Resource, TOCTOU Kill)"]
        Reg --> Net["Network (Ports, Process-on-Port)"]
        Reg --> Sys["System (CPU, RAM, GPU, LockWorkStation)"]
        Reg --> Proj["Projects (Git Status, Dev Ports)"]
        Reg --> Win["Windows (Tiling, Snapping, Undo)"]
        Reg --> UI["Interaction (Inspect UI, Click, Text, Shortcuts)"]
        Reg -.->|Record Facts| Store["Structured ObservationStore (200 facts)"]
    end

    subgraph Learning ["Learning & Memory Subsystem (v0.8.5)"]
        TM -.->|Execution Events & Corrections| LE["LearningEngine (Background)"]
        UI -.->|Teaching Utterances| LE
        LE --> EE["EvidenceExtractor"]
        LE --> PM["PatternMiner (Support >= 3)"]
        EE --> MS["MemoryStore & AliasManager"]
        MS --> LDB[("SQLite LearningDB (WAL Mode)")]
        MS -.->|Learned Aliases (Multi-Tier)| Resolver
        PM -.->|Candidate Workflows| SK["SkillManager"]
        SK -.->|Human Review Required| SKUI["SkillReviewWidget"]
        LDB -.-> MemView["MemoryView (Audit & Provenance)"]
    end
```

---

## Keyboard Controls

| Shortcut / Key | Context | Action |
| :--- | :--- | :--- |
| **`Alt + Space`** | Global (Anywhere) | Toggle / summon AstraRun command bar |
| **`Up / Down Arrow`** | Command Bar / Cards / Lists | Navigate through ranked suggestions, results, or history items |
| **`Tab`** | Command Bar Active | Autocomplete input with selected suggestion title |
| **`Enter`** | Low-Risk / Result Card | Execute selected suggestion or trigger highlighted item |
| **`Ctrl + Enter`** | Confirmation Card | Explicitly confirm high-risk action (`terminate_process`) |
| **`Escape`** | Command Bar / Cards / Activity | Dismiss AstraRun, cancel active task, or exit confirmation |
| **`Click Outside`** | Command Bar Active | Auto-dismisses window (configurable) |

---

## Supported Commands

### 1. Applications & Window Management
```text
running apps                   # List interactive applications via visible windows
is vscode running              # Check if Visual Studio Code is open
focus chrome                   # Bring Google Chrome to foreground (or clarify if multiple)
close notepad                  # Gracefully closes Notepad via WM_CLOSE (prompts save)
open calculator                # Launches Calculator via discovery cache
```

### 2. Files & User Directories
```text
find file report.pdf           # Search files across Workspace, Downloads, Documents
latest screenshot              # Finds and reveals the most recent screenshot
recent files                   # Lists recent documents and files across user roots
open notes.txt                 # Opens document in registered system editor
reveal report.pdf              # Highlights file in File Explorer (/select)
open script.ps1                # BLOCKED by security policy (suggests reveal_file)
```

### 3. Processes & Resource Monitoring
```text
top processes by memory        # Lists top processes sorted by RSS memory usage
inspect process python         # Displays CPU%, memory, threads, ports, parent
who is using port 3000         # Identifies process bound to port 3000
stop process using port 3000   # Prompts confirmation card with TOCTOU token
kill lsass                     # BLOCKED: protected system process
```

### 4. Network & System Diagnostics
```text
listening ports                # Real-time list of all listening TCP/UDP ports
system status                  # Comprehensive host summary (CPU, RAM, disk, battery)
gpu status                     # Dedicated NVIDIA GPU metrics (VRAM, temp, utilization)
lock computer                  # Instantly locks Windows desktop safely
shutdown pc                    # BLOCKED: system shutdown blocked by security policy
```

### 5. Multi-Step Workflows
```text
open AstraRun and check git status   # Compiles sequential multi-capability workflow
find latest screenshot and reveal it # Resolves dependencies across capabilities
check system status and gpu          # Composes multiple diagnostic cards
```

### 6. Teaching, Preferences & Memory (v0.8.5)
```text
remember that notes is notepad       # Teaches explicit application alias
always use code for editing          # Teaches explicit developer preference
learn skills from history            # Runs offline pattern miner over task ledger
show learned memories                # Opens MemoryView inspector with full provenance
```

