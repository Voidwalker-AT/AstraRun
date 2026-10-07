# AstraRun Product Codebase & Architecture Reality Audit

> **Audit Version**: 1.0.0  
> **Date**: 2026-10-06  
> **Auditor**: Independent Architecture & Codebase Reality Audit  
> **Repository**: `E:\Workspace\Active\AstraRun`  
> **Base Commit**: `f4e5d06`  
> **Status**: COMPLETED — DO NOT PROCEED TO PACKAGING OR PUBLISHING BEFORE REMEDIATION  

---

## Executive Summary & Verdict

AstraRun is currently **architecturally fragmented with critical evidence and path defects**. 

While project documentation, milestones, and marketing narratives depict an autonomous multi-model workstation agent driven by Spark (planner), Qwen (coder), Laya (fast intent), OmniParser (visual grounder), and persistent RAG, **the actual running application is a deterministic Windows resident command bar** (v0.10 UIA + regex + hardcoded fallback templates). The advertised cognitive spine, RAG, and visual perception engines sit isolated in separate unit-test harnesses and benchmark dumps, completely unwired from the composition root (`entrypoint.py` -> `astrarun.main` -> `AstraApplication`).

### Primary Audit Highlights

1. **AUDIT-P0-001 (Resolved in Source)**: CWD-dependent runtime storage caused an unhandled crash (`WinError 5 Access is denied: 'C:\Windows\System32\data'`) when starting from arbitrary directories such as `C:\Windows\System32`. Centrally resolved via `AstraPaths` pointing to `%LOCALAPPDATA%\AstraRun`.
2. **AUDIT-P0-002 (Evidence Integrity Failure)**: Previous reports claimed `REAL_INSTALLED_PRODUCT_EXECUTION` for "ChatGPT Dogfood". Source code inspection reveals `ChatGPTWebDelegate` is a **100% hardcoded local string generator** returning fixed projectile motion code and review responses. It never opened a browser, navigated to `chatgpt.com`, or communicated with OpenAI.
3. **Dead Subsystems in Production**: Entire major subsystems—**RAG** (10 modules), **Perception/OmniParser** (11 modules), and **AI-Bridge** (2 modules)—are completely unimported in production.
4. **Cognitive Spine Bypassed**: In resident execution, `ModelService`, Spark (`:8090`), and Qwen (`:8089`) are never started or contacted. `GoalPlanner` uses an in-memory BM25 index, and `DynamicToolBuilder` falls back to canned matplotlib templates.
5. **Security Reality**: `SandboxManager` is **process containment** (Win32 Job Object memory limits + kill-on-close), **NOT** a security sandbox. Generated code executes under the full host user token. ActionGate is bypassed by built-in commands and dynamic tooling.

---

## Special Findings Matrix (A through O)

### Special Finding A: Exact Root Cause of the System32 Crash (AUDIT-P0-001)
- **Call Chain**:
  ```
  entrypoint.py
    -> astrarun.main.main()
      -> astrarun.app.AstraApplication.__init__()
        -> astrarun.machine.model.MachineModel.get_instance()
          -> MachineModel.__init__()
            -> Path("data/machine/machine_facts.db").parent.mkdir(parents=True, exist_ok=True)
  ```
- **Root Cause**: `MachineModel` defaulted its database path to `Path("data/machine/machine_facts.db")`. In standard Python, a relative path is resolved against `os.getcwd()`. When launched from `C:\Windows\System32`, `mkdir()` attempted to create `C:\Windows\System32\data\machine`, raising `PermissionError: [WinError 5] Access is denied`.

### Special Finding B: Relative Paths Across the Repository
- **Audit Scope**: Grepped all instances of `Path("data")`, `Path("logs")`, `Path("config")`, `sqlite3.connect()`, `open()`, and `Path.cwd()`.
- **Finding**: Found **44 relative path constructions across 20 production files**.
- **Remediation**: Implemented `AstraPaths` in `src/astrarun/core/paths.py`, re-anchoring all storage to `%LOCALAPPDATA%\AstraRun` and `%TEMP%\AstraRun`. Verified clean startup across 6 CWDs: `C:\`, `C:\Windows`, `C:\Windows\System32`, Desktop, Downloads, and Temp directory.

### Special Finding C: Exact Truth About "Real ChatGPT Dogfood" (AUDIT-P0-002)
- **Inspection of `src/astrarun/delegation/chatgpt_web.py`**:
  - Contains no Playwright, Selenium, Puppeteer, or CDP connection to an active user session.
  - Inspects `psutil.process_iter()` solely to check if `chrome.exe`, `msedge.exe`, or `brave.exe` is running.
  - In `_dispatch_browser_interaction()`:
    ```python
    if "review" in prompt.lower() or "audit" in prompt.lower():
        return "ChatGPT Review: Code looks clean, physics calculations are accurate..."
    return "```python\n# Projectile motion simulation\nimport numpy as np..."
    ```
  - `loop.py` specifically asserts the presence of hardcoded strings `"projectile_sim.py"` and `"Astra Delegate Test"`.
- **Reality**: Astra **NEVER** launched a browser, never visited `chatgpt.com`, never used an authenticated session, and never received an LLM response. The exchange was a 100% synthetic local string mock.

### Special Finding D: Evidence Classification of Dogfood Artifacts
- **Previous Label**: `REAL_INSTALLED_PRODUCT_EXECUTION`
- **Audit Classification**: `SIMULATED_PROVIDER` / `MOCK`
- **Evidence Gap**: The test `tests/delegation/test_dogfood_chatgpt_workflow.py` executed within source-tree `pytest` against Python classes, exercising deterministic string fallbacks. No external service was reached.

### Special Finding E: Separation Between Simulated and Real in Current Tests
- Current tests conflate architecture conformance with external execution reality.
- Acceptance tests (e.g., `test_acceptance_3d_vis.py`, `test_dogfood_chatgpt_workflow.py`) pass because the production fallback paths are hardcoded to produce the exact outputs expected by the assertions.
- Genuine real tests require external processes, live browser DOM attachment, or running local model weights.

### Special Finding F: Does Qwen Ever Run in the Resident Product?
- **NO.** In `AstraApplication`, Qwen (`:8089`) is never started. `ModelService` is not initialized by the composition root.
- When `DynamicToolBuilder` needs code, it checks `http://localhost:8089`. Because the port is closed, it hits its internal exception block and generates a canned mathematical script.

### Special Finding G: Does Spark Ever Run in the Resident Product?
- **NO.** In `AstraApplication`, Spark (`:8090`) is never started.
- `GoalPlanner` relies strictly on regex pattern matching and `CapabilitySemanticIndex` (an in-memory BM25 keyword index over static JSON capabilities).

### Special Finding H: Laya Viability in Frozen Desktop Environment
- `laya_worker.py` contains:
  ```python
  sys.modules["torchvision"] = None
  sys.modules["torchvision.ops"] = None
  ```
- **Rationale**: An emergency monkey-patch to prevent PyTorch from attempting to dynamically load broken/missing `torchvision` C++ DLLs in Windows environments.
- **Frozen Reality**: PyInstaller bundles PyTorch (365 MB), but model weights are NOT bundled in the installer. If `TRANSFORMERS_OFFLINE=1` is set, Laya crashes immediately on startup unless the user manually downloads weights to `%LOCALAPPDATA%\AstraRun\cache\huggingface`.

### Special Finding I: OmniParser True Semantics and Current Reachability
- `astrarun.perception.grounder` contains an OmniParser client and Florence-2 bounding-box parser.
- **Reachability**: **COMPLETELY DEAD IN PRODUCTION**.
- Production UI control is handled exclusively by `astrarun.interaction.service`, which uses Microsoft UI Automation (UIA) via `pywinauto`. Visual grounding (screenshots -> bounding boxes -> clicks) is never invoked by `AstraApplication`.

### Special Finding J: Can Astra Control ChatGPT Web for a Real Authenticated User Today?
- **NO.** Astra lacks:
  1. Chrome DevTools Protocol (CDP) attachment to running user browser instances with `--remote-debugging-port`.
  2. Browser extension bridge to existing authenticated cookies/session tokens.
  3. DOM element locators resistant to Cloudflare or ChatGPT UI updates.
  4. Any code path in `ChatGPTWebDelegate` capable of actual browser automation.

### Special Finding K: ActionGate Bypasses
- In `AstraApplication.handle_request()`:
  - Built-in fast-path queries (`open_application`, `open_url`, `system_info`) dispatch straight to `capability_registry.execute()`, completely bypassing `ActionGate.evaluate()`.
  - `DynamicToolBuilder` executes synthesized scripts in `SandboxManager` relying purely on Python AST node inspection, completely bypassing ActionGate's risk assessment and quarantine checks.

### Special Finding L: Is SandboxManager a True Security Sandbox?
- **NO.** It is **Process Containment**, not security virtualization.
- Uses Win32 Job Object API (`JOB_OBJECT_LIMIT_PROCESS_MEMORY` = 512 MB, `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`).
- It does **not** employ Windows AppContainers, integrity levels (Untrusted/Low IL), restricted tokens, or file system/registry filter drivers.
- Any Python script executed inside the sandbox runs with the **full privileges of the logged-in user**, with full read/write access to files, credentials, and open outbound network sockets.

### Special Finding M: Dead Subsystems Inventory
The following subsystems are present in `src/` but are **completely disconnected from the production composition root**:
1. `astrarun.rag.*` (10 files): `context.py`, `embeddings.py`, `indexer.py`, `models.py`, `router.py`, `skills.py`, `store.py`, `vector.py`, `worker.py`.
2. `astrarun.perception.*` (11 files): `capture.py`, `cdp.py`, `com.py`, `cv.py`, `grounder.py`, `input.py`, `models.py`, `ocr.py`, `router.py`, `vlm.py`.
3. `astrarun.ai_bridge.*` (2 files): `bridge.py`, `client.py`.

### Special Finding N: Duplicated Subsystems Inventory
Multiple subsystems were re-implemented across milestones without deprecating or removing earlier versions:
1. **Memory Storage**: `astrarun.rag.store.MemoryStore` vs `astrarun.learning.memory.MemoryStore`.
2. **Skill Registry**: `astrarun.rag.skills.SkillRegistry` vs `astrarun.learning.skills.SkillRegistry`.
3. **Action Gate**: `astrarun.security.action_gate.ActionGate` vs `astrarun.policy.action_gate.ActionGate`.
4. **Telemetry**: `TelemetryCollector` vs `ShadowCollector` (duplicate parallel logging).

### Special Finding O: The Single Weakest Link in the Current Architecture
**The disconnect between marketing/milestone claims and composition root reality.**
AstraRun suffers from "milestone theatre": components were built and validated inside isolated unit-test files (e.g., `test_milestone3_rag_subsystem.py`, `test_milestone4_perception_control.py`), and declared finished, but were **never integrated into `AstraApplication`**. The runtime product remains a simple v0.10 UIA runner with hardcoded regex fallbacks.

---

## Detailed Audit Sections (1 through 28)

### Section 1: Executive Verdict
AstraRun cannot be packaged, frozen, or published in its current state. The application exhibits critical path bugs (partially mitigated in source), mislabeled test evidence, disconnected cognitive subsystems, and packaging bloat. A consolidation phase is required to unify the composition root and eliminate simulated fallbacks.

### Section 2: Repository Structure & Module Classification
- **Source Modules**: 257 Python files across 38 packages.
  - **PRODUCTION_REACHABLE**: 192 modules.
  - **DEAD / UNWIRED**: 23 modules (`rag`, `perception`, `ai_bridge`).
  - **DUPLICATED**: 6 modules (`rag.store`, `rag.skills`, `policy.action_gate`).
  - **SIMULATED**: 2 modules (`chatgpt_web.py`, `loop.py`).
- **Test Modules**: 2,041 files.
  - `tests/unit`, `tests/integration`, `tests/acceptance`: 57 files.
  - `tests/benchmarks`: **1,984 files** containing massive vendored copies of upstream open-source projects (`open_interpreter`), polluting linters and static analysis.

### Section 3: Path and Filesystem Architecture Audit (AUDIT-P0-001)
- **Root Cause & Call Chain**: Documented in Special Finding A.
- **Architectural Fix**: Created `AstraPaths` class in `src/astrarun/core/paths.py`. All persistent data resolves to `%LOCALAPPDATA%\AstraRun`, logs to `%LOCALAPPDATA%\AstraRun\logs`, and temporary files to `%TEMP%\AstraRun`.
- **Validation**: Tested headless execution across 6 CWDs:
  - `C:\` -> PASS
  - `C:\Windows` -> PASS
  - `C:\Windows\System32` -> PASS
  - User Desktop -> PASS
  - User Downloads -> PASS
  - `%TEMP%\audit_test` -> PASS
  All tests exited code 0 with zero files written to CWD.

### Section 4: Composition Root and Startup Audit
- **Entrypoint**: `entrypoint.py` -> `astrarun.main.main()` -> `AstraApplication`.
- **Eagerly Initialized**:
  - `MachineModel` (hardware facts)
  - `InteractionService` (UIA automation)
  - `CapabilityRegistry` (built-in actions)
  - `GoalPlanner` (in-memory BM25 index)
  - `ActionGate` (security policy)
  - `LauncherWindow` (PyQt6 UI)
- **Not Initialized / Omitted**:
  - `ModelService`, `ModelSupervisor`
  - `RAGWorker`, `ChromaVectorStore`
  - `PerceptionService`, `OmniParser`
  - `BrowserManager`

### Section 5: Cognitive Architecture Reality
- **Representative Query Traces**:
  1. `"hi"`: Matched by regex rule in `InputRouter` -> Instant static conversational greeting. No LLM invoked.
  2. `"open calculator"`: Matched by `CapabilitySemanticIndex` -> Dispatches `open_application(calculator)` via UIA. ActionGate bypassed.
  3. `"what GPU do I have?"`: Matched by regex -> Queries `MachineModel` SQLite database. Returns static hardware string.
  4. `"create a Fibonacci program"`: Routed to `DynamicToolBuilder`. Checks `http://localhost:8089`. Connection refused -> Returns fallback script or errors.
  5. `"make a 3D graph"`: Routed to `DynamicToolBuilder`. Hits hardcoded regex fallback returning canned matplotlib script.
  6. `"debug this Python project"`: Planner creates single-step plan. Code analysis engine unreachable.
  7. `"continue what we were doing"`: `ContinuityManager` loads last session state from `%LOCALAPPDATA%\AstraRun\tasks\ledger.json`.
  8. `"ask ChatGPT to review this"`: Routes to `ChatGPTWebDelegate`. Checks `psutil`, returns hardcoded approval text.

### Section 6: Model Lifecycle & Serving Reality
- `ModelSupervisor` (`src/astrarun/cognition/supervisor.py`) contains process lifecycle logic for `llama-server.exe` (Spark on port 8090, Qwen on port 8089).
- **Reality**: It is never started by `AstraApplication`. In the installed application, no local model servers run. No VRAM is consumed.

### Section 7: Laya Architecture & Frozen Viability
- Laya worker is an ONNX/PyTorch small model intended for fast intent routing.
- The `sys.modules["torchvision"] = None` monkey-patch prevents DLL missing entrypoint crashes on Windows.
- PyInstaller bundles PyTorch (365 MB) but leaves out model weights. Offline execution without prior weight download fails.

### Section 8: Agent Loop Reality
- `GoalPlanner` generates a DAG of tasks.
- If a capability is found in the static index, it executes sequentially via `AgentExecutionEngine`.
- If no capability is found, it calls `DynamicToolBuilder`.
- Verification is performed by `GoalVerifier`, which checks exit codes and stdout patterns.

### Section 9: Dynamic Tooling & Code Provenance Reality
- `CandidateTool` compiles Qwen-generated code into an AST.
- `ASTInspector` scans for forbidden imports (`os.system`, `subprocess.Popen`, raw sockets).
- Byte identity (DF-016) is verified by comparing SHA-256 hashes of generated code, staged code, and executed code.
- However, when Qwen is offline, code is generated from canned string templates.

### Section 10: Sandbox Reality
- Confirmed: Win32 Job Object memory containment only (512 MB).
- No file system isolation, no token isolation, no network restriction.

### Section 11: Windows Desktop Automation (UIA) Reality
- `astrarun.interaction.service` utilizes `pywinauto` to walk the native Windows accessibility tree.
- Reliable for standard Win32, WinForms, and basic WPF apps.
- Fails or falls back on Chromium-rendered apps (Electron, VSCode, Chrome) when accessibility trees are collapsed.

### Section 12: Delegation Subsystem & Dogfood Reality (AUDIT-P0-002)
- Fully detailed in Special Finding C. The delegation dogfood workflow was 100% simulated.
- Production code contains test-specific paths hardcoded to match the dogfood evaluation harness.

### Section 13: Browser Automation Reality
- `astrarun.browser` provides basic Playwright wrappers.
- Completely disconnected from resident desktop execution. Cannot attach to user browser sessions.

### Section 14: Perception Subsystem Reality
- Entire `astrarun.perception` package (11 modules) is unimported by production.
- Visual grounding and OCR exist only as isolated test benchmarks.

### Section 15: RAG Subsystem Reality
- Entire `astrarun.rag` package (10 modules) is unimported by production.
- No semantic retrieval over user documents or session history occurs in the resident app.

### Section 16: Skills Subsystem Reality
- Skills are represented as static JSON schemas in `src/astrarun/skills/builtin`.
- Loaded eagerly into `CapabilityRegistry`. Dynamic skill acquisition from execution is not wired.

### Section 17: Learning Subsystem Reality
- `LearningEngine` records completed execution traces into a local SQLite store.
- Reinforcement or heuristic updates to the planner are stubs.

### Section 18: Telemetry Subsystem Reality
- Parallel telemetry pipelines (`TelemetryCollector` and `ShadowCollector`) write duplicate JSONL records to `%LOCALAPPDATA%\AstraRun\logs`.
- Causes redundant disk I/O on every action.

### Section 19: Security, Policy, & Quarantine Reality
- `ActionGate` defines RISK_LOW, RISK_MEDIUM, RISK_HIGH actions.
- Bypassed by direct built-in execution in `AstraApplication`.

### Section 20: Continuity, Power, & Recovery Reality
- `ContinuityManager` persists state on power suspend events (`WM_POWERBROADCAST`).
- Successfully saves and restores task DAG state.

### Section 21: Configuration Subsystem Reality
- `AstraConfig` loads from `%LOCALAPPDATA%\AstraRun\config\config.json`.
- Uses overly broad `except Exception:` blocks, silently masking configuration parsing errors.

### Section 22: UI, Tray, & Hotkey Reality
- PyQt6 command bar with global hotkey (`Alt+Space`) via Windows `RegisterHotKey`.
- Functional and responsive, but completely decoupled from cognitive model streaming.

### Section 23: Packaging & Installer Reality
- PyInstaller bundle size: **1.1 GB**.
- Includes 167 MB of `polars` (unused), 112 MB of `cv2` (unused), and 365 MB of `torch` (without weights).
- Bloat factor: >60% of the binary size is dead weight.

### Section 24: Test Suite & Benchmark Reality
- Test tree is contaminated by 1,984 files of vendored third-party benchmarks.
- Several core acceptance tests rely on canned production fallbacks to achieve green status.

### Section 25: Performance & Resource Footprint Reality
- Resident idle RAM: ~85 MB (PyQt6 + UIA).
- Fast and lightweight, but solely because cognitive models (Spark, Qwen, Laya, OmniParser) are NOT running.

### Section 26: Architectural Inconsistencies & Duplications
- 3 parallel subsystems duplicated across milestone iterations (Memory, Skills, ActionGate).

### Section 27: Dead Code, Stubs, & Placeholders
- 23 unimported modules identified in `src/astrarun`.
- Placeholders in `chatgpt_web.py` returning canned trajectories.

### Section 28: Recommendations & Action Plan (Phased Roadmap)
1. **Phase 1: Remediation & Sanitization (Immediate)**
   - Rebuild PyInstaller spec excluding `polars`, `cv2`, and unused packages to reduce size below 300 MB.
   - Remove canned dogfood mocks from `chatgpt_web.py` and `loop.py`. Relabel all evidence to `SIMULATED_PROVIDER`.
   - Remove vendored benchmarks from `tests/`.
2. **Phase 2: Architectural Unification**
   - Connect or officially deprecate `rag` and `perception`.
   - Wire `ModelService` into `AstraApplication` behind explicit user configuration.
   - Enforce `ActionGate` across all execution paths.
3. **Phase 3: Real Delegation Engine**
   - Implement authentic CDP browser attachment for ChatGPT delegation.
   - Validate true end-to-end execution before generating dogfood artifacts.
