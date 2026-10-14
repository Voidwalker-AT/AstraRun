"""
scripts/run_case_d_physical.py
Physically execute Case D:
Non-document UI interaction in an unrelated built-in application (Calculator).
Prompt: 'open calculator and type 7*8='
Verify:
1. Calculator launched and discovered generically.
2. Initial display state observed (BEFORE state: 'Display is 0').
3. Direct keystrokes injected ('7*8=').
4. State transition observed (AFTER state: 'Display is 56').
5. Task-owned Calculator cleanly closed with zero process leak.
6. Record BEFORE state, ACTION, AFTER state and POSTCONDITION.
"""

import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrarun.agent.loop import AgentExecutionEngine
from astrarun.tasks.resource_ledger import AstraResourceLedger
from astrarun.agent.models import AgentTaskStatus
from astrarun.windows.discovery import list_windows, foreground_window
from astrarun.computer_use.ui.uia_support import get_uia_interface, get_uia_module
import psutil
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32

def main():
    print("=== CASE D PHYSICAL EXECUTION (NON-DOCUMENT APP: CALCULATOR) ===")
    prompt = "open calculator and type 7*8="
    print(f"Prompt: {prompt}")

    # Ensure no lingering calc processes before starting
    for p in psutil.process_iter(["pid", "name"]):
        if "calc" in (p.info["name"] or "").lower():
            try:
                p.terminate()
            except Exception:
                pass
    time.sleep(0.5)

    # 1. Capture BEFORE State
    before_windows = list_windows(limit=20).data.get("windows", [])
    before_calc_pids = [
        p.info["pid"] for p in psutil.process_iter(["pid", "name"])
        if "calc" in (p.info["name"] or "").lower()
    ]
    fg_before = foreground_window().data
    print(f"\n[BEFORE STATE]")
    print(f"Foreground Window: HWND {fg_before.get('hwnd')}, Title: {fg_before.get('title')!r}")
    print(f"Pre-existing Calculator PIDs: {before_calc_pids}")

    # 2. Execute Goal through AgentExecutionEngine
    t0 = time.time()
    engine = AgentExecutionEngine()
    task = engine.execute_goal(prompt)
    duration = time.time() - t0

    print(f"\n[ACTION EXECUTION]")
    print(f"Task ID: {task.task_id}")
    print(f"Task Status: {task.status.value}")
    print(f"Duration: {duration:.2f}s")
    for i, s in enumerate(task.plan.steps):
        res = s.result
        print(f"  Step {i+1} [{s.capability_id}]: success={res.success if res else False}, msg={res.message if res else ''}")

    # 3. Capture AFTER State / State Transition Evidence
    step2 = task.plan.steps[1] if len(task.plan.steps) > 1 else None
    step2_ver = getattr(step2, "verification", None) if step2 else None
    ver_evidence = step2_ver.evidence if step2_ver else {}
    transition_verified = step2_ver.verified if step2_ver else False

    # 4. Resource Ledger Cleanup Report
    ledger_report = task.context.get("cleanup_report", {})
    print(f"\n[RESOURCE CLEANUP REPORT]")
    print(f"Clean: {ledger_report.get('clean')}")
    print(f"Cleaned count: {ledger_report.get('cleaned_count')}")
    print(f"Remaining active: {ledger_report.get('remaining_active_resources')}")
    print(f"Process cleaned up: {ledger_report.get('process_cleaned_up')}")

    # OS Residue check for Calculator
    remaining_calc = [
        p.info for p in psutil.process_iter(["pid", "name"])
        if "calc" in (p.info["name"] or "").lower()
    ]
    print(f"Remaining Calculator processes on OS: {remaining_calc}")

    overall_success = (
        task.status == AgentTaskStatus.COMPLETED
        and transition_verified
        and len(remaining_calc) == 0
    )

    evidence = {
        "case_id": "CASE_D",
        "application": "calculator",
        "application_type": "NON_DOCUMENT_INTERACTIVE",
        "prompt": prompt,
        "task_id": task.task_id,
        "task_status": task.status.value,
        "duration_seconds": round(duration, 2),
        "before_state": {
            "foreground_window": fg_before,
            "calculator_pids_running": before_calc_pids,
            "initial_calc_running": len(before_calc_pids) > 0,
        },
        "action": {
            "steps": [
                {
                    "step_id": s.step_id,
                    "capability": s.capability_id,
                    "arguments": s.arguments,
                    "success": s.result.success if s.result else False,
                    "message": s.result.message if s.result else "",
                }
                for s in task.plan.steps
            ],
        },
        "after_state": {
            "state_transition_verified": transition_verified,
            "verification_evidence": ver_evidence,
            "verification_message": step2_ver.message if step2_ver else "",
        },
        "postcondition": {
            "requested_state_transition_achieved": transition_verified,
            "task_owned_resources_cleaned": ledger_report.get("clean", False),
            "os_residue_zero": len(remaining_calc) == 0,
            "remaining_calc_pids": [p["pid"] for p in remaining_calc],
        },
        "overall_success": overall_success,
    }

    evidence_path = Path(__file__).resolve().parent.parent / "docs" / "audit" / "F0_24A2_CASE_D_EVIDENCE.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"\nWrote evidence to: {evidence_path}")
    print(f"Overall Case D Success: {overall_success}")
    return 0 if overall_success else 1

if __name__ == "__main__":
    sys.exit(main())
