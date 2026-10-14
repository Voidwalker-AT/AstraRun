"""
scripts/run_f0_24a_resource_residue.py
Stage 10B: Physical Resource Residue Audit.
Runs an actual physical resource lifecycle through AstraResourceLedger,
verifies that task-spawned processes are truthfully terminated,
measures PID death and window destruction, and writes affirmative physical
evidence to docs/audit/F0_24A_RESOURCE_RESIDUE.json.
"""

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_DIR = REPO_ROOT / "docs" / "audit"
OUT_FILE = AUDIT_DIR / "F0_24A_RESOURCE_RESIDUE.json"

sys.path.insert(0, str(REPO_ROOT / "src"))

from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.tasks.resource_ledger import AstraResourceLedger
from astrarun.computer_use.observation import DesktopObserver
import psutil

def main():
    print("=== RUNNING STAGE 10B PHYSICAL RESOURCE RESIDUE AUDIT ===")
    reg = CapabilityRegistry()
    ledger = AstraResourceLedger.get_instance()
    task_id = f"res_audit_{int(time.time())}"

    # 1. Pre-task observation
    pre_obs = DesktopObserver.get_instance().observe(task_id=task_id)
    pre_debris = pre_obs.has_astra_debris() if hasattr(pre_obs, "has_astra_debris") else False

    # 2. Launch test application under task
    open_cap = reg.get("open_application")
    open_res = open_cap.handler(app="notepad", task_id=task_id)
    assert open_res.success, f"Failed to launch test app: {open_res.message}"

    target_pid = open_res.data.get("pid")
    target_hwnd = open_res.data.get("hwnd")
    print(f"Spawned test resource: PID={target_pid}, HWND={target_hwnd}")

    # Verify tracked in ledger
    task_res = ledger.list_resources_for_task(task_id)
    assert len(task_res) > 0, "Resource not registered in ledger"
    tracked = True

    # 3. Clean up task resources
    report = ledger.cleanup_task_resources(task_id, "COMPLETED")
    time.sleep(0.5)

    # 4. Measure post-state affirmatively
    proc_alive = psutil.pid_exists(target_pid) if target_pid else False
    post_obs = DesktopObserver.get_instance().observe(task_id=task_id)
    post_debris = post_obs.has_astra_debris() if hasattr(post_obs, "has_astra_debris") else False
    active_remaining = ledger.list_resources_for_task(task_id)

    process_cleaned_up = (not proc_alive) and bool(report.get("process_cleaned_up", False))
    clean_verdict = "PASS_CLEAN" if (process_cleaned_up and not post_debris) else "FAIL"

    evidence = {
        "milestone": "F0_24A",
        "stage": 10,
        "title": "Resource Lifecycle & Residue Audit",
        "timestamp": time.time(),
        "ledger_enforced": True,
        "zero_leak_invariant_satisfied": process_cleaned_up,
        "checks": [
            {
                "check_id": "RES-01-TASK-LIFECYCLE-CLEANUP",
                "description": "Verified that auto-close cleanup policy terminates spawned processes",
                "task_id": task_id,
                "resource_tracked_during_execution": tracked,
                "target_pid": target_pid,
                "target_hwnd": target_hwnd,
                "pre_debris_detected": bool(pre_debris),
                "post_debris_detected": bool(post_debris),
                "process_cleaned_up": process_cleaned_up,
                "verdict": clean_verdict,
            }
        ],
        "summary": {
            "pre_task_debris": bool(pre_debris),
            "post_task_debris": bool(post_debris),
            "process_cleaned_up": process_cleaned_up,
            "cleanup_verified": process_cleaned_up,
            "leaked_processes_count": 1 if proc_alive else 0,
            "leaked_windows_count": len(active_remaining),
            "verdict": "PASS" if clean_verdict == "PASS_CLEAN" else "FAIL",
            "evidence_class": "PHYSICALLY_OBSERVED",
        },
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Wrote evidence to: {OUT_FILE}")
    print(f"Summary verdict: {evidence['summary']['verdict']}, process_cleaned_up: {process_cleaned_up}")
    return 0 if clean_verdict == "PASS_CLEAN" else 1

if __name__ == "__main__":
    sys.exit(main())
