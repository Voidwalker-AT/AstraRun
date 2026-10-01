# 44_UPSTREAM_EXTRACTION_PLAN.md — Upstream Architectural Extraction & Synthesis Plan

> **Scope**: Component Extraction Ledger, Adaptation Blueprints, and Rejection Decisions  
> **Target System**: AstraRun v0.12 Planning & Architecture Foundation  
> **Status**: COMPLETED & VERIFIED  
> **Phase**: Phase 17-R (Secondary Upstream Architecture Mining Pass)  
> **Parent Documents**:  
> - `docs/architecture-research/42_UPSTREAM_IMPLEMENTATION_MINING.md`  
> - `docs/architecture-research/43_AGENT_ARCHITECTURE_LANDSCAPE.md`  

---

## 1. Executive Summary & Selective Extraction Philosophy

The secondary upstream architecture mining pass analyzed eight major autonomous workstation and coding agent systems. AstraRun will **NOT** import these frameworks wholesale or inherit their heavyweight cloud dependencies. Instead, AstraRun applies **Selective Mechanism Extraction**: extracting battle-tested architectural patterns, algorithms, and data representations, while implementing them natively as lean, deterministic, zero-dependency Python/Win32 components.

Every upstream component is evaluated against four strict invariant filters:
1. **Local Hardware Budget**: Must run inside RTX 2050 (4 GB VRAM, 3.4 GB free) and 16 GB RAM (~3.3 GB normally free physical memory).
2. **Workstation Non-Intrusiveness**: Must NEVER move the physical OS mouse cursor, steal foreground window focus, or fight the user for desktop control.
3. **Deterministic Security Boundary**: Must NEVER rely on prompt-only LLM self-reporting; all execution is gated by the out-of-band `ActionGate` and isolated inside Windows Job Object sandboxes.
4. **Context Window Parsimony**: Must minimize token bloat in local small models (Qwen 1.5B / Spark 1.7B / Hermes 3B) using compact semantic representations.

---

## 2. Category 1: ADOPT DIRECTLY

The following mechanisms are extracted from upstream systems and adopted directly into AstraRun v0.12 with identical semantics:

### 2.1 Parent-Containment DOM Pruning
- **Source Project**: Browser Use (`https://github.com/browser-use/browser-use.git`)
- **Source Path**: `browser_use/dom/serializer/serializer.py` (`_is_contained`, threshold: `0.99`)
- **Mechanism**: Calculates 2D bounding box intersection between DOM nodes. If a child element (e.g. `<span class="label">Submit</span>`) is $\ge 99\%$ contained inside an interactive parent element (`<button>`), the child element is pruned from the accessibility index.
- **Why Useful**: Completely eliminates redundant child tokens and nested container noise in browser web pages without losing clickable targets. [MEASURED_LOCAL: Lab D showed raw Chromium AXTree added +41% token overhead; pruning eliminates this bloat].
- **Dependency Cost**: Zero external dependencies (simple arithmetic: `left, top, right, bottom`).
- **Runtime Cost**: $<1\,\text{ms}$ over 500 DOM elements.
- **Coupling Risk**: None (pure data transformation).
- **License**: MIT License.
- **Astra Subsystem Affected**: `src/astrarun/browser/dom_serializer.py` (`BrowserSemanticTree`).

### 2.2 Progressive Skill Disclosure (Model-Agnostic Agent Harness)
- **Source Project**: Hermes Agent (`https://github.com/NousResearch/Hermes-Agent.git`)
- **Source Path**: `tools/skills_tool.py:1` (`skills_list` vs `skill_view`)
- **Crucial Distinction (Harness vs Model)**: Hermes Agent's progressive disclosure, `SKILL.md` format, and skill management are a **model-agnostic agent software layer**. Hermes Agent connects to `llama.cpp`, `Ollama`, `vLLM`, and custom endpoints via its `plugins/model-providers/custom/` profile.
  - **Compatibility Taxonomy**:
    * `PROTOCOL_COMPATIBLE`: Endpoint connects via OpenAI `/v1/chat/completions` wire format.
    * `TOOL_FORMAT_COMPATIBLE`: Model/runtime exposes and accepts expected `tools` parameter and/or XML `<tool_call>` syntax.
    * `EMPIRICALLY_RELIABLE`: Model consistently emits valid, structured, non-hallucinatory tool calls under torture tests.
    * *Spark-X2.5 and Qwen are currently PROTOCOL_COMPATIBLE candidates; actual empirical tool reliability, `skill_view` invocation, and multi-turn stability must be empirically measured in Stage 2.*
- **Mechanism**: Splits skill representation into two tiers:
  1. *Prompt Invariant*: Injects *only* the skill name and short description (~15–25 tokens per skill) into the system prompt.
  2. *On-Demand Disclosure*: When the model identifies that a task matches a skill, it invokes `skill_view(skill_name)` to load full instructions, parameters, and scripts into context.
- **Why Useful**: Preserves 90%+ of the model's limited context window. Injecting 50 full skills would burn 15,000+ tokens; progressive disclosure consumes $<800\,\text{tokens}$.
- **Dependency Cost**: Zero external dependencies (standard library filesystem and YAML parser).
- **Runtime Cost**: Disk stat cache check ($<0.5\,\text{ms}$).
- **Coupling Risk**: None.
- **License**: MIT License.
- **Astra Subsystem Affected**: `src/astrarun/skills/registry.py` (`SkillRegistry`).

### 2.3 Action / Observation Event-Stream Protocol
- **Source Project**: OpenHands (`https://github.com/All-Hands-AI/OpenHands.git`)
- **Source Path**: `openhands/events/action/` and `openhands/events/observation/`
- **Mechanism**: Represents every agent operation as an immutable `Action` event (intent) paired with a typed `Observation` event (environment feedback):
  - `CmdRunAction` ➔ `CmdOutputObservation(exit_code, stdout, stderr, duration)`
  - `FileEditAction` ➔ `FileEditObservation(diff, success)`
  - `BrowseAction` ➔ `BrowserOutputObservation(url, content)`
- **Why Useful**: Enforces clean architectural separation between what the agent *intends* to do and what the machine *actually did*, providing structured inputs for error diagnosis and replanning.
- **Dependency Cost**: Zero (Python `pydantic` or `dataclasses`).
- **Runtime Cost**: In-memory serialization ($<0.01\,\text{ms}$).
- **Coupling Risk**: None.
- **License**: MIT License.
- **Astra Subsystem Affected**: `src/astrarun/agent/events.py` (`PlanStep` and `StepObservation`).

### 2.4 Normalized `[0, 1000]` Visual Coordinate Representation
- **Source Project**: ByteDance UI-TARS (`https://github.com/bytedance/UI-TARS-desktop.git`)
- **Source Path**: `packages/ui-tars/action-parser/src/actionParser.ts:92`
- **Mechanism**: Normalizes physical display coordinates to integer range $[0, 1000]$:
  $$x_{\text{norm}} = \text{round}\left(\frac{x_{\text{phys}} \times 1000}{W_{\text{screen}}}\right), \quad y_{\text{norm}} = \text{round}\left(\frac{y_{\text{phys}} \times 1000}{H_{\text{screen}}}\right)$$
- **Why Useful**: Makes visual actions resolution-independent across laptops, external 4K monitors, and scaling DPIs. Small models reason far better over 3-digit integers than floating-point coordinates.
- **Dependency Cost**: Zero external dependencies.
- **Runtime Cost**: Negligible.
- **Coupling Risk**: None.
- **License**: Apache-2.0.
- **Astra Subsystem Affected**: `src/astrarun/grounding/coordinate_scaler.py`.

### 2.5 Ambient Credential Scrubbing
- **Source Project**: DeepSeek Harness (`https://github.com/deepseek-ai/deepseek-harness.git`)
- **Source Path**: `packages/subprocess/subprocess/src/` (`scrubbedParentEnv`)
- **Mechanism**: Automatically sanitizes child process environment variables prior to launch, scrubbing sensitive keys (`DSH_*`, `OPENAI_*`, API tokens, private URLs) while allowing explicit overrides.
- **Why Useful**: Prevents untrusted scripts or subprocesses from accidentally inheriting or leaking ambient system credentials.
- **Dependency Cost**: Zero external dependencies (standard library dictionary filtering).
- **Runtime Cost**: Negligible ($<0.05\,\text{ms}$).
- **Coupling Risk**: None.
- **License**: MIT License.
- **Astra Subsystem Affected**: `src/astrarun/execution/sandbox.py` (`ProcessRunner`).

### 2.6 Non-Consuming Stream Reads (`readFrom(offset)`)
- **Source Project**: DeepSeek Harness (`https://github.com/deepseek-ai/deepseek-harness.git`)
- **Source Path**: `packages/subprocess/subprocess/src/` (`readFrom(offset)`)
- **Mechanism**: Retains process stdout/stderr streams in a ring buffer with absolute byte offset pointers. Consumers read with `readFrom(offset)` without stealing or draining each other's stream bytes.
- **Why Useful**: Allows the Task HUD, live debug loggers, and the Agent Execution Engine to simultaneously observe real-time process output without race conditions or stream contention.
- **Dependency Cost**: Zero external dependencies.
- **Runtime Cost**: Negligible in-memory slice operations.
- **Coupling Risk**: None.
- **License**: MIT License.
- **Astra Subsystem Affected**: `src/astrarun/execution/process_runner.py`.

---

## 3. Category 2: ADAPT


The following mechanisms are adapted with substantial modifications to meet AstraRun's hardware, performance, and security constraints:

### 3.1 Bounded C++ COM `FindAllBuildCache`
- **Source Project**: Microsoft UFO / UFO² (`https://github.com/microsoft/UFO.git`)
- **Source Path**: `ufo/automator/ui_control/inspector.py:251`
- **Upstream Flaw**: Naively traverses `TreeScope_Descendants` across the entire window without depth bounds. [MEASURED_LOCAL: Lab I proved this causes a 3.9-second COM freeze on Chromium/Vivaldi windows with 3,263 descendants].
- **AstraRun Adaptation**:
  1. Enforce an `AndCondition` pre-filter in C++ COM: `UIA_IsControlElementPropertyId == True` AND `UIA_IsEnabledPropertyId == True` AND `UIA_IsOffscreenPropertyId == False`.
  2. Implement shallow iterative depth bounding (`TreeScope_Children` before descending).
  3. Pre-fetch only 3 properties: `ControlType`, `Name`, and `BoundingRectangle`.
  4. Serialize into AstraRun Semantic Compact format (`@e{id} {type} "{name}" [{bbox}]`), cutting tokens by **66.5% - 82.2%** compared to UFO² JSON [MEASURED_LOCAL: Lab I].
- **Astra Subsystem Affected**: `src/astrarun/windows/uia_inspector.py`.

### 3.2 Trajectory Reflection Loop (DAG Re-Planner)
- **Source Project**: Simular AI Agent S3 (`https://github.com/simular-ai/Agent-S.git`)
- **Source Path**: `gui_agents/s3/agents/worker.py:125` (`_generate_reflection`)
- **Upstream Flaw**: Calls a separate massive cloud VLM (Claude Sonnet/Opus) on every micro-turn with dual 1080p images, burning extreme latency and tokens.
- **AstraRun Adaptation**:
  1. Decouple reflection from heavy image inspection: Run reflection over the structured `StepObservation` (exit codes, error strings, window state diffs).
  2. Invoke reflection *only upon step failure* or unexpected environment state, rather than unconditionally on every step.
  3. Feed the reflection directly into AstraRun's DAG re-planner to prune failed branches and generate alternate recovery steps.
- **Astra Subsystem Affected**: `src/astrarun/agent/execution_engine.py` (Replanning & Failure Recovery).

### 3.3 CodeAgent Subtask Delegation
- **Source Project**: Simular AI Agent S3 (`https://github.com/simular-ai/Agent-S.git`)
- **Source Path**: `gui_agents/s3/agents/code_agent.py:90`
- **Upstream Flaw**: Runs un-sandboxed shell commands via `env_controller.run_bash_script()`.
- **AstraRun Adaptation**:
  1. When a goal involves data manipulation, file filtering, mathematical calculations, or structured batch edits, the planner delegates to a subtask code block rather than executing dozens of UI clicks.
  2. The code block executes strictly inside AstraRun's **Windows Job Object sandbox** with a hard 128 MB RAM ceiling, a hard 15-second timeout watchdog, and secret stream scrubbing [MEASURED_LOCAL: Lab G verified 5/5 PASS].
- **Astra Subsystem Affected**: `src/astrarun/runtime/dynamic_execution.py`.

### 3.4 Async Environment Watchdogs
- **Source Project**: Browser Use (`https://github.com/browser-use/browser-use.git`)
- **Source Path**: `browser_use/browser/watchdogs/` (`dom_watchdog.py`, `downloads_watchdog.py`)
- **AstraRun Adaptation**:
  1. Implement native Windows async watchdogs:
     - `NetworkIdleWatchdog`: Verifies CDP browser navigation is settled before reading DOM.
     - `ProcessMemoryWatchdog`: Enforces Windows Job Object memory ceilings.
     - `DownloadWatchdog`: Monitors shell Known Folder `Downloads` for file completion.
- **Astra Subsystem Affected**: `src/astrarun/runtime/watchdogs.py`.

### 3.5 Syntax-Highlighted Preview & Confirmation UX
- **Source Project**: Open Interpreter / Codex (`https://github.com/openinterpreter/open-interpreter.git`)
- **Source Path**: `openai_codex/_approval_mode.py`
- **AstraRun Adaptation**:
  1. Adapt the formatted preview UI into the AstraRun Task HUD V2: When a high-risk action (deleting files, running system commands, network reconfiguration) is proposed, display the command diff, target paths, and risk explanation directly in the HUD.
  2. Require explicit Win32 hotkey / UI authorization before the `ActionGate` releases the cryptographic HMAC token to execute.
- **Astra Subsystem Affected**: `src/astrarun/ui/hud.py` and `src/astrarun/security/action_gate.py`.

### 3.6 AST Skill Linter & Safety Guard (Defense-in-Depth Only)
- **Source Project**: Hermes Agent (`https://github.com/NousResearch/Hermes-Agent.git`)
- **Source Path**: `tools/skill_linter.py` and `tools/skills_guard.py`
- **AstraRun Adaptation & Security Invariant**:
  1. Parse dynamically generated Python skill scripts with Python's built-in `ast` module before registering into the skill library.
  2. Disallow forbidden imports (`subprocess`, `ctypes`, `socket`, `os.system`) unless explicitly declared in frontmatter.
  3. Validate frontmatter schema, parameter types, and docstrings.
  4. **Strict Security Principle**: Hermes skill linting is **strictly defense-in-depth**. It does **NOT** replace AstraRun's `ActionGate`, `SecretBroker`, or Windows Job Object sandboxes. A skill that passes AST linting has zero system authority until AstraRun's deterministic policy layer authorizes each action.
- **Astra Subsystem Affected**: `src/astrarun/skills/compiler.py`.

### 3.7 Multi-Source Skill Provider Architecture
- **Source Project**: DeepSeek Harness (`https://github.com/deepseek-ai/deepseek-harness.git`)
- **Source Path**: `packages/skill/skill/src/` (`SkillRegistry.registerProvider`)
- **AstraRun Adaptation**:
  1. Refactor AstraRun's `SkillRegistry` from a single folder scanner into a multi-source provider seam:
     - `BuiltInSkillProvider`: Native system primitives.
     - `UserSkillProvider`: User personal skills (`~/.astrarun/skills/`).
     - `ProjectSkillProvider`: Workspace repo skills (`.astrarun/skills/`).
     - `GeneratedSkillProvider`: Procedurally synthesized & verified skills.
     - `ApprovedExternalSkillProvider`: Community vetted skill repositories.
  2. The registry merges all provider candidates, resolves duplicate names deterministically by layer rank, and serves a single unified view.
- **Astra Subsystem Affected**: `src/astrarun/skills/registry.py`.

### 3.8 Digest-Diffed Progressive Skill Catalog
- **Source Project**: DeepSeek Harness (`https://github.com/deepseek-ai/deepseek-harness.git`)
- **Source Path**: `packages/skill/tool-skill/src/` (`renderSkillCatalog`)
- **AstraRun Adaptation**:
  1. Hash the sorted list of skill headers (name + capped description) into a SHA-256 digest.
  2. Inject an `<available_skills>` catalog into message history only when the digest changes, ensuring that subsequent model turns maintain a static, reusable KV-cache prefix.
  3. Load full instruction bodies strictly on-demand when requested by the model or human `/name` gesture.
- **Astra Subsystem Affected**: `src/astrarun/skills/catalog.py`.

### 3.9 Out-of-Band SQLite FTS5 Episodic Memory Tools
- **Source Project**: DeepSeek Harness (`https://github.com/deepseek-ai/deepseek-harness.git`)
- **Source Path**: `packages/session-query/session-query-sqlite/` and `packages/session-query/tool-session-query/`
- **AstraRun Adaptation**:
  1. Index past execution trajectories into an out-of-band SQLite database with FTS5 virtual tables.
  2. Expose narrow, read-only episodic memory query tools (`session_search`, `session_event_search`) to the planner.
  3. Rather than dumping entire conversation histories into context, retrieve only relevant past event snippets on demand.
- **Astra Subsystem Affected**: `src/astrarun/memory/episodic.py`.

### 3.10 Four-Phase Goal Lifecycle Model
- **Source Project**: DeepSeek Harness (`https://github.com/deepseek-ai/deepseek-harness.git`)
- **Source Path**: `packages/goal/goal/src/` (`GoalService`)
- **AstraRun Adaptation**:
  1. Model long-running user objectives using DeepSeek's 4 durable phases: `active`, `paused`, `blocked` (with machine-readable error code and human explanation), and `complete`.
  2. Implement compare-and-set revision guards (`{id, revision}`) to prevent concurrent state corruption.
  3. Disarm autonomous continuation across cold restarts to avoid runaway background loops.
- **Astra Subsystem Affected**: `src/astrarun/planning/goal.py`.

---

## 4. Category 3: REIMPLEMENT MINIMAL


The following capabilities are re-implemented from scratch as lightweight native routines:

### 4.1 Headless Office / Explorer COM Automation
- **Source Project Reference**: Microsoft UFO (`ufo/automator/app_apis/word/wordclient.py`)
- **Upstream Flaw**: Calls `.Select()` and `.Activate()`, stealing foreground focus and disrupting the user.
- **AstraRun Reimplementation**:
  - Implement a lean, 150-line native Win32 COM adapter using `win32com.client.Dispatch()` / `GetActiveObject()` that manipulates Word/Excel document ranges in the background without bringing windows to the foreground.
- **Astra Subsystem Affected**: `src/astrarun/windows/office_com.py`.

### 4.2 Point-in-BBox Visual Verification Gate
- **Source Project Reference**: Midscene (`packages/core/src/element-describer.ts:81`)
- **AstraRun Reimplementation**:
  - When visual fallback grounding generates a click coordinate $(x, y)$, verify that $(x, y)$ falls within the semantic element's known bounding box or within a 20-pixel threshold before clicking.
- **Astra Subsystem Affected**: `src/astrarun/grounding/visual_verifier.py`.

---

## 5. Category 4: STRICTLY REJECT

The following upstream mechanisms are **explicitly prohibited** from AstraRun:

| Rejected Upstream Mechanism | Upstream Origin | Strict Rejection Rationale |
| :--- | :--- | :--- |
| **Physical Mouse Cursor Disruption** | UFO² (`controller.py:134`), Agent S3 (`grounding.py`), UI-TARS (`nut-js`) | **UX Invariant Violation**: AstraRun is a background workstation assistant. Moving the user's mouse cursor causes cursor-fighting and interrupts active user work. AstraRun interacts programmatically via UIA COM patterns and CDP DOM events. [MEASURED_LOCAL: Lab I verified 0 px displacement]. |
| **Disabling Safety Failsafes** | UFO² (`controller.py:42`: `pyautogui.FAILSAFE = False`) | **Severe Safety Hazard**: Disabling emergency aborts creates runaway execution risk. AstraRun enforces a global cancel hotkey and Job Object watchdog. |
| **Prompt-Only Safety Confirmation** | UFO² (`app_agent.yaml:36`: `status: "CONFIRM"`) | **Security Theater**: Hallucination-prone models cannot be trusted to self-police. Security must be an out-of-band programmatic boundary (`ActionGate`). |
| **Monolithic Full-Screen VLM Per-Step Loop** | Agent S3 (`worker.py`), UI-TARS (`GUIAgent.ts`) | **Hardware Budget Violation**: Sending 1080p images on every single micro-step requires a 14B+ VLM or high-cost cloud APIs. Completely incompatible with local RTX 2050 4 GB GPU. |
| **In-Memory FAISS Vector Injection** | UFO² (`experience/summarizer.py`) | **Context Window Exhaustion**: Dumping multi-step past trajectories into an 8k context window burns tokens and degrades reasoning. AstraRun compiles skills into standalone Python scripts. |
| **Heavy Docker Container Requirement** | OpenHands (`openhands/runtime/impl/docker/`) | **Startup Latency & Portability**: Docker Desktop on Windows has high startup overhead (>3s) and consumes 2+ GB RAM. AstraRun uses lightweight native Windows Job Objects ($<1\,\text{ms}$ startup, 0 MB baseline RAM). |
| **Direct Un-Sandboxed Host Shell Execution** | Open Interpreter (`client.py`) | **Security Vulnerability**: Executing arbitrary model-generated shell commands without memory caps or timeouts risks system corruption. |
| **Cordis Inversion-of-Control Microkernel** | DeepSeek Harness (`@deepseek-ai/cordis`) | **Excessive Indirection & Runtime Overhead**: 58-package TS framework with declaration merges adds immense debugging friction for a Python workstation agent. |
| **Puppeteer Browser-Use Dependency** | DeepSeek Harness (`packages/browser-use`) | **Incompatible with Workstation State**: Spawns isolated headless Chromium instances rather than attaching directly to the user's running Vivaldi browser session via native CDP. |

---

## 6. The Unified Architecture Synthesis

Does combining the strongest mechanisms from these eight systems produce the optimal design for AstraRun?

```
                                  USER GOAL
                                      │
                        ┌─────────────▼─────────────┐
                        │   AstraRun Planner DAG    │◄─── (Hermes Progressive Skill Registry)
                        └─────────────┬─────────────┘
                                      │ PlanStep DAG
                                      ▼
                        ┌───────────────────────────┐
                        │    AstraRun ActionGate    │◄─── (Open Interpreter Preview UX)
                        └─────────────┬─────────────┘
                                      │ Authorized Step
            ┌─────────────────────────┼─────────────────────────┐
            │ Native Windows          │ Browser Web             │ Subtask Code
            ▼                         ▼                         ▼
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────┐
│ Astra UIA Inspector   │ │ Astra CDP Client      │ │ Dynamic Execution     │
│ (Adapted UFO²         │ │ (Adopted Browser Use  │ │ Runtime               │
│ Bounded BuildCache +  │ │ Parent-Containment    │ │ (Job Object Sandbox   │
│ Compact Serialization)│ │ Pruning + Watchdogs)  │ │ + Agent S3 CodeAgent) │
└───────────┬───────────┘ └───────────┬───────────┘ └───────────┬───────────┘
            │                         │                         │
            └─────────────────────────┼─────────────────────────┘
                                      │
                                      ▼
                        ┌───────────────────────────┐
                        │      StepObservation      │ (Adopted OpenHands Event Protocol)
                        └─────────────┬─────────────┘
                                      │
                      ┌───────────────┴───────────────┐
                      │ PASS                          │ FAIL
                      ▼                               ▼
            ┌───────────────────┐           ┌───────────────────┐
            │ Next DAG Step /   │           │ Reflection Engine │ (Adapted Agent S3
            │ Goal Verification │           │ & DAG Re-Planner  │  Trajectory Reflection)
            └───────────────────┘           └───────────────────┘
```

### The Architectural Verdict:
**YES.** By taking:
- **UFO²'s** Win32 handle discovery and C++ COM caching (bounded with strict filters),
- **Browser Use's** parent-containment DOM pruning and compact element IDs,
- **Agent S3's** trajectory reflection loop and CodeAgent delegation pattern,
- **UI-TARS's** normalized `[0, 1000]` coordinate representation,
- **Hermes's** progressive skill disclosure and AST security linter,
- **OpenHands's** clean Action/Observation event protocol,
- **Open Interpreter's** syntax-highlighted preview UX,
and grounding them on **AstraRun's** deterministic foundations (`ActionGate`, `SecretBroker`, Windows Job Object sandbox, Task HUD V2, and UIA pattern invocation without cursor displacement), AstraRun achieves a system that is:
1. **Faster than UFO²** (no COM stalls, 66–82% fewer tokens),
2. **More non-intrusive than Agent S3 & UI-TARS** (zero mouse hijacking),
3. **Safer than Open Interpreter & UFO²** (deterministic Job Object sandboxing, zero disabled failsafes), and
4. **Feasible on our 4GB RTX 2050 workstation** (zero heavy VLM dependencies for standard workstation tasks).

---

## 7. Model Tournament Protocol Impacts (Before Stage 2 Downloads)

The upstream architecture mining reveals four critical refinements to the **Phase 17 Model Tournament Protocol** (`35_MODEL_TOURNAMENT_PROTOCOL.md`) that must be formalized *before* downloading model weights:

1. **Test Serialization Format Adherence (Compact vs JSON)**:
   - Rather than testing only generic JSON generation, candidate models must be evaluated on their ability to ingest AstraRun's **Semantic Compact format** (`@e1 Button "Submit" [x,y,w,h]`) and output structured target IDs (`@e1`).
2. **Separate Planning from Grounding**:
   - Upstream evidence proves that high-level DAG planning (decomposing a goal into steps) and low-level coordinate grounding (finding a pixel coordinate) require completely different faculties. The tournament must benchmark planning independently from pixel grounding.
3. **Benchmark Skill Selection Accuracy**:
   - Candidate models must be tested on Hermes-style progressive skill selection: given a list of 20 skill headers (name + description), can the model reliably select the correct skill without seeing the full body?
4. **Evaluate Code-Delegation Triggers**:
   - Candidate models must be tested on whether they recognize when to delegate a task to a Python code step (bulk data calculation, spreadsheet manipulation, regex file search) versus attempting repetitive UI clicks.
5. **Cross-Model Skill Portability Testing**:
   - Test whether skills authored by strong external teachers or Qwen can be executed reliably and cheaply by Spark-X2.5-1.7B.
6. **Reassessment & Removal of Hermes-3 Download**:
   - Hermes Agent is an architecture, not a model. Evaluating the Hermes Agent harness across Spark and Qwen eliminates the need for downloading `Hermes-3-Llama-3.2-3B-Q4_K_M.gguf` (~2.0 GB), reducing total Stage 2 downloads to **~3.72 GB**.

---

## 8. Architectural Taxonomy: Where Astra Intelligence Lives

AstraRun avoids fine-tuning every workstation workflow into model weights. Intelligence is cleanly partitioned:
1. **Model Weights**: Generalized linguistic reasoning, DAG planning, tool calling grammar (Qwen / Spark).
2. **Procedural Skills**: Reusable multi-step workflows (`SKILL.md` + `scripts/run.py`). Modular, human-readable, testable, and linted.
3. **Semantic Memory**: Machine paths, user preferences, hardware constants (SQLite WAL + FTS5).
4. **Episodic Memory**: Past execution traces, error diagnostics, and trajectory reflections.
5. **Deterministic Capabilities**: Trusted machine operations (`ActionGate`, `SecretBroker`, Job Object sandbox, Win32/CDP APIs).
