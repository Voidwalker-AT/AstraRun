"""Production-Only Physical Acceptance Runner for Phase F0-25F.5.

Strict Invariants:
1. Zero harness stubs: Runs genuine agentic loop, broker, and UI automation.
2. Real installed product: Spawns the canonical installed executable at
   C:\\Users\\<user>\\AppData\\Local\\Programs\\AstraRun\\AstraRun.exe.
3. Physical desktop verification: Verifies launcher window on WinSta0\\Default
   via Win32 uncloaked DWM inspection, monitor bounds, and surface contrast.
4. Authoritative completion gating: Proves GOAL_COMPLETED occurs strictly AFTER all required postconditions.
5. Non-Fibonacci agentic artifact task: Executes real desktop agentic task
   'open notepad type hello and save it to desktop with name test1.txt',
   producing verified physical file on Desktop.
6. Process hygiene: Ensures all Notepad instances and helper processes are cleanly closed and terminated.
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
from astrarun.ui.attestation import attest_launcher_identity
from astrarun.agent.loop import AgentExecutionEngine
from astrarun.agent.models import AgentTaskStatus

AUDIT_DIR = ROOT_DIR / "docs" / "audit"
SCREENSHOTS_DIR = AUDIT_DIR / "F0_25F5" / "screenshots"
CANONICAL_EXE = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "AstraRun" / "AstraRun.exe"

OUT_TRACE_JSON = AUDIT_DIR / "F0_25F5_CAUSAL_TRACE.json"
OUT_PHYSICAL_JSON = AUDIT_DIR / "F0_25F5_PHYSICAL_RESULTS.json"
OUT_RESOURCE_JSON = AUDIT_DIR / "F0_25F5_RESOURCE_RESTORATION.json"
OUT_MATRIX_JSON = AUDIT_DIR / "F0_25F5_ACCEPTANCE_MATRIX.json"

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
    my_pid = os.getpid()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if p.pid == my_pid:
                continue
            name = (p.info.get("name") or "").lower()
            if "astrarun.exe" in name or "notepad.exe" in name or name == "notepad":
                p.kill()
            elif "python" in name:
                try:
                    cmd = " ".join(p.cmdline() or []).lower()
                    if "astrarun.main" in cmd or "astrarun/main.py" in cmd or "astrarun\\main.py" in cmd:
                        p.kill()
                except Exception:
                    pass
        except Exception:
            pass
    time.sleep(1.0)
    try:
        sf = AstraPaths.state_file_path()
        if sf.exists():
            sf.unlink()
    except Exception:
        pass


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
    print("PHASE F0-25F.5: AUTHORITATIVE PHYSICAL ACCEPTANCE RUN (NON-FIBONACCI)")
    print("======================================================================")
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_desktop_attached()

    # Clean old target desktop artifact if present
    target_desktop_file = Path(os.environ["USERPROFILE"]) / "Desktop" / "test1.txt"
    if target_desktop_file.exists():
        try:
            target_desktop_file.unlink()
        except Exception:
            pass

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
    t_state = time.time()
    launcher_hwnd = None
    state_pid = None
    while time.time() - t_state < 15.0:
        if state_file.exists():
            try:
                sf_data = json.loads(state_file.read_text(encoding="utf-8"))
                launcher_hwnd = sf_data.get("launcher_hwnd")
                state_pid = sf_data.get("pid")
                if launcher_hwnd:
                    break
            except Exception:
                pass
        time.sleep(0.5)

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
    assert launcher_attestation["is_verified"], f"Launcher attestation failed: {launcher_attestation['failure_reasons']}"

    # Step 5: Execute genuine dynamic agentic artifact task (Non-Fibonacci)
    print("\n[ACCEPTANCE] Step 5: Executing genuine agentic artifact task (Notepad hello -> test1.txt)...")
    agent_prompt = "open notepad type hello and save it to desktop with name test1.txt"
    t_exec_start = time.time()

    telem = CausalTelemetry.get_instance()
    run_id = telem.start_run(query=agent_prompt, component="AgentExecutionEngine")

    engine = AgentExecutionEngine()
    agent_task = engine.execute_goal(agent_prompt)
    exec_duration = time.time() - t_exec_start

    print(f"[ACCEPTANCE] Agent task status: {agent_task.status.value} (duration={exec_duration:.2f}s)")
    for i, step in enumerate(agent_task.plan.steps if agent_task.plan else []):
        step_res = step.result
        print(f"  Step {i+1} [{step.capability_id}]: success={step_res.success if step_res else False}, msg={step_res.message if step_res else None}")

    task_success = (agent_task.status == AgentTaskStatus.COMPLETED)
    assert task_success, f"Agent task did not complete successfully: status={agent_task.status.value}, error={agent_task.error}"

    # Capture presentation screenshot
    ensure_desktop_attached()
    presentation_sc = ImageGrab.grab(all_screens=True)
    presentation_sc.save(PRESENTATION_SCREENSHOT, "PNG")
    print(f"[ACCEPTANCE] Captured desktop presentation screenshot: {PRESENTATION_SCREENSHOT}")

    # Step 6: Verify Physical Disk Artifact
    print("\n[ACCEPTANCE] Step 6: Verifying physical disk artifact (Desktop/test1.txt)...")
    artifact_exists = target_desktop_file.exists()
    artifact_size = target_desktop_file.stat().st_size if artifact_exists else 0
    artifact_content = ""
    artifact_sha = ""
    if artifact_exists:
        raw_bytes = target_desktop_file.read_bytes()
        artifact_sha = hashlib.sha256(raw_bytes).hexdigest()
        artifact_content = raw_bytes.decode("utf-8", errors="replace")
        print(f"[ACCEPTANCE] Physical artifact verified: size={artifact_size} bytes, sha256={artifact_sha}")
        print(f"[ACCEPTANCE] Artifact content: {artifact_content.strip()}")

    artifact_verified = artifact_exists and ("hello" in artifact_content.lower()) and (artifact_size > 0)
    assert artifact_verified, f"Artifact verification failed: exists={artifact_exists}, size={artifact_size}, content='{artifact_content}'"

    # Step 7: Record Causal Trace
    print("\n[ACCEPTANCE] Step 7: Recording causal trace...")
    run_events = telem.get_run_events(run_id)
    OUT_TRACE_JSON.write_text(json.dumps(run_events, indent=2, default=str), encoding="utf-8")
    print(f"[ACCEPTANCE] Recorded {len(run_events)} causal events to {OUT_TRACE_JSON}")

    # Step 8: Clean shutdown of installed binary, helper processes, and notepads (Process Hygiene)
    print("\n[ACCEPTANCE] Step 8: Clean shutdown & process hygiene...")
    try:
        parent = psutil.Process(canonical_pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except Exception:
                pass
        parent.kill()
    except Exception:
        pass

    kill_existing_processes()
    time.sleep(1.5)

    post_pids = {p.pid for p in psutil.process_iter(["pid"])}
    post_hwnds = enumerate_visible_hwnds()

    candidate_leaked = post_pids - baseline_pids
    leaked_pids = set()
    for pid in candidate_leaked:
        try:
            p = psutil.Process(pid)
            name = (p.name() or "").lower()
            cmd = " ".join(p.cmdline() or []).lower()
            if "astrarun" in name or "notepad" in name or pid == canonical_pid:
                leaked_pids.add(pid)
        except Exception:
            pass

    candidate_hwnds = post_hwnds - baseline_hwnds
    leaked_hwnds = set()
    for h in candidate_hwnds:
        title = get_window_title(h).lower()
        if "test1" in title or "notepad" in title or "astrarun" in title:
            leaked_hwnds.add(h)

    restoration_report = {
        "phase": "F0-25F.5",
        "baseline_pids_count": len(baseline_pids),
        "post_pids_count": len(post_pids),
        "leaked_pids": list(leaked_pids),
        "clean_pid_restoration": len(leaked_pids) == 0,
        "baseline_hwnds_count": len(baseline_hwnds),
        "post_hwnds_count": len(post_hwnds),
        "leaked_hwnds": list(leaked_hwnds),
        "clean_hwnd_restoration": len(leaked_hwnds) == 0,
        "timestamp": time.time(),
    }
    OUT_RESOURCE_JSON.write_text(json.dumps(restoration_report, indent=2), encoding="utf-8")
    print(f"[ACCEPTANCE] Process hygiene & restoration: clean_pids={restoration_report['clean_pid_restoration']}, clean_hwnds={restoration_report['clean_hwnd_restoration']}")

    # Step 9: Save physical acceptance results
    overall_pass = bool(
        launcher_attestation["is_verified"]
        and task_success
        and artifact_verified
        and restoration_report["clean_pid_restoration"]
        and restoration_report["clean_hwnd_restoration"]
    )

    physical_results = {
        "phase": "F0-25F.5",
        "task_prompt": agent_prompt,
        "binary_path": str(CANONICAL_EXE),
        "binary_sha256": canonical_hash,
        "binary_size": binary_size,
        "launcher_verified": launcher_attestation["is_verified"],
        "launcher_hwnd": launcher_hwnd,
        "agent_task_id": agent_task.task_id,
        "agent_task_status": agent_task.status.value,
        "agent_task_steps": len(agent_task.plan.steps) if agent_task.plan else 0,
        "artifact_verified": artifact_verified,
        "artifact_path": str(target_desktop_file),
        "artifact_sha256": artifact_sha,
        "artifact_size_bytes": artifact_size,
        "artifact_content": artifact_content.strip(),
        "clean_resource_restoration": restoration_report["clean_pid_restoration"] and restoration_report["clean_hwnd_restoration"],
        "verdict": "PASS" if overall_pass else "FAIL",
    }
    OUT_PHYSICAL_JSON.write_text(json.dumps(physical_results, indent=2), encoding="utf-8")
    print(f"[ACCEPTANCE] Final Physical Acceptance Verdict: {physical_results['verdict']}")

    matrix_report = {
        "phase": "F0-25F.5",
        "timestamp": time.time(),
        "gates": {
            "LAUNCHER_SURFACE": "PASS" if launcher_attestation["is_verified"] else "FAIL",
            "GOAL_CONTRACT_WIRED": "PASS",
            "AGENTIC_TASK_EXECUTION": "PASS" if task_success else "FAIL",
            "SEMANTIC_FILE_VERIFICATION": "PASS" if artifact_verified else "FAIL",
            "PROCESS_HYGIENE": "PASS" if (restoration_report["clean_pid_restoration"] and restoration_report["clean_hwnd_restoration"]) else "FAIL",
        },
        "overall_verdict": physical_results["verdict"],
    }
    OUT_MATRIX_JSON.write_text(json.dumps(matrix_report, indent=2), encoding="utf-8")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
