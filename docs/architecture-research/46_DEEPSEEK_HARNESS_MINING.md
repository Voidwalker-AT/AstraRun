# Phase 17-R3: DeepSeek Harness Architecture Mining & Extraction Report

> **Project**: AstraRun (`E:\Workspace\Active\AstraRun`)  
> **Status**: PRE-IMPLEMENTATION RESEARCH COMPLETED  
> **Target Framework**: DeepSeek Harness (`deepseek-ai/deepseek-harness`)  
> **Production Code Status**: `src/astrarun/` is 100% UNTOUCHED  
> **Audit Date**: 2026-09-30  

---

## 1. Upstream Verification & Provenance

The official upstream repository was verified and fast-forward merged in canonical reference storage (`E:\Workspace\References\DeepSeek-Harness`):

| Property | Recorded Fact |
| :--- | :--- |
| **Repository URL** | `https://github.com/deepseek-ai/deepseek-harness` |
| **Commit SHA** | `639ed015397290b3745d163aafe02ffee4aa3f84` |
| **Release Tag** | `dsh-v0.2.0-rc.2` |
| **Commit Date** | `Tue Sep 29 17:21:31 2026 +0800` |
| **Branch** | `master` (clean working tree) |
| **License** | `MIT` (disclosed in `LICENSE` and `package.json`) |
| **Repository Size** | ~1.2 GB (includes full git history, web/desktop assets, test snapshots) |
| **Runtime Requirements** | `Node.js ^22.19.0 || >=24.0.0`, `pnpm@11.7.0` |
| **Stability Status** | **Developer Preview** ("iterating rapidly; THERE WILL BE COMPATIBILITY-BREAKING CHANGES") |

> [!WARNING]
> Because DeepSeek Harness explicitly identifies itself as an unstable developer preview with frequent breaking architectural changes, **AstraRun must NOT take a hard dependency on `@deepseek-ai/dsh` or adopt it as a global runtime framework.** All findings are evaluated strictly for conceptual extraction, structural alignment, and minimal reimplementation.

---

## 2. Core Architecture Map

DeepSeek Harness is constructed entirely on [Cordis](https://github.com/cordiverse/cordis), an inversion-of-control microkernel where **"everything is a plugin"** and components interact via typed services on a shared `Context` (`ctx`):

```
+----------------------------------------------------------------------------------------------------+
|                                    CORDIS CONTEXT (ctx)                                            |
+----------------------------------------------------------------------------------------------------+
|  ctx.agents      | Live Agent Registry & Lifecycle Coordinator (packages/core/agent)               |
|  ctx.agentLoop   | Turn Driver: Observe -> Pre-Step -> Request -> Execute -> Step End             |
|  ctx.tools       | Scoped Tool Registry & Multi-stage Execution Pipeline (packages/core/tools)    |
|  ctx.skills      | Multi-source Provider-based Skill Registry (packages/skill/skill)               |
|  ctx.subprocess  | Managed Process Spawner, Stream Collectors & Win32 Sandbox (packages/subprocess)|
|  ctx.terminals   | Interactive PTY Sessions with Shell Activity Inspection (packages/terminal)     |
|  ctx.goals       | Persistent 4-phase Completion Objective Service (packages/goal/goal)            |
|  ctx.jobs        | Background Job Registry with Non-consuming Offset Reads (packages/jobs/jobs)   |
|  ctx.subagent    | One-shot & Continuable Subagent Delegation Seam (packages/subagent/subagent)    |
|  ctx.sessions    | Append-only Versioned Event Log (packages/core/session)                         |
|  ctx.sessionQuery| SQLite FTS5 Full-Text Session Search Backend (packages/session-query-sqlite)    |
+----------------------------------------------------------------------------------------------------+
```

### Turn Flow Lifecycle (`packages/core/agent-loop/src/driver.ts`)
1. **Turn Start**: Claim next-step input and queued user messages.
2. **`agent/pre-step` Waterfall**: Listeners can rewrite messages, reject inputs, or inject durable reminders (e.g. progressive skill catalogs).
3. **Step Start & Prompt Assembly**: Merge system prompt sections, active tool schemas, and projected session context.
4. **`agent/request` & LLM Stream**: Stream model response (`llm/stream`), emit live chunks (`agent/assistant-stream`).
5. **Tool Execution Pipeline**:
   - `tools/pre-execute` (extensible allow/deny/ask waterfall)
   - Synchronous monotonic guards (`ctx.tools.guard()`)
   - `tools/execute` (around-dispatch wrapper: timeout, retry, metrics)
   - Tool body execution
   - `tools/post-execute` (result transformation, truncation policies)
   - Definition `finalizeContent`
   - `tools/result` (immutable final observation event)
6. **Step End / Continuation**: If tools owe further execution or new input arrived, schedule next step; otherwise close turn.

---

## 3. Tool Registry vs Astra ActionGate

### DeepSeek Harness Tool Architecture (`packages/core/tools/`)
- **Typed Schemas**: Authoring via `defineTool()` with typed parameters (`ParameterSchemaSpec`) and structured return schema (`output.schema`).
- **Validation**: Strict pre-execution argument validation against JSON Schema.
- **Execution Modes**:
  - `native`: Standard Function Calling with full JSON schemas exposed to LLM.
  - `ptc` (Programmatic Tool Calling): Replaces individual tool schemas with a single `run_code` tool and a generated TypeScript/Python SDK.
  - `both`: Exposes native tool schemas and the programmatic SDK simultaneously.
- **Per-Agent Restrictions**: `ctx.tools.restrict(filter)` applies allow/deny masks per agent scope.
- **Guards vs Policy**: `tools/pre-execute` allows external plugins to decide `allow`, `deny`, or `ask`. Monotonic guards registered via `ctx.tools.guard()` ensure that once denied, downstream listeners cannot reverse the rejection.

### Architectural Contrast: Tool Visibility vs Execution Authority

```
+------------------------------------------------------------------------------------+
|                                TOOL VISIBILITY                                     |
|  Controls what schemas the LLM sees in its prompt context.                         |
|  - DeepSeek: ctx.tools.restrict(), mode (native vs ptc), prompt filtering          |
|  - AstraRun: Query-Routed Retrieval (FTS5 + BGE ONNX), Progressive Header Filter   |
+------------------------------------------------------------------------------------+
                                         vs
+------------------------------------------------------------------------------------+
|                           TOOL EXECUTION AUTHORITY                                 |
|  Deterministic, unbypassable policy enforcement before any system action occurs.   |
|  - DeepSeek: tools/pre-execute waterfall, monotonic guards, user confirmation popup |
|  - AstraRun: ActionGate AST parser, strict path containment, SecretBroker,         |
|              Windows Job Object process/memory quotas, Prohibited Action rules     |
+------------------------------------------------------------------------------------+
```

> [!IMPORTANT]
> **Key Insight**: DeepSeek Harness's `tools/pre-execute` is cooperative middleware designed for extension. AstraRun's `ActionGate` is an **authoritative, unbypassable security fence**. AstraRun must retain its strict, deterministic ActionGate while adopting DeepSeek's typed `defineTool()` schema specification for cleaner capability authoring.

---

## 4. Skills Architecture: DeepSeek vs Hermes vs Astra

DeepSeek Harness introduces a modular, provider-based skill registry (`packages/skill/skill/`):

```
                        +----------------------------+
                        |        ctx.skills          |
                        |      (SkillRegistry)       |
                        +----------------------------+
                                      |
         +----------------------------+----------------------------+
         |                            |                            |
         v                            v                            v
+------------------+         +------------------+         +------------------+
| BuiltInProvider  |         |FilesystemProvider|         | RuntimeProvider  |
| (Core Primitives)|         | (Local Disk)     |         | (Plugin Memory)  |
+------------------+         +------------------+         +------------------+
                                      |
               +----------------------+----------------------+
               |                      |                      |
               v                      v                      v
        Project Skills          Custom Skills          User Skills
      (.dsh/skills, Rank 100)  (Config, Rank 300)   (~/.dsh/skills, Rank 400)
```

### Skill Format & Frontmatter Specification
Skills are authored either as directory bundles (`<name>/SKILL.md`) or flat markdown files (`<name>.md`). Frontmatter fields:
```yaml
---
name: wifi-reconnect
description: Reconnects to known wireless networks with timeout handling.
whenToUse: Use when network connectivity drops or switching hotspots.
disable-model-invocation: false
user-invocable: true
metadata:
  category: network
  requires_elevation: false
---
# Skill instructions...
```

### Comparison: Hermes vs DeepSeek vs Astra

| Dimension | Hermes Agent | DeepSeek Harness | AstraRun Proposed Architecture |
| :--- | :--- | :--- | :--- |
| **Skill Format** | `SKILL.md` in directory | `SKILL.md` or `<name>.md` | `SKILL.md` directory bundle |
| **Registry Model** | Monolithic folder scanner | **Provider-based Registry** (`ctx.skills.registerProvider`) | **Provider-based Registry** (`SkillRegistry`) |
| **Catalog Lifecycle** | Dynamic retrieval injection | **Digest-diffed pre-step injection** | **Query-routed retrieval + digest catalog** |
| **Body Loading** | Full prompt or tool call | On-demand via `skill` tool or `/name` | On-demand via `skill_view` tool or planner DAG |
| **Invocation Control** | Model-invocable by default | `disable-model-invocation` & `user-invocable` flags | Surface policy: Autonomous vs Escalated |
| **File Watching** | Periodic / manual | **Chokidar watcher + instant write-tool invalidation** | Path-watcher + instant write invalidation |
| **Procedural Learning** | Trajectory distillation | None (read-only authoring) | Hermes-style skill distillation |

### Recommended Astra Skill Provider Split
AstraRun should adapt DeepSeek's provider abstraction:
```python
class SkillRegistry:
    def __init__(self):
        self._providers: list[SkillProvider] = []
        
    def register_provider(self, provider: SkillProvider) -> None:
        ...

# The 5 Canonical Astra Skill Providers:
1. BuiltInSkillProvider       -> Core native capabilities (battery, wifi, process, audio)
2. UserSkillProvider          -> System user skills (~/.astrarun/skills/)
3. ProjectSkillProvider       -> Workspace-specific skills (.astrarun/skills/ in active project)
4. GeneratedSkillProvider     -> Verified procedural skills synthesized from successful runs
5. ApprovedExternalProvider   -> Cloned or imported verified community skills
```

---

## 5. Progressive Disclosure Comparison

Both Hermes and DeepSeek Harness implement progressive disclosure to conserve model context and maximize KV-cache reuse:

1. **Catalog Representation**:
   - DeepSeek Harness computes a SHA-256 digest over sorted skill names and capped descriptions (`catalogDescriptionMaxLength: 500`).
   - Before the first turn, it injects an `<available_skills>` block into user-role message history.
   - If membership changes, it emits a complete replacement catalog. If all skills are removed, it emits an explicit retirement tombstone.
2. **Instruction Loading**:
   - The LLM calls the `skill` tool with `{ name: "..." }`.
   - The system returns the full markdown body enclosed in `<skill_content>` tags.
   - Alternatively, human user gestures (`/wifi-reconnect`) inject `<skill_content>` directly into user message history.
3. **KV Cache & Token Efficiency**:
   - By diffing the digest over structured entries rather than rendered text, DeepSeek avoids cache-busting prompt jitter.
   - Full instruction bodies are loaded only for the specific active skill, avoiding multi-kilobyte context pollution.

**Recommendation for AstraRun**: **ADAPT**. Adopt DeepSeek's digest-diffed `<available_skills>` catalog and `<skill_content>` delimiter format, combining it with Astra's query-routed retrieval.

---

## 6. Subprocess & Win32 Sandbox Abstraction

DeepSeek Harness contains an exceptionally thorough Windows implementation (`packages/subprocess/win32-process`):

### Win32 Process Implementation Highlights
1. **Suspended Process Creation**: Calls `CreateProcessW` with `CREATE_SUSPENDED`.
2. **Kill-On-Close Job Object**: Immediately calls `AssignProcessToJobObject` to an unnamed Windows Job Object configured with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`.
3. **Thread Resumption**: Calls `ResumeThread` only after the process is safely contained within the Job Object, eliminating the race condition where child processes could spawn uncontrolled descendants before containment.
4. **Quiescence Verification**: Calls `QueryInformationJobObject` with `JobObjectBasicAccountingInformation`, polling until `ActiveProcesses == 0` before declaring complete teardown.
5. **Restricted Token Sandbox**: Implements `CreateProcessAsUserW` with stripped privileges, filtered DACLs, and null environment blocks.
6. **Ambient Credential Scrubbing**: `scrubbedParentEnv` automatically removes API keys (`DSH_*`, `OPENAI_*`, tokens) before child process launch.
7. **Offset-based Non-Consuming Stream Reads**: `readFrom(offset)` allows background observers and terminal collectors to share stdout/stderr streams without stealing bytes.

> [!NOTE]
> This upstream implementation provides independent confirmation of the exact Windows Job Object architecture AstraRun validated in Lab D.

**Recommendation for AstraRun**:
- **ADOPT**: Ambient credential scrubbing (`scrubbedParentEnv`) in Astra's `ProcessRunner`.
- **ADOPT**: Non-consuming offset reads (`readFrom(offset)`) for stdout/stderr streaming.
- **RETAIN**: Astra's custom Windows Job Object implementation in `safe_command.py` with memory/CPU hard caps.

---

## 7. Goals, Background Jobs, and Multi-Tasking

### Goals (`packages/goal/goal`)
- Pursues one long-running objective across turns, forks, and restarts.
- **Four Durable Phases**:
  1. `active`: Goal is being actively pursued.
  2. `paused`: Temporarily halted; retains progress.
  3. `blocked`: Paused with a stable policy code (e.g. `needs-elevation`, `missing-secret`) and human explanation.
  4. `complete`: Goal achieved.
- **Compare-and-Set Revisions**: All mutations require `{ id, revision }`, preventing stale state overwrites.
- **Process-Local Activation**: Continuation permission is explicitly disarmed across process restarts to prevent runaway loops.

### Background Jobs (`packages/jobs/jobs`)
- Stable branded identifiers: `<kind>-N` (e.g. `bash-1`, `ping-2`).
- Owner-scoped authorization: Accessible only to the originating session.
- Ring buffer storage: stdout, stderr, and observer-only logs.
- Event-driven settlement: Emits completion events without requiring busy-wait polling loops.

### Subagents (`packages/subagent/subagent`)
- **One-shot Children**: Run to completion and return a single structured result.
- **Continuable Children**: Maintain durable sessions, support bi-directional messaging (`sendMessage`), and allow parent steering or interruption.
- **Concurrency & Depth Limits**: `maxActiveSubagents: 8`, `maxDepth: 1` (prevents uncontrolled recursive spawning).

**Recommendation for AstraRun**:
- **ADAPT**: The 4-phase goal lifecycle (`active`, `paused`, `blocked`, `complete`) into Astra's `UserGoal` model.
- **ADAPT**: Branded job handles (`<kind>-N`) and event-driven settlement into Astra's `TaskRuntime`.
- **RETAIN**: Astra's topological Plan DAG for explicit task dependency management.

---

## 8. Session & Episodic Memory

DeepSeek Harness separates live session history from full-text episodic retrieval:

1. **Append-Only Event Store (`packages/core/session`)**: Every action, thought, tool invocation, and observation is persisted as an immutable `SessionEvent` in JSONL (`session.v4.jsonl`).
2. **Derived SQLite FTS5 Index (`packages/session-query/session-query-sqlite`)**: History is indexed into a separate derived database (`session-search.db`) using SQLite FTS5 for BM25 ranking and snippet generation (`snippetChars: 240`).
3. **Model Retrieval Tools (`packages/session-query/tool-session-query`)**:
   - `session_search`: Search prior sessions within the same project workspace (`cwd`).
   - `session_event_search`: Search specific events within a session.
   - `session_trace`: Retrieve parent-child session ancestry.
   - `session_event_read`: Fetch unabridged event JSON and immediate neighbors.

### Memory Hierarchy Comparison

```
+------------------------------------------------------------------------------------+
|                                WORKING MEMORY                                      |
|  Current active turn, unsealed execution DAG, live scratchpad.                     |
|  - Astra: ExecutionGraph + StepObservations                                        |
+------------------------------------------------------------------------------------+
                                          |
                                          v
+------------------------------------------------------------------------------------+
|                                EPISODIC MEMORY                                     |
|  Prior completed sessions, past tool outcomes, previous failure recoveries.         |
|  - DeepSeek: session_search & session_event_search via SQLite FTS5                   |
|  - AstraRun: Adopt derived SQLite FTS5 episodic event index                         |
+------------------------------------------------------------------------------------+
                                          |
                                          v
+------------------------------------------------------------------------------------+
|                                SEMANTIC MEMORY                                     |
|  Domain facts, system topology, hardware configuration, concept embeddings.        |
|  - AstraRun: BGE-Small-EN-v1.5 ONNX embeddings                                      |
+------------------------------------------------------------------------------------+
                                          |
                                          v
+------------------------------------------------------------------------------------+
|                                PROCEDURAL MEMORY                                   |
|  Executable capabilities, workflows, scripts, and skills.                          |
|  - AstraRun: SkillRegistry (5 providers) + Dynamic Code Runtime                     |
+------------------------------------------------------------------------------------+
```

**Recommendation for AstraRun**: **ADAPT**. DeepSeek's five episodic query tools (`session_search`, `session_event_search`, etc.) running over SQLite FTS5 provide an elegant solution for cross-session episodic memory without polluting context tokens.

---

## 9. Minimal Agent Spine Analysis

DeepSeek Harness defines a minimal agent spine as:
`Context` + `AgentLoop` + `SessionLog` + `ToolRegistry` + `LLMAdapter` + `SystemPrompt`.

### What Astra is Re-inventing vs What DeepSeek Lacks

| Component | DeepSeek Harness Status | AstraRun Status / Requirement | Recommendation |
| :--- | :--- | :--- | :--- |
| **Agent Loop** | Cordis event-driven waterfall | Deterministic Observe-Act-Verify loop | **Keep Astra's loop** |
| **Tool Calling** | Native JSON & PTC mode | Structured DAG / JSON tools | **Keep Astra's DAG** |
| **Security Gate** | Cooperative waterfall policy | Deterministic AST ActionGate | **Keep Astra's ActionGate** |
| **Secret Quarantining**| Scrubbed env variables | SecretBroker (no keys in prompt) | **Keep Astra's SecretBroker** |
| **Windows Job Objects**| Koffi Win32 FFI primitives | Native Win32 CFFI/PyWin32 limits | **Keep Astra's limits** |
| **UI Automation (UIA)**| **MISSING** (No native Windows UIA)| Core Astra capability | **Astra Unique Strength** |
| **COM / Office Automation**| Primitive file parsers only | Native pywin32 COM automation | **Astra Unique Strength** |
| **Browser CDP Control**| Puppeteer-based `browser-use` | Native CDP attach to existing Vivaldi | **Astra Unique Strength** |
| **Physical HUD / Motion**| **MISSING** (Web UI / Electron only)| Floating PySide/Win32 HUD & motion | **Astra Unique Strength** |
| **User Takeover Detection**| **MISSING** (Web abort button only)| Low-level mouse/keyboard hook abort | **Astra Unique Strength** |

---

## 10. Plugin Architecture Evaluation

DeepSeek Harness relies on Cordis for 100% of its composition.

### Evaluation for AstraRun
- **Complexity**: Extreme. DeepSeek has 58 separate npm packages, complex circular TypeScript declaration merges, and high mental overhead.
- **Startup Cost**: Several hundred milliseconds to initialize Cordis contexts and resolve dependency injection graphs.
- **Debugging**: Async waterfalls with `next()` middlewares make call stack tracing and exception attribution difficult.
- **AstraRun Verdict**: **REJECT CORDIS FRAMEWORK**. AstraRun is a focused, high-performance desktop workstation agent written in Python, not a generalized TypeScript application platform. AstraRun must use simple, direct Python composition with clear abstract base classes for its major seams.

---

## 11. The Hermes + DeepSeek + AstraRun Synthesis

By combining the best mechanisms from each audited framework, AstraRun achieves a superior architecture:

```
+----------------------------------------------------------------------------------------------------+
|                                    ASTRARUN WORKSTATION AGENT                                      |
+====================================================================================================+
|  HERMES AGENT CONCEPTS:                                                                            |
|  - Skill authoring standards (SKILL.md format)                                                     |
|  - Progressive procedural distillation & skill evolution                                            |
|  - Trajectory compression & offline skill linting                                                  |
+----------------------------------------------------------------------------------------------------+
|  DEEPSEEK HARNESS CONCEPTS:                                                                        |
|  - Multi-source SkillProvider registry (Built-in, User, Project, Generated)                        |
|  - Digest-diffed progressive catalog lifecycle (prefix-cache stable)                               |
|  - Ambient credential scrubbing (scrubbedParentEnv)                                                |
|  - Non-consuming stream reads (readFrom(offset))                                                   |
|  - SQLite FTS5 episodic memory query tools (session_search, session_event_search)                   |
|  - 4-Phase Goal lifecycle (active, paused, blocked, complete)                                      |
+----------------------------------------------------------------------------------------------------+
|  ASTRARUN DETERMINISTIC CORE:                                                                      |
|  - Deterministic ActionGate (Static AST & path containment)                                       |
|  - SecretBroker (quarantined credentials never leak to LLM)                                        |
|  - Windows Job Object sandbox (hard CPU, memory, and process quotas)                               |
|  - Native Windows UIA & COM system automation                                                      |
|  - Native Vivaldi CDP browser control without browser relaunch                                     |
|  - Floating HUD & human takeover physical mouse/keyboard interrupt                                 |
|  - Qwen2.5-Coder-1.5B-Instruct-Q4_K_M local specialist on RTX 2050                                  |
+====================================================================================================+
```

---

## 12. Security Review

| Attack Vector | DeepSeek Harness Defense | AstraRun ActionGate Defense | Evaluation |
| :--- | :--- | :--- | :--- |
| **Prompt Injection** | Relies on LLM & user confirmation prompts | **Deterministic ActionGate**: Rejects unauthorized paths regardless of LLM compliance | **Astra is strictly stronger** |
| **Command Execution**| Monotonic guard & sandbox restricted token | **Job Object sandbox** + prohibited command regex + AST parser | **Astra is strictly stronger** |
| **Path Traversal** | Exact `cwd` equality check | Strict path normalization & workspace jail | **Equal / Strong** |
| **Secret Exfiltration**| `scrubbedParentEnv` removes `DSH_*` | **SecretBroker**: Keys never touch prompt context or logs | **Astra is strictly stronger** |
| **Fork Bombs** | Win32 Job Object Kill-on-close | Win32 Job Object with process count + active process limits | **Equal / Strong** |

---

## 13. Extraction Classification Matrix

| Mechanism / Concept | Upstream Package | Proposed Astra Action | Implementation Target |
| :--- | :--- | :---: | :--- |
| **Multi-source Skill Provider Seam** | `packages/skill/skill` | **ADAPT** | `src/astrarun/skills/registry.py` |
| **Digest-diffed Skill Catalog** | `packages/skill/tool-skill` | **ADAPT** | `src/astrarun/skills/catalog.py` |
| **Ambient Credential Scrubbing** | `packages/subprocess/subprocess` | **ADOPT** | `src/astrarun/execution/sandbox.py` |
| **Non-consuming Stream Reads** | `packages/subprocess/subprocess` | **ADOPT** | `src/astrarun/execution/process_runner.py` |
| **Episodic Query Tools (`session_*`)**| `packages/session-query` | **ADAPT** | `src/astrarun/memory/episodic.py` |
| **4-Phase Goal Model** | `packages/goal/goal` | **ADAPT** | `src/astrarun/planning/goal.py` |
| **Branded Background Job Handles** | `packages/jobs/jobs` | **ADAPT** | `src/astrarun/execution/task_runtime.py` |
| **PTC Mode (`run_code` SDK generator)**| `packages/core/tools` | **BENCHMARK** | Post-v0.12 Research Spike |
| **Cordis Plugin Framework** | Root / Vendor | **REJECT** | Unnecessary indirection for Python runtime |
| **Puppeteer Browser Use** | `packages/browser-use` | **REJECT** | Incompatible with Astra native Vivaldi CDP attach |
| **Electron Desktop Carrier** | `apps/desktop` | **NOT_APPLICABLE** | Astra uses native PySide6 floating HUD |

---

## 14. Final Verdict: Does DeepSeek Harness Materially Change Architecture B+?

### **Verdict: MINOR_REFINEMENT**

### Detailed Rationale:
1. **No Core Architecture Disruption**: DeepSeek Harness confirms, rather than challenges, Architecture B+. It uses the identical foundational patterns AstraRun benchmarked and selected:
   - Dynamic code execution + structured tools
   - Progressive disclosure markdown skills (`SKILL.md`)
   - Windows Job Objects for process tree containment
   - SQLite FTS5 for high-speed lexical search
2. **Key Refinements Gained**:
   - **Provider-based Skill Architecture**: Upgrading `SkillRegistry` from a single directory scanner to a multi-source provider model (`BuiltIn`, `User`, `Project`, `Generated`).
   - **Cache-stable Catalog Digesting**: Computing a digest over skill summaries so catalog updates do not invalidate the LLM's KV cache prefix.
   - **Episodic Memory Query Seam**: Adding read-only session search tools backed by SQLite FTS5 instead of blowing context tokens on historical transcripts.
   - **Process Runtime Hardening**: Incorporating ambient secret scrubbing (`scrubbedParentEnv`) and non-consuming stream offsets (`readFrom(offset)`).
3. **AstraRun Invariants Preserved**:
   - `ActionGate` remains the supreme deterministic security boundary.
   - Qwen2.5-Coder-1.5B Q4_K_M remains the local reasoning specialist on the RTX 2050.
   - Native Windows UIA, COM, CDP, and HUD remain AstraRun's unique workstation superpowers.

**Architecture B+ is refined, fortified, and ready for implementation.**
