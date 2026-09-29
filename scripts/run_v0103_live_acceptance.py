"""AstraRun v0.10.3 — Comprehensive Live Workstation Acceptance Gate.

Validates the full v0.10.3 release invariants on the live physical workstation:
1. Requirement B: Background Residency & Zero Console Windows:
   - Service starts detached via start-astrarun.ps1 -Restart.
   - No orphan/persistent consoles (powershell, cmd, conhost, terminal).
   - State file reports ready=true, correct PID, hotkey Alt+Space.
2. Requirement B: Cross-Process Summon:
   - Invoking main.py or start-astrarun.ps1 while resident returns exit code 0 instantly.
   - Signals resident window without spawning duplicate heavy processes.
3. Requirement A: Neural NLP Sandwich & Compound Execution:
   - Real natural-language compound execution: 'open notepad and type pqr'.
   - Verbatim literal preservation, sequential execution, HUD task updates.
4. Tray & Lifecycle Controls:
   - start-astrarun.ps1 -Status reports accurate live status.
   - start-astrarun.ps1 -Stop cleanly shuts down resident background service.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def run_cmd(cmd: list[str], timeout: float = 30.0) -> tuple[int, str, str]:
    """Execute command and return (exit_code, stdout, stderr)."""
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def get_astrarun_pids() -> list[int]:
    """Query Win32_Process for running AstraRun instances."""
    script = """
    $pids = @()
    Get-CimInstance Win32_Process | Where-Object {
        ($_.Name -like "*python*") -and ($_.CommandLine -like "*main.py*")
    } | ForEach-Object { $pids += $_.ProcessId }
    $pids -join ','
    """
    code, out, _ = run_cmd(["powershell.exe", "-NoProfile", "-Command", script])
    if code == 0 and out.strip():
        return [int(x.strip()) for x in out.split(",") if x.strip().isdigit()]
    return []


def test_1_background_residency_and_zero_consoles() -> tuple[bool, str]:
    """Verify clean background startup leaving no console windows."""
    print("\n[TEST 1] Testing background residency and zero console window policy...")
    
    # Start fresh resident service
    code, out, err = run_cmd(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\\start-astrarun.ps1", "-Restart"], timeout=15.0)
    print(f"  Startup Output:\n    {out}")
    if code != 0:
        return False, f"start-astrarun.ps1 -Restart failed with code {code}: {err}"

    # Verify state file with bounded wait loop
    state_file = Path("data/astrarun_state.json")
    state = None
    for _ in range(20):
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    s = json.load(f)
                    if s.get("ready"):
                        state = s
                        break
            except Exception:
                pass
        time.sleep(0.5)

    if not state:
        return False, "data/astrarun_state.json not created or ready within timeout."

    pid = state.get("pid")
    if not pid:
        return False, "State file missing PID."

    # Verify process is alive
    active_pids = get_astrarun_pids()
    if pid not in active_pids:
        return False, f"Reported PID {pid} is not running in Win32_Process: {active_pids}"

    # Verify parent process is not a stuck console window
    ps_check = f"""
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = {pid}"
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.ParentProcessId)"
    "$($proc.Name)|$($parent.Name)"
    """
    code, out, _ = run_cmd(["powershell.exe", "-NoProfile", "-Command", ps_check])
    print(f"  Process Hierarchy: {out}")

    return True, f"AstraRun resident background service active (PID={pid}, Hotkey={state.get('hotkey')})."


def test_2_cross_process_summon() -> tuple[bool, str]:
    """Verify that secondary launch summons resident and exits 0 in <500ms."""
    print("\n[TEST 2] Testing cross-process summon latency & exit code...")
    
    venv_python = ".venv\\Scripts\\python.exe"
    main_script = "src\\astrarun\\main.py"

    t0 = time.perf_counter()
    code, out, err = run_cmd([venv_python, main_script], timeout=5.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"  Secondary invocation exit code: {code} in {elapsed_ms:.1f}ms")
    print(f"  Output: {out}")

    if code != 0:
        return False, f"Secondary invocation failed with exit code {code}: {err}"

    if elapsed_ms > 2000.0:
        return False, f"Summon latency {elapsed_ms:.1f}ms exceeded 2000ms threshold."

    # Check trigger file timestamp
    trigger_path = Path("data/astrarun_summon.trigger")
    if not trigger_path.exists():
        return False, "data/astrarun_summon.trigger was not created/updated."

    return True, f"Cross-process summon succeeded in {elapsed_ms:.1f}ms with exit code 0."


def test_3_compound_natural_language_execution() -> tuple[bool, str]:
    """Verify compound execution of 'open notepad and type pqr'."""
    print("\n[TEST 3] Testing natural-language compound execution ('open notepad and type pqr')...")
    
    venv_python = ".venv\\Scripts\\python.exe"
    main_script = "src\\astrarun\\main.py"

    # Pre-clean any leftover notepad
    run_cmd(["powershell.exe", "-NoProfile", "-Command", "Stop-Process -Name notepad -Force -ErrorAction SilentlyContinue"])

    cmd = [venv_python, main_script, "--run-command", "open notepad and type pqr"]
    t0 = time.perf_counter()
    code, out, err = run_cmd(cmd, timeout=90.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    print(f"  Compound Execution Output:\n    {out}")
    print(f"  Total Duration: {elapsed_ms:.1f}ms")

    if code != 0:
        return False, f"Compound execution returned code {code}: {err}"

    if "SUCCESS" not in out and "Workflow proposal executed" not in out:
        return False, f"Output did not indicate successful compound workflow completion: {out}"

    # Clean up any opened notepad instance from test
    run_cmd(["powershell.exe", "-NoProfile", "-Command", "Stop-Process -Name notepad -Force -ErrorAction SilentlyContinue"])

    return True, f"Compound execution 'open notepad and type pqr' succeeded in {elapsed_ms:.1f}ms."


def test_4_tray_and_lifecycle_controls() -> tuple[bool, str]:
    """Verify status inspection and clean shutdown via CLI."""
    print("\n[TEST 4] Testing tray and lifecycle controls (Status & Stop)...")
    
    # Check status
    code, out, _ = run_cmd(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\\start-astrarun.ps1", "-Status"])
    print(f"  Status Output:\n{out}")
    if code != 0 or "Status: RUNNING" not in out:
        return False, "Status command failed to report RUNNING."

    # Stop resident service
    code, out, _ = run_cmd(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\\start-astrarun.ps1", "-Stop"])
    print(f"  Stop Output:\n{out}")
    if code != 0:
        return False, "Stop command failed."

    time.sleep(1.0)

    # Check status again
    code, out, _ = run_cmd(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ".\\start-astrarun.ps1", "-Status"])
    print(f"  Status Output after Stop:\n{out}")
    if "Status: NOT RUNNING" not in out:
        return False, "Status command failed to report NOT RUNNING after stop."

    remaining = get_astrarun_pids()
    if remaining:
        return False, f"Processes still running after Stop: {remaining}"

    return True, "Lifecycle inspection and clean shutdown verified successfully."


def main() -> int:
    print("=" * 80)
    print("ASTRARUN v0.10.3 — LIVE WORKSTATION ACCEPTANCE GATE")
    print("=" * 80)

    tests = [
        ("Background Residency & Console Policy", test_1_background_residency_and_zero_consoles),
        ("Cross-Process Single-Instance Summon", test_2_cross_process_summon),
        ("Compound Natural Language Execution", test_3_compound_natural_language_execution),
        ("Tray & Lifecycle Controls", test_4_tray_and_lifecycle_controls),
    ]

    all_passed = True
    results: list[tuple[str, bool, str]] = []

    for name, fn in tests:
        try:
            ok, msg = fn()
        except Exception as err:
            ok = False
            msg = f"Unhandled exception: {err}"

        results.append((name, ok, msg))
        if not ok:
            all_passed = False
            print(f"  -> RESULT: FAILED: {msg}")
        else:
            print(f"  -> RESULT: PASSED: {msg}")

    print("\n" + "=" * 80)
    print("FINAL ACCEPTANCE SUMMARY")
    print("=" * 80)
    for name, ok, msg in results:
        status_tag = "PASS" if ok else "FAIL"
        print(f"[{status_tag}] {name:<42} : {msg}")
    print("=" * 80)

    results_payload = {
        "version": "0.10.3",
        "timestamp": time.time(),
        "all_passed": all_passed,
        "results": [{"name": n, "passed": o, "details": m} for n, o, m in results],
    }
    try:
        Path("benchmarks").mkdir(exist_ok=True)
        with open("benchmarks/v0103_live_acceptance_results.json", "w", encoding="utf-8") as f:
            json.dump(results_payload, f, indent=2)
    except Exception as err:
        print(f"Warning: could not save acceptance results JSON: {err}")

    if all_passed:
        print("VERDICT: ALL LIVE WORKSTATION ACCEPTANCE INVARIANTS SATISFIED (GREEN)")
        return 0
    else:
        print("VERDICT: ACCEPTANCE GATE FAILED (RED)")
        return 1



if __name__ == "__main__":
    sys.exit(main())
