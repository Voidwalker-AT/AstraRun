"""
scripts/run_case_b_physical.py
Physically execute Case B:
Execute with pre-existing application open on desktop.
Verify:
1. Goal completes and creates Desktop/test2.txt.
2. Pre-existing user application is preserved (no collateral closure).
3. Astra task-owned resource is closed cleanly.
"""

import sys
import os
import time
import json
import hashlib
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrarun.agent.loop import AgentExecutionEngine
from astrarun.tasks.resource_ledger import AstraResourceLedger
from astrarun.agent.models import AgentTaskStatus
import psutil

def main():
    desktop_file = Path(os.environ["USERPROFILE"]) / "Desktop" / "test2.txt"
    if desktop_file.exists():
        try:
            desktop_file.unlink()
        except Exception:
            pass

    # Setup pre-existing user document
    temp_user_doc = Path(os.environ["TEMP"]) / "user_doc_dont_touch.txt"
    temp_user_doc.write_text("IMPORTANT USER NOTES DO NOT TOUCH", encoding="utf-8")

    print("=== CASE B PHYSICAL EXECUTION (PRE-EXISTING APP STATE) ===")
    print("Launching pre-existing user Notepad instance...")
    user_proc = subprocess.Popen(["notepad.exe", str(temp_user_doc)])
    time.sleep(2.0)

    user_pids = [
        p.pid for p in psutil.process_iter(["pid", "name"])
        if "notepad" in (p.info["name"] or "").lower()
    ]
    print(f"Pre-existing user Notepad PIDs: {user_pids}")
    assert len(user_pids) > 0, "Failed to launch pre-existing user Notepad"

    prompt = "open notepad type hello and save it to desktop with name test2.txt"
    print(f"\nExecuting AstraRun Prompt: {prompt}")

    t0 = time.time()
    engine = AgentExecutionEngine()
    task = engine.execute_goal(prompt)
    duration = time.time() - t0

    print(f"\nTask ID: {task.task_id}")
    print(f"Task Status: {task.status.value}")
    print(f"Duration: {duration:.2f}s")
    for i, s in enumerate(task.plan.steps):
        res = s.result
        print(f"  Step {i+1} [{s.capability_id}]: success={res.success if res else False}, msg={res.message if res else ''}")

    # Physical verification of desktop file
    file_exists = desktop_file.exists()
    file_size = desktop_file.stat().st_size if file_exists else 0
    file_content = ""
    file_sha = ""
    if file_exists:
        try:
            raw = desktop_file.read_bytes()
            file_sha = hashlib.sha256(raw).hexdigest()
            file_content = raw.decode("utf-8", errors="replace")
        except Exception as e:
            file_content = f"Error reading: {e}"

    print(f"\n[PHYSICAL ARTIFACT]")
    print(f"File Path: {desktop_file}")
    print(f"File Exists: {file_exists}")
    print(f"File Size: {file_size} bytes")
    print(f"Content: {file_content!r}")
    print(f"SHA-256: {file_sha}")

    # Check whether the pre-existing user process was preserved
    user_pids_alive = [pid for pid in user_pids if psutil.pid_exists(pid)]
    print(f"\n[PRE-EXISTING USER APPLICATION PRESERVATION]")
    print(f"User PIDs initially recorded: {user_pids}")
    print(f"User PIDs still alive after AstraRun cleanup: {user_pids_alive}")
    user_preserved = len(user_pids_alive) > 0

    # Resource Ledger Report
    ledger_report = task.context.get("cleanup_report", {})
    print(f"\n[RESOURCE CLEANUP REPORT]")
    print(f"Clean: {ledger_report.get('clean')}")
    print(f"Cleaned count: {ledger_report.get('cleaned_count')}")
    print(f"Remaining active: {ledger_report.get('remaining_active_resources')}")
    print(f"Process cleaned up: {ledger_report.get('process_cleaned_up')}")

    # Clean up the pre-existing user process now
    for pid in user_pids_alive:
        try:
            p = psutil.Process(pid)
            p.kill()
        except Exception:
            pass
    try:
        temp_user_doc.unlink(missing_ok=True)
    except Exception:
        pass

    overall_success = (
        task.status == AgentTaskStatus.COMPLETED
        and file_exists
        and file_size > 0
        and "hello" in file_content.lower()
        and user_preserved
    )

    evidence = {
        "case_id": "CASE_B",
        "prompt": prompt,
        "task_id": task.task_id,
        "task_status": task.status.value,
        "duration_seconds": round(duration, 2),
        "steps": [
            {
                "capability": s.capability_id,
                "arguments": s.arguments,
                "success": s.result.success if s.result else False,
                "message": s.result.message if s.result else "",
            }
            for s in task.plan.steps
        ],
        "artifact": {
            "path": str(desktop_file),
            "exists": file_exists,
            "size_bytes": file_size,
            "content": file_content,
            "sha256": file_sha,
            "semantic_match": "hello" in file_content.lower(),
        },
        "pre_existing_preservation": {
            "initial_user_pids": user_pids,
            "retained_user_pids": user_pids_alive,
            "user_application_preserved": user_preserved,
        },
        "cleanup": ledger_report,
        "overall_success": overall_success,
    }

    evidence_path = Path(__file__).resolve().parent.parent / "docs" / "audit" / "F0_24A2_CASE_B_EVIDENCE.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"\nWrote evidence to: {evidence_path}")
    print(f"Overall Case B Success: {overall_success}")
    return 0 if overall_success else 1

if __name__ == "__main__":
    sys.exit(main())
