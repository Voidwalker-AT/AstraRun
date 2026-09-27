# AstraRun — Windows Intelligent Command Launcher & Workstation Control Plane (v0.8.5)

AstraRun is a local, lightweight, low-latency Windows command launcher and workstation orchestrator engineered as the foundational command interface for an evolving AI-assisted workstation control ecosystem.

AstraRun replaces fragile string-interpolated shell execution with a strictly typed pipeline:
`Natural Language -> NLP Engine -> StructuredUtterance -> Context Engine -> Entity Resolution -> ActionGate -> Task Runtime -> Capability Registry -> Windows OS`.

---

## Key Capabilities (v0.8.5)

- **Instantaneous Hotkey Activation**: Summoned with `Alt+Space` in ~4.5ms from a pre-warmed resident background process.
- **Memory, Learning & Skill Foundation (v0.8.5)**: Durable workstation semantic memory, natural language teaching parser, and candidate skill discovery operating strictly off the interactive hot path in background threads.
- **Zero Neural / Learned Execution Authority (v0.8.5)**: Learning never directly executes commands or expands computer control authority. Every proposed action continues to pass through `ActionGate` and hard policy enforcement.
- **Non-Learnable Security Policies (v0.8.5)**: Repeating high-risk capabilities or confirmations can **NEVER** downgrade `CONFIRM` to `AUTO`, bypass `ActionGate`, or alias protected system processes (`lsass.exe`, `csrss.exe`) and dangerous commands (`format c:`, `rmdir /s`).
- **Dual-Database Architecture (v0.8.5)**: Physical separation between ephemeral execution tracking (`data/astra_history.db`, 30-day retention) and durable workstation knowledge (`data/astra_learning.db`, SQLite WAL mode, `PRAGMA user_version = 1`, append-only audit trail).
- **Mathematical Confidence Engine (v0.8.5)**: Continuous Bayesian-inspired confidence accounting for positive evidence, asymmetric contradiction penalties, asymptotic support saturation, 70-day exponential time decay, and pinned fact guarantees ($\ge 0.95$).
- **Multi-Tier Alias Precedence (v0.8.5)**: Multi-tier resolution (`Static Config > Conflicted Gating > User-Confirmed Learned > High-Confidence Habit > Fuzzy Fallback`). Conflicting aliases automatically trigger safe disambiguation.
- **Declarative Pattern Mining & Skill Synthesis (v0.8.5)**: Discovers recurring multi-step workflows from task history, parameterizes variable arguments (`{target_project}`), and compiles into typed `Workflow` structures requiring explicit human approval.
- **Memory Inspector & Skill Review UI (v0.8.5)**: PySide6 split-view inspector (`MemoryView`) with full provenance audit and candidate skill review dialog (`SkillReviewWidget`).
- **Offline Training Dataset Exporter (v0.8.5)**: Offline dataset builder (`dataset_builder.py`) sanitizing queries with credential redaction and path normalization, gated behind `allow_training_dataset_export: true`.
- **Task Runtime & Lifecycle Authority (v0.8)**: Centrally governed by `TaskManager` across a formal 14-state directed Finite State Machine (`TaskStatus`).
- **Live Activity Timeline UI (v0.8)**: Real-time observable step visualization (`TaskActivityView`) rendering ground-truth system operations with zero fake progress or fabricated thinking.
- **Cooperative Cancellation (v0.8)**: Graceful abort mechanism governed by `CancellationToken` checkpoints preventing orphaned processes and resource leaks.
- **Persistent SQLite Task Ledger (v0.8)**: High-performance SQLite engine (`data/astra_history.db`) in Write-Ahead Logging (WAL) mode supporting 99,000+ rows/sec ingestion, startup crash recovery (`INTERRUPTED` states), and automatic corruption repair.
- **Conversation & Message History (v0.8)**: Multi-turn dialogue threading (`Conversation`) and chronological audit messaging (`ConversationMessage`).
- **Dedicated History & Audit UI (v0.8)**: Split-view `HistoryView` featuring instant substring search across past requests, quick date/status filter chips, timeline inspection, and safe semantic re-runs.
- **Semantic Re-Run Safety Invariant (v0.8)**: Historical re-runs strictly spawn a brand-new task using the original semantic request text, re-evaluating against real-time workstation state with zero stale argument replay.
- **Privacy & Redaction Controls (v0.8)**: Automatic regex redaction of API keys, tokens, and passwords; SHA-256 request hashing; and bounded capability payloads.
- **Workstation Capability Architecture (v0.7)**: Universal typed operating boundary providing **47 registered capabilities** across 9 OS categories (`APPLICATION`, `FILE`, `PROCESS`, `NETWORK`, `SYSTEM`, `PROJECT`, `WINDOW`, `AUDIO`, `WORKFLOW`).
- **Standardized `CapabilityResult` Contract (v0.7)**: Strongly-typed return envelope with execution timing and error codes (`NOT_FOUND`, `PERMISSION_DENIED`, `INVALID_ARGUMENT`, `AMBIGUOUS`, `OS_ERROR`).
- **Desktop Application Discovery & Window Focus (v0.7)**: Discovers interactive user applications via Win32 top-level window filtering (`EnumWindows`, `IsWindowVisible`). Restores and focuses windows with automatic disambiguation.
- **Non-Destructive Graceful Close (v0.7)**: Closes applications safely via native `WM_CLOSE` messages, prompting native save dialogs and eliminating accidental work loss.
- **Bounded File Indexing & Security Guardrails (v0.7)**: Fast metadata index over user directories (`Workspace`, `Downloads`, `Documents`, `Desktop`, `Pictures`). Blocks executable scripts (`.bat`, `.cmd`, `.ps1`, `.exe`) with `PERMISSION_DENIED`, offering safe `reveal_file` in File Explorer.
- **Deep Process Inspection & TOCTOU Safety (v0.7)**: Deterministic process sorting (memory RSS, CPU%, name), sanitized command lines, parent/child trees, and TOCTOU-safe termination revalidating PID, creation timestamp, and executable name. Hard policy blocks protected system processes (`explorer.exe`, `system`, `lsass.exe`, `csrss.exe`, etc.).
- **Read-Only Network Diagnostics (v0.7)**: Real-time listening ports and process-to-port mapping (`find_process_on_port`) across all ports (including privileged ports `<= 1023`) with zero mutation.
- **System Health & Dedicated GPU Telemetry (v0.7)**: Host overview (CPU cores, RAM, disk, battery, audio) and discrete GPU metrics via `nvidia-smi` (NVIDIA GeForce RTX 2050) with graceful fallback. Native desktop locking (`LockWorkStation`).
- **Workspace Project Integration (v0.7)**: Reads `E:\Workspace\workspace.json`. Queries Git branch and status via injection-proof structured commands. Detects project-bound processes and listening dev ports.
- **Window Discovery Sensory Layer (v0.7)**: Read-only enumeration of desktop window handles, captions, and geometry (`WindowEntity`), preparing for v0.9 window management.
- **Structured UI Result Cards (v0.7)**: Dark Catppuccin Mocha presentation cards: `ResultCard` (key-value summaries with action buttons) and `ListResultCard` (keyboard-navigable selectable lists).
- **Ephemeral Observation Store (v0.7)**: In-memory bounded ring buffer (200 facts) capturing structured OS facts for future System-2 reasoning handoffs without disk overhead or external model calls.
- **Decoupled Reasoning Provider Architecture (v0.7)**: Generic `ReasoningProvider` interface and `ReasoningRequired` escalation boundary remain unconfigured, ensuring 100% local, deterministic execution.
- **Hybrid NLP Understanding Engine (v0.6.5)**: Deterministic clause decomposition, negation scoping (**0.00% Negated Action Leakage**), local temporal intervals, and entity recognition.
- **Benchmark-Proven Performance**:
  - **Learning Benchmark V1 (320 cases)**: **100.0% Accuracy**, **0.00% False Memory Activation Rate**, **100.0% Security Invariant Enforcement Rate**, **25.28 ms mean latency**.
  - **Task Benchmark V1 (300 cases)**: **100.0% Status Accuracy**, **100.0% Sequence Accuracy**, **100.0% Persistence Accuracy**, **64.6 ms mean latency**.
  - **Scale Benchmark (10k tasks / 100k events)**: **99,757 rows/sec insert**, **1.26 ms recent query**, **7.43 ms search**, **339 ms retention prune**.
  - **Capability Benchmark V1 (520 cases)**: **100.0% Capability Accuracy**, **100.0% Permission Accuracy**, **100.0% Block Recall**, **0.561 ms mean latency**.
  - **Action Benchmark V1 (330 cases)**: **100.0% Intent Accuracy**, **100.0% Gate Accuracy**, **0.00% False Execution Rate (FER)**, **0.057 ms mean latency**.
  - **NLP Benchmark V1 (620 cases)**: **100.0% Intent Accuracy**, **95.2% Clause Acc**, **0.00% Negated Action Leakage Rate**, **7.364 ms mean latency**.
- **215 Passing Automated Tests**: 100% test pass rate across 19 test modules in ~12.56s.

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

