"""F0-25F Stage 0: Reproduce launcher visibility contradiction with raw Win32 measurements."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil
from PIL import ImageGrab

ROOT_DIR = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT_DIR / "docs" / "audit"
CANONICAL_EXE = Path(r"C:\Users\hp\AppData\Local\Programs\AstraRun\AstraRun.exe")
OUT_JSON = AUDIT_DIR / "F0_25F_LAUNCHER_ROOT_CAUSE.json"
OUT_SCREENSHOT = AUDIT_DIR / "F0_25F_reproduction.png"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
try:
    dwmapi = ctypes.windll.dwmapi
except Exception:
    dwmapi = None

# Configure ctypes prototypes
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindow.restype = wintypes.BOOL

user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int

user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int

user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int

user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.restype = wintypes.BOOL

user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG

user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND

user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND

user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND

GWL_STYLE = -16
GWL_EXSTYLE = -20
GW_OWNER = 4
GW_HWNDPREV = 3
GW_HWNDNEXT = 2
DWMWA_CLOAKED = 14


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [
        ("length", wintypes.UINT),
        ("flags", wintypes.UINT),
        ("showCmd", wintypes.UINT),
        ("ptMinPosition", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("rcNormalPosition", wintypes.RECT),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def ensure_desktop_attached() -> None:
    """Ensure current thread is attached to interactive desktop Default on WinSta0."""
    try:
        hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if not hdesk:
            hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def get_user_object_name(h_obj: int) -> str:
    """Get the name of a desktop or window station."""
    if not h_obj:
        return ""
    needed = wintypes.DWORD()
    UOI_NAME = 2
    user32.GetUserObjectInformationW(h_obj, UOI_NAME, None, 0, ctypes.byref(needed))
    if needed.value == 0:
        return ""
    buf = ctypes.create_unicode_buffer(needed.value // 2 + 2)
    if user32.GetUserObjectInformationW(h_obj, UOI_NAME, buf, needed.value, ctypes.byref(needed)):
        return buf.value
    return ""


def get_window_details(hwnd: int) -> Dict[str, Any]:
    """Capture exhaustive Win32 metadata for an HWND."""
    is_win = bool(user32.IsWindow(hwnd))
    if not is_win:
        return {"hwnd": hwnd, "is_window": False}

    pid = wintypes.DWORD()
    thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    is_vis = bool(user32.IsWindowVisible(hwnd))

    len_t = user32.GetWindowTextLengthW(hwnd)
    buf_t = ctypes.create_unicode_buffer(len_t + 1)
    user32.GetWindowTextW(hwnd, buf_t, len_t + 1)
    title = buf_t.value

    buf_c = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf_c, 256)
    cls_name = buf_c.value

    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

    owner_hwnd = user32.GetWindow(hwnd, GW_OWNER)
    parent_hwnd = user32.GetParent(hwnd)

    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(WINDOWPLACEMENT)
    show_cmd = -1
    if user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        show_cmd = wp.showCmd

    # DWM cloaked state
    cloaked = ctypes.c_int(0)
    cloaked_status = "NOT_CHECKED"
    if dwmapi:
        hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        cloaked_status = f"HR_{hr:#x}_VAL_{cloaked.value}"

    # Desktop and Window Station
    h_thread_desktop = user32.GetThreadDesktop(thread_id)
    thread_desktop_name = get_user_object_name(h_thread_desktop)
    h_win_station = user32.GetProcessWindowStation()
    win_station_name = get_user_object_name(h_win_station)

    # Monitor intersection
    MONITOR_DEFAULTTONEAREST = 2
    h_mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    mon_info = MONITORINFO()
    mon_info.cbSize = ctypes.sizeof(MONITORINFO)
    mon_rect = [0, 0, 0, 0]
    intersects_monitor = False
    if h_mon and user32.GetMonitorInfoW(h_mon, ctypes.byref(mon_info)):
        mr = mon_info.rcMonitor
        mon_rect = [mr.left, mr.top, mr.right, mr.bottom]
        ix_left = max(rect.left, mr.left)
        ix_top = max(rect.top, mr.top)
        ix_right = min(rect.right, mr.right)
        ix_bottom = min(rect.bottom, mr.bottom)
        if ix_right > ix_left and ix_bottom > ix_top:
            intersects_monitor = True

    # Z-order neighbors
    hwnd_prev = user32.GetWindow(hwnd, GW_HWNDPREV)
    hwnd_next = user32.GetWindow(hwnd, GW_HWNDNEXT)

    # Process details
    proc_name = ""
    try:
        proc_name = psutil.Process(pid.value).name()
    except Exception:
        pass

    return {
        "hwnd": hwnd,
        "pid": pid.value,
        "process_name": proc_name,
        "thread_id": thread_id,
        "title": title,
        "class_name": cls_name,
        "is_window": is_win,
        "is_window_visible": is_vis,
        "rect": [rect.left, rect.top, rect.right, rect.bottom],
        "width": w,
        "height": h,
        "style_hex": f"{style:#010x}",
        "ex_style_hex": f"{ex_style:#010x}",
        "is_topmost": bool(ex_style & 0x00000008),
        "is_tool_window": bool(ex_style & 0x00000080),
        "owner_hwnd": owner_hwnd,
        "parent_hwnd": parent_hwnd,
        "show_cmd": show_cmd,
        "dwm_cloaked": cloaked_status,
        "desktop_name": thread_desktop_name,
        "window_station": win_station_name,
        "monitor_rect": mon_rect,
        "intersects_monitor": intersects_monitor,
        "hwnd_prev_zorder": hwnd_prev,
        "hwnd_next_zorder": hwnd_next,
    }


def main() -> int:
    print("[STAGE 0] Reproducing Launcher Visibility Contradiction...")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_desktop_attached()

    # Kill any stale AstraRun processes
    for p in psutil.process_iter(["pid", "name"]):
        if "astrarun" in (p.info["name"] or "").lower():
            try:
                p.kill()
            except Exception:
                pass
    time.sleep(1.0)

    # Capture foreground window before launch
    fg_before = user32.GetForegroundWindow()
    fg_before_details = get_window_details(fg_before) if fg_before else {}

    # Launch canonical AstraRun.exe with --show-now
    print(f"[LAUNCH] Starting canonical executable: {CANONICAL_EXE}")
    proc = subprocess.Popen([str(CANONICAL_EXE), "--show-now"], cwd=str(CANONICAL_EXE.parent))
    target_pids = {proc.pid}
    print(f"Spawned parent PID={proc.pid}")

    # Connect via AstraSingleInstance IPC and request SHOW_MAIN_UI
    sys.path.insert(0, str(ROOT_DIR / "src"))
    from astrarun.core.single_instance import AstraSingleInstance
    si = AstraSingleInstance()

    ipc_connected = False
    ipc_response = {}
    t0 = time.time()
    while time.time() - t0 < 10.0:
        res = si.send_command("SHOW_MAIN_UI", timeout_ms=500)
        if res.get("status") == "OK" or res.get("action") == "SHOW_MAIN_UI_TRIGGERED":
            ipc_connected = True
            ipc_response = res
            break
        time.sleep(0.5)

    print(f"IPC connection result: connected={ipc_connected}, response={ipc_response}")
    time.sleep(1.5)

    # Discover child PIDs if any
    try:
        parent_proc = psutil.Process(proc.pid)
        for child in parent_proc.children(recursive=True):
            target_pids.add(child.pid)
    except Exception:
        pass

    # Read state file written by AstraRun
    from astrarun.core.paths import AstraPaths
    state_file = AstraPaths.state_file_path()
    state_content = {}
    launcher_hwnd = None
    if state_file.exists():
        try:
            state_content = json.loads(state_file.read_text(encoding="utf-8"))
            launcher_hwnd = state_content.get("launcher_hwnd")
        except Exception:
            pass

    # Inspect AstraRun log for recent LAUNCHER lifecycle lines
    log_file = AstraPaths.logs_dir() / "astrarun.log"
    recent_log_lines: List[str] = []
    if log_file.exists():
        try:
            all_lines = log_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            recent_log_lines = all_lines[-40:]
        except Exception:
            pass

    # Capture details of the launcher HWND reported by AstraRun
    launcher_window_details = {}
    if launcher_hwnd:
        launcher_window_details = get_window_details(launcher_hwnd)

    # Foreground window during measurement
    fg_now = user32.GetForegroundWindow()
    fg_now_details = get_window_details(fg_now) if fg_now else {}

    # Check top-level windows visible to EnumWindows on Default desktop
    desktop_windows_on_default: List[Dict[str, Any]] = []
    def enum_cb(h, lp):
        if user32.IsWindowVisible(h):
            p = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value in target_pids or h == launcher_hwnd:
                desktop_windows_on_default.append(get_window_details(h))
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

    # Capture real physical screenshot
    timestamp = time.time()
    print("[CAPTURE] Capturing physical desktop screenshot...")
    ensure_desktop_attached()
    screenshot = ImageGrab.grab(all_screens=True)
    screenshot.save(OUT_SCREENSHOT, "PNG")
    screenshot_hash = hashlib.sha256(OUT_SCREENSHOT.read_bytes()).hexdigest()

    # Sample pixels in launcher's reported rect
    pixel_sample = {}
    if launcher_window_details.get("width", 0) > 0:
        rx1, ry1, rx2, ry2 = launcher_window_details["rect"]
        try:
            cropped = screenshot.crop((rx1, ry1, rx2, ry2))
            colors = list(cropped.getdata())
            r_avg = sum(c[0] for c in colors) / len(colors)
            g_avg = sum(c[1] for c in colors) / len(colors)
            b_avg = sum(c[2] for c in colors) / len(colors)
            pixel_sample = {
                "rect": launcher_window_details["rect"],
                "avg_rgb": [round(r_avg, 1), round(g_avg, 1), round(b_avg, 1)],
                "total_pixels": len(colors),
            }
        except Exception as e:
            pixel_sample = {"error": str(e)}

    # Assemble raw diagnostic output
    raw_diagnostic = {
        "timestamp": timestamp,
        "target_executable": str(CANONICAL_EXE),
        "target_pids": sorted(list(target_pids)),
        "ipc_connected": ipc_connected,
        "ipc_response": ipc_response,
        "state_file_content": state_content,
        "launcher_hwnd_from_state": launcher_hwnd,
        "launcher_window_details": launcher_window_details,
        "desktop_windows_on_default_desktop": desktop_windows_on_default,
        "foreground_window_before": fg_before_details,
        "foreground_window_during_diagnostic": fg_now_details,
        "pixel_sample_at_launcher_rect": pixel_sample,
        "screenshot": {
            "path": str(OUT_SCREENSHOT),
            "size_bytes": OUT_SCREENSHOT.stat().st_size,
            "sha256": screenshot_hash,
            "dimensions": [screenshot.width, screenshot.height],
        },
        "recent_log_lines": recent_log_lines,
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(raw_diagnostic, f, indent=2)

    print(f"\n[DONE] Wrote raw measurements to {OUT_JSON}")
    print(f"Screenshot saved to {OUT_SCREENSHOT}")

    # Clean up process
    try:
        si.send_command("QUIT")
    except Exception:
        pass
    time.sleep(0.5)
    for p in target_pids:
        try:
            psutil.Process(p).kill()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
