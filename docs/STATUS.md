# AstraRun v0.10 Status Report

> **Date**: 2026-09-28  
> **Status**: STABLE / VERIFIED / MILESTONE COMPLETE  
> **Milestone**: v0.10 Complete (Application Interaction, UI Automation & Control Grounding)  
> **Prior Milestone**: v0.9 Complete (`fe397e3`)  

---

## 1. What Works Completely

1. **Semantic UI Automation Subsystem (`astrarun.interaction`)**:
   - 11 new workstation capabilities expanding the platform to **70 typed capabilities across 10 categories**.
   - Direct inspection of native desktop application element trees via Microsoft UI Automation (`IUIAutomation`, `IUIAutomationTreeWalker`).
   - Dedicated COM MTA worker thread (`UIAutomationWorker`) isolating COM calls from the PySide6 UI loop.
   - Support for standard accessibility patterns: `InvokePattern`, `ValuePattern`, `TogglePattern`, `SelectionItemPattern`, `ScrollPattern`, and `ExpandCollapsePattern`.

2. **Control Grounding & Origin Window Centrality**:
   - Unambiguous grounding to the pre-captured `origin_window` when control interactions omit explicit target applications.
   - Multi-stage fuzzy and semantic UI element resolver (`UIElementResolver`) with strict precedence: `AutomationId exact > Name exact > ControlType + Name > word boundary > synonym > fuzzy`.
   - Ambiguity detection returning structured clarification cards (`CLARIFY`) when multiple controls share similar scores.

3. **Safe Keystroke Injection & Clipboard Subsystem**:
   - Validated keyboard shortcut parser with strict modifier whitelist (`ctrl`, `shift`, `alt`, `win`).
   - 64-bit SendInput ABI union (`sizeof(INPUT) == 40`) with Unicode keystroke typing.
   - Text entry treated strictly as literal data payload, never evaluated as shell commands.
   - Safe UTF-16LE Windows clipboard access with 64-bit global memory handle alignment.

4. **Destructive Control Gating & Password Privacy Invariant**:
   - Destructive keywords (`delete`, `remove`, `format`, `drop`, `wipe`, `purge`, `reset`, `buy`, `terminate`) gated behind `ActionGate` user confirmation prompts.
   - Safe navigation exceptions (`cancel`, `close`, `dismiss`, `back`, `reset zoom`) remain responsive without false alarms.
   - Password fields (`is_password=True` or `password`/`pin` heuristics) completely masked; values never logged, persisted, or leaked to telemetry or task history.

5. **Strict Coordinate Prohibition Invariant**:
   $$\text{UIA Semantic Pattern} > \text{Win32 Control Message} > \text{Keyboard Shortcut} > \text{Coordinate Interaction (PERMANENTLY PROHIBITED)}$$
   - AstraRun never performs blind coordinate clicks (`pyautogui.click(x, y)`). Unsupported controls return `UNSUPPORTED_UI` or `NOT_FOUND`.

---

## 2. Verification & Benchmark Results

### 2.1 Automated Unit & Integration Tests
- **Status**: **293 / 293 PASSED** in **30.76s**
- **Regressions**: **0**
- Test suites: Config, Routing, UI, Telemetry, Action Gate, Ensemble, NLP Engine, Capabilities, Tasks, Learning, Daily Driver & Window Subsystem, and UI Interaction & Control Grounding (41 new tests).

### 2.2 Standard Benchmark Suites (All 8 Green)

| Benchmark Suite | Case Count | Target Dataset SHA256 | Primary Accuracy Metric | Key Safety Metric | Mean Latency |
|---|---|---|---|---|---|
| **Action Benchmark V1** | 330 | `d73ac62ab9...` | **100.0%** Intent Acc | **0.00%** FER | **0.094 ms** |
| **NLP Benchmark V1 (Test)** | 310 | `41f1ad1b6a...` | **100.0%** Intent Acc | **0.00%** Negated Leakage | **7.275 ms** |
| **Capability Benchmark V1** | 520 | `32ca0f2946...` | **100.0%** Cap Acc | **100.0%** Block Recall | **0.624 ms** |
| **Task Benchmark V1** | 300 | `7979fb8dd6...` | **100.0%** Status Acc | **100.0%** Seq & Persist Acc | **79.583 ms** |
| **Learning Benchmark V1** | 320 | `b935f4ece7...` | **100.0%** Overall Acc | **0.00%** False Activation | **28.320 ms** |
| **Window Benchmark V1** | 330 | `4307223c89...` | **100.0%** Accuracy | **0.00%** Wrong Window Rate | **0.0169 ms** |
| **Interaction Benchmark V1** | 405 | `a249617656...` | **100.0%** Accuracy | **0.00%** WEAR (0 pwd leaks) | **0.0621 ms** |
| **Product Benchmark V2** | 280 | `0e3face273...` | **100.0%** Accuracy | **0.00%** FER (< 3ms Fast Path) | **0.5983 ms** |

**Total Deterministic Benchmark Cases**: **2,795 / 2,795 PASSED (100.0%)** across 8 independent suites.

### 2.3 Live Acceptance Suite (25 / 25 Passed)
- Executed 25 canonical commands with explicit fidelity labels: `SIMULATED`, `LIVE_FIXTURE`, and `LIVE_WORKSTATION`.
- 100.0% pass rate with zero safety violations. Documented in `docs/V0.10_LIVE_ACCEPTANCE.md`.

### 2.4 Resident Dogfooding
- 30-minute continuous interactive session completed with 0 hotkey drops, 0 crashes, 0.0% idle CPU, and stable resident memory footprint at **~69.2 MB**. Documented in `docs/V0.10_DOGFOOD.md`.
