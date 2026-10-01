# 42_UPSTREAM_IMPLEMENTATION_MINING.md — Upstream Implementation Mining & Evidence Synthesis

> **Scope**: Source-Code Mining of Mature Open-Source Workstation & Browser Agents  
> **Status**: COMPLETED  
> **Phase**: Phase 17-R (Pre-Implementation Architectural Reality Gate)  
> **Execution Date**: 2026-09-30  
> **Target Systems**: Microsoft UFO / UFO² and Browser Use  
> **Parent Contract**: `E:\Workspace\Active\AstraRun\AGENTS.md`  

---

## 1. Upstream Audit Ledger & Repository Metadata

All source code analysis in this document was conducted directly against cloned upstream repositories located in isolated research directories. Zero upstream code was copied into `src/astrarun/`.

| Upstream Project | Cloned Research Path | Upstream Git URL | Inspected Commit SHA | License | Primary Architectural Focus |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Microsoft UFO / UFO²** | `tests/benchmarks/phase17/upstream/ufo/` | `https://github.com/microsoft/UFO.git` | `a795552d976c4c019d7c2f778a0effb5cef7de6b` | MIT License | Dual-agent desktop OS navigation, Win32/UIA COM inspection, Office COM APIs |
| **Browser Use** | `tests/benchmarks/phase17/upstream/browser_use/` | `https://github.com/browser-use/browser-use.git` | `4cbe921673b48a488f5415d9159249afd12a625b` | MIT License | CDP browser automation, interactive DOM tree pruning, async watchdogs |

---

## 2. Component Extraction Decision Matrix

The following matrix classifies every major upstream architectural mechanism into an explicit AstraRun engineering verdict:
- **`ADOPT`**: Implement directly in AstraRun v0.12 with identical semantics.
- **`ADAPT`**: Adopt the core concept but redesign to fit AstraRun's local resource budget, non-intrusiveness invariants, and security requirements.
- **`REIMPLEMENT_MINIMAL`**: Strip upstream bloat, third-party framework overhead, and external dependencies; implement as a lean native Python/Win32 routine.
- **`BENCHMARK`**: Maintain as a candidate comparative baseline in Phase 17 tournaments.
- **`REJECT`**: Explicitly prohibited from AstraRun due to security vulnerabilities, UX disruption, or resource violation.
- **`NOT_APPLICABLE`**: Cloud-only or out-of-scope upstream components.

| Component / Subsystem | Upstream Source Location | Upstream Mechanism | AstraRun Verdict | Architectural Rationale & Local Evidence Link |
| :--- | :--- | :--- | :--- | :--- |
| **Win32 Window Discovery** | `ufo/automator/ui_control/inspector.py:189` | `Desktop(backend="win32").windows()` before UIA wrapping | **ADOPT** | Avoids severe UIA COM stalls on initial desktop inspection. [MEASURED_LOCAL: Lab I verified input desktop HWND enumeration takes <1 ms]. |
| **UIA COM Batch Caching** | `ufo/automator/ui_control/inspector.py:251` | `FindAllBuildCache` with `TreeScope_Descendants` | **ADAPT** | Batch pre-fetching properties in C++ COM cuts per-element overhead, BUT upstream lacks depth limits. Must enforce `IsControlElement` pre-filter to prevent Chromium stalls [MEASURED_LOCAL: Lab I showed 3.9s stall without pre-filter, 2.0s with pre-filter]. |
| **Parent-Containment DOM Pruning** | `browser_use/dom/serializer/serializer.py` | Exclude elements 99% contained inside interactive parents | **ADOPT** | Dramatically eliminates redundant child tokens (`span` inside `button`) without losing click targets. [MEASURED_LOCAL: Lab D showed raw AXTree added +41% token overhead; pruning required]. |
| **Semantic Compact Element IDs** | `browser_use/dom/views.py` / `ufo/prompts/` | Compact index markup `[12] <button>` vs JSON arrays | **ADOPT** | UFO²'s JSON array format wastes context window. AstraRun `@e{id} {type} "{name}"` achieves 66.5% - 82.2% token reduction. [MEASURED_LOCAL: Lab I empirical verification]. |
| **Desktop State Machine** | `ufo/agents/agent/host_agent.py` | Two-tier `HostAgent` (router) ➔ `AppAgent` (operator) | **ADAPT** | Conceptually sound macro/micro separation, but UFO runs 1 LLM call per micro-step. AstraRun adapts this into a deterministic Plan DAG with dynamic re-observation. |
| **Async Watchdogs** | `browser_use/browser/watchdogs/` | Background tasks monitoring DOM stability, popups, downloads | **ADAPT** | Critical for robust non-blocking execution. Adapts to Windows Job Object watchdog and CDP network idle polling [MEASURED_LOCAL: Lab G & Lab D verified]. |
| **Office COM ROT Dispatch** | `ufo/automator/app_apis/word/wordclient.py` | `win32com.client.Dispatch()` with ROT window title matching | **REIMPLEMENT_MINIMAL** | Excellent zero-dependency programmatic document control, but remove UFO's `.Select()` calls to preserve background execution. |
| **Interactive Cursor Hijacking** | `ufo/automator/ui_control/controller.py:134` | `pyautogui.click()` and `pywinauto.click_input()` moving mouse | **REJECT** | Physically moves the OS mouse cursor and fights user inputs. Violates AstraRun non-intrusiveness invariant [MEASURED_LOCAL: Lab I confirmed 0 px displacement via programmatic UIA]. |
| **Disabling Failsafes** | `ufo/automator/ui_control/controller.py:42` | `pyautogui.FAILSAFE = False` | **REJECT** | Critical safety violation. Removing emergency escape aborts creates runaway execution risk. AstraRun uses Win32 hotkey + Job Object quotas [MEASURED_LOCAL: Lab G]. |
| **Prompt-Only Safety Confirmation** | `ufo/prompts/share/base/app_agent.yaml:36` | LLM self-reports `status: "CONFIRM"` to request permission | **REJECT** | Hallucination-prone security theater. AstraRun mandates deterministic code-level `ActionGate` with cryptographic HMAC tokens. |
| **FAISS Vector In-Context Demonstration** | `ufo/experience/summarizer.py` | Post-task LLM summary embedded in FAISS vector store | **REJECT / ADAPT_MINIMAL** | High memory footprint; injects variable-length unstructured demonstrations into 8k context window. AstraRun replaces this with compiled deterministic Python skills. |
| **Dual Screenshot Visual Grounding** | `ufo/prompts/share/base/app_agent.yaml` | Dual raw 1080p screenshots (clean + annotated bboxes) to VLM | **REJECT (for local 4GB GPU)** | Exceeds 4 GB VRAM budget. Requires multi-modal VLM context (~2,000+ tokens per step). AstraRun prioritizes semantic text/UIA first, visual fallback only. |

---

## 3. Microsoft UFO / UFO² Architectural Audit (`UPSTREAM_SOURCE_VERIFIED`)

### 3.1 Coordination & State Machine: Macro Router vs Deterministic DAG
- **Upstream Pattern**:
  - `HostAgent` (`ufo/agents/agent/host_agent.py:47`): Discovers running application windows on the desktop, takes a full-screen screenshot, calls an LLM to select the target window, and transitions to `AssignHostAgentState` (`ufo/agents/states/host_agent_state.py:176`).
  - `AppAgent` (`ufo/agents/agent/app_agent.py:53`): Takes an in-app screenshot, reads UIA control elements, calls an LLM to decide a single atomic action (click, type, scroll), executes it, and evaluates whether the sub-goal is finished.
  - Return to Host: Emits `status = "FINISH"` to yield control back to `HostAgent`.
- **AstraRun Evaluation**:
  - *Strengths*: Clean separation between desktop-level routing and application-level execution.
  - *Weaknesses*: **Extreme latency and cost**. UFO executes **1 LLM call per single click/keypress**. A 5-step task requires 5-7 sequential roundtrips.
  - *AstraRun Decision (`ADAPT`)*: AstraRun retains the macro/micro conceptual separation, but replaces the per-step LLM ping-pong with a **Plan DAG**. The planner generates a structured multi-step DAG executed deterministically by the local runtime, re-invoking the model *only* when dynamic observation fails or branch conditions trigger.

### 3.2 Windows Control Surfaces & UIA Traversal
- **Upstream Pattern**:
  - Window Acquisition: `inspector.py:189` discovers top-level windows via `Desktop(backend="win32").windows()` and passes `window.handle` to `UIAElementInfo(handle_or_elem=window.handle)`.
  - Batch Caching: `inspector.py:251` calls `window_elem_com_ref.FindAllBuildCache(scope=TreeScope_Descendants, condition=condition, cacheRequest=cache_request)` prefetching `UIA_ControlTypePropertyId`, `UIA_NamePropertyId`, and `UIA_BoundingRectanglePropertyId`.
  - Control Filtering: Uses an in-memory `SentenceTransformers` neural cross-encoder (`ufo/automator/ui_control/control_filter.py:84`) to match planned action descriptions against control names.
- **AstraRun Evaluation & Empirical Findings (Lab I)**:
  - *Empirical Measurement*: In [Lab I](file:///E:/Workspace/Active/AstraRun/tests/benchmarks/phase17/reports/LAB_I_REPORT.md), `FindAllBuildCache` on File Explorer completed in **20.15 ms** vs **42.94 ms** uncached (2.13x speedup).
  - *Empirical Hazard Discovered*: On large application trees (Vivaldi window with 3,263 descendants), full `FindAllBuildCache` blocked for **3,904.72 ms** because Windows COM must build cache entries for every descendant in the target process. Pre-filtering (`IsControlElement`, `IsEnabled`, `not IsOffscreen`) reduced elements to 1,408 and cut latency to **2,045.41 ms**.
  - *Neural Filtering Rejection*: UFO's `SentenceTransformers` control filter requires downloading heavy PyTorch models (~500 MB) and consumes CPU/GPU memory during traversal. AstraRun's retrieval benchmark ([Lab F](file:///E:/Workspace/Active/AstraRun/tests/benchmarks/phase17/reports/LAB_F_REPORT.md)) demonstrated that lexical FTS5 filtering runs in **0.02 ms** with 0 MB model overhead.
  - *AstraRun Decision (`ADAPT`)*: Adopt Win32 handle discovery and `FindAllBuildCache`, but strictly bound traversal with native COM `AndCondition` pre-filters and lexical search, rejecting neural runtime embedding.

### 3.3 Office COM Automation & ROT Handling
- **Upstream Pattern**:
  - `ufo/automator/app_apis/word/wordclient.py` and `basic.py`: Uses `win32com.client.Dispatch()` to acquire running Word/Excel/PowerPoint application instances from the Running Object Table (ROT).
  - Direct Document Manipulation: Uses Word VBA COM models (`doc.Tables.Add(Range, ...)`, `doc.Paragraphs.Add()`) rather than simulating UI clicks.
- **AstraRun Evaluation**:
  - *Strengths*: Extremely fast, highly reliable, completely bypasses visual inspection and UI rendering delays.
  - *Weaknesses*: UFO mixes headless COM manipulation with invasive UI commands (e.g. calling `Range.Select()`, which activates Word and steals window focus).
  - *AstraRun Decision (`REIMPLEMENT_MINIMAL`)*: Reimplement native Python `win32com.client` automation wrappers for Office and Explorer, strictly forbidding any call to `.Select()` or `.Activate()` that steals desktop focus.

### 3.4 Action Safety & Failsafe Architecture
- **Upstream Pattern**:
  - `ufo/automator/ui_control/controller.py:42`: Explicitly sets `pyautogui.FAILSAFE = False`.
  - `ufo/prompts/share/base/app_agent.yaml:36`: Asks the LLM to output `status: "CONFIRM"` when it believes an action is dangerous (e.g., deleting a file).
- **AstraRun Evaluation & Empirical Hazard**:
  - *Critical Vulnerability*: Disabling `FAILSAFE = False` removes the user's ability to abort an errant mouse loop by slamming the cursor to the screen corner.
  - *Security Theater*: An LLM prone to hallucinations or prompt injection cannot be trusted to reliably report `status: "CONFIRM"`.
  - *AstraRun Decision (`REJECT`)*: AstraRun strictly rejects prompt-only confirmation. All actions route through the deterministic, out-of-model **ActionGate** backed by Windows Job Object execution sandboxes ([Lab G](file:///E:/Workspace/Active/AstraRun/tests/benchmarks/phase17/reports/LAB_G_REPORT.md)).

---

## 4. Browser Use Architectural Audit (`UPSTREAM_SOURCE_VERIFIED`)

### 4.1 DOM Tree Serialization & Interactive Pruning
- **Upstream Pattern**:
  - `browser_use/dom/serializer/serializer.py`: Iterates the browser DOM over Chrome DevTools Protocol (CDP) and transforms it into a serialized accessibility tree.
  - **Parent-Containment Pruning** (`_is_contained`, threshold 0.99): If a child element's bounding box is 99% covered by an interactive parent element (e.g. `<button><span class="icon"></span><span class="label">Text</span></button>`), the child elements are pruned from the indexing map.
  - Indexing: Assigns compact integer IDs `[12] <button "Submit"/>` rather than dumping HTML markup.
- **AstraRun Evaluation & Empirical Findings (Lab D & Lab I)**:
  - *Corroboration with Lab D*: In [Lab D](file:///E:/Workspace/Active/AstraRun/tests/benchmarks/phase17/reports/LAB_D_REPORT.md), naive Chromium AXTree serialization produced **-12.38% to +41.54% token overhead** due to verbose metadata wrappers, whereas semantic text compression achieved **84.6% - 93.1% token reduction**.
  - *Empirical Token Measurement in Lab I*: Browser Use's bracketed style `[12] <Button name="..."/>` achieved **76.6% - 78.8% token reduction** relative to UFO² JSON.
  - *AstraRun Decision (`ADOPT`)*: Adopt parent-containment pruning and compact integer IDs in AstraRun's CDP browser subsystem (`@e{id}`).

### 4.2 Async Watchdog Architecture
- **Upstream Pattern**:
  - `browser_use/browser/watchdogs/`: Implements specialized asynchronous watchdog tasks running alongside the agent loop:
    - `dom_watchdog.py`: Monitors DOM mutation events and waits for the page to stabilize before allowing the LLM to inspect state.
    - `popups_watchdog.py`: Automatically detects and suppresses common modal dialogs, cookie banners, and authentication prompts.
    - `downloads_watchdog.py`: Monitors browser download progression and captures destination file paths.
- **AstraRun Evaluation**:
  - *Strengths*: Prevents the agent from acting on a shifting, half-rendered DOM; encapsulates asynchronous environment changes cleanly.
  - *AstraRun Decision (`ADAPT`)*: Adapt watchdog pattern into AstraRun's runtime execution loop:
    1. CDP Navigation / DOM Watchdog (ensuring network idle before screen capture).
    2. Dynamic Job Object Watchdog ([Lab G](file:///E:/Workspace/Active/AstraRun/tests/benchmarks/phase17/reports/LAB_G_REPORT.md): hard execution timeout + 128 MB RAM quota).

### 4.3 Profile Isolation & Chromium Singleton Locks
- **Upstream Pattern**:
  - `browser_use/browser/browser.py`: Configures Playwright / CDP browser instances with dedicated isolated user data directories (`--user-data-dir`).
- **AstraRun Evaluation & Empirical Findings (Lab D)**:
  - *Corroboration with Lab D*: In [Lab D](file:///E:/Workspace/Active/AstraRun/tests/benchmarks/phase17/reports/LAB_D_REPORT.md), attempting to attach CDP to the user's active default Vivaldi profile triggered the Chromium singleton lock (`ProcessSingleton`), proving that **live profile sharing is impossible while the browser is running**.
  - *AstraRun Decision (`ADOPT`)*: AstraRun will use an isolated profile (`AppData/Local/AstraRun/browser_profile`) for automated sessions, or connect strictly via DevTools remote debugging port when explicitly launched in debugging mode.

---

## 5. Local Empirical Synthesis & Cross-Lab Correlation

The table below synthesizes the findings across all Phase 17 empirical benchmark labs (Labs D, E, F, G, and I) and correlates them directly with the upstream mining audit:

| Phase 17 Lab | Tested Mechanism | Local Empirical Result | Upstream Mining Corroboration | Architectural Impact on Architecture B+ |
| :--- | :--- | :--- | :--- | :--- |
| **Lab G (Runtime Sandbox)** | Windows Job Objects, kill-on-close, 128 MB quota, secret scrubber | **5/5 PASS**. Hard timeout killed runaway processes in 1.05s; memory limit triggered Win32 STATUS_QUOTA_EXCEEDED; secret scrubber stripped keys in <0.02 ms. | Proves that OS-level determinism is vastly superior to UFO²'s prompt-only `FAILSAFE = False` safety self-reporting. | Confirms Architecture B+ **ActionGate** and execution runtime must be enforced via Windows Job Objects. |
| **Lab E (WinRT OCR)** | Native Windows WinRT OCR (`Windows.Media.Ocr.dll`) | **2/5 PASS, 3/5 FAIL**. OS DLL exists, but zero Python stdlib projection; `winsdk` not installed; claim of zero-dependency OCR falsified. | UFO² relies on full VLM vision; Browser Use avoids OCR by using DOM accessibility. | Mandates fallback priority: (1) DOM/AXTree ➔ (2) UIA COM ➔ (3) Optional external OCR/VLM only when needed. |
| **Lab F (Retrieval)** | FTS5 Lexical vs Vector Embedding Retrieval | **FTS5: 100% Recall@6 on lexical holdouts**, but collapsed to **20.0% on paraphrases**. Latency: 0.02 ms. | UFO² uses FAISS + SentenceTransformers, incurring heavy memory overhead and high cold-start latency. | Confirms Architecture B+ must use a **Hybrid FTS5 + ONNX Dense** retrieval engine once Stage 2 model is selected. |
| **Lab D (Browser CDP)** | Chromium CDP over WebSockets | **100% SUCCESS**. Port 9222 connects; DOM text extraction achieved **84.6% - 93.1% token compression**; zero-mouse DOM clicks verified. | Perfectly aligns with Browser Use's DOM serializer and proves physical mouse clicking is unnecessary. | Confirms native WebSocket CDP client as AstraRun's primary browser automation surface. |
| **Lab I (UIA Comparison)** | UFO² `FindAllBuildCache` vs Uncached vs AstraRun Compact Serialization | **100% SUCCESS**. `FindAllBuildCache` is 2.1x faster on small trees, but stalls on 3.2k trees unless filtered. **AstraRun Semantic Compact achieves 66.5% token reduction; Minimal achieves 82.2% reduction**. 0 px mouse displacement. | Explains UFO²'s high token consumption (wasting 4.6k tokens on 78 elements) and provides definitive proof of AstraRun's non-intrusive advantage. | Confirms AstraRun UIA inspection format: `@e{id} {type} "{name}" [{bbox}]` with bounded C++ COM filtering. |

---

## 6. Final Architectural Decisions for AstraRun v0.12

Based on the combined evidence from the code-level upstream mining of Microsoft UFO² and Browser Use, alongside the empirical data from Labs D, E, F, G, and I:

1. **Adopt Compact Semantic Serialization as the System Standard**:
   - UFO²'s verbose JSON representation wastes 65% - 82% of LLM context capacity.
   - AstraRun adopts `@e{id} {type} "{name}" [{bbox}]` for UIA elements and browser DOM interactive nodes.
2. **Enforce Programmatic Non-Intrusiveness**:
   - Strictly reject UFO²'s `pyautogui.click()` and `pywinauto.click_input()` mouse cursor hijacking.
   - AstraRun will interact via UIA COM patterns (`IUIAutomationInvokePattern`, `IUIAutomationValuePattern`, `IUIAutomationSelectionItemPattern`) and Chromium CDP DOM events, keeping the physical mouse cursor 100% free for the user.
3. **Bounded C++ COM Traversal**:
   - Use `FindAllBuildCache` to prefetch `ControlType`, `Name`, and `BoundingRectangle` in a single COM call.
   - Enforce an `AndCondition` pre-filter (`IsControlElement`, `IsEnabled`, `not IsOffscreen`) and a maximum depth/node cap to prevent COM stalls on complex applications.
4. **Deterministic Security via Job Objects, NOT Prompt Instructions**:
   - Never rely on LLM self-reported confirmation.
   - All external execution (PowerShell, CLI utilities, sandboxed scripts) is governed by Windows Job Objects with hard memory quotas (128 MB), hard timeouts, and in-memory secret scrubbing.
5. **Phase 17-R Stage 1 Complete**:
   - All zero-download research and empirical validation labs (Labs D, E, F, G, I) are 100% complete with reproducible logs, raw JSON datasets, and reports.
   - Ready for Stage 2 Model Download Authorization.
