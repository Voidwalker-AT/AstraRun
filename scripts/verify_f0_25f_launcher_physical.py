"""Stage 1: Physical verification of launcher visibility with newly built canonical binary."""

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

import psutil
from PIL import ImageGrab

ROOT_DIR = Path(__file__).resolve().parent.parent
AUDIT_DIR = ROOT_DIR / "docs" / "audit"
CANONICAL_EXE = Path(r"C:\Users\hp\AppData\Local\Programs\AstraRun\AstraRun.exe")
OUT_JSON = AUDIT_DIR / "F0_25F_STAGE1_PHYSICAL_VERIFICATION.json"
OUT_SCREENSHOT = AUDIT_DIR / "F0_25F_stage1_verified.png"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

def ensure_desktop_attached() -> None:
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

def get_name(h_obj: int) -> str:
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

def main() -> int:
    print("[STAGE 1] Running Physical Launcher Verification on Canonical Binary...")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_desktop_attached()

    # Kill stale AstraRun processes
    for p in psutil.process_iter(["pid", "name"]):
        if "astrarun" in (p.info["name"] or "").lower():
            try:
                p.kill()
            except Exception:
                pass
    time.sleep(1.0)

    # Launch canonical binary
    si_cmd = subprocess.STARTUPINFO()
    si_cmd.lpDesktop = r"WinSta0\Default"
    proc = subprocess.Popen([str(CANONICAL_EXE), "--show-now"], cwd=str(CANONICAL_EXE.parent), startupinfo=si_cmd)
    print(f"Spawned canonical AstraRun.exe PID={proc.pid}")

    sys.path.insert(0, str(ROOT_DIR / "src"))
    from astrarun.core.single_instance import AstraSingleInstance
    si = AstraSingleInstance()

    t0 = time.time()
    ipc_ready = False
    while time.time() - t0 < 15.0:
        res = si.send_command("SHOW_MAIN_UI", timeout_ms=500)
        if res.get("status") == "OK" or res.get("action") == "SHOW_MAIN_UI_TRIGGERED":
            ipc_ready = True
            break
        time.sleep(0.5)

    print(f"IPC ready: {ipc_ready}")
    time.sleep(1.5)

    from astrarun.core.paths import AstraPaths
    state_file = AstraPaths.state_file_path()
    sf = json.loads(state_file.read_text(encoding="utf-8"))
    launcher_hwnd = sf.get("launcher_hwnd")
    pid = sf.get("pid")
    print(f"State file: pid={pid}, launcher_hwnd={launcher_hwnd}")

    pid_val = wintypes.DWORD()
    tid = user32.GetWindowThreadProcessId(launcher_hwnd, ctypes.byref(pid_val))
    th_desk = user32.GetThreadDesktop(tid)
    desk_name = get_name(th_desk)
    print(f"Window thread desktop: '{desk_name}'")
    is_win = bool(user32.IsWindow(launcher_hwnd))
    is_vis = bool(user32.IsWindowVisible(launcher_hwnd))
    print(f"IsWindow: {is_win}, IsWindowVisible: {is_vis}")

    # Check EnumWindows on Default desktop
    enum_found = []
    def cb(h, lp):
        if h == launcher_hwnd:
            enum_found.append(h)
        return True
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    print(f"EnumWindows found launcher_hwnd: {enum_found}")

    rect = wintypes.RECT()
    user32.GetWindowRect(launcher_hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    print(f"Rect: ({rect.left}, {rect.top}, {rect.right}, {rect.bottom}), w={w}, h={h}")

    # Attestation
    from astrarun.ui.attestation import attest_launcher_identity, attest_window_visibility
    attestation = attest_window_visibility(launcher_hwnd, expected_pid=pid)
    print(f"Attestation status: {attestation['status']}, is_visible={attestation['is_visible']}")
    print(f"Failure reasons: {attestation['failure_reasons']}")

    # Capture physical screenshot
    ensure_desktop_attached()
    screenshot = ImageGrab.grab(all_screens=True)
    screenshot.save(OUT_SCREENSHOT, "PNG")
    screenshot_hash = hashlib.sha256(OUT_SCREENSHOT.read_bytes()).hexdigest()

    launcher_attestation = attest_launcher_identity(launcher_hwnd, screenshot, expected_pid=pid)
    print(f"Launcher multi-factor attestation status: {launcher_attestation['status']}")
    print(f"Launcher surface metrics: {launcher_attestation.get('surface_metrics')}")

    cropped = screenshot.crop((rect.left, rect.top, rect.right, rect.bottom))
    colors = [cropped.getpixel((x, y)) for x in range(cropped.width) for y in range(cropped.height)]

    report = {
        "timestamp": time.time(),
        "canonical_executable": str(CANONICAL_EXE),
        "executable_sha256": hashlib.sha256(CANONICAL_EXE.read_bytes()).hexdigest(),
        "pid": pid,
        "launcher_hwnd": launcher_hwnd,
        "desktop_name": desk_name,
        "is_window": is_win,
        "is_window_visible": is_vis,
        "bounds": [rect.left, rect.top, rect.right, rect.bottom],
        "width": w,
        "height": h,
        "enum_windows_found": len(enum_found) > 0,
        "attestation": attestation,
        "launcher_attestation": launcher_attestation,
        "screenshot": {
            "path": str(OUT_SCREENSHOT),
            "sha256": screenshot_hash,
            "size_bytes": OUT_SCREENSHOT.stat().st_size,
        },
        "surface_metrics": launcher_attestation.get("surface_metrics", {}),
        "verdict": "PASS" if launcher_attestation["is_verified"] else "FAIL",
    }

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\n[STAGE 1 VERDICT]: {report['verdict']}")
    print(f"Wrote verification to {OUT_JSON}")

    # Teardown
    try:
        si.send_command("QUIT")
    except Exception:
        pass
    time.sleep(0.5)
    try:
        proc.kill()
    except Exception:
        pass

    return 0 if report["verdict"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
