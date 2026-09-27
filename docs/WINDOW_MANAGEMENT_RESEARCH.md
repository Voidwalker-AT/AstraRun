# Windows Window Management & Desktop Control Research

> **Target**: Native Win32 window discovery, monitor enumeration, geometry control, and DPI handling for AstraRun v0.9.  
> **Status**: APPROVED RESEARCH  
> **Platform**: Windows 11 Host (x64), PySide6 / Win32 `ctypes`  

---

## 1. Win32 API Primitives & Calling Conventions

AstraRun manages desktop windows via direct Win32 API calls (`ctypes.windll.user32`, `ctypes.windll.dwmapi`, and `ctypes.windll.shcore`) without external heavyweight automation frameworks (e.g., PyAutoGUI, UIAutomation).

### 1.1 Window Enumeration & Visibility
1. **`EnumWindows(WNDENUMPROC lpEnumFunc, LPARAM lParam)`**:
   - Enumerates all top-level windows on the desktop.
   - Must be filtered carefully to exclude non-interactive, tool, or background helper windows.
2. **Filtering Rules**:
   - `IsWindowVisible(hwnd)`: Excludes hidden background windows.
   - `GetWindowTextLengthW(hwnd) > 0`: Excludes empty-title helper windows.
   - `GetWindowRect(hwnd, &rect)`: Excludes degenerate windows with width or height $\le 50$ px.
   - **DWM Cloaked Windows**: Windows 10/11 UWP apps and virtual desktop background windows remain "visible" according to `IsWindowVisible`, but are cloaked.
     ```python
     cloaked = ctypes.c_int(0)
     dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) # DWMWA_CLOAKED = 14
     if cloaked.value != 0:
         return False # Cloaked window
     ```
   - **Extended Window Styles**: Exclude `WS_EX_TOOLWINDOW` unless specifically requested.

### 1.2 Window State Mutation
1. **Focus / Foreground Activation**:
   - Direct `SetForegroundWindow(hwnd)` can be denied by Windows if the calling process does not currently own foreground focus (`LockSetForegroundWindow`).
   - Solution: Attach thread input (`AttachThreadInput`) between the calling thread and the target thread, call `BringWindowToTop(hwnd)`, `ShowWindow(hwnd, SW_RESTORE)` if minimized, and `SetForegroundWindow(hwnd)`.
2. **Minimize / Maximize / Restore**:
   - `ShowWindow(hwnd, SW_MINIMIZE)` (6) or `SW_SHOWMINIMIZED` (2).
   - `ShowWindow(hwnd, SW_MAXIMIZE)` (3).
   - `ShowWindow(hwnd, SW_RESTORE)` (9): Restores a minimized or maximized window to its normal bounds.
3. **Graceful Close**:
   - **Strict Invariant**: Window closure MUST use `PostMessageW(hwnd, WM_CLOSE, 0, 0)`.
   - Never call `TerminateProcess` or `taskkill` when closing a window. `WM_CLOSE` allows applications (Notepad, VS Code, Office) to prompt the user to save unsaved documents.

---

## 2. Monitor Enumeration & Multi-Monitor Geometry

### 2.1 Enumeration
- **`EnumDisplayMonitors(NULL, NULL, MONITORENUMPROC lpfnEnum, LPARAM dwData)`**:
  - Iterates over all active display monitors.
  - Retrieves `HMONITOR` handles.
- **`GetMonitorInfoW(HMONITOR hMonitor, LPMONITORINFOEXW lpmi)`**:
  - `rcMonitor`: Total monitor rectangle (e.g., $1920 \times 1080$).
  - `rcWork`: **Work Area rectangle**, excluding the Windows Taskbar and docked toolbars (e.g., $1920 \times 1032$).
  - `dwFlags & MONITORINFOF_PRIMARY`: Identifies the primary monitor.
  - `szDevice`: Device name string (e.g., `\\.\DISPLAY1`).

### 2.2 Natural Language Monitor Resolution
Monitors are mapped dynamically from physical and geometric properties:
1. **`primary` / `main`**: The monitor with `MONITORINFOF_PRIMARY` set.
2. **Geometric Left-to-Right Ordering**: Sort all active monitors by `rcMonitor.left`.
   - `monitor 1` = Leftmost monitor (or primary depending on convention; by standard geometric sorting, indices 1..N order from left to right).
   - `monitor 2` = Second monitor.
   - `left monitor` = Monitor with lowest `rcMonitor.left`.
   - `right monitor` = Monitor with highest `rcMonitor.left`.
   - `other monitor` = The monitor that is NOT currently holding the target window.

---

## 3. Desktop Layout Engine & Tiling Math

All tiling and snapping calculations operate strictly within the target monitor's `rcWork` (Work Area), preventing windows from overlapping or hiding the Windows Taskbar.

Let $W_x, W_y, W_w, W_h$ denote `rcWork.left`, `rcWork.top`, `rcWork.right - rcWork.left`, and `rcWork.bottom - rcWork.top`.

| Layout Name | Target Bounds $(X, Y, \text{Width}, \text{Height})$ |
| :--- | :--- |
| `FULL` | $(W_x, W_y, W_w, W_h)$ |
| `LEFT_HALF` | $(W_x, W_y, \lfloor W_w / 2 \rfloor, W_h)$ |
| `RIGHT_HALF` | $(W_x + \lfloor W_w / 2 \rfloor, W_y, W_w - \lfloor W_w / 2 \rfloor, W_h)$ |
| `TOP_HALF` | $(W_x, W_y, W_w, \lfloor W_h / 2 \rfloor)$ |
| `BOTTOM_HALF` | $(W_x, W_y + \lfloor W_h / 2 \rfloor, W_w, W_h - \lfloor W_h / 2 \rfloor)$ |
| `TOP_LEFT` | $(W_x, W_y, \lfloor W_w / 2 \rfloor, \lfloor W_h / 2 \rfloor)$ |
| `TOP_RIGHT` | $(W_x + \lfloor W_w / 2 \rfloor, W_y, W_w - \lfloor W_w / 2 \rfloor, \lfloor W_h / 2 \rfloor)$ |
| `BOTTOM_LEFT` | $(W_x, W_y + \lfloor W_h / 2 \rfloor, \lfloor W_w / 2 \rfloor, W_h - \lfloor W_h / 2 \rfloor)$ |
| `BOTTOM_RIGHT`| $(W_x + \lfloor W_w / 2 \rfloor, W_y + \lfloor W_h / 2 \rfloor, W_w - \lfloor W_w / 2 \rfloor, W_h - \lfloor W_h / 2 \rfloor)$ |
| `LEFT_TWO_THIRDS` | $(W_x, W_y, \lfloor 2 W_w / 3 \rfloor, W_h)$ |
| `RIGHT_ONE_THIRD` | $(W_x + \lfloor 2 W_w / 3 \rfloor, W_y, W_w - \lfloor 2 W_w / 3 \rfloor, W_h)$ |

### 3.1 Moving Maximized Windows
If a window is currently `MAXIMIZED`, calling `SetWindowPos` directly produces graphical artifacts or fails.
**Procedure**:
1. Check window placement via `GetWindowPlacement(hwnd, &wp)`.
2. If `wp.showCmd == SW_SHOWMAXIMIZED`, restore window: `ShowWindow(hwnd, SW_RESTORE)`.
3. Apply `SetWindowPos(hwnd, HWND_TOP, x, y, width, height, SWP_NOACTIVATE | SWP_NOZORDER | SWP_FRAMECHANGED)`.

---

## 4. Origin Window Semantics (The Alt+Space Problem)

### 4.1 The Challenge
When the user presses `Alt+Space`, AstraRun's launcher window appears and immediately receives keyboard and foreground focus.
If the user subsequently types:
- `"maximize this"`
- `"move this window to monitor 2"`
- `"snap this left"`

A naive call to `GetForegroundWindow()` returns **AstraRun's own window**!

### 4.2 The Solution: Origin Window Hook
1. Inside `HotkeyManager`, the instant the global hotkey is detected and *before* `launcher.show_and_activate()` is executed:
   - Call Win32 `GetForegroundWindow()`.
   - Check if the handle belongs to AstraRun. If not, capture:
     - `origin_hwnd`: Target HWND
     - `origin_pid`: Process ID
     - `origin_title`: Window text
     - `origin_app`: Application name
     - `origin_monitor`: Active monitor
     - `timestamp`: Timestamp of hotkey press
2. Pass this `OriginWindowContext` to the active `RoutingContext` / `WorkstationContext`.
3. Any contextual pronoun reference (`this window`, `current window`, `this`) deterministically binds to `origin_window`.
4. AstraRun utility windows (launcher, activity card, history dialog, memory inspector) are explicitly forbidden from being mutated as the target of "this window".

---

## 5. DPI Awareness & Multi-DPI Scaling

On Windows 10/11 with mixed-DPI setups (e.g. 4K laptop display at 150% + 1080p external monitor at 100%):
1. **API**: `user32.GetDpiForWindow(hwnd)` (returns integer DPI, baseline 96 = 100%).
2. **Monitor DPI**: `shcore.GetDpiForMonitor(hmonitor, MDT_EFFECTIVE_DPI, &dpiX, &dpiY)`.
3. When moving a window across monitors with different DPI scalings, Windows automatically scales non-client frame metrics. Geometry calculations using monitor-local `rcWork` coordinates inherently scale correctly because `rcWork` is expressed in the monitor's coordinate space.

---

## 6. Window Layout Undo Stack

To support `"undo last window move"` safely:
1. Maintain an in-memory `WindowRestoreStack` with bounded size (e.g., 20 snapshots) and 10-minute TTL.
2. Before any mutation (`move`, `resize`, `snap`, `maximize`), capture a `WindowLayoutSnapshot`:
   - `hwnd`: HWND handle
   - `pid`: Process ID
   - `bounds`: $(x, y, w, h)$
   - `show_state`: `normal`, `maximized`, `minimized`
   - `timestamp`: Timestamp
3. When `"undo"` is requested:
   - Pop the top snapshot.
   - Revalidate identity: `IsWindow(hwnd)`, `GetWindowThreadProcessId(hwnd) == pid`.
   - If invalid/stale, reject with `STALE_ENTITY` error.
   - If valid, restore previous bounds and state.
