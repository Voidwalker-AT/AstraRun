# MONITOR_MODEL.md — AstraRun Multi-Monitor Model & DPI Geometry

> **Milestone**: AstraRun v0.9 (Daily Driver Integration & Window Intelligence)  
> **Status**: APPROVED  
> **Subsystem**: `src/astrarun/windows/monitors.py`  
> **Target Audience**: Windows Systems Engineers, Graphics Developers  
> **Last Updated**: 2026-09-27  

---

## 1. Overview & Multi-Monitor Topologies

Modern workstation setups frequently feature heterogeneous display configurations:
- Primary 14" 1080p laptop display (125% DPI scale, 96-120 DPI)
- Secondary 27" 4K external monitor (150% DPI scale, 144 DPI)
- Vertical portrait code monitor (1080x1920)
- Negative coordinate virtual desktop layouts (monitors placed to the left or above the primary monitor)

AstraRun's `MonitorEntity` and `monitors.py` subsystem model multi-monitor topologies with exact geometric precision and Per-Monitor DPI v2 awareness.

---

## 2. Monitor Data Model

```python
@dataclass
class MonitorEntity:
    monitor_id: int                            # 1-indexed identifier (1, 2, ...)
    device_name: str                           # e.g., r"\\.\DISPLAY1"
    work_area: tuple[int, int, int, int]       # (left, top, width, height) excluding taskbar/appbars
    full_bounds: tuple[int, int, int, int]     # (left, top, width, height) total screen physical pixels
    is_primary: bool                           # True if monitor is primary (0,0 origin)
    dpi: int = 96                              # Native monitor DPI
```

### Key Fields:
- **`work_area`**: The usable desktop rectangle returned by `GetMonitorInfoW.rcWork`. This area excludes the Windows Taskbar (whether positioned top, bottom, left, or right) and any docked sidebars. Window tiling algorithms operate exclusively on `work_area`.
- **`full_bounds`**: The raw monitor screen rectangle (`rcMonitor`), used for full-screen maximization bounds and display coordinate translation.
- **`is_primary`**: The primary display is always assigned `monitor_id = 1` and has its top-left at `(0, 0)`.

---

## 3. Win32 Enumeration Pipeline & DPI Awareness

`enumerate_monitors()` discovers and sorts physical displays:
1. **DPI Awareness Declaration**: Upon startup, AstraRun calls `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)`. This prevents Windows from applying bitmap stretching to AstraRun overlays and ensures all Win32 coordinates are reported in true physical pixels.
2. **`EnumDisplayMonitors`**: Iterates through all active monitor handles (`HMONITOR`).
3. **`GetMonitorInfoW`**: Retrieves `MONITORINFOEXW` containing `rcMonitor`, `rcWork`, and `dwFlags` (`MONITORINFOF_PRIMARY`).
4. **`GetDpiForMonitor`**: Queries the native DPI along horizontal and vertical axes via `Shcore.dll`.
5. **Deterministic Geometric Sorting**: Monitors are sorted with the Primary display first (`monitor_id = 1`), followed by secondary monitors ordered from left-to-right (`x`), then top-to-bottom (`y`).

---

## 4. Natural Language Monitor Resolution

Users refer to monitors using varying spatial, index-based, or descriptive terminology:
- `"monitor 1"`, `"display 1"`, `"screen 1"`, `"first monitor"` -> Resolves to Monitor 1 (Primary)
- `"monitor 2"`, `"display 2"`, `"screen 2"`, `"second monitor"` -> Resolves to Monitor 2
- `"primary"`, `"main screen"`, `"main monitor"` -> Resolves to `is_primary = True`
- `"secondary"`, `"external screen"`, `"external display"` -> Resolves to first non-primary monitor
- `"left monitor"`, `"right monitor"` -> Resolves based on relative horizontal work area X coordinates

`resolve_monitor()` handles these queries deterministically, returning the matched `MonitorEntity`.

---

## 5. Safe Geometry Clamping & Virtual Desktop Bounds

Moving a window to another monitor can result in windows appearing partially offscreen or lost in unmapped virtual desktop space. `policy.clamp_geometry()` enforces strict safety invariants:

```python
def clamp_geometry(bounds: WindowBounds, monitor: MonitorEntity) -> WindowBounds:
    mx, my, mw, mh = monitor.work_area
    w = max(min(bounds.width, mw), 300)      # Enforce min width 300px
    h = max(min(bounds.height, mh), 200)     # Enforce min height 200px
    x = max(mx, min(bounds.x, mx + mw - w))  # Keep within monitor work area
    y = max(my, min(bounds.y, my + mh - h))
    return WindowBounds(x=x, y=y, width=w, height=h)
```

This guarantees that every window placed by AstraRun remains completely visible and interactable.
