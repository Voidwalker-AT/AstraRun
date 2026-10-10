# AstraRun Computer-Use Architecture Audit & F0-17 Forensic Analysis

**Status**: COMPLETED  
**Scope**: Entire AstraRun Computer-Use & Production Routing Subsystem  
**Reference Benchmark**: Microsoft UFO2 (UI-Focused Agent 2.0)  
**Date**: 2026-10-08  

---

## Executive Summary

This architecture audit addresses two interdependent milestones:
1. **Immediate Root-Cause Fix (F0-17)**: Resolving the human-observed production routing failure (`"Blocked: Blocked: Target tool 'unknown' is not registered"` for natural-language prompts like `"can u open calculator"`).
2. **General Computer-Use Architecture Audit**: Auditing AstraRun's existing computer-use, UI automation, and browser capabilities against Microsoft UFO2 principles, eliminating application-specific hacks (Notepad, Calculator, ChatGPT), and establishing a cohesive, provider-independent computer-use subsystem.

---

## 1. Current Computer-Use Architecture Inventory

AstraRun currently has **84 registered capabilities** across several separate subsystems. However, its computer-use logic is fragmented across 4 decoupled directories:

| Subsystem Component | Current File Locations | Responsibilities | Limitations / Gaps |
| :--- | :--- | :--- | :--- |
| **Window Management** | `src/astrarun/windows/controller.py`<br>`src/astrarun/windows/discovery.py`<br>`src/astrarun/windows/resolver.py`<br>`src/astrarun/windows/monitors.py` | Window enumeration (`EnumWindows`), HWND resolution, minimize, maximize, restore, snap, move, tile, close. | Operates on top-level HWNDs only. Does not inspect internal child controls or accessibility trees. |
| **UI Automation (UIA)** | `src/astrarun/interaction/discovery.py`<br>`src/astrarun/interaction/controller.py`<br>`src/astrarun/interaction/service.py` | Microsoft UI Automation (`IUIAutomation`), tree traversal, pattern dispatch (`InvokePattern`, `ValuePattern`, `TogglePattern`, `SelectionItemPattern`). | Tree traversal can be slow if unbounded; lacks bounding-box coordinate mouse click fallback if patterns fail; split from physical input. |
| **Physical Input & Takeover** | `src/astrarun/perception/input.py`<br>`src/astrarun/interaction/keyboard.py` | Win32 `SendInput`, normalized mouse coordinates (0–65535), Unicode keyboard input, global physical takeover detection (`check_user_takeover`). | Disconnected from UI Automation element resolution; lives under `perception/` rather than a unified `interaction/` or `controller/`. |
| **Managed Browser Automation** | `src/astrarun/browser/service.py`<br>`src/astrarun/perception/cdp.py` | Chromium/Edge launch with remote debugging (CDP port 9222), DOM token compression, interactive element extraction. | Separate from desktop UI automation; lacks tab switching and unified session lifecycle management. |
| **Delegation / External AI** | `src/astrarun/delegation/chatgpt_web.py`<br>`src/astrarun/delegation/provider.py` | Advisory consultation with external assistants. | **Architectural defect**: ChatGPT Web hardcodes vendor-specific logic (`has_chatgpt_tab`) instead of operating as a generic provider over standard browser automation. |
| **Visual Perception / Fallback** | `src/astrarun/perception/capture.py`<br>`src/astrarun/perception/cv.py`<br>`src/astrarun/perception/ocr.py`<br>`src/astrarun/perception/vlm.py` | Screen capture, template matching, OCR, local vision model fallback. | Not integrated into a unified `Observe` step before action execution. |
| **Execution Governance** | `src/astrarun/security/execution_broker.py`<br>`src/astrarun/security/action_gate.py`<br>`src/astrarun/tasks/resource_ledger.py` | Choke-point enforcement, privilege gating, user confirmation, resource tracking (PID/HWND lifecycle). | Complete and authoritative, but prior code routed unresolved queries (`tool="unknown"`) directly into the gate. |

---

## 2. Actual Production Call Graph

The end-to-end production pipeline from user input to OS/browser execution operates as follows:

```mermaid
flowchart TD
    User([User Prompt: "can u open calculator"]) --> Entry[AstraLauncher / IPC Pipe / CLI]
    Entry --> App[AstraApplication.handle_request]

    subgraph Tier0_FastPath [Tier 0: Deterministic Router]
        App -->|Query starts with simple verb & <= 3 words| FastPath[DeterministicRouter.route]
        FastPath -->|Hit| FastExec[Direct Tool Proposal]
    end

    subgraph RichPath [Tier 1: Rich Natural Language Pipeline]
        App -->|Conversational / Complex / Polite| LayaA[Laya A Pre-Gate: Intent & Ambiguity]
        LayaA --> Structure[NeuralStructureEngine.parse: spaCy / Fallback]
        Structure --> LayaB[Laya B Verifier: Consistency & Negation]
        LayaB --> Fusion[DecisionFusionEngine.fuse: Synthesizes Plan]
        Fusion --> Compiler[WorkflowCompiler.compile: Maps Clauses to Capabilities]
    end

    subgraph SecurityChokePoint [Authoritative Security Choke-Point]
        FastExec --> Gate[ActionGate.evaluate]
        Compiler --> Gate
        Gate -->|BLOCK| Blocked[Reject Task & Show Reason]
        Gate -->|CONFIRM| Confirm[Prompt User Confirmation Card]
        Gate -->|ALLOW| Broker[ExecutionBroker.execute]
    end

    subgraph ExecutionLayer [OS / Browser Execution]
        Broker --> Ledger[AstraResourceLedger: Record Pre-State]
        Ledger --> Dispatch{Capability Handler}
        Dispatch -->|open_application| AppService[applications.service.open_application]
        Dispatch -->|UI Automation| InterService[interaction.service / controller.py]
        Dispatch -->|Window Control| WinService[windows.controller.WindowController]
        Dispatch -->|Browser| BrowserService[browser.service.BrowserService]
        AppService --> OS[(Windows OS / Win32 / UIA / CDP)]
        InterService --> OS
        WinService --> OS
        BrowserService --> OS
        OS --> PostLedger[AstraResourceLedger: Register Owned PID/HWND]
    end

    subgraph ClosedLoop [Observation & Verification]
        PostLedger --> Obs[MachineObserver: Capture State]
        Obs --> Verifier[StepVerifier / GoalVerifier]
        Verifier -->|Verified| Complete[TaskStatus.COMPLETED]
        Verifier -->|Failed & Retries Left| Replan[AgentExecutionEngine: Bounded Replan]
        Replan --> Broker
    end
```

---

## 3. Application-Specific Logic Audit

We identified several instances of hardcoded application-specific logic that violate generic agent principles:

### A. Windows 11 Tabbed Application Special-Casing
- **Location**: `src/astrarun/applications/service.py:277-285`
- **Code**:
  ```python
  if not owned_res.hwnd and app.lower().replace(".exe", "") == "notepad":
      if "notepad" in w_title.lower():
          logger.info("[TABBED_APP_SEPARATION] Pre-existing Notepad detected; spawning isolated task window via Ctrl+Shift+N.")
  ```
- **Finding**: Hardcodes `"notepad"` specifically. Windows 11 Terminal, Explorer, and other tabbed apps exhibit the exact same multi-tab single-process behavior.
- **Remedy**: Abstract into a generic `TabbedApplicationAdapter` with declarative config (`supports_tabs=True`, `new_window_hotkey="Ctrl+Shift+N"`).

### B. Hardcoded Application Aliases in Resource Ledger
- **Location**: `src/astrarun/tasks/resource_ledger.py:312-316`
- **Code**:
  ```python
  if target_name_lower in ("calc", "calculator"):
      aliases.extend(["calc", "calculator", "calculatorapp"])
  elif target_name_lower == "notepad":
      aliases.extend(["notepad", "text editor"])
  ```
- **Finding**: Ledger hardcodes string aliases for Calculator and Notepad rather than querying `AppDiscoveryCache` or `AliasManager`.
- **Remedy**: Delegate target alias resolution to the unified `EntityResolutionEngine`.

### C. Hardcoded Invariant Recovery in Task Runtime
- **Location**: `src/astrarun/tasks/runtime.py:958-963`
- **Code**:
  ```python
  if invariant.target.lower() in ("notepad", "notepad.exe"):
      res = open_application("notepad")
  elif invariant.target.lower() in ("calc", "calculator", "calc.exe"):
      res = open_application("calculator")
  ```
- **Finding**: Invariant disturbance recovery only knows how to relaunch Notepad and Calculator.
- **Remedy**: Generic recovery: `open_application(invariant.target)` for any application target.

### D. Hardcoded Application List in Structure Engine Regex
- **Location**: `src/astrarun/nlp/structure_engine.py:371, 380`
- **Code**:
  ```python
  (paint|notepad|word|chrome|edge|cmd|terminal|code|vscode|snippingtool|excel|calc|slack|discord|spotify|explorer|firefox|taskmgr)
  ```
- **Finding**: Explicit list of 19 application names hardcoded in regex branches.
- **Remedy**: Generalize regex to match generic application object noun `([a-zA-Z0-9_\-\.]+)` and validate against `AppDiscoveryCache`.

### E. ChatGPT-Specific Delegation Embedded in Web Automation
- **Location**: `src/astrarun/delegation/chatgpt_web.py:23-45`
- **Code**:
  ```python
  class ChatGPTWebDelegate(DelegateProvider):
      def is_available(self):
          if self._browser and hasattr(self._browser, "has_chatgpt_tab"):
              return bool(self._browser.has_chatgpt_tab())
  ```
- **Finding**: Couples generic browser automation to ChatGPT specifically.
- **Remedy**: Transform into a generic `WebAdvisorDelegate` that accepts any web LLM provider URL (`chatgpt.com`, `claude.ai`, `gemini.google.com`, `chat.deepseek.com`) and operates via standard DOM selectors.

---

## 4. Legitimate vs. Unnecessary Application Logic

| Logic Category | Legitimate Application Adapter (Keep & Generalize) | Unnecessary Hack (Eliminate) |
| :--- | :--- | :--- |
| **Launch Binary Discovery** | Querying Start Menu, Registry, and PATH (`AppDiscoveryCache`) to find `calc.exe`, `notepad.exe`, `code.exe`. | Hardcoding `if app == "calc": return "C:\Windows\System32\calc.exe"`. |
| **Window Identity & Grouping** | Reading Process Name + Window Class + UIA Bounding Box to detect whether a window is tabbed or modal. | Hardcoding `if "notepad" in title: press_keys("Ctrl+Shift+N")`. |
| **Control Resolution** | Finding `ControlType.DOCUMENT` or `ControlType.EDIT` via generic UIA search (`resolve_editable_element`). | Searching specifically for `automation_id="NotepadTextBox"`. |
| **External AI Consultation** | A generic browser-based chat automation adapter with configurable URL and DOM input/output selectors. | Dedicated `ChatGPTWebDelegate` checking `has_chatgpt_tab`. |
| **Lifecycle & Termination** | Tracking Astra-created PID/HWND in `AstraResourceLedger` and sending `WM_CLOSE` to owned HWND. | `kill -name calc` closing every calculator on the desktop. |

---

## 5. Comparison with Microsoft UFO2

Microsoft UFO2 is designed for open-ended Windows computer use with large multimodal models (GPT-4V / OmniParser). AstraRun operates under tighter local constraints: **RTX 2050 4GB VRAM**, requiring **zero hallucination**, **deterministic safety gating**, and **fast latency (< 15ms local response)**.

| Architectural Dimension | Microsoft UFO2 | AstraRun Current Architecture | Recommended Unified Direction |
| :--- | :--- | :--- | :--- |
| **Agent Decomposition** | **HostAgent** (global desktop orchestrator) + **AppAgent** (in-app specialist). | Monolithic `AgentExecutionEngine` + flat capability execution in `AstraApplication`. | Adopt HostAgent / AppAgent split conceptually: `DesktopController` (Host) routes to active window; `InAppAgent` (App) executes in-window Observe-Act loops. |
| **Interaction Modality** | **Hybrid GUI/API**: Prefers COM/API when available (Word/Excel COM), falls back to UIA and OmniParser vision. | UI Automation via COM (`comtypes.client`) + Win32 `SendInput`. Vision fallback (`cv.py`, `vlm.py`) exists but is not piped into the main loop. | Maintain Hybrid UIA + SendInput. Use UIA semantic controls first; fall back to coordinate clicks via `element.bounds` or CV template matching. |
| **Perception Mechanism** | **UIA Tree + OmniParser (YOLO/VLM)** for screenshot coordinate grounding. | COM `IUIAutomation` walker + Win32 `EnumWindows`. VLM grounder exists in `perception/vlm.py` (Qwen2-VL / MiniCPM). | On 4GB VRAM, prioritize UIA Accessibility Tree (0 VRAM, < 10ms latency). Use on-demand local VLM only when UIA tree is empty (e.g. Canvas/Game/DirectX). |
| **Execution Safety** | Blacklist system commands, prompt confirmation for critical actions. | Authoritative **ExecutionBroker + ActionGate + TrustKernel + AppContainer Sandbox**. | AstraRun's security is significantly superior to UFO2. Preserve ExecutionBroker and ActionGate as absolute non-bypassable choke points. |
| **Execution Loop** | **Observe -> Think -> Act -> Verify** per atomic UI step. | `AstraApplication` is single-shot per tool; `AgentExecutionEngine` has closed-loop but replanning could loop infinitely. | Unify into bounded `Observe -> Find -> Act -> Verify` loop with max 3 replans. |
| **Cross-App Orchestration** | Supported via HostAgent switching between AppAgents. | Partially supported via multi-clause DAG plans in `GoalPlanner`. | Allow AppAgent to yield control back to HostAgent when window focus changes or task switches applications. |
| **Hardware Footprint** | Cloud API (OpenAI API / Azure OpenAI) or 16GB+ VRAM local. | Local RTX 2050 (4GB VRAM), quantized Laya (ONNX), Spark (GGUF), Qwen (GGUF). | Keep local footprint strictly <= 3.5GB VRAM. Fast-path & UIA must require 0 VRAM. |

---

## 6. Proposed Unified ComputerUse Subsystem

We propose consolidating AstraRun's computer-use capabilities into a coherent, layered subsystem without rewriting existing working infrastructure:

```
src/astrarun/computer_use/
├── __init__.py
├── controller.py           # DesktopController: Top-level coordinator (launches, focuses, tracks active window)
├── uia.py                  # UIAutomation: Clean wrapper around existing interaction/discovery & controller
├── input.py                # InputController: Unified SendInput (Mouse, Keyboard, Physical Takeover guard)
├── browser.py              # BrowserController: Provider-independent CDP / DOM automation
├── perception.py           # VisualPerception: Screenshot capture, bounding box calculator, CV fallback
├── adapters/               # ApplicationAdapters: Declarative adapters (e.g. TabbedAppAdapter, EditorAdapter)
│   ├── base.py
│   └── tabbed.py
└── lifecycle.py            # ResourceLifecycle: AstraResourceLedger wrapper for PID/HWND tracking
```

### Module Responsibilities (Reusing Existing Code):
1. **`DesktopController`**: Reuses `src/astrarun/windows/controller.py` + `applications/service.py`. Manages top-level desktop state, active window focus, and process spawning.
2. **`UIAutomation`**: Reuses `src/astrarun/interaction/discovery.py` + `interaction/controller.py`. Traverses UIA trees, searches by name/automation_id/control_type, invokes patterns.
3. **`InputController`**: Unifies `src/astrarun/perception/input.py` and `src/astrarun/interaction/keyboard.py`. Dispatches mouse moves, clicks, scroll, and text typing, respecting `check_user_takeover()`.
4. **`BrowserController`**: Reuses `src/astrarun/browser/service.py`. Handles Edge/Chrome launch, DOM parsing, and element interaction without provider-specific hardcoding.
5. **`VisualPerception`**: Reuses `src/astrarun/perception/capture.py`, `cv.py`, and `ocr.py`. Provides visual fallback when UIA elements cannot be resolved.
6. **`ResourceLifecycle`**: Reuses `src/astrarun/tasks/resource_ledger.py`. Ensures strict Astra-ownership and cleanup of created resources.

---

## 7. F0-17 Root-Cause Findings & Targeted Test Evidence

### Root-Cause Chain for `"Blocked: Blocked: Target tool 'unknown' is not registered"`:
1. **Packaging Defect**: In `packaging/AstraRun.spec`, `en_core_web_sm` model data and submodules were omitted. In the frozen executable, `NeuralStructureEngine.get_nlp()` failed with `[E050] Can't find model 'en_core_web_sm'`, forcing execution into `_parse_fallback`.
2. **Action Pattern Mapping Defect**: In `src/astrarun/nlp/clause_decomposer.py:73`, generic verbs `open|launch|start|run|bring up` were mapped to `"open_project"` instead of `"open_app"`.
3. **Missing Politeness Stripping**: In `clause_decomposer.py`, conversational framing like `"can u open calculator"` was passed into clause evaluation without stripping polite prefixes (`"can u "`), preventing pattern matching.
4. **Empty Proposal Step Routing Defect**: In `src/astrarun/app.py:976`, when `proposal.steps` was empty, `tool_name` defaulted to `"unknown"`, which was submitted to `ActionGate.evaluate()`. `ActionGate` saw unregistered tool `"unknown"` and blocked it.
5. **String Duplication**: In `app.py:998`, the error message was formatted as `f"Blocked: {gate_decision.reason}"`, and `launcher.py:882` prefixed another `"Blocked: "`, producing the double `"Blocked: Blocked:"`.

### Fixes Applied:
- `packaging/AstraRun.spec`: Added `collect_data_files("spacy")`, `collect_data_files("en_core_web_sm")`, `collect_submodules("spacy")`, `collect_submodules("en_core_web_sm")`.
- `config/nlp_lexicon.json`: Removed bare `"open"` from `open_project` synonyms; added common conversational prefixes (`"can u"`, `"could u"`, `"would u"`, `"will you"`, `"plz"`).
- `src/astrarun/nlp/clause_decomposer.py`: Mapped `open|launch|start|run|bring up` to `"open_app"`; integrated `strip_politeness` with built-in prefixes.
- `src/astrarun/nlp/structure_engine.py`: Added regex entity extraction fallback for `open_app` in both `_parse_with_spacy` and `_parse_fallback`.
- `src/astrarun/workflows/compiler.py`: Enhanced regex in `open_app` to handle optional articles (`"the"`, `"a"`).
- `src/astrarun/app.py`: Replaced `tool_name = "unknown"` with graceful unsupported command reporting; fixed duplicate `"Blocked:"` prefix.
- `src/astrarun/ui/launcher.py`: Guarded against duplicate `"Blocked:"` prefix in `show_feedback`.

### Targeted Test Verification (`tests/test_f0_17_production_routing.py`):
```
tests/test_f0_17_production_routing.py::test_positive_app_launch_spacy[can u open calculator-calculator] PASSED
tests/test_f0_17_production_routing.py::test_positive_app_launch_spacy[open calculator-calculator] PASSED
tests/test_f0_17_production_routing.py::test_positive_app_launch_spacy[could you open the calculator-calculator] PASSED
tests/test_f0_17_production_routing.py::test_positive_app_launch_spacy[launch calc-calc] PASSED
tests/test_f0_17_production_routing.py::test_positive_app_launch_spacy[start calculator-calculator] PASSED
tests/test_f0_17_production_routing.py::test_positive_app_launch_spacy[please bring up calculator-calculator] PASSED
tests/test_f0_17_production_routing.py::test_positive_app_launch_spacy[open notepad-notepad] PASSED
tests/test_f0_17_production_routing.py::test_positive_app_launch_spacy[can you launch notepad-notepad] PASSED
tests/test_f0_17_production_routing.py::test_positive_app_launch_spacy[start paint-paint] PASSED
tests/test_f0_17_production_routing.py::test_positive_app_launch_spacy[open settings-settings] PASSED
tests/test_f0_17_production_routing.py::test_positive_app_launch_fallback[...] (10 tests) PASSED
tests/test_f0_17_production_routing.py::test_negative_queries_do_not_launch_app[...] (4 tests) PASSED
tests/test_f0_17_production_routing.py::test_negation_safety_dont_open_calculator PASSED
tests/test_f0_17_production_routing.py::test_end_to_end_app_handle_request_dry_run PASSED

============================= 26 passed in 27.60s =============================
```

---

## 8. Remaining Architectural Gaps & Action Items

1. **Replan Bounded Ceiling in Agent Engine**:
   - `AgentExecutionEngine._attempt_replan` must enforce `MAX_REPLANS = 3` to prevent infinite replan loops during failed tool verifications.
2. **Coordinate Click Fallback in UI Controller**:
   - In `interaction/controller.py`, if `InvokePattern`, `TogglePattern`, and `BM_CLICK` all fail, invoke `PhysicalInputController.click_at()` on the center coordinates of `element.bounds`.
3. **Generalize Tabbed Application Handling**:
   - Replace `app == "notepad"` in `applications/service.py` with generic declarative configuration.
4. **Generalize External AI Delegation**:
   - Refactor `chatgpt_web.py` into a generic browser-based advisor adapter that takes target URLs and selector profiles from config.
