# Windows Interaction Surface Research & Tiering Architecture

> **Author**: AstraRun Architecture Team  
> **Status**: APPROVED  
> **Target Version**: v0.11+  
> **Platform**: Windows 11 x64 (Build 26100+)  

---

## 1. Executive Overview

A workstation automation agent operating on Windows 11 cannot rely on a single execution mechanism. Modern desktop applications span multiple legacy and modern presentation frameworks: Win32 (GDI/User32), DirectWrite/Direct2D, WPF, Windows Forms, UWP/WinUI 3, Electron/Chromium, Qt/QML, and Java AWT/Swing.

Attempting to interact with this heterogeneous surface via naive mouse coordinate clicks or indiscriminate shell execution leads to severe fragility, security vulnerabilities, and user disruption.

AstraRun v0.11 establishes an explicit, strictly ordered **Interaction Tier Hierarchy**:

```
┌─────────────────────────────────────────────────────────┐
│ TIER A: Native Win32 / WLAN / Power APIs (Fastest, 100%)│
├─────────────────────────────────────────────────────────┤
│ TIER B: Structured CLI Adapters (Typed, Validated, Safe)│
├─────────────────────────────────────────────────────────┤
│ TIER C: Windows UI Automation (COM UIA, Value/Invoke)   │
├─────────────────────────────────────────────────────────┤
│ TIER D: Windows SendInput & Accelerators (Keyboard/Focus)│
├─────────────────────────────────────────────────────────┤
│ TIER E: Visual Computer Use Fallback (Shadow / Vision)  │
├─────────────────────────────────────────────────────────┤
│ [PROHIBITED] Tier F: Blind Coordinates & Hardcoded Clicks│
└─────────────────────────────────────────────────────────┘
```

---

## 2. Interaction Tier Breakdown

### 2.1 Tier A: Native Win32, WLAN, and Power C-APIs
Whenever Windows exposes an in-process, synchronous C API, Tier A is chosen. Tier A does not spawn child processes, does not interact with presentation trees, and does not require screen visibility.

- **Native Wi-Fi (`wlanapi.dll`)**:
  - `WlanOpenHandle`: Acquires WLAN client session.
  - `WlanEnumInterfaces`: Identifies physical and virtual 802.11 adapters.
  - `WlanGetAvailableNetworkList`: Returns BSSID, SSID, signal quality ($0-100\%$), security algorithms (`DOT11_AUTH_ALGO_RSNA_PSK`, etc.).
  - `WlanConnect` / `WlanDisconnect`: Triggers programmatic connection via configured profiles.
  - *Advantages*: Latency $< 5\,\text{ms}$, zero child process overhead, zero string parsing fragility, zero cleartext command line leakage.
- **Native Power Management (`powrprof.dll` / `kernel32.dll`)**:
  - `GetSystemPowerStatus`: Instant retrieval of AC line status, battery flag, remaining battery percentage, and battery life time.
  - *Advantages*: $< 1\,\text{ms}$ execution, instant verification.
- **Window Management (`user32.dll`)**:
  - `EnumWindows`, `GetWindowTextW`, `GetWindowRect`, `SetWindowPos`, `ShowWindow`, `SetForegroundWindow`, `BringWindowToTop`.
  - Direct atomic window manipulation with zero GUI simulation overhead.

### 2.2 Tier B: Structured System Utility Adapters
When certain Windows administrative operations are only accessible via OS-bundled executables (e.g. detailed battery health analytics, hardware diagnostics), AstraRun wraps them through a dedicated `SystemUtilityAdapter`.

- **Rules for Tier B**:
  - `shell=False` is strictly enforced.
  - Argument lists are hardcoded or strictly validated against immutable regular expressions / schemas.
  - Input and output paths are normalized, resolved, and verified against path traversal attacks.
  - Standard error and standard output are parsed deterministically into structured dataclasses.
- **Example: `powercfg.exe` Battery Report**:
  - Command: `powercfg.exe /batteryreport /output "<normalized_path>"`
  - Execution via `subprocess.run(args, capture_output=True, text=True, check=True)`.
  - Followed immediately by atomic verification that `<normalized_path>` was generated and is valid HTML.

### 2.3 Tier C: Windows UI Automation (UIA)
For modern desktop GUI applications (UWP, WinUI 3, Chromium, Qt, WPF), Windows UI Automation provides programmatic accessibility tree access.

- **Mechanism**:
  - COM-based `IUIAutomation` interface accessed via `ctypes` or `comtypes`.
  - Scoped traversal using `TreeScope_Descendants` and targeted conditions (`AutomationId`, `ClassName`, `ControlType`).
  - Native control patterns:
    - `ValuePattern`: Instant programmatic text injection (`SetValue`) without simulated typing.
    - `InvokePattern`: Deterministic programmatic clicking without moving the mouse pointer.
    - `WindowPattern`: Programmatic minimize/maximize/close.
    - `ScrollItemPattern`: Bringing off-screen controls into viewport.
- **Fail-Safe Fallbacks**:
  - When modern AppX controls (e.g., Windows 11 Notepad `RichEditD2DPT`) do not implement full `ValuePattern`, fall back to focus synchronization (`SetFocus`) followed by Tier D `SendInput`.

### 2.4 Tier D: Native Windows SendInput & Accelerators
When programmatic patterns are unsupported or intentionally disabled by the target application (e.g. game launchers, terminal emulators, custom GDI canvasses), Tier D provides human-input emulation.

- **Mechanism**:
  - User32 `SendInput` API with `INPUT_KEYBOARD` and `INPUT_MOUSE`.
  - Precondition: Verified target window foreground state (`GetForegroundWindow() == target_hwnd`).
  - Dwell times and key release sequencing matching human ergonomics ($10-30\,\text{ms}$ key down).
  - Use of standard Windows accelerator shortcuts (e.g., `Ctrl+S`, `Ctrl+O`, `Alt+F4`) over visual hunting.

### 2.5 Tier E: Visual Computer Use Fallback (Shadow / Experimental)
When accessibility trees are completely missing or uninformative (e.g., complex web canvas, virtual machines, remote desktop viewers), Tier E captures screenshots, performs visual grounding, and predicts target regions.

- **Scope in v0.11**:
  - Runs in shadow/experimental mode.
  - Captures high-DPI desktop screenshots via `PrintWindow` or Desktop Duplication API.
  - Provides bounding box proposals that must be verified by secondary geometry checks.

### 2.6 Tier F: Raw Coordinates & Blind Clicking (PROHIBITED)
- Hardcoded screen coordinates (e.g. `click(x=1045, y=320)`) are **STRICTLY PROHIBITED**.
- Any UI interaction must be anchored to an element identifier, bounding rectangle of an active verified window, or confirmed OCR visual token.

---

## 3. Surface Comparison Matrix

| Property | Tier A (Native Win32/WLAN) | Tier B (Structured CLI) | Tier C (UI Automation) | Tier D (SendInput) | Tier E (Visual Fallback) | Tier F (Raw Coords) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Typical Latency** | $< 5\,\text{ms}$ | $50-500\,\text{ms}$ | $20-150\,\text{ms}$ | $30-250\,\text{ms}$ | $300-1500\,\text{ms}$ | $< 10\,\text{ms}$ |
| **Reliability** | $99.99\%$ | $99.5\%$ | $95.0\%$ | $90.0\%$ | $75.0\%$ | $< 30\%$ |
| **Focus Dependency** | None | None | None (mostly) | Strict Active Window | Strict Active Screen | Strict Monitor Setup |
| **DPI Sensitivity** | None | None | None | Low | High | Fatal |
| **Background Operable**| Yes | Yes | Partial | No | No | No |
| **Verification Ease** | Direct return code | File / Exit code | UIA State property | Element value read | Visual diff / OCR | None |

---

## 4. Architectural Implementation Strategy for v0.11

1. **Capability Schema Encoding**:
   Every capability declared in AstraRun specifies its `interaction_tier`. The Agent Planner prioritizes lower-tier capabilities when constructing execution graphs.
2. **Automatic Degradation**:
   If Tier C UI Automation fails to locate an element within a bounded timeout ($500\,\text{ms}$), the agent execution engine cleanly degrades to Tier D focus-and-input, recording the degradation event in the task telemetry ledger.
3. **Observability**:
   All tier transitions and execution states are rendered in real time on the Live Task HUD V2.
