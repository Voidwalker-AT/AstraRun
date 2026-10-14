# AU-1.1A-C — REAL LAUNCHER INGRESS CLOSURE REPORT

**Phase**: AU-1.1A-C (Closure & Freeze)  
**Parent Blueprint**: `ASTRARUN_AU1_ARCHITECTURE_BLUEPRINT.md`  
**Base Commit**: `4a5b409d3a02586f4d3249fc7839601439900de8`  
**Date**: October 14, 2026  
**Status**: COMPLETE / PASS  

---

## 1. Executive Summary & Original AU-1.1A Claim Evaluation

### 1.1 Historical Claim Evaluation: OVERSTATED
In AU-1.1A, development documentation reported that `Launcher`, `CLI`, and `TaskRuntime` were unified behind `AstraApplication.handle_request` and `RequestBoundaryRouter`. However, rigorous forensic inspection revealed that the claim regarding the interactive desktop Launcher was **OVERSTATED**:
1. **Physical Smoke Exercised CLI Only**: The physical smoke evidence archived in `docs/audit/AU_1_1A/` exercised headless CLI and programmatic invocations, rather than an interactive PySide6 desktop Launcher on the active desktop.
2. **Hidden Pre-Boundary Bypass in `launcher.py`**: Prior to AU-1.1A-C, `src/astrarun/ui/launcher.py` contained an unrouted branch:
   ```python
   intent = classify_launcher_input(query)
   if intent == InputIntent.NATURAL_LANGUAGE:
       response = get_conversational_response(query)
       self.show_feedback(response, is_error=False)
       return
   ```
   This branch directly invoked conversational generation, bypassing `RequestEnvelope`, `AstraApplication.handle_request`, `RequestBoundaryRouter`, and the central telemetry bus.
3. **Suggestion Routing Incomplete**: Selecting suggestion entries in the launcher invoked `handle_request` with raw strings, defaulting to `origin=INTERNAL` instead of `RequestOrigin.LAUNCHER`.

### 1.2 Transition: OVERSTATED → FULLY_CLOSED
In AU-1.1A-C, the physical and architectural integrity of the Launcher ingress has been completely rectified:
- The pre-boundary conversational branch was eradicated.
- All typed user input and suggestion selections construct `RequestEnvelope.create(raw_query=..., origin=RequestOrigin.LAUNCHER)`.
- Physical testing was executed against the real interactive PySide6 desktop Launcher attached to the active Windows desktop (`WinSta0\Default`).
- All 6 physical test scenarios (Cases A through F) were validated with pixel-verified desktop screenshots and zero orphaned processes.

---

## 2. Ingress Architecture & Enforcement

### 2.1 Canonical Request Flow
```
Launcher / CLI / TaskRuntime
            ↓
  RequestEnvelope(origin=...)
            ↓
AstraApplication.handle_request
            ↓
RequestBoundaryRouter.classify_ingress
   ├── META_COMMAND (HELP, SETTINGS, GREETING, ACK)
   │         ↓
   │     meta_handler (Inline UI, zero workstation side-effects)
   │
   └── OPERATIONAL_GOAL
             ↓
         [Existing Downstream Execution Paths]
         ├── PURE_QUERY (Math / Calculation)
         ├── AGENT_EXECUTION_ENGINE (Complex goals, e.g., battery report)
         ├── DETERMINISTIC_ROUTER (Fast-path applications, e.g., open calculator)
         └── LEGACY_LAYA_WORKFLOW (Composite requests)
```

### 2.2 Telemetry & Request ID Correlation
A single 12-character hex identifier (`request_id`) is minted at `RequestEnvelope.create()` and strictly correlated across all lifecycle events:
- `REQUEST_INGRESS_CLASSIFIED`: records `request_id`, `origin`, `classification`, `reason`, `confidence`.
- `REQUEST_DOWNSTREAM_SELECTED`: records `request_id`, `origin`, `selected_downstream`.
- `ExecutionResult.request_id`: populated on the returned dataclass and propagated to UI/client callers.

---

## 3. Physical Interactive Desktop Verification

Physical interactive testing was executed via `scripts/physical_launcher_test.py` on Windows 11 with real desktop surface capture:

| Case | Submitted Query | Boundary Classification | Downstream Path | Visible Result / Foreground HWND | Leaked Processes | Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **A** | `"help"` | `META_COMMAND` (`META_HELP`) | `META_HANDLER` | AstraRun Launcher (Feedback: "Available commands...") | 0 | **PASS** |
| **B** | `"hello"` | `META_COMMAND` (`META_GREETING`) | `META_HANDLER` | AstraRun Launcher (Feedback: "Hello! How can I help...") | 0 | **PASS** |
| **C** | `"hello, open calculator"` | `OPERATIONAL_GOAL` (`COMPOSITE_CONTAINS_OPERATIONAL_CLAUSE`) | `LEGACY_LAYA_WORKFLOW` | Calculator (`HWND 132488`, `PID 23140`) | 0 (Cleaned up) | **PASS** |
| **D** | `"calculate 2 + 2"` | `OPERATIONAL_GOAL` (`OPERATIONAL_DEFAULT`) | `PURE_QUERY` | AstraRun Launcher (Feedback: "4") | 0 | **PASS** |
| **E** | `"battery report"` | `OPERATIONAL_GOAL` (`OPERATIONAL_DEFAULT`) | `AGENT_EXECUTION_ENGINE` | AstraRun Launcher (Report text displayed) | 0 | **PASS** |
| **F** | `"open calculator"` | `OPERATIONAL_GOAL` (`OPERATIONAL_DEFAULT`) | `DETERMINISTIC_ROUTER` | Calculator (`HWND 132512`, `PID 4436`) | 0 (Cleaned up) | **PASS** |

### 3.1 Screenshot Evidence Manifest
All 13 captured desktop screenshots are cataloged in `docs/audit/AU_1_1A_C/06_SCREENSHOT_MANIFEST.json` and physically located in `docs/audit/AU_1_1A_C/screenshots/`. Every screenshot was verified for non-blank window content, correct window titles, and accurate foreground window handle (`HWND`) and process ID (`PID`).

---

## 4. Preservation & Invariants Maintained

The following boundaries were strictly respected without premature modification:
- **No AU-1.1B Deletions**: Candidate dead wrappers identified in `ASTRARUN_AU1_ARCHITECTURE_BLUEPRINT.md` remain untouched until AU-1.1B.
- **No AU-1.2 Downstream Redesign**: Existing downstream routing engines, `GoalPlanner`, `AgentExecutionEngine`, `ExecutionBroker`, and `ActionGate` remain in their exact operational states.
- **Production Purity**: All mock/test contamination in `src/astrarun/delegation/provider.py` remains eliminated. Tests explicitly register mocks.
- **Zero Desktop Leaks**: All desktop processes spawned during physical tests (`CalculatorApp.exe`) were verified terminated cleanly via win32 APIs.

---

## 5. Closure Gate Matrix Summary

All 14 closure gate criteria defined in Section 15 of the mandate are evaluated and recorded in `docs/audit/AU_1_1A_C/09_CLOSURE_MATRIX.json`:
1. Every human Launcher request reaches RequestBoundaryRouter: **PASS**
2. No conversational user-text bypass remains before the boundary: **PASS**
3. Suggestion submission cannot bypass the boundary: **PASS**
4. Launcher/CLI/Runtime origins are preserved correctly: **PASS**
5. Request ID is correlated through ingress and downstream telemetry: **PASS**
6. Meta greetings still work: **PASS**
7. Greeting+operation composites are OPERATIONAL: **PASS**
8. Existing downstream execution behavior remains unchanged: **PASS**
9. Actual interactive Launcher physical test passes: **PASS**
10. Screenshots visibly support claimed UI state: **PASS**
11. Calculator physical launch is visible: **PASS**
12. Full regression has 0 failures/errors: **PASS** (1,047 passed, 14 skipped, 0 failed, 0 errors in 670.67s across 1,061 collected tests)
13. Historical AU-1.1A evidence is not rewritten: **PASS**
14. No AU-1.2+ work is performed: **PASS**

---

## 6. Argon Handoff Readiness

With the canonical ingress seam established and verified against real desktop execution, AstraRun is fully prepared for Argon review and transition to **AU-1.1B** (Dead Wrapper Removal).
