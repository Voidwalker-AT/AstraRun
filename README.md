# AstraRun — Windows Intelligent Command Launcher & Workstation Control Plane (v0.10.3)

AstraRun is a local, lightweight, low-latency Windows command launcher and workstation orchestrator engineered as the foundational command interface for an evolving AI-assisted workstation control ecosystem.

AstraRun replaces fragile string-interpolated shell execution with a strictly typed pipeline:
`Natural Language -> Neural NLP Sandwich -> StructuredUtterance -> Context Engine -> Entity Resolution -> ActionGate -> Task Runtime -> Capability Registry -> Windows OS`.

---

## Key Capabilities (v0.10.3)

- **Neural NLP Sandwich Architecture (v0.10.3)**: Embeds a high-precision `spaCy` neural dependency engine between semantic `Laya` (ModernBERT 421M) decision stages.
  - **Single Shared 421M Instance**: Zero duplicate model weights between Pre-Gate and Verifier stages (+0MB RAM bloat).
  - **100% Verbatim Literal Preservation**: Text payloads (`type pqr`, `enter text "secret"`) preserve exact character offsets without token truncation or normalization.
  - **100% Negation Safety**: Strict structural negation gating (`negated: bool`) ensures negative requests (`don't open notepad`) are completely excluded from execution.
  - **Benchmark Proven**: 98.44% test compound accuracy, 100% negation accuracy, 17.09ms p95 latency (`docs/NEURAL_NLP_BENCHMARK.md`).
- **True Resident Background Application Mode (v0.10.3)**:
  - **Zero Persistent Consoles**: Spawns detached via `pythonw.exe` (`0x00000008 | 0x00000200`). Leaves zero background `powershell.exe`, `cmd.exe`, or terminal windows.
  - **Global Hotkey & Tray**: Resident in system notification area with `Alt+Space` hotkey, "Restart AstraRun", and "Exit AstraRun" lifecycle controls.
  - **Instant Cross-Process Summon**: Re-invoking the launcher signals the active resident instance via named mutex and trigger file in 928ms with exit code 0.
- **Native Interactive Desktop Process Launching (v0.10.3)**:
  - Launches desktop applications directly onto `WinSta0\Default` using native Win32 `CreateProcessW` with `lpDesktop = r"WinSta0\Default"`.
  - Resolves packaged Windows 11 AppX applications (like modern Notepad) without background suspend deadlocks or DCOM session starvation.
- **Synchronized Compound Workflow Pipeline (v0.10.2)**: Resolves multi-clause natural-language commands (e.g. `open notepad and type pqr`) into synchronized 4-step execution chains: `open_application` -> `wait_for_window` -> `resolve_editable_element` -> `type_text`.
- **Compound-Aware Suggestion Suppression (v0.10.2)**: Detects syntactic conjunctions (`and`, `then`, `&`, `;`) and suppresses single-app autocomplete suggestions, guaranteeing that Enter dispatches the complete natural-language instruction without truncation.
- **WorkflowContext State Propagation (v0.10.2)**: Tracks mutable runtime entities (`last_opened_application`, `last_opened_window` HWND, `last_ui_element`) across sequential steps, enabling downstream operations to automatically bind handles discovered upstream.
- **Decoupled Floating Task HUD & Non-Focus-Stealing Invariant**: Lightweight, frameless top-right HUD tracking asynchronous task progress (`PASSIVE_PROGRESS`, `SUCCESS`, `ERROR`, `WAITING_CONFIRMATION`). Enforces Win32 `WS_EX_NOACTIVATE (0x08000000)`, `Qt.WindowType.WindowDoesNotAcceptFocus`, and `Qt.WidgetAttribute.WA_ShowWithoutActivating` to ensure background tasks NEVER steal keyboard focus from active target applications (e.g. Notepad, VS Code, Browser).
- **Semantic UI Automation Subsystem**: 72 typed workstation capabilities across 10 OS categories with direct Microsoft UI Automation (`IUIAutomation`) tree inspection and control manipulation on a dedicated COM MTA worker thread.
- **Strict Control Mutation Invariant**:
  $$\text{UIA Semantic Pattern} > \text{Win32 Control Message} > \text{Keyboard Shortcut} > \text{Coordinate Interaction (PERMANENTLY PROHIBITED)}$$
  Zero blind coordinate clicking (`pyautogui.click(x, y)`). All control manipulations use strongly-typed UIA patterns (`InvokePattern`, `ValuePattern`, `TogglePattern`, `SelectionItemPattern`, `ScrollPattern`).
- **Benchmark-Proven Performance**:
  - **Live Workstation Acceptance Suite**: **100.0% Pass Rate** across Background Residency, Single-Instance Summon, Compound Execution, and Lifecycle Controls (`docs/V0.10.3_LIVE_ACCEPTANCE.md`).
  - **Neural NLP Benchmark (840 cases)**: **99.04% Dev / 98.44% Test Compound Accuracy**, **100.0% Literal Preservation**, **17.09ms p95 latency**.
  - **Compound Benchmark V1 (50 cases)**: **100.0% Pass Rate** (50 / 50), **100.0% Compound Clause Recall**, **0.00% Fast-Path Truncation Rate**, **0.00% Misroute Rate**.
- **353 Passing Automated Tests**: 100% test pass rate across 24 test modules in 108s.


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

