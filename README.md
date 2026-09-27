# AstraRun — Windows Intelligent Command Launcher & Workstation Control Plane (v0.9)

AstraRun is a local, lightweight, low-latency Windows command launcher and workstation orchestrator engineered as the foundational command interface for an evolving AI-assisted workstation control ecosystem.

AstraRun replaces fragile string-interpolated shell execution with a strictly typed pipeline:
`Natural Language -> NLP Engine -> StructuredUtterance -> Context Engine -> Entity Resolution -> ActionGate -> Task Runtime -> Capability Registry -> Windows OS`.

---

## Key Capabilities (v0.9)

- **Instantaneous Hotkey Activation**: Summoned with `Alt+Space` in ~4.5ms from a pre-warmed resident background process.
- **Window Intelligence & Native Win32 Subsystem (v0.9)**: 12 new capabilities expanding the platform to **59 typed workstation capabilities** across 9 OS categories with zero external GUI automation dependencies.
- **The Origin Window Invariant (v0.9)**: Captures foreground `HWND` synchronously on `Alt+Space` before the launcher steals focus; grounds relative actions (`snap left`, `maximize window`, `snap to top left`, `close window`) and deictic pronouns (`this window`, `it`) with automatic focus restoration.
- **Self-Targeting Window Immunity (v0.9)**: Process-wide `_ASTRARUN_HWNDS` registry unconditionally prevents AstraRun from modifying, snapping, or closing its own resident windows.
- **Deterministic Desktop Tiling Mathematics (v0.9)**: 11 exact geometric layout algorithms (`FULL`, `LEFT_HALF`, `RIGHT_HALF`, `TOP_HALF`, `BOTTOM_HALF`, `TOP_LEFT`, `TOP_RIGHT`, `BOTTOM_LEFT`, `BOTTOM_RIGHT`, `LEFT_TWO_THIRDS`, `RIGHT_ONE_THIRD`) and atomic multi-window arrangement (`arrange_desktop`).
- **Bounded LIFO Window Restore Stack (v0.9)**: Thread-safe undo history (max depth 20, 600s TTL) enabling instantaneous 1-click or voice `undo` in **0.06 ms**.
- **Multi-Monitor Geometry & DPI Awareness (v0.9)**: Multi-monitor enumeration via `EnumDisplayMonitors` with Per-Monitor DPI v2 awareness and work area boundary compliance.
- **Canonical Composition Root (`AstraApplication`) (v0.9)**: Single pipeline unifying all 14 platform subsystems, enforcing direct navigation, sub-3ms fast-path launcher routing (0.47 ms measured), rich NLP, ActionGate safety, and background learning.
- **Ambient Resident UI & System Tray (v0.9)**: Windows named mutex single-instance lock (`Local\AstraRun_SingleInstance_Mutex`), programmatically rendered high-DPI Catppuccin Mocha tray icon, interactive Diagnostics Dialog, and Settings Dialog.
- **Memory, Learning & Skill Foundation (v0.8.5)**: Durable workstation semantic memory, natural language teaching parser, and candidate skill discovery operating strictly off the interactive hot path in background threads.
- **Zero Neural / Learned Execution Authority**: Learning never directly executes commands or expands computer control authority. Every proposed action passes through `ActionGate` and hard policy enforcement.
- **Non-Learnable Security Policies**: Repeating high-risk capabilities or confirmations can **NEVER** downgrade `CONFIRM` to `AUTO`, bypass `ActionGate`, or alias protected system processes (`lsass.exe`, `csrss.exe`) and dangerous commands (`format c:`, `rmdir /s`).
- **Dual-Database Architecture**: Physical separation between ephemeral execution tracking (`data/astra_history.db`, 30-day retention) and durable workstation knowledge (`data/astra_learning.db`, SQLite WAL mode, `PRAGMA user_version = 1`, append-only audit trail).
- **Task Runtime & Lifecycle Authority**: Centrally governed by `TaskManager` across a formal 14-state directed Finite State Machine (`TaskStatus`).
- **Live Activity Timeline UI**: Real-time observable step visualization (`TaskActivityView`) rendering ground-truth system operations with zero fake progress or fabricated thinking.
- **Benchmark-Proven Performance**:
  - **Window Benchmark V1 (330 cases)**: **100.0% Accuracy**, **0.00% Wrong Window Action Rate**, **0.0229 ms mean latency**.
  - **Product Benchmark V1 (220 cases)**: **100.0% Accuracy**, **0.00% False Execution Rate**, **0.4699 ms fast-path routing latency** (< 3ms invariant verified).
  - **Learning Benchmark V1 (320 cases)**: **100.0% Accuracy**, **0.00% False Memory Activation Rate**, **100.0% Security Invariant Enforcement Rate**, **24.57 ms mean latency**.
  - **Task Benchmark V1 (300 cases)**: **100.0% Status Accuracy**, **100.0% Sequence Accuracy**, **100.0% Persistence Accuracy**, **73.36 ms mean latency**.
  - **Capability Benchmark V1 (520 cases)**: **100.0% Capability Accuracy**, **100.0% Permission Accuracy**, **100.0% Block Recall**, **0.783 ms mean latency**.
  - **Action Benchmark V1 (330 cases)**: **100.0% Intent Accuracy**, **100.0% Gate Accuracy**, **0.00% False Execution Rate (FER)**, **0.091 ms mean latency**.
  - **NLP Benchmark V1 (620 cases)**: **100.0% Intent Accuracy**, **95.2% Clause Acc**, **0.00% Negated Action Leakage Rate**, **7.809 ms mean latency**.
- **252 Passing Automated Tests**: 100% test pass rate across 20 test modules in ~18.78s.

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
        TM --> Reg["CapabilityRegistry (47 Capabilities)"]
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
        Reg --> Win["Windows (Discovery & Enumeration)"]
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

