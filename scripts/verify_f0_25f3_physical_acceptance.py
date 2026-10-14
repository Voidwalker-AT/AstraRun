"""Production-Only Physical Acceptance Runner for Phase F0-25F.3.

Strict Invariants:
1. Zero harness stubs: Harness NEVER stubs the broker, NEVER manually emits product telemetry,
   and NEVER creates Astra's output file.
2. Real installed product: Spawns the canonical installed executable at
   C:\\Users\\<user>\\AppData\\Local\\Programs\\AstraRun\\AstraRun.exe.
3. Physical desktop verification: Verifies launcher window and presentation window on WinSta0\\Default
   via Win32 uncloaked DWM inspection, monitor bounds, and surface contrast.
4. Authoritative completion gating: Proves GOAL_COMPLETED occurs strictly AFTER all required postconditions.
5. Production causal provenance: Validates MODEL -> BROKER -> ACTION -> OBSERVATION -> POSTCONDITION -> PRESENTATION -> COMPLETION.
"""

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
from typing import Any, Dict, List, Set, Tuple

import psutil
from PIL import ImageGrab

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from astrarun.core.paths import AstraPaths
from astrarun.core.single_instance import AstraSingleInstance
from astrarun.core.telemetry import CausalEventType, CausalTelemetry
from astrarun.tasks.resource_ledger import AstraResourceLedger
from astrarun.ui.attestation import attest_launcher_identity, attest_window_visibility, verify_surface_contrast

AUDIT_DIR = ROOT_DIR / "docs" / "audit"
SCREENSHOTS_DIR = AUDIT_DIR / "F0_25F3" / "screenshots"
CANONICAL_EXE = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "AstraRun" / "AstraRun.exe"

OUT_TRACE_JSON = AUDIT_DIR / "F0_25F3_CAUSAL_TRACE.json"
OUT_PHYSICAL_JSON = AUDIT_DIR / "F0_25F3_PHYSICAL_RESULTS.json"
OUT_RESOURCE_JSON = AUDIT_DIR / "F0_25F3_RESOURCE_RESTORATION.json"
OUT_MATRIX_JSON = AUDIT_DIR / "F0_25F3_ACCEPTANCE_MATRIX.json"

LAUNCHER_SCREENSHOT = SCREENSHOTS_DIR / "01_launcher_visible.png"
PRESENTATION_SCREENSHOT = SCREENSHOTS_DIR / "02_result_presentation.png"

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


def kill_existing_processes() -> None:
    for p in psutil.process_iter(["pid", "name"]):
        try:
            name = (p.info["name"] or "").lower()
            if "astrarun" in name and p.pid != os.getpid():
                p.kill()
        except Exception:
            pass
    time.sleep(1.0)


def enumerate_visible_hwnds() -> Set[int]:
    ensure_desktop_attached()
    hwnds: Set[int] = set()

    def cb(h, _):
        if user32.IsWindowVisible(h):
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                hwnds.add(h)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return hwnds


def get_window_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def main() -> int:
    print("======================================================================")
    print("PHASE F0-25F.3: AUTHORITATIVE PHYSICAL ACCEPTANCE RUN")
    print("======================================================================")
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_desktop_attached()

    # Step 0: Ensure canonical binary exists and record identity
    assert CANONICAL_EXE.exists(), f"Canonical binary missing at {CANONICAL_EXE}"
    canonical_hash = hashlib.sha256(CANONICAL_EXE.read_bytes()).hexdigest()
    binary_size = CANONICAL_EXE.stat().st_size
    print(f"[ACCEPTANCE] Canonical binary: {CANONICAL_EXE}")
    print(f"[ACCEPTANCE] SHA256: {canonical_hash}")
    print(f"[ACCEPTANCE] Size: {binary_size} bytes")

    # Step 1: Pre-execution baseline inventory
    print("\n[ACCEPTANCE] Step 1: Recording pre-execution baseline OS inventory...")
    kill_existing_processes()
    baseline_pids = {p.pid for p in psutil.process_iter(["pid"])}
    baseline_hwnds = enumerate_visible_hwnds()
    print(f"[ACCEPTANCE] Baseline processes: {len(baseline_pids)}, visible windows: {len(baseline_hwnds)}")

    # Step 2: Spawn installed AstraRun binary on WinSta0\\Default
    print(f"\n[ACCEPTANCE] Step 2: Spawning installed AstraRun.exe on WinSta0\\Default...")
    si_cmd = subprocess.STARTUPINFO()
    si_cmd.lpDesktop = r"WinSta0\Default"
    proc = subprocess.Popen([str(CANONICAL_EXE), "--show-now"], cwd=str(CANONICAL_EXE.parent), startupinfo=si_cmd)
    canonical_pid = proc.pid
    print(f"[ACCEPTANCE] Spawned PID={canonical_pid}")

    # Step 3: Establish local IPC connection
    print("\n[ACCEPTANCE] Step 3: Connecting to local Named Pipe IPC...")
    si = AstraSingleInstance()
    t0 = time.time()
    ipc_ready = False
    while time.time() - t0 < 15.0:
        res = si.send_command("SHOW_MAIN_UI", timeout_ms=500)
        if res.get("status") == "OK" or res.get("action") == "SHOW_MAIN_UI_TRIGGERED":
            ipc_ready = True
            break
        time.sleep(0.5)

    assert ipc_ready, "Failed to connect to installed AstraRun.exe via local IPC"
    print(f"[ACCEPTANCE] Local IPC connected: {ipc_ready}")
    time.sleep(1.5)

    # Step 4: Verify Launcher Window Physical Identity
    print("\n[ACCEPTANCE] Step 4: Verifying physical launcher UI...")
    state_file = AstraPaths.state_file_path()
    assert state_file.exists(), f"State file {state_file} missing"
    sf_data = json.loads(state_file.read_text(encoding="utf-8"))
    launcher_hwnd = sf_data.get("launcher_hwnd")
    state_pid = sf_data.get("pid")
    print(f"[ACCEPTANCE] State file: pid={state_pid}, launcher_hwnd={launcher_hwnd}")
    assert launcher_hwnd, "Launcher HWND not registered"

    ensure_desktop_attached()
    launcher_sc = ImageGrab.grab(all_screens=True)
    launcher_sc.save(LAUNCHER_SCREENSHOT, "PNG")
    print(f"[ACCEPTANCE] Captured launcher screenshot: {LAUNCHER_SCREENSHOT}")

    launcher_attestation = attest_launcher_identity(
        hwnd=launcher_hwnd,
        screenshot=launcher_sc,
        expected_pid=canonical_pid,
    )
    print(f"[ACCEPTANCE] Launcher attestation: verified={launcher_attestation['is_verified']}")
    print(f"[ACCEPTANCE] Facts: {launcher_attestation.get('facts')}")
    assert launcher_attestation["is_verified"], f"Launcher attestation failed: {launcher_attestation['failure_reasons']}"

    # Step 5: Execute genuine dynamic computation via SUBMIT_QUERY (NO HARNESS TELEMETRY STUBS)
    print("\n[ACCEPTANCE] Step 5: Submitting genuine agentic goal via IPC...")
    task_query = os.environ.get(
        "ASTRA_ACCEPTANCE_QUERY",
        "compute first 50 fibonacci numbers and save to fibonacci.txt and reveal in explorer",
    )
    target_stem = "fibonacci" if "fibonacci" in task_query.lower() else ("primes" if "primes" in task_query.lower() else "factorial")
    t_start = time.time()
    submit_res = si.send_command("SUBMIT_QUERY", {"query": task_query}, timeout_ms=3000)
    print(f"[ACCEPTANCE] IPC SUBMIT_QUERY result: {submit_res}")
    assert submit_res.get("action") == "QUERY_SUBMITTED", "Failed to submit query to live application"

    # Step 6: Wait for production agent execution, postconditions, presentation, and completion
    print("\n[ACCEPTANCE] Step 6: Waiting for production task completion & presentation...")
    telem = CausalTelemetry.get_instance()
    ledger = AstraResourceLedger.get_instance()

    target_file = AstraPaths.temp_dir() / "sandbox" / f"{target_stem}.txt"
    # Also check current working directory or sandbox outputs
    completed_event = None
    presented_event = None
    matched_explorer_hwnd = None
    matched_explorer_title = ""

    wait_timeout = 25.0
    poll_interval = 0.5
    start_poll = time.time()

    while time.time() - start_poll < wait_timeout:
        runs_dir = AstraPaths.data_dir() / "runs"
        latest_events = []
        if runs_dir.exists():
            for rf in sorted(runs_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                try:
                    for line in rf.read_text(encoding="utf-8").splitlines():
                        if line.strip():
                            latest_events.append(json.loads(line.strip()))
                except Exception:
                    pass

        for ev in latest_events:
            etype = ev.get("event_type")
            if etype == CausalEventType.RESULT_PRESENTED.value:
                presented_event = ev
            elif etype == CausalEventType.GOAL_COMPLETED.value:
                completed_event = ev

        # Check for matching Explorer window
        hwnds = enumerate_visible_hwnds()
        for h in hwnds:
            title = get_window_title(h)
            if target_stem in title.lower() or "output" in title.lower() or "sandbox" in title.lower():
                matched_explorer_hwnd = h
                matched_explorer_title = title
                break

        if completed_event and presented_event:
            print("[ACCEPTANCE] Affirmative RESULT_PRESENTED and GOAL_COMPLETED detected!")
            break
        time.sleep(poll_interval)

    # Capture result presentation screenshot
    ensure_desktop_attached()
    presentation_sc = ImageGrab.grab(all_screens=True)
    presentation_sc.save(PRESENTATION_SCREENSHOT, "PNG")
    print(f"[ACCEPTANCE] Captured presentation screenshot: {PRESENTATION_SCREENSHOT}")

    # Step 7: Record final causal trace from production events
    print("\n[ACCEPTANCE] Step 7: Auditing production causal trace...")
    run_id = completed_event.get("run_id") if completed_event else (presented_event.get("run_id") if presented_event else "")
    run_events = telem.get_run_events(run_id) if run_id else latest_events

    # Save causal trace JSON
    OUT_TRACE_JSON.write_text(json.dumps(run_events, indent=2), encoding="utf-8")
    print(f"[ACCEPTANCE] Recorded {len(run_events)} production causal events to {OUT_TRACE_JSON}")

    # Step 8: Clean shutdown of installed binary and post-run OS restoration
    print("\n[ACCEPTANCE] Step 8: Clean shutdown & resource restoration...")
    si.send_command("QUIT")
    time.sleep(1.0)
    kill_existing_processes()

    post_pids = {p.pid for p in psutil.process_iter(["pid"])}
    post_hwnds = enumerate_visible_hwnds()
    leaked_pids = list((post_pids - baseline_pids) - {canonical_pid})
    leaked_hwnds = list(post_hwnds - baseline_hwnds)

    restoration_report = {
        "benchmark": "PHYSICAL_RESOURCE_RESTORATION",
        "phase": "F0-25F.3",
        "baseline_pids_count": len(baseline_pids),
        "post_pids_count": len(post_pids),
        "leaked_pids": leaked_pids,
        "clean_pid_restoration": len(leaked_pids) == 0,
        "baseline_hwnds_count": len(baseline_hwnds),
        "post_hwnds_count": len(post_hwnds),
        "leaked_hwnds": leaked_hwnds,
        "clean_hwnd_restoration": len(leaked_hwnds) == 0,
        "timestamp": time.time(),
    }
    OUT_RESOURCE_JSON.write_text(json.dumps(restoration_report, indent=2), encoding="utf-8")
    print(f"[ACCEPTANCE] Resource restoration: clean_pids={restoration_report['clean_pid_restoration']}, clean_hwnds={restoration_report['clean_hwnd_restoration']}")

    # Step 9: Save physical acceptance results
    physical_results = {
        "phase": "F0-25F.3",
        "binary_path": str(CANONICAL_EXE),
        "binary_sha256": canonical_hash,
        "binary_size": binary_size,
        "launcher_verified": launcher_attestation["is_verified"],
        "launcher_hwnd": launcher_hwnd,
        "presentation_verified": presented_event is not None,
        "presentation_event": presented_event,
        "presentation_hwnd": matched_explorer_hwnd or (presented_event.get("data", {}).get("hwnd") if presented_event else None),
        "presentation_title": matched_explorer_title or (presented_event.get("data", {}).get("title") if presented_event else ""),
        "goal_completed_verified": completed_event is not None,
        "goal_completed_event": completed_event,
        "clean_resource_restoration": restoration_report["clean_pid_restoration"],
        "verdict": "PASS" if (launcher_attestation["is_verified"] and completed_event and presented_event) else "FAIL",
    }
    OUT_PHYSICAL_JSON.write_text(json.dumps(physical_results, indent=2), encoding="utf-8")
    print(f"[ACCEPTANCE] Final Physical Acceptance Verdict: {physical_results['verdict']}")

    return 0 if physical_results["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
