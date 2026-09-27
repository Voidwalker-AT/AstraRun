# Application Capabilities — AstraRun v0.7

> **Scope**: Desktop application discovery, lifecycle, focus, and graceful termination  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. Subsystem Architecture

The Application Capability Subsystem (`src/astrarun/applications/service.py`) provides typed operations for interacting with desktop applications installed on the Windows workstation.

### Key Capabilities:
- `list_running_applications`: Enumerate user-facing desktop applications.
- `is_application_running`: Check if a specific application has active windows.
- `find_application`: Resolve application binaries from Start Menu shortcuts and App Paths.
- `open_application`: Launch an application executable.
- `focus_application`: Bring an open application window to the foreground.
- `close_application`: Gracefully request an application to close via `WM_CLOSE`.

---

## 2. Desktop Application Discovery: Windows vs Processes

### 2.1 The Headless Process Problem
A fundamental challenge in workstation intelligence is that traditional process enumeration (`psutil.process_iter()`) lists hundreds of background system services, daemon agents, worker threads, and headless utilities (e.g. `svchost.exe`, `RuntimeBroker.exe`, `conhost.exe`). If a user asks *"what applications are running?"*, presenting 200 background system processes is unhelpful and confusing.

### 2.2 Win32 Top-Level Window Filtering
AstraRun solves this by querying visible top-level desktop windows via native Win32 APIs:
- `user32.EnumWindows`: Enumerate all top-level HWNDs.
- `user32.IsWindowVisible`: Verify the window is actually visible to the user.
- `user32.GetWindowTextLengthW`: Verify the window has a non-empty title.
- Window Bounds Check (`user32.GetWindowRect`): Exclude zero-width or 1x1 invisible helper windows.
- Process Attribute Mapping: Correlate window HWND to process PID and executable name via `GetWindowThreadProcessId`.

This produces an accurate list of true interactive desktop applications (e.g., *Visual Studio Code*, *Google Chrome*, *Slack*, *Windows Terminal*, *Notepad*).

---

## 3. Window Focusing and Disambiguation

When executing `focus_application(app="code")`:
1. The subsystem queries open windows whose titles or owning process names match the query.
2. If exactly one matching window is found:
   - Restores the window if minimized (`ShowWindow(hwnd, SW_RESTORE)`).
   - Sets foreground focus (`SetForegroundWindow(hwnd)`).
   - Returns `CapabilityResult.ok(message="Focused window ...")`.
3. If multiple windows match (e.g. multiple VS Code project windows or browser windows):
   - AstraRun does **not** make an arbitrary guess.
   - It returns `CapabilityResult.fail(error_code=AMBIGUOUS, data={"candidates": [...]})`.
   - The UI automatically presents a disambiguation card (`DisambiguationCard` / `ListResultCard`) allowing the user to select the intended window.

---

## 4. Graceful Termination vs Force-Kill (`WM_CLOSE`)

### 4.1 Invariant: No Force-Kill on Applications
The `close_application` capability is strictly non-destructive. It does **not** call `TerminateProcess` or `taskkill /F`.

### 4.2 The `WM_CLOSE` Protocol
`close_application` sends a native Windows message:
```python
user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE = 0x0010
```
**Benefits**:
- If the application has unsaved files (e.g. Notepad, Word, VS Code), it displays its native *"Do you want to save changes?"* dialog.
- The application cleanly runs its internal shutdown routines, persists state, and closes child threads.
- If multiple windows are open, AstraRun returns `AMBIGUOUS` with candidate window titles rather than closing the wrong window.

If a developer explicitly intends to abort an unresponsive or runaway background process, they must use `terminate_process`, which is classified as `HIGH` risk and strictly gated by confirmation.
