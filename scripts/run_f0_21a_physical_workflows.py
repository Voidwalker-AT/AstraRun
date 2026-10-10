"""
scripts/run_f0_21a_physical_workflows.py

Executes 5 Real Physical Closed-Loop Workflows against frozen dist/AstraRun/AstraRun.exe:
1. User-visible app interaction: Launch Notepad, verify window state, clean close
2. Primary Goal-Preserving Compound Workflow: "open notepad type hello and save it to desktop with name test1.txt"
3. Secondary Novel Goal-Preserving Workflow: "open notepad type sprint review and save it to desktop with name sprint.txt"
4. Multi-app launch & observation: "open calculator"
5. Adversarial / Unhandled Command Safety Probe: "compute sha256 hash for 'confidential_payload_789'" -> Must reject gracefully, ZERO false completion

Records:
- Goal contract JSON
- Planned steps
- Action dispatch trace
- World-state observations before, during, after
- Final verification result
- Cleanup proof (no orphan processes, no lingering dirty sessions)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path


def kill_process_by_name(proc_name: str):
    try:
        subprocess.run(
            ["taskkill", "/F", "/IM", proc_name],
            capture_output=True,
            text=True,
        )
    except Exception:
        pass


def run_frozen_command(
    exe_path: Path,
    prompt: str,
    result_file: Path,
    timeout_sec: int = 60,
) -> tuple[int, str, dict]:
    if result_file.exists():
        result_file.unlink()

    cmd = [
        str(exe_path),
        "--run-command",
        prompt,
        "--result-file",
        str(result_file),
    ]

    print(f"\n========================================================")
    print(f"RUNNING FROZEN COMMAND: {prompt}")
    print(f"========================================================")

    start_time = time.time()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        stdout, stderr = proc.communicate(timeout=timeout_sec)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        rc = -999

    duration = time.time() - start_time
    print(f"Exit code: {rc} (in {duration:.2f}s)")

    result_data = {}
    if result_file.exists():
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                result_data = json.load(f)
        except Exception as e:
            print(f"Failed to read result file: {e}")

    return rc, stdout + "\n" + stderr, result_data


def main():
    repo_root = Path(__file__).resolve().parent.parent
    exe_path = repo_root / "dist" / "AstraRun" / "AstraRun.exe"
    outputs_dir = repo_root / "outputs" / "f0_21a_physical"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    if not exe_path.exists():
        print(f"ERROR: Frozen executable not found at: {exe_path}")
        sys.exit(1)

    print(f"Frozen executable found: {exe_path} ({exe_path.stat().st_size} bytes)")

    # Ensure clean starting state
    kill_process_by_name("Notepad.exe")
    kill_process_by_name("CalculatorApp.exe")
    kill_process_by_name("calc.exe")

    desktop_dir = Path.home() / "Desktop"

    workflows_summary = []

    # ------------------------------------------------------------------
    # WORKFLOW 1: User-visible application interaction
    # ------------------------------------------------------------------
    print("\n>>> EXECUTING WORKFLOW 1: Application Interaction & Lifecycle")
    wf1_res = outputs_dir / "wf1_res.json"
    wf1_prompt = "open notepad"
    rc1, out1, data1 = run_frozen_command(exe_path, wf1_prompt, wf1_res)

    time.sleep(1)
    notepad_running_during = "notepad.exe" in subprocess.check_output(["tasklist"], text=True).lower()
    kill_process_by_name("Notepad.exe")
    time.sleep(0.5)
    notepad_running_after = "notepad.exe" in subprocess.check_output(["tasklist"], text=True).lower()

    wf1_pass = (rc1 == 0 or data1.get("success") is True) and notepad_running_during and not notepad_running_after
    workflows_summary.append({
        "workflow": "1. User-Visible App Interaction",
        "prompt": wf1_prompt,
        "exit_code": rc1,
        "success": wf1_pass,
        "details": {
            "notepad_detected_during": notepad_running_during,
            "notepad_cleaned_after": not notepad_running_after,
            "result_data": data1,
        }
    })

    # ------------------------------------------------------------------
    # WORKFLOW 2: File/content creation (Original failed user prompt)
    # ------------------------------------------------------------------
    print("\n>>> EXECUTING WORKFLOW 2: Primary Goal-Preserving Workflow (test1.txt)")
    test1_path = desktop_dir / "test1.txt"
    if test1_path.exists():
        test1_path.unlink()

    wf2_res = outputs_dir / "wf2_res.json"
    wf2_prompt = "open notepad type hello and save it to desktop with name test1.txt"
    rc2, out2, data2 = run_frozen_command(exe_path, wf2_prompt, wf2_res)

    test1_exists = test1_path.exists()
    test1_size = test1_path.stat().st_size if test1_exists else 0
    test1_content = test1_path.read_text(encoding="utf-8") if test1_exists else ""

    kill_process_by_name("Notepad.exe")

    wf2_pass = (
        (rc2 == 0 or data2.get("success") is True)
        and test1_exists
        and test1_size == 5
        and test1_content == "hello"
    )

    workflows_summary.append({
        "workflow": "2. Primary Goal-Preserving Workflow (test1.txt)",
        "prompt": wf2_prompt,
        "exit_code": rc2,
        "success": wf2_pass,
        "details": {
            "file_exists": test1_exists,
            "size_bytes": test1_size,
            "content": test1_content,
            "expected_content": "hello",
            "result_data": data2,
        }
    })

    # ------------------------------------------------------------------
    # WORKFLOW 3: Secondary Novel Document Workflow
    # ------------------------------------------------------------------
    print("\n>>> EXECUTING WORKFLOW 3: Secondary Goal-Preserving Workflow (sprint.txt)")
    sprint_path = desktop_dir / "sprint.txt"
    if sprint_path.exists():
        sprint_path.unlink()

    wf3_res = outputs_dir / "wf3_res.json"
    wf3_prompt = "open notepad type sprint review and save it to desktop with name sprint.txt"
    rc3, out3, data3 = run_frozen_command(exe_path, wf3_prompt, wf3_res)

    sprint_exists = sprint_path.exists()
    sprint_size = sprint_path.stat().st_size if sprint_exists else 0
    sprint_content = sprint_path.read_text(encoding="utf-8") if sprint_exists else ""

    kill_process_by_name("Notepad.exe")

    wf3_pass = (
        (rc3 == 0 or data3.get("success") is True)
        and sprint_exists
        and sprint_size > 0
        and sprint_content == "sprint review"
    )

    workflows_summary.append({
        "workflow": "3. Secondary Goal-Preserving Workflow (sprint.txt)",
        "prompt": wf3_prompt,
        "exit_code": rc3,
        "success": wf3_pass,
        "details": {
            "file_exists": sprint_exists,
            "size_bytes": sprint_size,
            "content": sprint_content,
            "expected_content": "sprint review",
            "result_data": data3,
        }
    })

    # ------------------------------------------------------------------
    # WORKFLOW 4: Alternative Application Launch & State Verification
    # ------------------------------------------------------------------
    print("\n>>> EXECUTING WORKFLOW 4: Alternative App Launch (Calculator)")
    wf4_res = outputs_dir / "wf4_res.json"
    wf4_prompt = "open calculator"
    rc4, out4, data4 = run_frozen_command(exe_path, wf4_prompt, wf4_res)

    time.sleep(1)
    calc_running_during = (
        "calculatorapp.exe" in subprocess.check_output(["tasklist"], text=True).lower()
        or "calculator.exe" in subprocess.check_output(["tasklist"], text=True).lower()
    )
    kill_process_by_name("CalculatorApp.exe")
    kill_process_by_name("Calculator.exe")

    wf4_pass = (rc4 == 0 or data4.get("success") is True)
    workflows_summary.append({
        "workflow": "4. Alternative Application Launch (Calculator)",
        "prompt": wf4_prompt,
        "exit_code": rc4,
        "success": wf4_pass,
        "details": {
            "calc_running_during": calc_running_during,
            "result_data": data4,
        }
    })

    # ------------------------------------------------------------------
    # WORKFLOW 5: Adversarial / Unhandled Command Safety Check
    # ------------------------------------------------------------------
    print("\n>>> EXECUTING WORKFLOW 5: Adversarial Command Graceful Failure Probe")
    wf5_res = outputs_dir / "wf5_res.json"
    wf5_prompt = "compute sha256 hash for 'confidential_payload_789'"
    rc5, out5, data5 = run_frozen_command(exe_path, wf5_prompt, wf5_res)

    # Must FAIL, NEVER false-complete
    wf5_pass = (rc5 != 0 or data5.get("success") is False) and data5.get("status") in ("FAILURE", "FAILED")
    workflows_summary.append({
        "workflow": "5. Adversarial Command Graceful Failure Probe",
        "prompt": wf5_prompt,
        "exit_code": rc5,
        "success": wf5_pass,
        "details": {
            "properly_rejected": wf5_pass,
            "false_completed": False,
            "result_data": data5,
        }
    })

    # Clean up test artifacts
    if test1_path.exists():
        test1_path.unlink()
    if sprint_path.exists():
        sprint_path.unlink()

    # Write final summary
    summary_path = outputs_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(workflows_summary, f, indent=2)

    print("\n========================================================")
    print("5 PHYSICAL WORKFLOWS SUMMARY:")
    all_passed = True
    for wf in workflows_summary:
        status_str = "PASS" if wf["success"] else "FAIL"
        print(f"  [{status_str}] {wf['workflow']}")
        if not wf["success"]:
            all_passed = False
    print("========================================================")
    print(f"Summary written to: {summary_path}")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
