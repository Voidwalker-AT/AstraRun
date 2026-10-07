# AstraRun Runtime Architecture V2 (Phase C1 Baseline)

> **Document Type**: Production Architecture Specification  
> **Target Release**: AstraRun 1.0 (Post-Consolidation Baseline)  
> **Status**: RATIFIED & EMPIRICALLY VERIFIED  
> **Date**: October 2026  
> **Baseline Commit**: `f4e5d06`  

---

## 1. Composition Root V2

The authoritative composition root is [`AstraApplication`](file:///E:/Workspace/Active/AstraRun/src/astrarun/app.py) instantiated via [`entrypoint.py`](file:///E:/Workspace/Active/AstraRun/src/astrarun/entrypoint.py) ➔ [`astrarun.main`](file:///E:/Workspace/Active/AstraRun/src/astrarun/main.py).

All production subsystems are explicitly constructed, owned, and reachable through this unified directed graph. Random module-level instantiations and ambient global state have been removed.

```
AstraApplication (Composition Root)
├── AstraPaths (Centralized filesystem authority)
├── AppConfig (Authoritative configuration)
├── MachineModel & MachineQueryEngine (Hardware & workstation registry)
├── SecurityKernel
│   ├── ActionGate (Canonical policy & TOCTOU confirmation token authority)
│   ├── ASTInspector (Static AST screening for dynamic code)
│   ├── SandboxManager (Win32 Job Object process containment)
│   └── ExecutionBroker (Single consequential action dispatch barrier)
├── ModelRuntime
│   ├── ModelSupervisor (Out-of-process process supervisor & Win32 Job Objects)
│   ├── ModelService (Loopback HTTP client with strict typed schemas)
│   ├── Spark-X2.5 (1.7B Q4_K_M on 127.0.0.1:8090 - Fast intent & routing)
│   └── Qwen2.5-Coder (1.5B Q4_K_M on 127.0.0.1:8089 - Deep code synthesis & repair)
├── MemoryService (Authoritative unified facade)
│   ├── WorkingMemory (Active turn context scratchpad)
│   ├── EpisodicFaculty (SQLite task history trajectories)
│   ├── SemanticFaculty (SQLite persistent facts & user preferences)
│   ├── ProceduralFaculty / SkillService (Hermes progressive disclosure skills)
│   └── WorkspaceFaculty (FTS5 BM25 lexical & vector indexing)
├── PerceptionService
│   ├── Win32 / UIA (Native UI Automation COM walker via UIAutomationCore)
│   ├── COM Surfaces
│   ├── CDP / DOM (Chrome DevTools Protocol & semantic tree compression)
│   └── PerceptionRouter (Escalation ladder to OCR / CV / Grounder)
├── BrowserService (Managed Chromium/Edge launch, DOM compression, element interaction)
├── AgentRuntime
│   ├── InputRouter (Lightweight semantic intent gating: Conversational/Goal/App)
│   ├── GoalPlanner (CapabilitySemanticIndex DAG synthesis + RAG ContextBuilder)
│   ├── ExecutionGraph (Dataflow propagation & OutputReference resolution)
│   ├── DynamicToolBuilder (Model-driven code generation, AST checks, Job Object execution)
│   ├── GoalVerifier (Empirical post-execution acceptance predicates)
│   └── ResourceLockManager (Deadlock & concurrency protection)
└── Desktop Presentation
    ├── FloatingTaskHUD (Real-time task progress card)
    ├── LauncherWindow (Top-center floating command bar)
    ├── HotkeyManager (Low-level Win32 RegisterHotKey with conflict detection)
    └── AstraTrayIcon (Resident tray controller & notification icon)
```

---

## 2. Process Graph & Model Lifecycle

Hardware constraints (RTX 2050 4GB Laptop GPU) prohibit running all neural networks simultaneously in host memory. AstraRun operates an out-of-process, resource-aware lifecycle:

```
[Windows OS Session]
  │
  ├── [AstraRun.exe] (Host Resident Process, PID ~ 17000)
  │     ├── Resident GUI (PySide6 / Qt6) ~ 85 MB RAM
  │     ├── Single Instance Mutex + Named Pipe IPC
  │     ├── ExecutionBroker & ActionGate
  │     └── In-Memory State
  │
  ├── [llama-server.exe (Spark)] (Spawned Out-of-Process, Port 8090)
  │     ├── Bound to Win32 Job Object (Kill-on-Close, no console window)
  │     ├── Model: Spark-X2.5-1.7B-Q4_K_M.gguf (~ 1.1 GB VRAM)
  │     └── Lifecycle: Starts on demand for ambiguous routing; pinned or warm
  │
  ├── [llama-server.exe (Qwen)] (Spawned Out-of-Process, Port 8089)
  │     ├── Bound to Win32 Job Object (Kill-on-Close, no console window)
  │     ├── Model: Qwen2.5-Coder-1.5B-Instruct-Q4_K_M.gguf (~ 1.2 GB VRAM)
  │     └── Lifecycle: Starts on demand for code generation/repair; auto-unloads
  │
  └── [python.exe (Dynamic Worker)] (Ephemeral Sandboxed Child Process)
        ├── Bound to Ephemeral Win32 Job Object (512 MB memory limit, timeout)
        └── Executes synthesized code in isolated temporary workspace
```

- **Zero Global Singletons**: Process ownership is managed by `ModelSupervisor`.
- **Zero Port Collisions**: Ports are isolated (Spark 8090, Qwen 8089) with health check polling.
- **Clean Subprocess Termination**: `ModelSupervisor.stop_server()` sends graceful SIGINT/SIGTERM followed by Job Object termination if unresponsive.

---

## 3. Consequential Execution Authority (`ExecutionBroker`)

To prevent bypasses where components directly execute OS commands, all consequential actions MUST funnel through [`ExecutionBroker`](file:///E:/Workspace/Active/AstraRun/src/astrarun/security/execution_broker.py):

```
       ActionProposal
             │
             ▼
      ExecutionBroker
             │
             ▼
         ActionGate
             │
    ┌────────┴─────────┬──────────────────────┐
    ▼                  ▼                      ▼
  ALLOW             CONFIRM                 BLOCK
    │                  │                      │
    │         (User confirmation dialog)      ▼
    │         (TOCTOU token validation)    Audit Log
    │                  │                      │
    └────────┬─────────┘                      ▼
             ▼                            Reject / Return
    Capability Execution
             │
             ▼
     CapabilityResult
             │
             ▼
   Audit Trail & Observer
```

- **Action Classification**: Actions are categorized into `ACT` (mutations, process launches, file modifications) and `OBSERVE` (UIA inspection, DOM reading, telemetry query).
- **TOCTOU Token Protection**: High-risk actions generate cryptographically unique, single-use confirmation tokens with TTL to prevent replay or race conditions.
- **Model Invariant**: Cognitive models (`Spark`, `Qwen`) NEVER invoke execution handles directly; they emit proposals that must be evaluated and dispatched by `ExecutionBroker`.

---

## 4. Memory & Knowledge Architecture (`MemoryService`)

AstraRun unifies its fragmented memory into one canonical facade [`MemoryService`](file:///E:/Workspace/Active/AstraRun/src/astrarun/memory/service.py):
1. **Working Memory**: Transient dictionary for the active conversation turn.
2. **Episodic Faculty**: SQLite database storing past DAG execution traces, step latencies, error messages, and verified outcomes.
3. **Semantic Faculty**: SQLite database storing learned preferences, explicit user teachings, and verified facts.
4. **Procedural Faculty (`SkillService`)**: Progressive disclosure skill catalog (Tier 1: Name + description, Tier 2: Parameter schema, Tier 3: Executable workflow).
5. **Workspace Faculty**: FTS5 lexical BM25 virtual table index for workstation files, code snippets, and configs.

### RAG Integration into Planning
When `GoalPlanner.create_plan()` generates a DAG:
- Context is assembled via [`ContextBuilder`](file:///E:/Workspace/Active/AstraRun/src/astrarun/rag/context.py).
- Retrieved facts and documents are strictly wrapped in untrusted containment tags:
  `<retrieved_document id="..." source="..." trust="TRUSTED_LOCAL" type="TEXT"> ... </retrieved_document>`.
- System prompts explicitly warn the model that retrieved text is passive reference data that must never override safety boundaries.

---

## 5. Perception Escalation Hierarchy (`PerceptionService`)

Perception avoids expensive visual models when structured APIs are available:
```
Tier 0: Win32 OS APIs (user32, psutil, GetWindowRect)
   ▼
Tier 1: Application-Native COM Surfaces (Office, Visual Studio)
   ▼
Tier 2: Chrome DevTools Protocol (CDP DOM tree + token compression)
   ▼
Tier 3: Windows UI Automation (IUIAutomation tree walker via comtypes)
   ▼
Tier 4: Windows Media OCR (WinRT text recognition)
   ▼
Tier 5: Classical Computer Vision (OpenCV contours & templates)
   ▼
Tier 6: Visual Grounder (OmniParser v2.0 YOLO)
   ▼
Tier 7: Local VLM (SmolVLM-500M)
   ▼
Tier 8: External Multimodal Model (Escalation only)
```

---

## 6. Authoritative Storage Locations (`AstraPaths`)

All path resolution is governed by [`AstraPaths`](file:///E:/Workspace/Active/AstraRun/src/astrarun/core/paths.py), eliminating CWD dependency (`[WinError 3]` / `[WinError 5]` crash):

- **Program Directory**: `%LOCALAPPDATA%\Programs\AstraRun\` (Release) or Source Tree (Dev)
- **User Data Root**: `%LOCALAPPDATA%\AstraRun\`
  - `config/`: `settings.json`, `apps.json`, `aliases.json`
  - `data/`: `astra_learning.db`, `astra_history.db`, `usage.json`
  - `logs/`: `astrarun.log`, `crash_recovery_*.json`
  - `cache/`: Model downloads, HuggingFace cache
  - `models/`: Managed GGUF weights
  - `skills/`: Installed YAML/MD skill definitions
  - `runtimes/`: Managed llama.cpp binaries
- **Temporary Storage**: `%TEMP%\AstraRun\` (Scrubbed on session end)
- **External AI Models**: `E:\AI_Models\GGUF` (Read-only, never moved or deleted)
