"""Real Task Resource Restoration Validation for Stage 5."""

import json
import os
import psutil
import sys
import time
import ctypes
from ctypes import wintypes
from pathlib import Path

from astrarun.sandbox.manager import SandboxManager
from astrarun.tools.candidate import CandidateTool
from astrarun.tasks.resource_ledger import AstraResourceLedger

def get_hwnds():
    hwnds = set()
    if sys.platform == "win32":
        user32 = ctypes.windll.user32
        def enum_cb(h, l):
            if user32.IsWindowVisible(h):
                hwnds.add(h)
            return True
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return hwnds

def get_pids():
    return {p.pid for p in psutil.process_iter(["pid"])}

def main():
    print("[STAGE 5] Real Task Resource Restoration Validation")
    # 1. Baseline state capture
    baseline_pids = get_pids()
    baseline_hwnds = get_hwnds()

    mgr = SandboxManager()
    ledger = AstraResourceLedger.get_instance()

    # 2. Real task candidate execution
    task_id = f"real_task_restoration_{int(time.time())}"
    candidate = CandidateTool(
        goal="Compute factorials and write to disk",
        task_id=task_id,
        tool_id=f"tool_{task_id}",
        executable_code="""
import json
from pathlib import Path

facts = {str(i): 1 for i in range(1, 6)}
for i in range(2, 6):
    facts[str(i)] = i * facts[str(i-1)]

out_dir = Path("output")
out_dir.mkdir(exist_ok=True)
(out_dir / "factorials.json").write_text(json.dumps(facts))
print("SUCCESS_FACTORIALS_WRITTEN")
""",
    )

    res = mgr.execute_candidate(candidate)
    print(f"Execution status: {res.status}, exit_code: {res.exit_code}")
    print(f"Stdout: {res.stdout.strip()}")
    sb_dir = res.working_dir
    assert sb_dir.exists(), "Sandbox directory was not created"
    print(f"Sandbox dir: {sb_dir}")

    # Mid-task resource check in ledger
    owned = ledger.list_resources_for_task(task_id)
    print(f"Registered owned resources for task: {len(owned)}")

    # 3. Cleanup via Ledger
    cleanup_report = ledger.cleanup_task_resources(task_id, task_status="COMPLETED")
    print(f"Cleanup report: {cleanup_report}")

    # 4. Post-cleanup physical verification
    sb_still_exists = sb_dir.exists()
    final_pids = get_pids()
    final_hwnds = get_hwnds()

    unmanaged_pids = list(final_pids - baseline_pids)
    unmanaged_hwnds = list(final_hwnds - baseline_hwnds)

    print(f"Sandbox directory physically deleted: {not sb_still_exists}")
    print(f"Unmanaged new PIDs: {unmanaged_pids}")
    print(f"Unmanaged new HWNDs: {unmanaged_hwnds}")

    clean_success = bool(cleanup_report.get("clean", False) or cleanup_report.get("clean_ok", False))
    verdict = "PASS" if (not sb_still_exists and len(unmanaged_pids) == 0 and len(unmanaged_hwnds) == 0 and clean_success) else "FAIL"

    report = {
        "task_id": task_id,
        "candidate_goal": candidate.goal,
        "execution_result": {
            "status": res.status,
            "exit_code": res.exit_code,
            "stdout": res.stdout.strip(),
            "peak_memory_mb": res.peak_memory_mb,
        },
        "sandbox_dir": str(sb_dir),
        "sandbox_physically_deleted": not sb_still_exists,
        "baseline_pids_count": len(baseline_pids),
        "final_pids_count": len(final_pids),
        "unmanaged_new_pids": unmanaged_pids,
        "baseline_hwnds_count": len(baseline_hwnds),
        "final_hwnds_count": len(final_hwnds),
        "unmanaged_new_hwnds": unmanaged_hwnds,
        "cleanup_report": cleanup_report,
        "verdict": verdict,
    }

    out_file = Path("docs/audit/F0_25F1_RESOURCE_RESTORATION.json")
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out_file}")
    print(f"VERDICT: {verdict}")
    return 0 if verdict == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
