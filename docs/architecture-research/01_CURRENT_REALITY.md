# 01 — Repository Reality Audit: AstraRun Current State

> **Milestone**: Pre-Implementation Architecture Research & Reality Audit  
> **Repository**: `E:\Workspace\Active\AstraRun`  
> **Verified Commit**: `4c57098` (AstraRun v0.11.1)  
> **Audit Date**: 2026-09-30  
> **Status**: COMPLETED AUDIT (Strict Evidence-Based Analysis)  

---

## 1. Executive Summary & Reality Check

AstraRun has undergone rapid evolutionary iterations from v0.1 (deterministic launcher) through v0.10.3 (neural sandwich) to v0.11.1 (generality & reality gate). The automated test suite reports **395 / 395 tests passing**, and the Generality Benchmark reports **100% Plan Validity** and **100% Held-Out Success**.

However, a line-by-line inspection of the implementation reveals a critical architectural reality:

> [!IMPORTANT]
> **The Generality Paradox**:  
> AstraRun's runtime execution layer (`ExecutionGraph`, `AgentExecutionEngine`, `ResourceLockManager`, `ActionGate`) is genuinely general, robust, and capable of topological DAG execution, dynamic replanning, and empirical verification.  
> **HOWEVER, the planning layer (`planner.py`) is fundamentally heuristic and pseudo-general.** It achieves high benchmark scores not through deep reasoning, but through an intricate web of specialized regexes, hardcoded capability branches, and lexical heuristics tuned directly against benchmark fixtures.

AstraRun has officially reached the ceiling of what heuristic and regex-driven planning can achieve.

---

## 2. Component-by-Component Reality Audit

### 2.1 The Routing Subsystems (`src/astrarun/routing/`)
- **DeterministicRouter (`deterministic.py`)**: `[MEASURED: LIVE_PHYSICAL_VERIFIED]`
  - Extremely fast ($< 2\,\text{ms}$ latency), zero VRAM, $< 5\,\text{MB}$ RAM.
  - Relies on exact verb prefixes (`open`, `launch`, `start`, `show`, `go to`) and in-memory search index queries.
  - Rock solid for primary application launching, folders, URLs, and status queries.
- **LayaRouter (`laya.py`, `laya_sandwich.py`)**: `[MEASURED: RESIDENT_OVERHEAD]`
  - Loads `convaiinnovations/laya` (421M parameter ModernBERT-large) directly into the Python process.
  - **Memory Footprint**: Consumes $\approx 850\,\text{MB} - 1.2\,\text{GB}$ of physical RAM on CPU.
  - **Current Role**: Acts as a 10-class intent classifier and semantic pre-gate (`Laya A`) / post-verifier (`Laya B`) in `LayaSandwichRouter`.
  - **Reality Verdict**: Laya possesses **zero production execution authority**. It is purely an expensive shadow classifier that duplicates what deterministic routing and semantic indexing already accomplish. Under our measured ~3.3 GB free RAM ceiling, keeping 1.2 GB of ModernBERT weights in RAM is an unacceptable tax for simple 10-class intent labeling.
- **KevRouter (`kev.py`)**: `[INSPECTION: DEAD / SHADOW SCAFFOLDING]`
  - Qwen 0.8B backbone + PEFT LoRA adapter + PointerHead.
  - Operates strictly in shadow mode; never executes tools.
  - Adds torch/peft dependency overhead without providing production planning value.
- **JevRouter (`jev.py`)**: `[INSPECTION: DEAD CODE / API STUB]`
  - External HTTP client targeting `https://api.typesafe.ai/v1/systemone`.
  - Completely unused in local daily-driver operations.

---

### 2.2 The NLP & Structure Engines (`src/astrarun/nlp/`)
- **NeuralStructureEngine (`structure_engine.py`)**: `[MEASURED: LIVE_PHYSICAL_VERIFIED]`
  - Loads `spaCy en_core_web_sm` (~40 MB RAM).
  - Performs syntactic clause segmentation, dependency parsing, exact literal span extraction, and negation tagging (`is_negated: bool`).
  - Highly effective at verbatim text payload preservation (`open notepad and type "secret key"`).
  - **Limitation**: Dependency parsing struggles on colloquial, multi-clause instructions with missing conjunctions or pronouns.

---

### 2.3 The Agent Planning Subsystem (`src/astrarun/agent/`)
- **CapabilitySemanticIndex (`indexer.py`)**: `[MEASURED: LIVE_PHYSICAL_VERIFIED]`
  - Inverted index over capability IDs, categories, descriptions, action verbs, input args, and outputs.
  - Sub-millisecond retrieval ($< 0.5\,\text{ms}$), 99.03% Recall@5.
  - Noun grounding penalties and verb boost prevent many false triggers (e.g. "summon dragon on desktop" rejected).
  - **Reality Verdict**: Genuinely dynamic for *retrieval* of registered capabilities.
- **GoalPlanner (`planner.py`)**: `[CRITICAL AUDIT: HEURISTIC CEILING REACHED]`
  - Line 270–350: Argument extraction relies on explicit regex clauses matching specific words:
    ```python
    re.search(r"^(?:reverse|type|write|save|count\s+words\s+in|calculate\s+hash\s+of|compute\s+sha256\s+hash\s+for|compute\s+hash\s+for|format\s+json\s+string|format\s+json\s+payload|beautify\s+json|format\s+json\s+data|beautify\s+json\s+string)\s+(.+?)...")
    ```
  - Line 388–400: Human label generation hardcodes `generate_battery_report`, `wifi_scan`, `reverse_text`, `save_text_file`.
  - Line 446–450: Dataflow output inference hardcodes `reverse_text` output `"reversed"`.
  - Line 430–439: Hardcoded transition from `type_text` to `type_into_window` if preceded by `open_application`.
  - **Reality Verdict**: The planner is **not an autonomous reasoning agent**. It is an advanced heuristic compiler that was manually patched to pass the 320-scenario benchmark. If a novel tool with novel argument semantics is introduced, the planner cannot reason about how to bind arguments without developer-authored regex updates.
- **ExecutionGraph (`graph.py`) & AgentExecutionEngine (`loop.py`)**: `[MEASURED: LIVE_PHYSICAL_VERIFIED]`
  - Full Kahn's cycle detection, topological dependency sorting, dynamic step readiness.
  - Runtime `OutputReference` argument substitution.
  - Closed-loop observe-act-verify cycle with `ResourceLockManager`.
  - **Reality Verdict**: The execution engine is genuinely general, robust, and production-ready. It only lacks a truly intelligent brain feeding it plans.

---

### 2.4 Control Surfaces & Adapters (`src/astrarun/tools/`, `capabilities/`)
- **Native Wi-Fi (`tools/wifi.py`)**: `[MEASURED: LIVE_PHYSICAL_VERIFIED]`
  - Direct Win32 C-API integration with `wlanapi.dll`.
  - Sub-5ms status queries, zero subprocesses, zero credential exposure. Verified on host machine.
- **System Adapters (`tools/system_adapter.py`)**: `[MEASURED: LIVE_PHYSICAL_VERIFIED]`
  - Safe `PowerCfgAdapter` running `powercfg.exe /batteryreport` with `shell=False` and parameter allowlisting. Verified creating valid HTML reports in Downloads.
- **UI Automation & Windows (`windows/`, `capabilities/`)**: `[MEASURED: PARTIALLY VERIFIED / FRAGILE]`
  - Win32 API window management (`GetForegroundWindow`, `MoveWindow`, `ShowWindow`) works reliably.
  - UI Automation (`pywinauto` / `UIAutomationCore`) is slow ($200–800\,\text{ms}$) and frequently fails on non-standard, custom-rendered Chromium or Electron application surfaces.
- **Browser Automation**: `[NOT_IMPLEMENTED]`
  - Zero CDP or DOM extraction currently exists in the codebase.
- **Visual Computer Use & OCR**: `[NOT_IMPLEMENTED]`
  - Zero screenshot capture, visual grounding, or OCR modules exist in production code.
- **Dynamic Code / Terminal Execution**: `[NOT_IMPLEMENTED]`
  - No sandboxed execution environment exists. All capabilities are pre-authored Python methods.

---

### 2.5 User Interface & Task HUD (`src/astrarun/ui/`)
- **Launcher Window (`window.py`)**: `[MEASURED: LIVE_PHYSICAL_VERIFIED]`
  - Frameless Qt window, centered on active monitor, Alt+Space hotkey latency $< 15\,\text{ms}$.
  - Fluid drop-in/slide-up animations governed by `MotionTokens`.
- **Live Task HUD V2 (`hud.py`)**: `[MEASURED: LIVE_PHYSICAL_VERIFIED]`
  - Non-focus-stealing floating window (`WS_EX_NOACTIVATE`, `WA_ShowWithoutActivating`).
  - Honest progress calculation, rolling average ETA estimator, collapsible step list, and cancellation support.

---

## 3. Sunk-Cost Classification of Neural Components

Based on empirical RAM cost vs actual product contribution:

| Subsystem | Primary Role | Measured RAM / VRAM | Real Production Value | Architectural Verdict |
| :--- | :--- | :---: | :---: | :---: |
| **DeterministicRouter** | Fast-path launching & queries | $< 5\,\text{MB}$ RAM / $0\,\text{MB}$ VRAM | CRITICAL ($< 15\,\text{ms}$ daily driver) | **KEEP_RESIDENT** |
| **CapabilitySemanticIndex** | Dynamic capability retrieval | $< 10\,\text{MB}$ RAM / $0\,\text{MB}$ VRAM | HIGH ($< 0.5\,\text{ms}$ sub-goal matching) | **KEEP_RESIDENT** |
| **NeuralStructureEngine (spaCy)**| Literal preservation & clause split | $\approx 45\,\text{MB}$ RAM / $0\,\text{MB}$ VRAM | MODERATE (good literal spans) | **KEEP_RESIDENT** |
| **ExecutionGraph & Loop** | DAG scheduling & verification | $< 5\,\text{MB}$ RAM / $0\,\text{MB}$ VRAM | CRITICAL (core agent engine) | **KEEP_RESIDENT** |
| **Laya (ModernBERT 421M)** | Intent classification & pre-gate | $\approx 850–1200\,\text{MB}$ RAM | ZERO (duplicates fast-path & indexer) | **REPLACE_CANDIDATE** |
| **Kev (Qwen 0.8B LoRA)** | Shadow intent routing | $\approx 1.8\,\text{GB}$ RAM / VRAM | ZERO (pure shadow test fixture) | **REMOVE_EVENTUALLY** |
| **Jev (External API)** | Benchmark reference | $0\,\text{MB}$ RAM / $0\,\text{MB}$ VRAM | ZERO (unmaintained external stub) | **REMOVE_EVENTUALLY** |
