"""Production-native external OS visibility attestation for AstraRun UI surfaces."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

DWMWA_CLOAKED = 14
MONITOR_DEFAULTTONEAREST = 2


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _get_user_object_name(h_obj: int) -> str:
    if not h_obj or sys.platform != "win32":
        return ""
    user32 = ctypes.windll.user32
    needed = wintypes.DWORD()
    UOI_NAME = 2
    user32.GetUserObjectInformationW(h_obj, UOI_NAME, None, 0, ctypes.byref(needed))
    if needed.value == 0:
        return ""
    buf = ctypes.create_unicode_buffer(needed.value // 2 + 2)
    if user32.GetUserObjectInformationW(h_obj, UOI_NAME, buf, needed.value, ctypes.byref(needed)):
        return buf.value
    return ""


def attest_window_visibility(hwnd: int, expected_pid: Optional[int] = None) -> Dict[str, Any]:
    """
    Independently verify whether hwnd corresponds to an externally observable Windows HWND that:
    1. IsWindow(hwnd) == true
    2. IsWindowVisible(hwnd) == true
    3. has non-empty on-screen bounds (width > 0, height > 0)
    4. belongs to AstraRun PID
    5. intersects an active monitor
    6. is not DWM cloaked
    7. is observable from the interactive desktop (Default)

    Never self-certifies visibility. Returns status 'LAUNCHER_VISIBLE' only when all OS facts agree,
    otherwise 'UNKNOWN/FAILED' with specific failure reasons.
    """
    if sys.platform != "win32" or not hwnd:
        return {
            "status": "UNKNOWN/FAILED",
            "is_visible": False,
            "failure_reasons": ["non_windows_or_null_hwnd"],
            "facts": {"hwnd": hwnd},
        }

    user32 = ctypes.windll.user32
    try:
        dwmapi = ctypes.windll.dwmapi
    except Exception:
        dwmapi = None

    failure_reasons: List[str] = []

    # 1. IsWindow
    is_win = bool(user32.IsWindow(hwnd))
    if not is_win:
        failure_reasons.append("is_not_window")

    # 2. IsWindowVisible
    is_vis = bool(user32.IsWindowVisible(hwnd))
    if not is_vis:
        failure_reasons.append("is_not_window_visible")

    # 3. Non-empty on-screen bounds
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        failure_reasons.append(f"empty_bounds_w_{w}_h_{h}")

    # 4. PID match
    win_pid = wintypes.DWORD()
    thread_id = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(win_pid))
    if expected_pid is not None and win_pid.value != expected_pid:
        failure_reasons.append(f"pid_mismatch_expected_{expected_pid}_got_{win_pid.value}")

    # 5. Monitor intersection
    h_mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    mon_info = MONITORINFO()
    mon_info.cbSize = ctypes.sizeof(MONITORINFO)
    intersects_monitor = False
    mon_rect = [0, 0, 0, 0]
    if h_mon and user32.GetMonitorInfoW(h_mon, ctypes.byref(mon_info)):
        mr = mon_info.rcMonitor
        mon_rect = [mr.left, mr.top, mr.right, mr.bottom]
        ix_left = max(rect.left, mr.left)
        ix_top = max(rect.top, mr.top)
        ix_right = min(rect.right, mr.right)
        ix_bottom = min(rect.bottom, mr.bottom)
        if ix_right > ix_left and ix_bottom > ix_top:
            intersects_monitor = True

    if not intersects_monitor:
        failure_reasons.append("does_not_intersect_monitor")

    # 6. DWM Cloaked State
    cloaked = ctypes.c_int(0)
    is_cloaked = False
    if dwmapi:
        hr = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if hr == 0 and cloaked.value != 0:
            is_cloaked = True
            failure_reasons.append(f"dwm_cloaked_val_{cloaked.value}")

    # 7. Observable from interactive desktop
    h_thread_desktop = user32.GetThreadDesktop(thread_id)
    thread_desktop_name = _get_user_object_name(h_thread_desktop)
    is_interactive_desktop = (thread_desktop_name.lower() == "default")
    if not is_interactive_desktop:
        failure_reasons.append(f"non_interactive_desktop_{thread_desktop_name}")

    # Verify EnumWindows on Default desktop visits this HWND
    found_in_enum = False
    def enum_cb(h, lp):
        nonlocal found_in_enum
        if h == hwnd:
            found_in_enum = True
            return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    if not found_in_enum:
        failure_reasons.append("hwnd_not_found_in_desktop_enum_windows")

    is_verified = (len(failure_reasons) == 0)
    status = "LAUNCHER_VISIBLE" if is_verified else "UNKNOWN/FAILED"

    return {
        "status": status,
        "is_visible": is_verified,
        "failure_reasons": failure_reasons,
        "facts": {
            "hwnd": hwnd,
            "pid": win_pid.value,
            "expected_pid": expected_pid,
            "thread_id": thread_id,
            "desktop_name": thread_desktop_name,
            "is_window": is_win,
            "is_window_visible": is_vis,
            "rect": [rect.left, rect.top, rect.right, rect.bottom],
            "width": w,
            "height": h,
            "monitor_rect": mon_rect,
            "intersects_monitor": intersects_monitor,
            "dwm_cloaked": is_cloaked,
            "found_in_enum_windows": found_in_enum,
        },
    }


def verify_surface_contrast(crop_image: Any) -> Tuple[bool, Dict[str, float]]:
    """
    Verify that an on-screen crop has non-monochrome structural content (text, icons, borders).
    Rejects completely flat surfaces (all-black, all-white, or single flat color).
    """
    if crop_image is None or crop_image.width < 10 or crop_image.height < 10:
        return False, {"std_dev": 0.0, "contrast_range": 0.0, "mean_brightness": 0.0}

    try:
        gray = crop_image.convert("L")
        pixels = gray.load()
        w, h = gray.width, gray.height
        vals = [pixels[x, y] for x in range(0, w, 2) for y in range(0, h, 2)]
        if not vals:
            return False, {"std_dev": 0.0, "contrast_range": 0.0, "mean_brightness": 0.0}

        mean_val = sum(vals) / len(vals)
        variance = sum((v - mean_val) ** 2 for v in vals) / len(vals)
        std_dev = variance ** 0.5
        contrast_range = max(vals) - min(vals)

        # Real launcher command bars have text, borders, and controls with contrast >= 15 and std_dev >= 4.0.
        # Flat black/white fake surfaces have std_dev < 1.0 and contrast_range < 5.
        is_structural = (std_dev >= 4.0 and contrast_range >= 15.0)
        return is_structural, {
            "std_dev": round(std_dev, 2),
            "contrast_range": float(contrast_range),
            "mean_brightness": round(mean_val, 2),
        }
    except Exception:
        return False, {"std_dev": 0.0, "contrast_range": 0.0, "mean_brightness": 0.0}


def attest_launcher_identity(
    hwnd: int,
    screenshot: Optional[Any] = None,
    expected_pid: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Multi-factor attestation of AstraRun launcher identity.
    Combines:
    - OS window facts (IsWindow, IsWindowVisible, Default desktop, EnumWindows presence)
    - Process correlation (AstraRun PID matching)
    - Monitor geometry and DWM cloaking verification
    - Visual surface contrast (rejects flat black or unrendered rectangles)
    """
    att = attest_window_visibility(hwnd, expected_pid=expected_pid)
    reasons = list(att.get("failure_reasons", []))

    surface_metrics: Dict[str, float] = {}
    if screenshot and att.get("is_visible"):
        try:
            rect = att["facts"]["rect"]
            w_crop = rect[2] - rect[0]
            h_crop = rect[3] - rect[1]
            if w_crop > 10 and h_crop > 10:
                crop = screenshot.crop((rect[0], rect[1], rect[2], rect[3]))
                has_contrast, metrics = verify_surface_contrast(crop)
                surface_metrics = metrics
                if not has_contrast:
                    reasons.append(f"flat_untextured_surface_contrast_range_{metrics.get('contrast_range')}")
        except Exception as e:
            reasons.append(f"surface_crop_error_{e}")

    is_verified = (len(reasons) == 0)
    return {
        "status": "LAUNCHER_VERIFIED" if is_verified else "LAUNCHER_REJECTED",
        "is_verified": is_verified,
        "failure_reasons": reasons,
        "facts": att.get("facts", {}),
        "surface_metrics": surface_metrics,
    }
