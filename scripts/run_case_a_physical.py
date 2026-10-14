"""
scripts/run_case_a_physical.py
Physically execute Case A:
'open notepad type hello and save it to desktop with name test1.txt'
Record all physical evidence, file contents, SHA-256, and lifecycle metrics.
"""

import sys
import os
import time
import json
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from astrarun.agent.loop import AgentExecutionEngine
from astrarun.tasks.resource_ledger import AstraResourceLedger
from astrarun.agent.models import AgentTaskStatus
import psutil

def main():
    desktop_file = Path(os.environ["USERPROFILE"]) / "Desktop" / "test1.txt"
    if desktop_file.exists():
        try:
            desktop_file.unlink()
        except Exception:
            pass

    print(f"=== CASE A PHYSICAL EXECUTION ===")
    prompt = "open notepad type hello and save it to desktop with name test1.txt"
    print(f"Prompt: {prompt}")

    t0 = time.time()
    engine = AgentExecutionEngine()
    task = engine.execute_goal(prompt)
    duration = time.time() - t0

    print(f"\nTask ID: {task.task_id}")
    print(f"Task Status: {task.status.value}")
    print(f"Duration: {duration:.2f}s")
    print(f"Steps executed: {len(task.plan.steps)}")

    for i, s in enumerate(task.plan.steps):
        res = s.result
        success = res.success if res else False
        msg = res.message if res else "No result"
        print(f"  Step {i+1} [{s.capability_id}]: success={success}, msg={msg}")

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

    # Resource Ledger Report
    ledger_report = task.context.get("cleanup_report", {})
    print(f"\n[RESOURCE CLEANUP REPORT]")
    print(f"Clean: {ledger_report.get('clean')}")
    print(f"Cleaned count: {ledger_report.get('cleaned_count')}")
    print(f"Remaining active: {ledger_report.get('remaining_active_resources')}")
    print(f"Process cleaned up: {ledger_report.get('process_cleaned_up')}")
    print(f"Verdict: {ledger_report.get('verdict')}")

    # Live OS verification
    remaining_notepads = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if "notepad" in (p.info["name"] or "").lower():
                remaining_notepads.append(p.info)
        except Exception:
            pass

    print(f"Remaining active Notepad processes on OS: {remaining_notepads}")

    evidence = {
        "case_id": "CASE_A",
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
        "cleanup": ledger_report,
        "os_residue": {
            "remaining_notepad_pids": [p["pid"] for p in remaining_notepads],
            "zero_leak": len(remaining_notepads) == 0,
        },
        "overall_success": (
            task.status == AgentTaskStatus.COMPLETED
            and file_exists
            and file_size > 0
            and "hello" in file_content.lower()
            and ledger_report.get("clean") is True
            and len(remaining_notepads) == 0
        )
    }

    evidence_path = Path(__file__).resolve().parent.parent / "docs" / "audit" / "F0_24A2_CASE_A_EVIDENCE.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"\nWrote evidence to: {evidence_path}")
    print(f"Overall Physical Success: {evidence['overall_success']}")
    return 0 if evidence["overall_success"] else 1

if __name__ == "__main__":
    sys.exit(main())
