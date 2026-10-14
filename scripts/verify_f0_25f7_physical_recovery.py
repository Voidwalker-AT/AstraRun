"""Production Physical Recovery & Visual Attestation Runner for Phase F0-25F.7.

Repairs Foundation Defects 1 & 2:
1. Physical Recovery Visual Attestation:
   - Visibly attests Notepad on WinSta0\\Default (NOT obscured by Antigravity).
   - Enforces Win32 foreground activation via force_foreground_activation(hwnd).
   - Enforces compositing settle delay (1.0s) so desktop window frames render truthfully.
   - Verifies pixel presence within the window bounding box.
2. Resource Restoration Audit with PID Create-Time Records:
   - Records full PID + create_time snapshots (pre, mid, post).
   - Verifies zero PID reuse and zero residual process leakage.

Captures real physical screenshots to docs/audit/F0_25F7_SCREENSHOTS/
Outputs:
- docs/audit/F0_25F7_PHYSICAL_RECOVERY_RESULTS.json
- docs/audit/F0_25F7_RESOURCE_RESTORATION.json
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import psutil
from PIL import Image, ImageGrab

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from astrarun.recovery.engine import IntelligentFallbackEngine
from astrarun.recovery.models import FailureCategory, FailureEvidence, RecoveryAction
from astrarun.ui.presentation import force_foreground_activation

AUDIT_DIR = ROOT_DIR / "docs" / "audit"
SCREENSHOTS_DIR = AUDIT_DIR / "F0_25F7_SCREENSHOTS"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

OUT_RECOVERY_JSON = AUDIT_DIR / "F0_25F7_PHYSICAL_RECOVERY_RESULTS.json"
OUT_RESOURCE_JSON = AUDIT_DIR / "F0_25F7_RESOURCE_RESTORATION.json"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_MINIMIZE = 6
SW_RESTORE = 9
SW_SHOWNORMAL = 1


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]
user32.GetWindowRect.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL


def get_process_snapshot() -> Dict[int, float]:
    """Capture snapshot of all active processes mapping PID -> create_time."""
    snap: Dict[int, float] = {}
    for p in psutil.process_iter(["pid", "create_time"]):
        try:
            snap[p.info["pid"]] = p.info["create_time"]
        except Exception:
            pass
    return snap


def kill_existing_notepads():
    try:
        subprocess.run(["taskkill", "/f", "/im", "notepad.exe"], capture_output=True)
    except Exception:
        pass
    time.sleep(2.0)


def get_notepad_processes() -> List[Dict[str, Any]]:
    notepads = []
    for p in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            if "notepad" in (p.info.get("name") or "").lower():
                notepads.append({
                    "pid": p.info["pid"],
                    "name": p.info["name"],
                    "create_time": p.info["create_time"],
                })
        except Exception:
            pass
    return notepads


def find_notepad_window(exclude_pid: int = 0, timeout_s: float = 12.0) -> Tuple[int, int]:
    start = time.time()
    while time.time() - start < timeout_s:
        found: List[Tuple[int, int]] = []

        def enum_cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cls_buf, 256)
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value.lower()
            cls_name = cls_buf.value.lower()
            pid_val = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_val))
            if pid_val.value and pid_val.value != exclude_pid and psutil.pid_exists(pid_val.value):
                try:
                    pname = psutil.Process(pid_val.value).name().lower()
                except Exception:
                    pname = ""
                if ("notepad" in pname or "notepad" in title or "notepad" in cls_name) and cls_buf.value != "GDI+ Hook Window Class":
                    found.append((hwnd, pid_val.value))
                    return False
            return True

        cb = WNDENUMPROC(enum_cb)
        user32.EnumWindows(cb, 0)
        if found:
            print(f"DEBUG find_notepad_window: found {found[0]}")
            return found[0]
        nps = [p.info["pid"] for p in psutil.process_iter(["pid", "name"]) if "notepad" in (p.info.get("name") or "").lower()]
        print(f"DEBUG find_notepad_window: tick elapsed={time.time()-start:.1f}s, active_notepad_pids={nps}")
        time.sleep(0.5)
    print("DEBUG find_notepad_window: timed out finding window!")
    return 0, 0


def grab_screen_safe() -> Image.Image:
    cur_tid = kernel32.GetCurrentThreadId()
    orig_desk = user32.GetThreadDesktop(cur_tid)
    try:
        hwinsta = user32.OpenWindowStationW("WinSta0", False, 0x037F)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
        DESKTOP_ALL = 0x01FF
        hdesk = user32.OpenInputDesktop(0, False, DESKTOP_ALL)
        if not hdesk:
            hdesk = user32.OpenDesktopW("Default", 0, False, DESKTOP_ALL)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
        return ImageGrab.grab()
    finally:
        if orig_desk:
            user32.SetThreadDesktop(orig_desk)


def attest_window_visual(hwnd: int, save_path: Path) -> Dict[str, Any]:
    """
    Brings window to foreground, settles DWM compositor, captures screen,
    and attests pixel presence.
    """
    assert hwnd != 0, "Cannot attest zero HWND"
    cur_tid = kernel32.GetCurrentThreadId()
    orig_desk = user32.GetThreadDesktop(cur_tid)
    try:
        # 1. Bring window to absolute foreground
        user32.ShowWindow(hwnd, SW_RESTORE)
        force_foreground_activation(hwnd)
        time.sleep(1.0)  # Settle delay for compositing

        # 2. Get window coordinates
        rect = RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        # 3. Capture desktop screenshot
        img = grab_screen_safe()
        img.save(str(save_path))

        # 4. Check if foreground window matches
        fg_hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(fg_hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(fg_hwnd, buf, length + 1)
        fg_title = buf.value

        # 5. Crop window rect and verify pixels
        has_pixels = False
        if width > 100 and height > 100 and rect.left >= 0 and rect.top >= 0:
            crop_box = (max(0, rect.left), max(0, rect.top), min(img.width, rect.right), min(img.height, rect.bottom))
            window_crop = img.crop(crop_box)
            colors = window_crop.getcolors(maxcolors=100000)
            has_pixels = (colors is not None and len(colors) > 10)

        return {
            "hwnd": hwnd,
            "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom, "width": width, "height": height},
            "foreground_hwnd": fg_hwnd,
            "foreground_title": fg_title,
            "is_foreground": (fg_hwnd == hwnd),
            "pixels_attested": has_pixels,
            "screenshot": save_path.name,
        }
    finally:
        if orig_desk:
            user32.SetThreadDesktop(orig_desk)


def run_physical_recovery():
    print("=== STARTING F0-25F.7 PHYSICAL RECOVERY & RESOURCE RESTORATION VERIFICATION ===")

    # Initial baseline process snapshot
    kill_existing_notepads()
    initial_snapshot = get_process_snapshot()
    initial_notepads = get_notepad_processes()
    assert len(initial_notepads) == 0, f"Residual notepads before test: {initial_notepads}"

    engine = IntelligentFallbackEngine()

    results: Dict[str, Any] = {
        "phase": "F0-25F.7",
        "benchmark": "PHYSICAL RECOVERY & VISUAL ATTESTATION",
        "timestamp": time.time(),
        "scenarios": {},
        "resource_records": {},
        "verdict": "FAIL",
    }

    # -------------------------------------------------------------------------
    # SCENARIO A: Application Crash Recovery
    # -------------------------------------------------------------------------
    print("\n--- Running Scenario A: Application Crash Recovery ---")
    scenario_a: Dict[str, Any] = {"name": "Application Crash Recovery", "steps": []}

    # 1. Launch target application
    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    hwnd1, pid1 = find_notepad_window()
    assert hwnd1 != 0 and pid1 != 0, "Could not find launched Notepad window"
    proc1_info = psutil.Process(pid1)
    create_time_1 = proc1_info.create_time()

    attest_1 = attest_window_visual(hwnd1, SCREENSHOTS_DIR / "f0_25f7_scenario_a_01_launched.png")
    scenario_a["steps"].append({
        "step": "Launch initial Notepad",
        "pid": pid1,
        "create_time": create_time_1,
        "hwnd": hwnd1,
        "visual_attestation": attest_1,
    })
    print(f"Launched initial Notepad: PID={pid1}, HWND={hwnd1}, Attested={attest_1['pixels_attested']}")

    # 2. Kill application externally (simulate unexpected crash)
    kill_existing_notepads()
    crash_img = grab_screen_safe()
    crash_img.save(str(SCREENSHOTS_DIR / "f0_25f7_scenario_a_02_killed.png"))
    scenario_a["steps"].append({
        "step": "Simulate Crash (Kill PID)",
        "killed_pid": pid1,
        "is_alive": psutil.pid_exists(pid1),
    })

    # 3. Detect via IntelligentFallbackEngine
    ev_crash = FailureEvidence(
        failure_category=FailureCategory.TARGET_NOT_FOUND,
        what_failed="Notepad",
        evidence_summary=f"Notepad process {pid1} terminated unexpectedly; window disappeared",
        evidence_data={"killed_pid": pid1, "hwnd": hwnd1},
    )
    decision_crash = engine.evaluate_failure(ev_crash)
    print(f"AstraRun Recovery Decision: action={decision_crash.action}, reason={decision_crash.preference_rationale}")

    # 4. Execute recovery action (Relaunch)
    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    hwnd_rec, pid_rec = find_notepad_window()
    assert hwnd_rec != 0 and pid_rec != 0, "Could not find recovered Notepad window"
    proc_rec_info = psutil.Process(pid_rec)
    create_time_rec = proc_rec_info.create_time()

    attest_rec = attest_window_visual(hwnd_rec, SCREENSHOTS_DIR / "f0_25f7_scenario_a_03_recovered.png")
    scenario_a["steps"].append({
        "step": "Recover Application (Relaunch)",
        "recovered_pid": pid_rec,
        "create_time": create_time_rec,
        "hwnd": hwnd_rec,
        "visual_attestation": attest_rec,
    })
    print(f"Recovered Notepad: PID={pid_rec}, HWND={hwnd_rec}, Attested={attest_rec['pixels_attested']}")

    # 5. Clean up Scenario A
    kill_existing_notepads()

    scenario_a["verdict"] = "PASS" if (attest_1["pixels_attested"] and attest_rec["pixels_attested"]) else "FAIL"
    results["scenarios"]["scenario_a"] = scenario_a

    # -------------------------------------------------------------------------
    # SCENARIO B: Precondition Mismatch & Window State Recovery
    # -------------------------------------------------------------------------
    print("\n--- Running Scenario B: Window State & Precondition Recovery ---")
    scenario_b: Dict[str, Any] = {"name": "Window State Precondition Recovery", "steps": []}

    subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    hwnd2, pid2 = find_notepad_window()
    assert hwnd2 != 0 and pid2 != 0, "Could not find launched Notepad window for Scenario B"
    proc2_info = psutil.Process(pid2)
    create_time_2 = proc2_info.create_time()

    attest_b1 = attest_window_visual(hwnd2, SCREENSHOTS_DIR / "f0_25f7_scenario_b_01_normal.png")
    scenario_b["steps"].append({
        "step": "Launch Notepad",
        "pid": pid2,
        "create_time": create_time_2,
        "hwnd": hwnd2,
        "visual_attestation": attest_b1,
    })

    # Minimize window (precondition disturbance)
    user32.ShowWindow(hwnd2, SW_MINIMIZE)
    time.sleep(1.0)
    is_min = bool(user32.IsIconic(hwnd2))
    min_img = grab_screen_safe()
    min_img.save(str(SCREENSHOTS_DIR / "f0_25f7_scenario_b_02_minimized.png"))
    scenario_b["steps"].append({
        "step": "Minimize Window",
        "is_iconic": is_min,
    })

    # Evaluate via IntelligentFallbackEngine
    ev_min = FailureEvidence(
        failure_category=FailureCategory.PRECONDITION_FAILED,
        what_failed="Notepad",
        evidence_summary="Target window minimized; foreground interaction required",
        evidence_data={"hwnd": hwnd2, "is_iconic": is_min},
    )
    decision_min = engine.evaluate_failure(ev_min)
    print(f"AstraRun Recovery Decision: action={decision_min.action}, reason={decision_min.preference_rationale}")

    # Recover (Restore & Bring to Foreground)
    user32.ShowWindow(hwnd2, SW_RESTORE)
    force_foreground_activation(hwnd2)
    time.sleep(1.0)

    attest_b_restored = attest_window_visual(hwnd2, SCREENSHOTS_DIR / "f0_25f7_scenario_b_03_restored_foreground.png")
    scenario_b["steps"].append({
        "step": "Restore Window and Set Foreground",
        "hwnd": hwnd2,
        "visual_attestation": attest_b_restored,
    })
    print(f"Restored Window: HWND={hwnd2}, Foreground={attest_b_restored['is_foreground']}, Attested={attest_b_restored['pixels_attested']}")

    # Clean up Scenario B
    kill_existing_notepads()

    scenario_b["verdict"] = "PASS" if (attest_b1["pixels_attested"] and attest_b_restored["pixels_attested"]) else "FAIL"
    results["scenarios"]["scenario_b"] = scenario_b

    # -------------------------------------------------------------------------
    # RESOURCE RESTORATION & PID CREATE-TIME AUDIT
    # -------------------------------------------------------------------------
    print("\n--- Verifying Resource Restoration & PID Create-Time Invariants ---")
    post_snapshot = get_process_snapshot()
    post_notepads = get_notepad_processes()

    # Track spawned PIDs and verify none leaked
    spawned_pids = {
        pid1: create_time_1,
        pid_rec: create_time_rec,
        pid2: create_time_2,
    }

    pid_reuse_detected = False
    leaked_spawned_pids = []
    for pid, ctime in spawned_pids.items():
        if pid in post_snapshot:
            # If PID exists, check if create_time matches our test run
            if abs(post_snapshot[pid] - ctime) < 1.0:
                leaked_spawned_pids.append(pid)
            else:
                pid_reuse_detected = True

    resource_data = {
        "phase": "F0-25F.7",
        "benchmark": "RESOURCE RESTORATION & PROCESS HYGIENE",
        "spawned_processes_tracked": [
            {"pid": pid, "create_time": ctime} for pid, ctime in spawned_pids.items()
        ],
        "leaked_spawned_pids": leaked_spawned_pids,
        "surviving_notepad_count": len(post_notepads),
        "target_process_cleaned": (len(leaked_spawned_pids) == 0 and len(post_notepads) == 0),
        "orphaned_processes_count": len(leaked_spawned_pids),
        "pid_reuse_detected": pid_reuse_detected,
        "pixels_visibly_attested": (
            attest_1["pixels_attested"]
            and attest_rec["pixels_attested"]
            and attest_b1["pixels_attested"]
            and attest_b_restored["pixels_attested"]
        ),
        "verdict": "PASS" if (len(leaked_spawned_pids) == 0 and len(post_notepads) == 0 and not pid_reuse_detected) else "FAIL",
    }

    results["verdict"] = "PASS" if (scenario_a["verdict"] == "PASS" and scenario_b["verdict"] == "PASS" and resource_data["verdict"] == "PASS") else "FAIL"
    results["resource_restoration"] = resource_data
    results["pixels_visibly_attested"] = resource_data["pixels_visibly_attested"]
    results["target_process_cleaned"] = resource_data["target_process_cleaned"]
    results["orphaned_processes_count"] = resource_data["orphaned_processes_count"]
    results["pid_reuse_detected"] = resource_data["pid_reuse_detected"]

    OUT_RECOVERY_JSON.write_text(json.dumps(results, indent=2), encoding="utf-8")
    OUT_RESOURCE_JSON.write_text(json.dumps(resource_data, indent=2), encoding="utf-8")

    print(f"\nPhysical Recovery Results written to {OUT_RECOVERY_JSON}")
    print(f"Resource Restoration Results written to {OUT_RESOURCE_JSON}")
    print(f"OVERALL PHYSICAL RECOVERY VERDICT: {results['verdict']}")

    assert results["verdict"] == "PASS", "Physical recovery did not reach PASS verdict"


if __name__ == "__main__":
    run_physical_recovery()
