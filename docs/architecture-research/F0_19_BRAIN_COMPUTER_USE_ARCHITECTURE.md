# AstraRun 1.0 — Brain & Universal Computer-Use Architecture Specification

**Phase**: F0-19 Architectural Ownership Refactor  
**Platform**: Windows 11 AMD64  
**Hardware Envelope**: Intel i5-12450H, 16 GB RAM, NVIDIA RTX 2050 (4 GB VRAM)  
**Status**: COMPLETE (Internal Verification Passed)  

---

## 1. Architectural Philosophy & Dual-Domain Separation

To achieve a true general-purpose, local-first Windows computer-use agent without application-specific hardcoding, AstraRun 1.0 enforces a strict dual-domain ownership contract:

```
+-----------------------------------------------------------------------------------+
|                                 USER INTERFACE                                    |
|                (Launcher Command Bar, Task Center, Tray, Native HUD)              |
+-----------------------------------------------------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                                   THE BRAIN                                       |
|  - Decision (Semantic Intent Classification, Dynamic Entity Resolution)          |
|  - Reasoning (GoalPlanner DAG Compilation, ExecutionEngine, GoalVerifier)        |
|  - Memory (Working Memory, Semantic Facts, Conversation Context)                  |
|  - Vision (Visual Grounding, Layout Comprehension, Spatial Anchoring)             |
|  * INVARIANT: Brain contains ZERO OS automation primitives (no ctypes, no Win32)  |
+-----------------------------------------------------------------------------------+
                                          |
                        Proposes Capability / DAG Steps
                                          v
+-----------------------------------------------------------------------------------+
|                              SECURITY AUTHORITY                                   |
|               (ExecutionBroker -> ActionGate -> TrustKernel)                      |
|  * INVARIANT: Models & Brain propose; Security Authorizes; ComputerUse Executes   |
+-----------------------------------------------------------------------------------+
                                          |
                             Authorized Action Request
                                          v
+-----------------------------------------------------------------------------------+
|                                 COMPUTER USE                                      |
|  - Controller (Universal Observe-Act-Verify-Recover Lifecycle)                    |
|  - Desktop (Application Launch, Window Focus, F0-15 AstraResourceLedger)         |
|  - UI Automation (Accessibility Tree, Control Patterns: Value, Invoke, Toggle)   |
|  - Browser (CDP Sessions, Tab Lifecycle, DOM Navigation)                          |
|  - Input (Physical Keyboard/Mouse Injection, User Takeover Guard)                 |
|  - Perception (Desktop Pixel Capture, Bounding Rectangles, OCR)                   |
|  - Session (ApplicationSession Lifecycle State & Heartbeat)                       |
|  * INVARIANT: ComputerUse contains ZERO semantic decision-making logic            |
+-----------------------------------------------------------------------------------+
```

---

## 2. Domain Responsibilities & Boundaries

### 2.1 The Brain Domain (`src/astrarun/brain/`)

1. **`brain.decision`**:
   - `IntentClassifier`: Classifies queries into `CONVERSATIONAL`, `QUESTION`, `DIRECT_ACTION`, `COMPOSITE_GOAL`, `CLARIFICATION_REQUIRED`, or `SECURITY_REJECTION`.
   - `SemanticEntityResolver`: Multi-stage candidate resolution (politeness stripping, exact cache lookup, multi-attribute search indexing, maintenance quarantine, canonical deduplication).
2. **`brain.reasoning`**:
   - `GoalPlanner`: Compiles goals into dependency-wired execution DAGs with dynamic dataflow parameter binding.
   - `AgentExecutionEngine`: Closed-loop orchestration (`ACT -> OBSERVE -> VERIFY -> REPLAN`).
   - `GoalVerifier`: Ground-truth empirical side-effect verification (file existence, non-empty bytes, window state).
3. **`brain.memory`**:
   - Unified working memory and persistent semantic facts.
4. **`brain.vision`**:
   - Visual grounding and spatial matching of descriptions to accessible UI hierarchies.

### 2.2 The ComputerUse Domain (`src/astrarun/computer_use/`)

1. **`computer_use.controller` (`ComputerUseController`)**:
   - Unified `observe()`: Captures window title, HWND, interactable element tree, browser tabs, and human takeover flag.
   - Unified `find_element()`: Searches accessible controls by Name, AutomationId, or ControlType.
   - Unified `interact()`: Dispatches pattern invocations (Value, Invoke) with physical fallback.
   - Unified `verify()`: Verifies environmental predicates (window visible, process running).
   - Unified `recover()`: Bounded recovery actions (`retry`, `reobserve`, `dismiss_dialog`, `fail`).
2. **`computer_use.desktop`**:
   - Application launch and window management under F0-15 resource ledger tracking.
3. **`computer_use.ui`**:
   - Direct Windows UI Automation accessibility tree walker.
4. **`computer_use.browser`**:
   - Chrome DevTools Protocol browser automation.
5. **`computer_use.input`**:
   - Physical mouse/keyboard driver with mandatory `"Do Not Fight The User"` takeover guard.
6. **`computer_use.session`**:
   - `ApplicationSession` abstraction tracking process lifecycle, window HWND, and task scope.

---

## 3. Closed-Loop Execution: Compound Goals

For a compound multi-step request such as:
`"open notepad and type hello and save it to desktop and name it test.txt"`

The execution trace follows an authoritative closed loop:
1. **Brain / Intent**: Classifies as `COMPOSITE_GOAL`.
2. **Brain / GoalPlanner**:
   - Decomposes clauses:
     - Clause 1: `open notepad` -> `open_application(app='notepad')`
     - Clause 2: `type hello` -> `type_into_window(text='hello', app_name='notepad')`
     - Clause 3: `save it to desktop and name it test.txt` -> `save_text_file(path='C:\Users\hp\Desktop\test.txt', text='hello')`
   - Dynamically wires OutputReferences and execution dependencies: `step_1 -> step_2 -> step_3`.
3. **Security Authority**:
   - `ExecutionBroker` verifies each step against `ActionGate`.
   - `PathPolicy` validates that `Desktop` is within authorized user workstation boundaries.
4. **ComputerUse / Execution**:
   - Step 1 launches Notepad; records PID and HWND in `AstraResourceLedger`.
   - Step 2 verifies window focus; types `"hello"`.
   - Step 3 writes `"hello"` to destination `C:\Users\hp\Desktop\test.txt`.
5. **Brain / GoalVerifier**:
   - Verifies empirical ground truth: file `C:\Users\hp\Desktop\test.txt` exists and is non-empty.
6. **Task Completion**:
   - Task completes with verified status.
