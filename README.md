# AstraRun — Windows Intelligent Command Launcher & Workstation Control Plane (v0.11)

AstraRun is a local, lightweight, low-latency Windows command launcher and workstation orchestrator engineered as the foundational command interface for an evolving AI-assisted workstation control ecosystem.

AstraRun replaces fragile string-interpolated shell execution with a strictly typed pipeline:
`Natural Language -> GoalPlanner -> DAG Execution Plan -> AgentExecutionEngine -> MachineObserver -> StepVerifier -> Live Task HUD V2 -> Windows OS`.

---

## Key Capabilities (v0.11)

- **Dynamic Workstation Agent Runtime (v0.11)**:
  - **Closed-Loop Execution**: Executes the autonomous workstation loop:
    $$\text{UNDERSTAND GOAL} \longrightarrow \text{PLAN} \longrightarrow \text{ACT} \longrightarrow \text{OBSERVE} \longrightarrow \text{VERIFY} \longrightarrow \text{REPLAN} \longrightarrow \text{COMPLETED}$$
  - **Goal & Plan DAG Abstraction**: Core abstraction centered on high-level `UserGoal` and directed acyclic `Plan` graphs with automated topological readiness and data mapping.
  - **Zero Raw Shell Invariant**: Models select strictly typed capability schemas with parameter validation; zero arbitrary shell generation.
- **Machine-Readable Capability Schemas (v0.11)**:
  - 77 registered workstation capabilities dynamically exporting typed `CapabilitySchema` contracts declaring parameter schemas, side effects, privilege levels, retry policies, and verifier strategies.
  - **Strict Interaction Tier Hierarchy**: Tier A (Native Win32/WLAN) > Tier B (Structured CLI Adapters) > Tier C (UI Automation) > Tier D (SendInput/Shortcuts) > Tier E (Visual Fallback).
- **Native Wi-Fi Capabilities (Tier A, v0.11)**:
  - Direct integration with Windows Native Wi-Fi API (`wlanapi.dll`) via `ctypes` (`WlanOpenHandle`, `WlanEnumInterfaces`, `WlanGetAvailableNetworkList`, `WlanConnect`).
  - Programmatic Wi-Fi scanning (`wifi_scan`), connection status (`wifi_status`), connection (`wifi_connect`), and disconnection (`wifi_disconnect`).
  - Fuzzy SSID matching (`WiFiResolver`) handling spoken or mistyped network names. Zero child processes, zero credential exposure.
- **System Utility Adapters & Battery Report (Tier B, v0.11)**:
  - Safe `SystemUtilityAdapter` and `PowerCfgAdapter` executing trusted utilities with `shell=False` and metacharacter filtering.
  - Generates full Windows battery life and health diagnostic reports (`powercfg.exe /batteryreport`) with portable Downloads resolution and empirical `FILE_NON_EMPTY` verification.
- **Workstation Resource Locking (v0.11)**:
  - `ResourceLockManager` providing granular mutual exclusion for physical workstation resources (`WINDOW:<hwnd>`, `FILE:<path>`, `NETWORK:WIFI`, `PROCESS:<pid>`).
- **Centralized Motion System & Live Task HUD V2 (v0.11)**:
  - `MotionTokens` system defining standardized animation durations and easing curves.
  - Automatic reduced-motion accessibility support via Win32 `SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION)` collapsing durations to 0ms.
  - Live Task HUD V2 featuring honest progress modes (`INSTANT`, `DETERMINATE`, `INDETERMINATE`, `EVENT_DRIVEN`).
  - `TaskETAEstimator` computing remaining duration based on measured step execution times.
  - Collapsible dynamic step list with status glyphs and cooperative task cancellation.
  - Non-focus-stealing invariant strictly enforced (`WS_EX_NOACTIVATE`, `WA_ShowWithoutActivating`).
- **Benchmark-Proven Performance & Safety**:
  - **Live Workstation Acceptance Suite**: **100.0% Pass Rate** across Autonomous Battery Report Goal, Native Wi-Fi, Resource Locking, and HUD V2 (`docs/V0.11_LIVE_ACCEPTANCE.md`).
  - **384 Passing Automated Tests**: 100% test pass rate across 28 test modules in 233s.
  - **100% Data Preservation**: Zero disruption to user Notepad sessions or unsaved tabs.


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

