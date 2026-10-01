# 43_AGENT_ARCHITECTURE_LANDSCAPE.md — Cross-Repository Architectural Capability Matrix

> **Scope**: Comparative Audit of 8 State-of-the-Art Autonomous Agent Frameworks  
> **Target System**: AstraRun Pre-Implementation Architecture Discovery  
> **Status**: COMPLETED & VERIFIED  
> **Phase**: Phase 17-R (Secondary Upstream Architecture Mining Pass)  
> **Audited Systems**:  
> 1. AstraRun (Current v0.11 / Proposed Architecture B+)  
> 2. Microsoft UFO / UFO² (`microsoft/UFO`)  
> 3. Browser Use (`browser-use/browser-use`)  
> 4. Simular AI Agent S3 (`simular-ai/Agent-S`)  
> 5. ByteDance UI-TARS / Agent TARS (`bytedance/UI-TARS-desktop`)  
> 6. Hermes Agent (`NousResearch/Hermes-Agent`)  
> 7. OpenHands (`All-Hands-AI/OpenHands`)  
> 8. Open Interpreter / Codex (`openinterpreter/open-interpreter`)  
> 9. DeepSeek Harness (`deepseek-ai/deepseek-harness`)  

---

## 1. Cross-Repository Capability Matrix

### Rating Definitions:
- **`STRONG`**: Production-grade, thoroughly tested, architectural pillar of the system.
- **`USEFUL`**: Implemented and functioning, but has known limitations, narrow scope, or coupling.
- **`WEAK`**: Incomplete, primitive, prompt-only, fragile, or prone to failure.
- **`NOT_PRESENT`**: Mechanism does not exist in the codebase.
- **`UNKNOWN`**: Insufficient code evidence to evaluate.

| Architecture Dimension | Astra Current (v0.11) | Astra Proposed (Arch B+) | Microsoft UFO² | Browser Use | Simular AI Agent S3 | ByteDance UI-TARS | Hermes Agent | OpenHands | Open Interpreter |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1. Planning** | **USEFUL**<br>Pre-compiled DAG templates | **STRONG**<br>Dynamic Plan DAG + LLM replan | **WEAK**<br>1-step micro-loop (`app_agent.py:53`) | **USEFUL**<br>Sequential single-action loop | **USEFUL**<br>Single-action generator (`worker.py:178`) | **WEAK**<br>Single-step reactive loop | **STRONG**<br>Multi-step plan decomposition | **STRONG**<br>Event-stream plan state | **USEFUL**<br>Conversational step proposal |
| **2. Replanning** | **WEAK**<br>Static error fallback | **STRONG**<br>Observation-driven DAG replanner | **WEAK**<br>Re-prompts on exception | **USEFUL**<br>Step retry on failure | **STRONG**<br>Reflection agent (`worker.py:125`) | **USEFUL**<br>Async retry loop (`GUIAgent.ts:185`) | **STRONG**<br>Trajectory-aware repair | **STRONG**<br>Observation feedback loop | **USEFUL**<br>Traceback re-prompting |
| **3. Goal Verification** | **USEFUL**<br>Deterministic post-validators | **STRONG**<br>Verifier node in Plan DAG | **WEAK**<br>LLM self-reports `FINISH` | **USEFUL**<br>DOM selector validation | **USEFUL**<br>GUI check before `done()` | **WEAK**<br>Model emits `finished()` | **STRONG**<br>Skill/Test post-conditions | **STRONG**<br>Test exit-code inspection | **WEAK**<br>User manual validation |
| **4. Windows Native Control** | **STRONG**<br>Win32 API bindings | **STRONG**<br>Unified Windows System Surface | **STRONG**<br>Win32 window discovery | **NOT_PRESENT**<br>Browser-only | **WEAK**<br>Linux `wmctrl` focus | **WEAK**<br>Cross-platform wrapper | **WEAK**<br>Linux/macOS focus | **WEAK**<br>Docker/WSL focus | **USEFUL**<br>Subprocess shell execution |
| **5. Windows UIA** | **NOT_PRESENT**<br>(Pre-v0.12) | **STRONG**<br>Filtered `BuildCache` UIA | **STRONG**<br>`FindAllBuildCache` (`inspector.py`) | **NOT_PRESENT**<br>Browser-only | **NOT_PRESENT**<br>Pure visual/pyautogui | **NOT_PRESENT**<br>Pure visual/nut-js | **NOT_PRESENT**<br>CLI/API focus | **NOT_PRESENT**<br>CLI/Editor focus | **NOT_PRESENT**<br>CLI focus |
| **6. Office / App COM** | **NOT_PRESENT**<br>(Pre-v0.12) | **STRONG**<br>Headless ROT COM dispatch | **STRONG**<br>Word/Excel COM (`wordclient.py`) | **NOT_PRESENT**<br>Browser-only | **USEFUL**<br>LibreOffice UNO (`grounding.py:51`) | **NOT_PRESENT**<br>Visual-only | **NOT_PRESENT**<br>CLI/API focus | **NOT_PRESENT**<br>CLI/Editor focus | **NOT_PRESENT**<br>CLI focus |
| **7. Browser CDP** | **NOT_PRESENT**<br>(Pre-v0.12) | **STRONG**<br>Native WebSocket CDP client | **NOT_PRESENT**<br>Desktop UI focus | **STRONG**<br>Full CDP / Playwright (`browser.py`) | **NOT_PRESENT**<br>Desktop UI focus | **USEFUL**<br>Browser Operator package | **NOT_PRESENT**<br>HTTP fetch tools only | **USEFUL**<br>Browse tool | **NOT_PRESENT**<br>CLI focus |
| **8. DOM Representation** | **NOT_PRESENT**<br>(Pre-v0.12) | **STRONG**<br>Parent-contained `@e{id}` | **NOT_PRESENT**<br>Desktop UI focus | **STRONG**<br>Parent-containment pruning | **NOT_PRESENT**<br>Desktop UI focus | **NOT_PRESENT**<br>Visual-only | **NOT_PRESENT**<br>Markdown only | **USEFUL**<br>HTML markdown extract | **NOT_PRESENT**<br>CLI focus |
| **9. Visual Grounding** | **NOT_PRESENT**<br>(Pre-v0.12) | **USEFUL**<br>Fallback normalized grounding | **USEFUL**<br>Dual screenshots to VLM | **NOT_PRESENT**<br>DOM coordinate focus | **STRONG**<br>Referring expr VLM grounding | **STRONG**<br>`[0, 1000]` normalized box | **NOT_PRESENT**<br>Text-only | **NOT_PRESENT**<br>Text-only | **NOT_PRESENT**<br>Text-only |
| **10. Local OCR** | **NOT_PRESENT**<br>(Pre-v0.12) | **USEFUL**<br>Tesseract/ONNX fallback | **WEAK**<br>Delegates to cloud VLM | **NOT_PRESENT**<br>DOM text extraction | **USEFUL**<br>`pytesseract` word bbox | **NOT_PRESENT**<br>VLM vision only | **NOT_PRESENT**<br>Text-only | **NOT_PRESENT**<br>Text-only | **NOT_PRESENT**<br>Text-only |
| **11. Mouse/Keyboard** | **USEFUL**<br>Native hotkey registration | **STRONG**<br>UIA Pattern invoke (0 px move) | **WEAK**<br>`pyautogui` moves OS cursor | **USEFUL**<br>Playwright virtual mouse | **WEAK**<br>`pyautogui` moves OS cursor | **WEAK**<br>`@nut-tree/nut-js` cursor | **NOT_PRESENT**<br>Subprocess only | **NOT_PRESENT**<br>Subprocess only | **USEFUL**<br>`pyautogui` optional |
| **12. User Takeover** | **NOT_PRESENT**<br>(Pre-v0.12) | **STRONG**<br>Win32 Hotkey pause + HUD | **NOT_PRESENT**<br>Fights user mouse | **NOT_PRESENT**<br>Headless browser | **NOT_PRESENT**<br>Fights user mouse | **USEFUL**<br>Electron pause button | **NOT_PRESENT**<br>Terminal interrupt | **USEFUL**<br>Web UI pause/resume | **USEFUL**<br>Ctrl+C interrupt |
| **13. Dynamic Code Exec** | **WEAK**<br>Static adapter calls | **STRONG**<br>Job Object sandboxed runner | **NOT_PRESENT**<br>Action macros only | **NOT_PRESENT**<br>Browser JS eval only | **STRONG**<br>CodeAgent (`code_agent.py:90`) | **NOT_PRESENT**<br>GUI actions only | **STRONG**<br>Python/Bash terminal exec | **STRONG**<br>Sandbox command runner | **STRONG**<br>Interactive Python REPL |
| **14. Terminal Runtime** | **USEFUL**<br>Subprocess wrapper | **STRONG**<br>Streaming ConPTY / Job Object | **NOT_PRESENT**<br>No terminal runtime | **NOT_PRESENT**<br>Browser-only | **USEFUL**<br>Subprocess bash runner | **NOT_PRESENT**<br>Desktop UI only | **STRONG**<br>Stateful terminal sessions | **STRONG**<br>Docker/Pty terminal runner | **STRONG**<br>Streaming terminal REPL |
| **15. Sandboxing** | **WEAK**<br>Process isolation | **STRONG**<br>Win32 Job Object (128MB limit) | **NOT_PRESENT**<br>Runs directly on host | **USEFUL**<br>Browser sandbox isolation | **NOT_PRESENT**<br>Runs directly on host | **NOT_PRESENT**<br>Runs directly on host | **USEFUL**<br>Docker / Sandbox opt-in | **STRONG**<br>Docker container isolation | **WEAK**<br>Prompt confirmation only |
| **16. Memory / State** | **WEAK**<br>Session state dictionary | **STRONG**<br>SQLite WAL + FTS5 memory | **USEFUL**<br>Blackboard session memory | **USEFUL**<br>Browser state snapshot | **USEFUL**<br>Worker history + reflections | **WEAK**<br>In-memory conversation | **STRONG**<br>SQLite WAL + FTS5 database | **STRONG**<br>File & event store | **WEAK**<br>In-memory message list |
| **17. Episodic History** | **WEAK**<br>Recent run history | **STRONG**<br>Structured execution traces | **USEFUL**<br>Trajectory JSON dumps | **USEFUL**<br>GIF/video recording | **STRONG**<br>BBON trajectory recordings | **USEFUL**<br>Screenshot history log | **STRONG**<br>Compressed trajectory store | **STRONG**<br>Event replay log | **WEAK**<br>Chat history only |
| **18. Skills** | **WEAK**<br>Hardcoded capabilities | **STRONG**<br>Compiled Python skill library | **NOT_PRESENT**<br>Prompt instructions only | **NOT_PRESENT**<br>Browser actions only | **WEAK**<br>Static procedural prompts | **NOT_PRESENT**<br>No skill system | **STRONG**<br>Dynamic `SKILL.md` library | **USEFUL**<br>Microagent system | **NOT_PRESENT**<br>No skill abstractions |
| **19. Skill Compilation** | **NOT_PRESENT**<br>(Pre-v0.12) | **STRONG**<br>Trajectory ➔ Python skill | **NOT_PRESENT**<br>No compilation | **NOT_PRESENT**<br>No compilation | **NOT_PRESENT**<br>No compilation | **NOT_PRESENT**<br>No compilation | **STRONG**<br>`skill_manager_tool.py` | **NOT_PRESENT**<br>No auto-skill creation | **NOT_PRESENT**<br>No skill compilation |
| **20. Tool Retrieval** | **WEAK**<br>Regex rule match | **STRONG**<br>Hybrid FTS5 + ONNX Dense | **WEAK**<br>SentenceTransformers filter | **NOT_PRESENT**<br>Fixed browser toolset | **NOT_PRESENT**<br>Static tool definitions | **NOT_PRESENT**<br>Fixed action schema | **STRONG**<br>`tool_search.py` + FTS | **USEFUL**<br>Tool schema registry | **NOT_PRESENT**<br>Fixed toolset |
| **21. Prompt Injection** | **USEFUL**<br>Strict schema routing | **STRONG**<br>Out-of-band ActionGate | **NOT_PRESENT**<br>Vulnerable to injections | **WEAK**<br>Prone to web page text | **WEAK**<br>Prone to screen text | **NOT_PRESENT**<br>Raw text in prompt | **STRONG**<br>`tirith_security.py` guard | **USEFUL**<br>Security analyzer guard | **NOT_PRESENT**<br>Direct prompt exec |
| **22. Secret Handling** | **WEAK**<br>Environment variable check | **STRONG**<br>SecretBroker (HMAC scrubbed) | **NOT_PRESENT**<br>Raw secrets in memory | **NOT_PRESENT**<br>Plaintext config | **NOT_PRESENT**<br>Plaintext config | **NOT_PRESENT**<br>Plaintext config | **STRONG**<br>`secret_capture` + `.env` | **USEFUL**<br>Secret masking runtime | **NOT_PRESENT**<br>Plaintext CLI inputs |
| **23. Multi-Tasking** | **NOT_PRESENT**<br>Synchronous execution | **STRONG**<br>Background TaskRuntime | **WEAK**<br>Single active app loop | **NOT_PRESENT**<br>Single tab/page focus | **NOT_PRESENT**<br>Single-threaded loop | **NOT_PRESENT**<br>Single-threaded loop | **STRONG**<br>Subagents & background cron | **STRONG**<br>Multi-agent delegation | **NOT_PRESENT**<br>Single REPL loop |
| **24. Progress Reporting** | **STRONG**<br>Live HUD V2 + Motion | **STRONG**<br>HUD V2 + Streaming ConPTY | **NOT_PRESENT**<br>Terminal print output | **USEFUL**<br>Terminal progress bars | **NOT_PRESENT**<br>Console logging | **STRONG**<br>Electron visualization app | **STRONG**<br>TUI / Gateway status stream | **STRONG**<br>Web UI state stream | **STRONG**<br>Rich terminal display |
| **25. Long-Horizon State** | **WEAK**<br>Turn-by-turn memory | **STRONG**<br>Plan DAG execution state | **WEAK**<br>Prone to context explosion | **USEFUL**<br>Step limit watchdogs | **STRONG**<br>Reflection on trajectory | **WEAK**<br>Context window overflow | **STRONG**<br>Trajectory compressor | **STRONG**<br>State machine controller | **WEAK**<br>Context window overflow |
| **26. Benchmarking** | **USEFUL**<br>Phase 17 Labs D/E/F/G/I | **STRONG**<br>AstraBench (25 North-Star) | **USEFUL**<br>Windows-Bench | **USEFUL**<br>WebArena / Mind2Web | **STRONG**<br>OSWorld benchmark suite | **STRONG**<br>GUI-World / OSWorld eval | **STRONG**<br>SWE-bench / Tool-bench | **STRONG**<br>SWE-bench integration | **WEAK**<br>Ad-hoc manual tests |

---

## 2. Key Synthesis by Repository

### 2.1 Simular AI Agent S3 (`simular-ai/Agent-S`)
- **Core Strengths**:
  - **Reflection Agent on Trajectory** (`worker.py:125`): Decouples evaluation from action generation. In each turn, a secondary prompt (`REFLECTION_ON_TRAJECTORY`) inspects `(last_action, new_screenshot)` to explain why an action failed, feeding structured reflections into the generator.
  - **CodeAgent Subtask Delegation** (`code_agent.py:90`): When tasks require bulk computation (spreadsheets, file transforms, math), the GUI worker delegates to a multi-step code agent (up to 20 steps) rather than attempting thousands of GUI clicks.
  - **BBON (Best-of-N) Narration** (`behavior_narrator.py`): Visual trajectory debugging by annotating action points on screenshots.
- **Fatal Weaknesses for AstraRun**:
  - Heavy reliance on massive cloud VLMs (Claude 3.7 / Opus) emitting 1080p images on every single micro-turn.
  - Physically moves the OS mouse cursor via `pyautogui`, conflicting with user tasks.
  - Heavy Linux bias (`wmctrl` commands hardcoded in prompt).

### 2.2 ByteDance UI-TARS / Agent TARS (`bytedance/UI-TARS-desktop`)
- **Core Strengths**:
  - **Coordinate Normalization Schema** (`actionParser.ts:92`): `[0, 1000]` normalized coordinates scaled to physical display resolution `(x * width / 1000, y * height / 1000)` allows model actions to remain resolution-independent.
  - **Action Grammar**: Clean, compact action syntax: `click(start_box='(x, y)')`, `type(content='text')`, `hotkey(key='ctrl+c')`.
  - **`smartResizeForV15`**: Dynamic aspect-ratio-preserving downsampling to cap image token consumption within strict limits.
- **Fatal Weaknesses for AstraRun**:
  - Monolithic VLM dependency: UI-TARS 7B / 72B models cannot run locally on 4GB VRAM.
  - Uses `@nut-tree/nut-js` to physically move mouse cursor and click.

### 2.3 Hermes Agent (`NousResearch/Hermes-Agent`) — Model-Agnostic Agent Harness
- **Crucial Architectural Distinction: Harness vs Model**:
  - Hermes Agent's entire architecture—progressive skill disclosure, `SKILL.md` layout, procedural learning, `skill_manager_tool`, AST linter, and trajectory compression—is a **100% model-agnostic agent layer**.
  - Hermes-3-Llama-3.2-3B is merely one candidate model.
  - Source inspection of `plugins/model-providers/` (`plugins/model-providers/custom/__init__.py`) proves Hermes Agent supports local OpenAI-compatible endpoints (`llama.cpp`, `Ollama`, `vLLM`).
  - **Compatibility Taxonomy**:
    * `PROTOCOL_COMPATIBLE`: Endpoint connects via OpenAI `/v1/chat/completions` wire format.
    * `TOOL_FORMAT_COMPATIBLE`: Model/runtime exposes and accepts expected `tools` parameter and/or XML `<tool_call>` syntax.
    * `EMPIRICALLY_RELIABLE`: Model consistently emits valid, structured, non-hallucinatory tool calls under torture tests.
    * *Spark-X2.5 and Qwen are currently PROTOCOL_COMPATIBLE candidates; actual empirical tool reliability, `skill_view` invocation, and multi-turn stability must be empirically measured in Stage 2.*
- **Core Strengths**:
  - **Progressive Skill Disclosure** (`skills_tool.py:1`): The system prompt injects *only* skill names and short descriptions (~15 tokens per skill). Full instructions are retrieved dynamically via `skill_view` only when matched.
  - **Procedural Memory Evolution** (`skill_manager_tool.py`): Allows the agent to author, test, lint (`skill_linter.py`), and verify new skills into `~/.hermes/skills/<skill_name>/SKILL.md`.
  - **Security Auditing** (`skills_guard.py` / `tirith_security.py`): AST-based syntax checking and dangerous pattern scanning before skill registration (defense-in-depth).
  - **Trajectory Compression** (`trajectory_compressor.py`): Summarizes completed execution spans into compact history blocks to prevent context explosion.

### 2.4 OpenHands (`All-Hands-AI/OpenHands`)
- **Core Strengths**:
  - **Strict Event-Stream Runtime Protocol** (`openhands/events/`): Formal separation between `Action` (intent) and `Observation` (environment reality).
  - **Clean Developer Loop**: `CmdRunAction` ➔ `CmdOutputObservation(exit_code, stdout, stderr)` ➔ `FileEditAction` ➔ `FileEditObservation` ➔ Re-run.
  - **Cancellation & Isolation**: Robust container/sandbox teardown on user interrupt or error.
- **Weaknesses for AstraRun**:
  - Docker-heavy Linux orientation; high container startup overhead (>3 seconds) unsuitable for instantaneous Windows launcher hotkey tasks.

### 2.5 Open Interpreter (`openinterpreter/open-interpreter`)
- **Core Strengths**:
  - **Interactive Code Preview UX** (`_approval_mode.py`): Formats generated scripts in styled terminal/HUD boxes, presenting explicit user review before execution.
  - **Streaming Feedback**: Streams stdout line-by-line into the active session rather than blocking for full completion.
- **Weaknesses for AstraRun**:
  - Overly trusting security model: Default runs directly on the host shell; no memory quotas or Job Object sandbox.

### 2.6 DeepSeek Harness (`deepseek-ai/deepseek-harness`)
- **Core Strengths**:
  - **Provider-Based Skill Registry** (`packages/skill/skill`): Decouples skill sources (BuiltIn, Filesystem, Runtime) from model catalog merging, deduplication, and resolution.
  - **Digest-Diffed Progressive Disclosure** (`packages/skill/tool-skill`): Injects an `<available_skills>` catalog into history only when a digest over entries changes, preserving KV cache prefix stability.
  - **Win32 Job Object Integration** (`packages/subprocess/win32-process`): Implements suspended process creation (`CREATE_SUSPENDED`), assigns to Kill-on-Close Job Object, and verifies process-tree quiescence (`ActiveProcesses == 0`).
  - **Ambient Credential Scrubbing** (`scrubbedParentEnv`): Automatically strips secrets, API keys, and harness credentials from child process environments.
  - **Offset-Based Non-Consuming Stream Reads** (`readFrom(offset)`): Multiple observers share stdout/stderr streams without stealing each other's bytes.
  - **Episodic Session Query Tools** (`packages/session-query`): 5 narrow read-only tools (`session_search`, `session_event_search`, `session_trace`, etc.) querying an out-of-band SQLite FTS5 database.
  - **4-Phase Goal Lifecycle** (`packages/goal/goal`): `active`, `paused`, `blocked`, `complete` with compare-and-set revisions.
- **Weaknesses for AstraRun**:
  - Unstable developer preview status; frequent compatibility-breaking changes.
  - Overly complex Cordis plugin framework (58 npm packages, heavy runtime indirection).
  - Lacks native Windows UIA, COM, CDP attach, and floating HUD.

