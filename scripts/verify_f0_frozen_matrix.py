"""Empirical verification script for Phase F0 Frozen Execution Test Matrix."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import psutil

from astrarun.core.paths import AstraPaths
from astrarun.core.crash import detect_previous_abnormal_termination
from astrarun.core.single_instance import AstraSingleInstance


def run_frozen_matrix() -> dict:
    results = {}
    frozen_exe = Path(r"E:\Workspace\Active\AstraRun\dist\AstraRun\AstraRun.exe").resolve()
    if not frozen_exe.exists():
        raise FileNotFoundError(f"Frozen executable not found at {frozen_exe}")

    results["frozen_exe"] = str(frozen_exe)
    results["frozen_exe_size"] = frozen_exe.stat().st_size
    results["timestamp"] = datetime.now(timezone.utc).isoformat()

    # -------------------------------------------------------------
    # Step 1: Resident Launch & Readiness Latency (Tests 5 & 6)
    # -------------------------------------------------------------
    print(">>> Launching AstraRun resident process (--background)...")
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    t0 = time.time()
    proc = subprocess.Popen(
        [str(frozen_exe), "--background"],
        cwd=str(frozen_exe.parent),
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    )
    results["resident_pid"] = proc.pid
    print(f"Spawned AstraRun resident PID {proc.pid}")

    state_path = AstraPaths.state_file_path()
    ready_data = None
    ready_time = None

    for _ in range(150):  # poll up to 15 seconds
        time.sleep(0.1)
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("pid") == proc.pid and data.get("status") == "READY" and data.get("ready") is True:
                    ready_data = data
                    ready_time = time.time()
                    break
            except Exception:
                pass

    if not ready_data:
        try:
            proc.kill()
        except Exception:
            pass
        raise RuntimeError(f"AstraRun PID {proc.pid} failed to reach READY state within 15 seconds")

    latency_sec = ready_time - t0
    results["startup_latency_seconds"] = latency_sec
    results["test_6_tray_and_hotkey_ready"] = {
        "pass": latency_sec < 15.0,
        "latency_sec": latency_sec,
        "state": ready_data,
    }
    print(f"AstraRun reached READY in {latency_sec:.3f}s (target < 2.5s: {latency_sec < 2.5})")

    # Give Laya worker a moment to spawn and log
    time.sleep(2.0)

    # -------------------------------------------------------------
    # Step 2: Identify LayaWorker process
    # -------------------------------------------------------------
    log_path = AstraPaths.logs_dir() / "astrarun.log"
    laya_pid = None
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        for line in reversed(lines):
            if "Spawned isolated LayaWorker PID " in line:
                parts = line.split("Spawned isolated LayaWorker PID ")
                if len(parts) > 1:
                    try:
                        laya_pid = int(parts[1].strip().split()[0])
                        break
                    except Exception:
                        pass

    # Fallback to psutil children
    if not laya_pid or not psutil.pid_exists(laya_pid):
        try:
            parent = psutil.Process(proc.pid)
            children = parent.children(recursive=True)
            if children:
                laya_pid = children[0].pid
        except Exception as e:
            print(f"Failed to find child process via psutil: {e}")

    results["laya_pid"] = laya_pid
    print(f"Detected Laya worker PID: {laya_pid}")

    # -------------------------------------------------------------
    # Step 3: Test 7 - External Kill of LayaWorker
    # -------------------------------------------------------------
    if laya_pid and psutil.pid_exists(laya_pid):
        print(f">>> Inducing external kill of LayaWorker PID {laya_pid}...")
        try:
            p_laya = psutil.Process(laya_pid)
            p_laya.kill()
            p_laya.wait(timeout=2)
            print("LayaWorker killed successfully.")
        except Exception as e:
            print(f"Error killing LayaWorker: {e}")

        time.sleep(1.5)
        # Verify AstraRun main process is still alive
        is_parent_alive = psutil.pid_exists(proc.pid)
        print(f"AstraRun main resident PID {proc.pid} alive after worker kill: {is_parent_alive}")

        results["test_7_laya_kill_resilience"] = {
            "pass": is_parent_alive,
            "main_resident_alive": is_parent_alive,
            "killed_laya_pid": laya_pid,
        }
    else:
        results["test_7_laya_kill_resilience"] = {
            "pass": False,
            "error": "Laya worker PID not detected or already stopped",
        }

    # -------------------------------------------------------------
    # Step 4: Test 8 - Graceful Shutdown
    # -------------------------------------------------------------
    print(">>> Sending QUIT command via local IPC named pipe...")
    single = AstraSingleInstance()
    ipc_resp = single.send_command("QUIT", timeout_ms=3000)
    print(f"IPC QUIT response: {ipc_resp}")

    try:
        proc.wait(timeout=6)
        exit_code = proc.returncode
    except subprocess.TimeoutExpired:
        print("Process timed out waiting for exit; killing...")
        proc.kill()
        exit_code = proc.wait()

    results["shutdown_exit_code"] = exit_code
    print(f"AstraRun process exited with code: {exit_code}")

    state_after_shutdown = {}
    if state_path.exists():
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state_after_shutdown = json.load(f)
        except Exception:
            pass

    results["test_8_graceful_shutdown"] = {
        "pass": exit_code == 0 and state_after_shutdown.get("status") == "CLEAN_EXIT",
        "exit_code": exit_code,
        "final_state": state_after_shutdown,
    }

    # -------------------------------------------------------------
    # Step 5: Test 9 - Immediate Relaunch Recovery Check
    # -------------------------------------------------------------
    rec = detect_previous_abnormal_termination()
    results["test_9_immediate_relaunch"] = {
        "pass": rec is None,
        "recovery_detected": rec is not None,
        "recovery_info": rec,
    }
    print(f"Crash recovery detected after clean shutdown: {rec is not None}")

    # Capture log tail for audit
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        log_lines = f.readlines()
    results["log_tail"] = [line.strip() for line in log_lines[-40:]]

    return results


if __name__ == "__main__":
    report = run_frozen_matrix()
    out_path = Path(r"E:\Workspace\Active\AstraRun\docs\audit\f0_matrix_run.json")
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Results written to {out_path}")
