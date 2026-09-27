# WINDOW_ARCHITECTURE.md — AstraRun Window Intelligence & Win32 Architecture

> **Milestone**: AstraRun v0.9 (Daily Driver Integration & Window Intelligence)  
> **Status**: APPROVED  
> **Target Audience**: Windows Systems Engineers, Runtime Developers  
> **Last Updated**: 2026-09-27  

---

## 1. Architectural Philosophy & Zero-Heavy-Framework Invariant

AstraRun v0.9 introduces native Window Intelligence directly into the daily driver experience. Unlike competing desktop launchers or tiling assistants that bundle heavy third-party automation tools, node-based wrappers, or accessibility engines (which introduce severe latency and memory bloat), AstraRun adheres strictly to the following invariant:

> **Invariant**: Window intelligence must be powered purely by native Win32 User32/Gdi32/Shell32 APIs via Python's standard `ctypes.windll`, with zero third-party GUI automation dependencies.

All window enumeration, layout calculations, geometry manipulation, and state changes execute in microseconds without spawning external helper processes.

---

## 2. Window Subsystem Component Hierarchy

The AstraRun Window Subsystem lives in `src/astrarun/windows/` and is partitioned into 7 decoupled modules:

```text
src/astrarun/windows/
├── __init__.py        # Public subsystem export surface
├── models.py          # WindowState, LayoutType, WindowBounds, MonitorEntity, WindowLayoutSnapshot
├── monitors.py        # EnumDisplayMonitors, GetMonitorInfoW, DPI awareness, NL monitor resolution
├── policy.py          # _ASTRARUN_HWNDS, protected shell classes, TOCTOU PID validation, geometry clamping
├── undo.py            # WindowRestoreStack, bounded LIFO, TTL pruning
├── layouts.py         # DesktopLayoutEngine, 11 deterministic layout geometry algorithms
├── controller.py      # focus, minimize, maximize, restore, move, resize, snap, close, arrange, undo
├── resolver.py        # WindowResolver, pronoun grounding, context recall, fuzzy matching, ambiguity gating
└── discovery.py       # EnumWindows, GetForegroundWindow, visible window filtering
```

### Module Responsibilities:
1. **`models.py`**: Immutable dataclasses and enums representing window geometry, display bounds, and layout states.
2. **`monitors.py`**: Interacts with `User32.EnumDisplayMonitors` and `User32.GetMonitorInfoW` to compute true display work areas (excluding taskbars and docked appbars) with Per-Monitor DPI v2 awareness.
3. **`policy.py`**: Central safety arbiter for window operations. Enforces self-targeting immunity (`_ASTRARUN_HWNDS`), blocks shell classes (`Shell_TrayWnd`, `Progman`, `WorkerW`), verifies process ownership via TOCTOU PID checks, and clamps coordinates to visible monitor bounds.
4. **`undo.py`**: Thread-safe bounded LIFO history stack (max depth: 20 snapshots, TTL: 600 seconds) allowing instant reversal of any layout modification.
5. **`layouts.py`**: Deterministic geometric engine converting work-area rectangles into exact pixel coordinates for 11 layout types.
6. **`controller.py`**: Executes atomic Win32 mutations (`SetWindowPos`, `ShowWindow`, `PostMessageW(WM_CLOSE)`), recording pre-mutation snapshots to the undo stack.
7. **`resolver.py`**: Grounding engine resolving natural language references (`"this window"`, `"current window"`, `"it"`, `"chrome"`, `"vs code"`) to verified `WindowEntity` objects.
8. **`discovery.py`**: Filtered desktop window enumeration eliminating tooltips, hidden offscreen frames, and cloaked virtual desktop windows.

---

## 3. Win32 Window Discovery & Filtering Pipeline

Enumerating top-level desktop windows on Windows requires careful filtering to exclude invisible, cloaked, or system helper windows. `discovery.py` implements the standard Win32 desktop window filter:

```python
def is_user_window(hwnd: int) -> bool:
    # 1. Must be a valid window handle
    if not user32.IsWindow(hwnd):
        return False
    # 2. Must be visible
    if not user32.IsWindowVisible(hwnd):
        return False
    # 3. Must not be cloaked by Windows Virtual Desktops (DWMWA_CLOAKED)
    cloaked = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    if cloaked.value != 0:
        return False
    # 4. Must not be a tool window or utility popup
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if ex_style & WS_EX_TOOLWINDOW:
        return False
    # 5. Must have a non-empty window title
    title_len = user32.GetWindowTextLengthW(hwnd)
    if title_len == 0:
        return False
    # 6. Must not be a protected shell class
    class_name = get_window_class(hwnd)
    if class_name in PROTECTED_SHELL_CLASSES:
        return False
    return True
```

This guarantees that queries like `list windows` return only real user-facing application windows.

---

## 4. Focus Handoff & The Origin Window Invariant

The central UX challenge of any hotkey-activated launcher (`Alt+Space`) is that opening the launcher steals keyboard focus, making the launcher itself the foreground window.

AstraRun solves this cleanly through the **Origin Window Invariant**:
1. When the global hotkey `Alt+Space` fires, `main.py` immediately queries `win32gui.GetForegroundWindow()` **BEFORE** showing or focusing the launcher window.
2. If the captured HWND belongs to another application (e.g. VS Code, Chrome, Terminal), it is stored as `AstraApplication.origin_window`.
3. If the user executes a relative window command (e.g., `snap left`, `maximize window`, `move to monitor 2`), the pipeline grounds the command directly to `origin_window`.
4. After executing the geometry change, AstraRun automatically restores keyboard focus to `origin_window` using `SetForegroundWindow()`.

---

## 5. Thread Isolation & Win32 Safety

Win32 UI APIs have strict threading rules:
- Window handles (`HWND`) can be inspected and moved across threads via `SetWindowPos()` and `PostMessage()`.
- Synchronous UI message loops must never be blocked by background worker threads.
- AstraRun isolates Win32 window controller operations in synchronous, non-blocking calls. Window closing uses non-blocking asynchronous `PostMessageW(hwnd, WM_CLOSE, 0, 0)`, allowing target applications to perform graceful shutdown and trigger save confirmations.
