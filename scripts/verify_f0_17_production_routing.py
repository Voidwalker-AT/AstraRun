"""Empirical verification script for Phase F0-17 Production Routing Closure.

Tests the INSTALLED AstraRun product (C:\\Users\\hp\\AppData\\Local\\Programs\\AstraRun\\AstraRun.exe)
for the exact human-observed natural language command:
    "can u open calculator"
both in headless execution mode and through the live resident GUI + IPC summon flow,
verifying:
- Natural-language decomposition and routing
- ExecutionBroker -> ActionGate authorization
- Desktop capability execution (Calculator window opens)
- AstraResourceLedger tracking (PID/HWND recorded, astra_created=True)
- Zero "Blocked: Blocked: Target tool 'unknown'" or tool registration errors
- Clean resource closure and graceful shutdown

Generates docs/audit/F0_17_PRODUCTION_ROUTING_EVIDENCE.json.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import psutil

from astrarun.core.crash import detect_previous_abnormal_termination
from astrarun.core.paths import AstraPaths
from astrarun.core.single_instance import AstraSingleInstance
from astrarun.tasks.resource_ledger import AstraResourceLedger


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def get_git_commit() -> str:
    res = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
    return res.stdout.strip()


def get_source_tree_hash() -> str:
    files = subprocess.check_output(["git", "ls-files"], text=True).splitlines()
    h = hashlib.sha256()
    for f in sorted(files):
        if os.path.isfile(f):
            h.update(f.encode("utf-8") + b"\0" + open(f, "rb").read())
    return h.hexdigest()


def ensure_no_lingering_processes() -> None:
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info["name"] or "").lower()
            if name in ("astrarun.exe", "llama-server.exe", "calculatorapp.exe", "calc.exe"):
                proc.kill()
        except Exception:
            pass
    time.sleep(1.0)


def run_f0_17_verification() -> Dict[str, Any]:
    print("=" * 75)
    print("PHASE F0-17: FROZEN PRODUCTION ROUTING EMPIRICAL VERIFICATION")
    print("=" * 75)

    ensure_no_lingering_processes()

    repo_root = Path(r"E:\Workspace\Active\AstraRun").resolve()
    installed_exe = Path(os.path.expandvars(r"%LOCALAPPDATA%\Programs\AstraRun\AstraRun.exe")).resolve()
    built_exe = (repo_root / "dist" / "AstraRun" / "AstraRun.exe").resolve()
    installer_exe = (repo_root / "dist" / "installer" / "AstraRun-Setup-1.0.0-rc.6-dogfood.exe").resolve()

    if not installed_exe.exists():
        raise FileNotFoundError(f"Installed executable not found: {installed_exe}")
    if not built_exe.exists():
        raise FileNotFoundError(f"Built executable not found: {built_exe}")
    if not installer_exe.exists():
        raise FileNotFoundError(f"Installer not found: {installer_exe}")

    commit_sha = get_git_commit()
    source_tree_hash = get_source_tree_hash()
    installed_exe_hash = sha256_file(installed_exe)
    built_exe_hash = sha256_file(built_exe)
    installer_hash = sha256_file(installer_exe)

    print(f"[*] Git Commit:          {commit_sha}")
    print(f"[*] Source Tree Hash:    {source_tree_hash}")
    print(f"[*] Installed EXE Path:  {installed_exe}")
    print(f"[*] Installed EXE SHA:   {installed_exe_hash}")
    print(f"[*] Built EXE SHA-256:   {built_exe_hash}")
    print(f"[*] Installer SHA-256:   {installer_hash}")
    assert built_exe_hash == installed_exe_hash, "Installed executable hash does not match built executable!"

    results: Dict[str, Any] = {
        "milestone": "F0-17",
        "description": "Production routing fix verification for natural language 'can u open calculator'",
        "commit_sha": commit_sha,
        "source_tree_hash": source_tree_hash,
        "installed_exe_path": str(installed_exe),
        "installed_exe_sha256": installed_exe_hash,
        "installed_exe_size_bytes": installed_exe.stat().st_size,
        "installer_path": str(installer_exe),
        "installer_sha256": installer_hash,
        "installer_size_bytes": installer_exe.stat().st_size,
        "test_timestamp": datetime.now(timezone.utc).isoformat(),
        "human_reported_defect": {
            "query": "can u open calculator",
            "previous_observed_error": "Blocked: Blocked: Target tool 'unknown' is not registered",
            "expected_outcome": "Calculator window opens without error; registered in AstraResourceLedger",
        },
        "tests": {},
    }

    # -------------------------------------------------------------
    # TEST 1: Headless Execution Mode ("can u open calculator")
    # -------------------------------------------------------------
    print("\n" + "=" * 75)
    print("TEST 1: HEADLESS EXECUTION of 'can u open calculator'")
    print("=" * 75)
    t0 = time.perf_counter()
    headless_res = subprocess.run(
        [str(installed_exe), "--run-command", "can u open calculator"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    t_headless = (time.perf_counter() - t0) * 1000
    print(f"[*] Headless exit code: {headless_res.returncode} (latency={t_headless:.1f}ms)")
    print(f"[*] Headless stdout: {headless_res.stdout.strip()}")
    print(f"[*] Headless stderr: {headless_res.stderr.strip()}")

    # Verify calculator process
    calc_procs = [p for p in psutil.process_iter(["pid", "name"]) if (p.info["name"] or "").lower() in ("calculatorapp.exe", "calc.exe")]
    print(f"[*] Running Calculator processes found: {len(calc_procs)}")

    # Verify resource ledger
    ledger = AstraResourceLedger.get_instance()
    active_calc = [
        r for r in ledger.list_active_astra_resources()
        if "calc" in r.launching_capability.lower() or (r.document_path and "calc" in r.document_path.lower())
    ]
    print(f"[*] Active Astra-owned resources in ledger: {len(active_calc)}")

    headless_pass = (
        headless_res.returncode == 0
        and len(calc_procs) > 0
        and len(active_calc) > 0
        and active_calc[-1].astra_created is True
        and "Target tool 'unknown'" not in headless_res.stdout
        and "Target tool 'unknown'" not in headless_res.stderr
    )

    results["tests"]["headless_routing"] = {
        "pass": headless_pass,
        "command": "can u open calculator",
        "exit_code": headless_res.returncode,
        "latency_ms": t_headless,
        "calculator_procs_count": len(calc_procs),
        "ledger_resource_count": len(active_calc),
        "ledger_resource_id": active_calc[-1].resource_id if active_calc else None,
        "ledger_pid": active_calc[-1].pid if active_calc else None,
        "ledger_hwnd": active_calc[-1].hwnd if active_calc else None,
        "astra_created": active_calc[-1].astra_created if active_calc else None,
        "unknown_tool_error_absent": "Target tool 'unknown'" not in headless_res.stdout + headless_res.stderr,
    }

    # Clean up launched calculator
    if active_calc:
        ledger.close_owned_resource(active_calc[-1])
    ensure_no_lingering_processes()
    print(f"[TEST 1 VERDICT] Headless 'can u open calculator': {'PASS' if headless_pass else 'FAIL'}")
    assert headless_pass, "Headless execution of 'can u open calculator' failed!"

    # -------------------------------------------------------------
    # TEST 2: Live Resident GUI + IPC Execution ("can u open calculator")
    # -------------------------------------------------------------
    print("\n" + "=" * 75)
    print("TEST 2: LIVE RESIDENT GUI + IPC DISPATCH of 'can u open calculator'")
    print("=" * 75)
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    t0 = time.time()
    main_proc = subprocess.Popen(
        [str(installed_exe), "--background"],
        cwd=str(installed_exe.parent),
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
    )
    print(f"[+] Started resident AstraRun PID {main_proc.pid}")

    state_path = AstraPaths.state_file_path()
    ready_state = None
    for _ in range(80):
        time.sleep(0.1)
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                if s_data.get("pid") == main_proc.pid and s_data.get("ready") is True:
                    ready_state = s_data
                    break
            except Exception:
                pass

    assert ready_state is not None, f"Resident process failed to enter READY state!"
    print(f"[+] Resident process reached READY in {time.time() - t0:.2f}s")

    # Send command via IPC SingleInstance client
    single = AstraSingleInstance()
    log_path = AstraPaths.logs_dir() / "astrarun.log"
    log_pos = log_path.stat().st_size if log_path.exists() else 0

    # 1. Summon UI
    summon_resp = single.send_command("SHOW_MAIN_UI", timeout_ms=3000)
    print(f"[+] IPC SHOW_MAIN_UI response: {summon_resp}")
    time.sleep(0.5)

    # 2. Execute query "can u open calculator" through production launcher pipeline
    print("[*] Submitting 'can u open calculator' via IPC EXECUTE_COMMAND...")
    exec_resp = single.send_command("EXECUTE_COMMAND", {"query": "can u open calculator"}, timeout_ms=5000)
    print(f"[+] IPC EXECUTE_COMMAND response: {exec_resp}")

    # Wait for execution to settle and ledger registration
    active_calc_gui = []
    calc_procs_gui = []
    for _ in range(12):
        time.sleep(0.5)
        calc_procs_gui = [p for p in psutil.process_iter(["pid", "name"]) if (p.info["name"] or "").lower() in ("calculatorapp.exe", "calc.exe")]
        calc_pids = {p.pid for p in calc_procs_gui}
        active_calc_gui = [
            r for r in ledger.list_active_astra_resources()
            if (
                "calc" in r.launching_capability.lower()
                or (r.document_path and "calc" in r.document_path.lower())
                or (r.metadata and any("calc" in str(v).lower() for v in r.metadata.values()))
                or (r.pid in calc_pids)
            )
        ]
        if len(calc_procs_gui) > 0 and len(active_calc_gui) > 0:
            break

    print(f"[*] Running Calculator processes found after GUI dispatch: {len(calc_procs_gui)}")
    print(f"[*] Active Astra-owned resources in ledger after GUI dispatch: {len(active_calc_gui)}")

    # Check new log output for any "Blocked: Blocked: Target tool 'unknown'" error
    new_log_content = ""
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(log_pos)
            new_log_content = f.read()
    has_unknown_tool_err = "Target tool 'unknown' is not registered" in new_log_content
    print(f"[*] 'Target tool unknown' error present in new log: {has_unknown_tool_err}")

    gui_pass = (
        len(calc_procs_gui) > 0
        and len(active_calc_gui) > 0
        and active_calc_gui[-1].astra_created is True
        and not has_unknown_tool_err
    )

    results["tests"]["gui_ipc_routing"] = {
        "pass": gui_pass,
        "query": "can u open calculator",
        "resident_pid": main_proc.pid,
        "ipc_summon_response": summon_resp,
        "ipc_execute_response": exec_resp,
        "calculator_procs_count": len(calc_procs_gui),
        "ledger_resource_count": len(active_calc_gui),
        "ledger_resource_id": active_calc_gui[-1].resource_id if active_calc_gui else None,
        "ledger_pid": active_calc_gui[-1].pid if active_calc_gui else None,
        "ledger_hwnd": active_calc_gui[-1].hwnd if active_calc_gui else None,
        "astra_created": active_calc_gui[-1].astra_created if active_calc_gui else None,
        "unknown_tool_error_absent": not has_unknown_tool_err,
    }

    # Clean up Calculator
    if active_calc_gui:
        ledger.close_owned_resource(active_calc_gui[-1])
    time.sleep(1.0)

    # Clean quit resident process
    print("[*] Sending IPC QUIT command...")
    quit_resp = single.send_command("QUIT", timeout_ms=3000)
    print(f"[+] IPC QUIT response: {quit_resp}")
    try:
        main_proc.wait(timeout=6)
        resident_exit = main_proc.returncode
    except subprocess.TimeoutExpired:
        main_proc.kill()
        resident_exit = main_proc.wait()

    print(f"[+] Resident process exited with code: {resident_exit}")
    results["tests"]["gui_ipc_routing"]["clean_shutdown_exit_code"] = resident_exit

    crash_rec = detect_previous_abnormal_termination()
    results["tests"]["gui_ipc_routing"]["abnormal_termination_detected"] = crash_rec is not None
    assert crash_rec is None, f"Crash recorded: {crash_rec}"

    print(f"[TEST 2 VERDICT] Live resident GUI dispatch: {'PASS' if gui_pass else 'FAIL'}")
    assert gui_pass, "Live resident GUI dispatch failed!"

    # -------------------------------------------------------------
    # 3. Overall Verdict & Evidence Generation
    # -------------------------------------------------------------
    overall_pass = headless_pass and gui_pass and resident_exit == 0
    results["overall_verdict"] = "PASS" if overall_pass else "FAIL"
    results["human_verification_status"] = "READY_FOR_HUMAN_RETEST"
    results["instructions_for_user"] = [
        "1. Launch AstraRun from the Start Menu or desktop shortcut.",
        "2. Press Alt+Space to summon the launcher.",
        "3. Type 'can u open calculator' and press Enter.",
        "4. Confirm that Calculator opens promptly and no 'Blocked' error appears.",
    ]

    evidence_path = repo_root / "docs" / "audit" / "F0_17_PRODUCTION_ROUTING_EVIDENCE.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("\n" + "=" * 75)
    print(f"OVERALL F0-17 VERIFICATION VERDICT: {results['overall_verdict']}")
    print(f"Evidence written to: {evidence_path}")
    print("=" * 75)

    return results


if __name__ == "__main__":
    run_f0_17_verification()
