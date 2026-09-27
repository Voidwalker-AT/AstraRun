# Window Discovery — AstraRun v0.7

> **Scope**: Read-only desktop window enumeration, foreground inspection, and application clustering  
> **Status**: APPROVED  
> **Milestone**: v0.7 (Workstation Capability Expansion)  
> **Last Verified**: 2026-09-27  

---

## 1. Architectural Scope & Roadmap Boundary

AstraRun v0.7 introduces **read-only window discovery**, establishing the sensory foundation for window management before introducing active window manipulation (such as snapping, resizing, moving across monitors, and virtual desktops), which is scheduled for **AstraRun v0.8**.

### Key Capabilities in v0.7:
- `list_windows`: Enumerate all visible top-level desktop windows with titles and geometry.
- `foreground_window`: Inspect the window that currently holds user input focus.
- `find_window`: Query open windows by partial title match.
- `windows_for_application`: Cluster and return all open windows belonging to a specific application process.

---

## 2. Window Data Contract: `WindowEntity`

Window queries return strongly-typed `WindowEntity` instances:

```python
@dataclass
class WindowEntity:
    hwnd: int                        # Win32 Window Handle
    title: str                       # Window Title Caption
    process_id: int                  # Owning Process PID
    process_name: str                # Owning Executable (e.g. Code.exe)
    is_visible: bool                 # Visibility Flag
    bounds: tuple[int, int, int, int]# Geometry: (left, top, right, bottom)
```

---

## 3. Win32 Implementation Details

Window discovery interfaces directly with Windows User32 APIs via `ctypes`:
- **Enumeration**: `ctypes.windll.user32.EnumWindows` traverses the OS window list.
- **Title Extraction**: `GetWindowTextLengthW` followed by `GetWindowTextW` retrieves the Unicode title string.
- **Process ID Mapping**: `GetWindowThreadProcessId` retrieves the PID owning the HWND.
- **Geometry Inspection**: `GetWindowRect` retrieves window bounding coordinates `(left, top, right, bottom)` for spatial awareness.
- **Active Focus**: `GetForegroundWindow` identifies the active window receiving user keyboard events.

---

## 4. Preparation for v0.8 Window Management

In v0.8, the window subsystem will be extended with active window control capabilities:
- `snap_window_left` / `snap_window_right`
- `maximize_window` / `minimize_window`
- `move_window_to_monitor`
- `arrange_workspace_split`

By completing and verifying typed window discovery in v0.7, v0.8 can build directly upon a tested, deterministic window catalog with zero Win32 discovery technical debt.
