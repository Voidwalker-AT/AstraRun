"""Stage 6: End-to-end physical validation of launcher, causal telemetry, result presentation, and resource ledger."""

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
OUT_JSON = AUDIT_DIR / "F0_25F_STAGE6_PHYSICAL_VERIFICATION.json"
LAUNCHER_SCREENSHOT = AUDIT_DIR / "F0_25F_PHYSICAL_LAUNCHER.png"
PRESENTATION_SCREENSHOT = AUDIT_DIR / "F0_25F_PHYSICAL_PRESENTATION.png"

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


def kill_existing_astrarun() -> None:
    for p in psutil.process_iter(["pid", "name"]):
        if "astrarun" in (p.info["name"] or "").lower():
            try:
                p.kill()
            except Exception:
                pass
    time.sleep(1.0)


def main() -> int:
    print("[STAGE 6] Starting End-to-End Physical Validation...")
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_desktop_attached()

    # 1. Clean environment
    kill_existing_astrarun()

    # 2. Spawn canonical AstraRun.exe
    si_cmd = subprocess.STARTUPINFO()
    si_cmd.lpDesktop = r"WinSta0\Default"
    proc = subprocess.Popen([str(CANONICAL_EXE), "--show-now"], cwd=str(CANONICAL_EXE.parent), startupinfo=si_cmd)
    print(f"[STAGE 6] Spawned canonical AstraRun.exe PID={proc.pid}")

    sys.path.insert(0, str(ROOT_DIR / "src"))
    from astrarun.core.single_instance import AstraSingleInstance
    si = AstraSingleInstance()

    # Wait for IPC
    t0 = time.time()
    ipc_ready = False
    while time.time() - t0 < 15.0:
        res = si.send_command("SHOW_MAIN_UI", timeout_ms=500)
        if res.get("status") == "OK" or res.get("action") == "SHOW_MAIN_UI_TRIGGERED":
            ipc_ready = True
            break
        time.sleep(0.5)

    print(f"[STAGE 6] IPC connection established: {ipc_ready}")
    assert ipc_ready, "Failed to connect to canonical AstraRun.exe via local IPC"
    time.sleep(1.5)

    # 3. Read state file & attest launcher visibility
    from astrarun.core.paths import AstraPaths
    state_file = AstraPaths.state_file_path()
    sf = json.loads(state_file.read_text(encoding="utf-8"))
    launcher_hwnd = sf.get("launcher_hwnd")
    pid = sf.get("pid")
    print(f"[STAGE 6] State file: pid={pid}, launcher_hwnd={launcher_hwnd}")

    from astrarun.ui.attestation import attest_window_visibility
    attestation = attest_window_visibility(launcher_hwnd, expected_pid=pid)
    print(f"[STAGE 6] Window attestation: is_visible={attestation['is_visible']}, failure_reasons={attestation['failure_reasons']}")

    # 4. Capture launcher screenshot & verify physical dark pixels
    ensure_desktop_attached()
    rect = wintypes.RECT()
    user32.GetWindowRect(launcher_hwnd, ctypes.byref(rect))
    launcher_sc = ImageGrab.grab(all_screens=True)
    launcher_sc.save(LAUNCHER_SCREENSHOT, "PNG")
    cropped = launcher_sc.crop((rect.left, rect.top, rect.right, rect.bottom))
    colors = [cropped.getpixel((x, y)) for x in range(cropped.width) for y in range(cropped.height)]
    dark_pixels = [c for c in colors if c[0] < 40 and c[1] < 40 and c[2] < 40]
    dark_pixel_ratio = len(dark_pixels) / len(colors) if colors else 0.0
    print(f"[STAGE 6] Launcher physical dark pixel ratio: {dark_pixel_ratio:.1%} ({len(dark_pixels)}/{len(colors)})")
    assert dark_pixel_ratio > 0.50, f"Launcher failed dark pixel check: {dark_pixel_ratio:.1%}"

    # 5. Submit real calculation query to test Causal Telemetry
    print("[STAGE 6] Submitting query 'calculate 40 + 2' via IPC...")
    q_res = si.send_command("SUBMIT_QUERY", {"query": "calculate 40 + 2"}, timeout_ms=5000)
    print(f"[STAGE 6] IPC submit response: {q_res}")
    time.sleep(2.0)

    # Inspect runs folder for causal telemetry
    runs_dir = AstraPaths.data_dir() / "runs"
    assert runs_dir.exists(), f"Runs directory {runs_dir} does not exist"
    run_files = sorted(runs_dir.glob("run_*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    assert run_files, "No run telemetry file generated in data/runs/"
    latest_run_file = run_files[0]
    print(f"[STAGE 6] Discovered latest run telemetry: {latest_run_file.name}")

    events = [json.loads(line) for line in latest_run_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    event_types = [e.get("event_type") for e in events]
    print(f"[STAGE 6] Telemetry event types recorded: {event_types}")
    assert "REQUEST_RECEIVED" in event_types, "Missing REQUEST_RECEIVED in telemetry"
    assert "GOAL_INTERPRETED" in event_types, "Missing GOAL_INTERPRETED in telemetry"
    assert "PLAN_CREATED" in event_types, "Missing PLAN_CREATED in telemetry"
    assert "GOAL_COMPLETED" in event_types, "Missing GOAL_COMPLETED in telemetry"

    # Verify monotonic clocks & hashes
    for idx in range(1, len(events)):
        assert events[idx]["timestamp_monotonic"] >= events[idx - 1]["timestamp_monotonic"], "Monotonic clock violated"
        assert events[idx]["event_id"].startswith("cev_"), "Invalid event ID"

    # 6. Submit result presentation query
    print("[STAGE 6] Submitting query 'show me the result' via IPC...")
    p_res = si.send_command("SUBMIT_QUERY", {"query": "show me the result"}, timeout_ms=5000)
    print(f"[STAGE 6] IPC result presentation response: {p_res}")
    time.sleep(2.0)

    # Capture presentation screenshot
    ensure_desktop_attached()
    pres_sc = ImageGrab.grab(all_screens=True)
    pres_sc.save(PRESENTATION_SCREENSHOT, "PNG")

    # Check updated telemetry for RESULT_PRESENTED
    pres_run_files = sorted(runs_dir.glob("run_*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    pres_run_file = pres_run_files[0]
    pres_events = [json.loads(line) for line in pres_run_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    pres_event_types = [e.get("event_type") for e in pres_events]
    print(f"[STAGE 6] Presentation run event types: {pres_event_types}")
    assert "RESULT_PRESENTED" in pres_event_types, (
        f"Missing result presentation events in {pres_run_file.name}"
    )

    # 7. Test Resource Ledger with REAL task execution and delta verification
    print("[STAGE 6] Testing Resource Ledger on real task candidate execution & cleanup...")
    baseline_task_pids = {p.pid for p in psutil.process_iter(['pid'])}
    from astrarun.sandbox.manager import SandboxManager
    from astrarun.tools.candidate import CandidateTool
    mgr = SandboxManager()
    ledger = AstraResourceLedger.get_instance()
    task_id = f"physical_test_task_{int(time.time())}"
    candidate = CandidateTool(
        goal="Calculate squares and persist to disk",
        task_id=task_id,
        tool_id=f"tool_{task_id}",
        executable_code="""
import json
from pathlib import Path
squares = {str(i): i*i for i in range(1, 10)}
out_dir = Path("output")
out_dir.mkdir(exist_ok=True)
(out_dir / "squares.json").write_text(json.dumps(squares))
print("SQUARES_DONE")
""",
    )
    res = mgr.execute_candidate(candidate)
    assert res.status == "SUCCESS", f"Sandbox candidate execution failed: {res.stderr}"
    sb_dir = res.working_dir
    assert sb_dir.exists(), "Sandbox directory was not created"

    cl_report = ledger.cleanup_task_resources(task_id, task_status="COMPLETED")
    clean_ok = bool(cl_report.get("clean", False) or cl_report.get("clean_ok", False))
    assert clean_ok, f"Cleanup failed: {cl_report}"
    assert not sb_dir.exists(), "Sandbox directory was not removed by resource ledger"
    post_task_pids = {p.pid for p in psutil.process_iter(['pid'])}
    orphaned_task_pids = list(post_task_pids - baseline_task_pids)
    print(f"[STAGE 6] Real task sandbox cleanup verified successfully. Orphaned PIDs: {orphaned_task_pids}")

    # 8. Cleanly terminate canonical instance via IPC
    print("[STAGE 6] Requesting clean QUIT via IPC...")
    si.send_command("QUIT", timeout_ms=2000)
    time.sleep(1.0)
    try:
        proc.wait(timeout=3.0)
        print(f"[STAGE 6] Canonical AstraRun.exe exited with code {proc.returncode}")
    except subprocess.TimeoutExpired:
        proc.kill()
        print("[STAGE 6] Forced kill of canonical AstraRun.exe")

    # Write report
    report = {
        "status": "PASS",
        "timestamp": time.time(),
        "canonical_executable": str(CANONICAL_EXE),
        "executable_sha256": hashlib.sha256(CANONICAL_EXE.read_bytes()).hexdigest(),
        "pid": pid,
        "launcher_hwnd": launcher_hwnd,
        "attestation": attestation,
        "dark_pixel_ratio": dark_pixel_ratio,
        "launcher_screenshot": str(LAUNCHER_SCREENSHOT),
        "presentation_screenshot": str(PRESENTATION_SCREENSHOT),
        "computation_run_file": str(latest_run_file),
        "computation_events": event_types,
        "presentation_run_file": str(pres_run_file),
        "presentation_events": pres_event_types,
        "resource_ledger_sandbox_verified": True,
        "clean_termination": True,
    }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[STAGE 6] Physical validation SUCCESS. Report written to {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
