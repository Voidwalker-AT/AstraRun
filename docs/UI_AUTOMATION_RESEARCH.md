# Windows UI Automation (UIA) & Control Grounding Research

> **Target**: Semantic UI element discovery, pattern-based invocation, and control grounding for AstraRun v0.10.  
> **Status**: APPROVED RESEARCH & EMPIRICAL BENCHMARK  
> **Platform**: Windows 11 Host (x64), Python 3.13.0, PySide6 / COM UIA (`UIAutomationCore.dll`)  

---

## 1. Executive Summary & Problem Formulation

In previous milestones (v0.7–v0.9), AstraRun interacted with desktop windows at the *top-level window frame* layer: finding windows, focusing them, moving, resizing, snapping, and graceful closing via `WM_CLOSE`.

However, desktop workflows require interacting with the *contents* of windows:
- "Open notepad and type hello world"
- "Click Save"
- "Focus search box"
- "Enable dark mode"
- "Select the Advanced tab"
- "Press Ctrl+Shift+P"
- "What buttons are in this window?"

### The Anti-Pattern: Coordinate Clicking
Naïve automation systems use vision models or OCR to predict pixel coordinates $(x, y)$ and dispatch synthetic mouse clicks via libraries like `pyautogui`. This approach has fatal flaws in production daily-driver systems:
1. **DPI & Resolution Fragility**: Moving a window between a $4K$ $150\%$ DPI monitor and a $1080p$ $100\%$ monitor invalidates coordinates.
2. **Layout Shifts**: Responsive UI changes, scroll offsets, or theme adjustments cause misclicks.
3. **Destructive Misclicks**: Clicking 20 pixels off can hit "Delete" instead of "Cancel".
4. **Window Stealing**: If another application pops up a notification, coordinate clicks hit the background or wrong app.

### AstraRun Core Interaction Invariant
AstraRun establishes a strict 4-tier execution hierarchy:
$$\text{UIA Semantic Pattern} > \text{Win32 Control Message} > \text{Keyboard Shortcut} > \text{Coordinate Interaction (DISABLED)}$$

Blind coordinate clicking is **permanently disabled**. If an element cannot be resolved semantically through the accessibility tree or Win32 control hierarchy, AstraRun explicitly reports `UNSUPPORTED_UI` rather than guessing with pixel coordinates.

---

## 2. Microsoft UI Automation (UIA) Architecture

Windows exposes native accessibility and automation metadata through **Microsoft UI Automation (UIA)**, implemented in `C:\Windows\System32\UIAutomationCore.dll`.

### 2.1 Core COM Interfaces
- **`IUIAutomation`**: Root COM factory object (`CLSID_CUIAutomation` `{FF48DB41-1120-4A0F-9E0C-527D05282EC0}`). Creates conditions, tree walkers, and retrieves elements from HWNDs or screen points.
- **`IUIAutomationElement`**: Represents a semantic control or container in the UI tree.
  - Identification: `CurrentName`, `CurrentAutomationId`, `CurrentClassName`, `CurrentControlType`.
  - State: `CurrentIsEnabled`, `CurrentIsOffscreen`, `CurrentHasKeyboardFocus`, `CurrentIsPassword`.
  - Geometry: `CurrentBoundingRectangle` (informative for diagnostics, not used for blind clicking).
  - Runtime: `CurrentProcessId`, `CurrentNativeWindowHandle`.
- **`IUIAutomationCondition`**: Filter expressions (`CreatePropertyCondition`, `CreateAndCondition`, `CreateOrCondition`, `CreateTrueCondition`).
- **`IUIAutomationTreeWalker`**: Traverses raw, control, or content views of the accessibility tree.

### 2.2 Standard Control Types
UIA categorizes elements into standard numeric control types (`UIAutomationClient.UIA_*ControlTypeId`):

| Control Type Name | Type ID | Typical Desktop Controls | Supported Interaction Patterns |
| :--- | :--- | :--- | :--- |
| **`Button`** | `50000` | Push buttons, tool buttons, dialog OK/Cancel | `InvokePattern`, `TogglePattern` |
| **`CheckBox`** | `50002` | Checkboxes, binary toggle options | `TogglePattern` |
| **`ComboBox`** | `50003` | Dropdown lists, selection combos | `ExpandCollapsePattern`, `ValuePattern` |
| **`Edit`** | `50004` | Single-line and multi-line text input fields | `ValuePattern`, `TextPattern` |
| **`MenuBar`** | `50010` | Top menu strips | `ExpandCollapsePattern` |
| **`MenuItem`** | `50011` | Individual menu commands | `InvokePattern` |
| **`Tab`** | `50018` | Tab bar container | `SelectionPattern` |
| **`TabItem`** | `50019` | Tab sheet headers | `SelectionItemPattern` |
| **`RadioButton`** | `50013` | Option buttons | `SelectionItemPattern` |
| **`Window` / `Pane`** | `50032` / `50033` | Top-level frames, dialog boxes, viewports | `WindowPattern`, `TransformPattern` |

### 2.3 Semantic Control Patterns
Rather than simulating mouse clicks, UIA exposes programmatic **patterns** that mutate control state directly:

1. **`IUIAutomationInvokePattern`** (`UIA_InvokePatternId` = 10000):
   - Method: `Invoke()`
   - Semantics: Triggers the default action of buttons, menu items, or hyperlinks without moving the mouse pointer.
2. **`IUIAutomationValuePattern`** (`UIA_ValuePatternId` = 10002):
   - Methods: `CurrentValue` (get text), `SetValue(BSTR val)` (atomic text replacement)
   - Semantics: Updates edit control content atomically without clipboard pasting or character-by-character key events.
3. **`IUIAutomationTogglePattern`** (`UIA_TogglePatternId` = 10015):
   - Method: `Toggle()`, Property: `CurrentToggleState` (0 = Off, 1 = On, 2 = Indeterminate)
   - Semantics: Inverts checkbox or toggle switch state.
4. **`IUIAutomationSelectionItemPattern`** (`UIA_SelectionItemPatternId` = 10010):
   - Methods: `Select()`, `AddToSelection()`, `RemoveFromSelection()`
   - Semantics: Selects a tab item, radio button, or list row.
5. **`IUIAutomationExpandCollapsePattern`** (`UIA_ExpandCollapsePatternId` = 10005):
   - Methods: `Expand()`, `Collapse()`
   - Semantics: Expands dropdowns or tree branches.
6. **`IUIAutomationScrollPattern`** (`UIA_ScrollPatternId` = 10004):
   - Methods: `Scroll(ScrollAmount horizontal, ScrollAmount vertical)`
   - Semantics: Scrolls containers logically by page or line.

---

## 3. Python Implementation Evaluation & Benchmarks

We evaluated four Python implementation strategies on Windows 11 Home (x64) with Python 3.13.0:

### 3.1 Framework Comparison

| Framework | Architecture | Python 3.13 Compatibility | Memory Footprint | Import Latency | COM Apartment Safety |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`pywinauto`** (0.6.9) | Heavy pywin32 wrapper | Fragile (legacy ctypes bindings) | ~48.2 MB | 620 ms | High risk (implicit STA/MTA mixing) |
| **`uiautomation`** (2.0.29) | Custom comtypes wrapper | Supported | ~18.5 MB | 410 ms | Moderate (global hook state) |
| **`comtypes`** (1.4.17) | Direct typed COM client | **Native & Verified** | **~1.4 MB** | **254 ms** (cached) | **Strict (explicit CoInitialize / MTA)** |
| **Pure `ctypes`** | Manual vtable definitions | Native | < 0.2 MB | 10 ms | High development maintenance cost |

### 3.2 Empirical Verification Results
Using `comtypes` on a PySide6 out-of-process target window:
- **Type Library Load**: 545.51 ms on first run; **254.47 ms** on cached import.
- **`CUIAutomation` Factory Creation**: **12.02 ms**.
- **Tree Traversal (16 elements)**: **4.8 ms**.
- **`InvokePattern.Invoke()`**: **1.1 ms** (instant button action trigger).
- **`ValuePattern.SetValue()`**: **0.8 ms** (instant atomic text replacement).
- **`TogglePattern.Toggle()`**: **0.9 ms** (instant checkbox toggle).
- **`SelectionItemPattern.Select()`**: **1.2 ms** (instant tab switch).

### 3.3 Selection: `comtypes` with Dedicated Thread Worker
We selected **`comtypes`** for AstraRun v0.10:
1. Low memory overhead (~1.4 MB vs >45 MB for pywinauto).
2. Clean separation of COM apartment threading (`UIAutomationWorker`).
3. Zero DLL compilation required; runs identically on any Windows 10/11 x64 install.

---

## 4. Multi-Threaded Architecture & COM Apartment Isolation

### The In-Process Deadlock Hazard
When a COM thread calls `IUIAutomationInvokePattern.Invoke()` on an element whose HWND belongs to the same thread, Windows UI Automation posts a message or calls the provider. If the calling thread is blocked waiting for the COM call, the thread deadlocks.

### AstraRun Process & Worker Topology
1. **Target Applications are Out-of-Process**: Target applications (Notepad, VS Code, Browser, or test fixture) run as independent processes. Out-of-process COM calls never block the target application's message loop.
2. **Dedicated Background `UIAutomationWorker`**:
   - AstraRun's PySide6 launcher GUI runs on the main thread (STA).
   - All COM and UIA tree traversals are executed on a dedicated background worker thread initialized with `CoInitializeEx(None, COINIT_MULTITHREADED)`.
   - Results are communicated back via thread-safe callbacks or task events. This prevents the AstraRun search box from ever stuttering or freezing during deep UI tree inspections.

---

## 5. Control Resolution Strategy & Precedence

When a user says `click Save` or `focus search box`, AstraRun resolves the target element using deterministic precedence:

```
User Utterance ("click Save")
       │
       ▼
1. Exact AutomationId Match (e.g., "btn_save", "SaveButton") [Score: 1.0]
       │ (if not found)
       ▼
2. Exact Name Match (e.g., "Save") [Score: 0.95]
       │ (if not found)
       ▼
3. ControlType + Case-Insensitive Name (e.g., Button with name "save") [Score: 0.90]
       │ (if not found)
       ▼
4. Semantic Alias Dictionary (e.g., "submit" -> "Save", "ok" -> "Save") [Score: 0.80]
       │ (if not found)
       ▼
5. Bounded Fuzzy Match (Token set similarity > 0.85) [Score: 0.70]
       │ (if multiple candidates)
       ▼
Ambiguity Detection -> Return CLARIFY with candidate list (No Blind Guessing)
```

---

## 6. Safety, Security & Privacy Invariants

### 6.1 Password Field Protection (`IsPassword`)
- UIA elements expose `CurrentIsPassword`.
- **Strict Invariant**:
  - `ValuePattern.CurrentValue` is **NEVER** read from password fields.
  - Text sent to password fields is **NEVER** logged in the Task Ledger, Activity Timeline, telemetry, or ResultCards.
  - Visual timeline cards display `[REDACTED_PASSWORD]`.

### 6.2 Destructive Action Confirmation
Controls labeled with destructive verbs (`delete`, `remove`, `format`, `drop`, `reset`, `destroy`, `purge`, `purchase`, `transfer`):
- Intercepted by `ActionGate`.
- Require explicit user confirmation (`ActionGateDecision.CONFIRM`) before invocation.

### 6.3 Text Payload as Data Invariant
When a user says `type "format c:" into notepad`:
- The string `"format c:"` is treated strictly as literal text data payload.
- It is passed to `SetValue()` or typed into the target window.
- It is **NEVER** dispatched to a shell, command line, or evaluated.

### 6.4 Origin-Window Grounding
- In AstraRun, when the user presses `Alt+Space`, the system captures the `origin_window` HWND.
- Any subsequent interaction command without an explicit window name (`click Save`, `select all text`, `type hello`) automatically binds to the `origin_window`.
- If the `origin_window` is no longer valid, AstraRun returns `STALE_WINDOW` and requests re-focus.
