"""
scripts/run_case_c_physical.py
Physically execute Case C:
Unrelated editable application (Notepad++).
Prompt: 'open notepad++ type AstraRunUnrelatedEditorTest and save it to desktop with name test3.txt'
Verify:
1. Notepad++ launched and discovered generically.
2. Editable surface discovered (Scintilla / generic edit / document).
3. Text injected and saved to Desktop/test3.txt.
4. File verified non-empty, contains exact text.
5. Task-owned Notepad++ cleanly closed with zero process leak.
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
    desktop_file = Path(os.environ["USERPROFILE"]) / "Desktop" / "test3.txt"
    if desktop_file.exists():
        try:
            desktop_file.unlink()
        except Exception:
            pass

    print("=== CASE C PHYSICAL EXECUTION (UNRELATED APP: NOTEPAD++) ===")
    prompt = "open notepad++ type AstraRunUnrelatedEditorTest and save it to desktop with name test3.txt"
    print(f"Prompt: {prompt}")

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

    # Resource Ledger Report
    ledger_report = task.context.get("cleanup_report", {})
    print(f"\n[RESOURCE CLEANUP REPORT]")
    print(f"Clean: {ledger_report.get('clean')}")
    print(f"Cleaned count: {ledger_report.get('cleaned_count')}")
    print(f"Remaining active: {ledger_report.get('remaining_active_resources')}")
    print(f"Process cleaned up: {ledger_report.get('process_cleaned_up')}")

    # OS Residue check for notepad++
    remaining_npp = [
        p.info for p in psutil.process_iter(["pid", "name"])
        if "notepad++" in (p.info["name"] or "").lower()
    ]
    print(f"Remaining Notepad++ processes on OS: {remaining_npp}")

    overall_success = (
        task.status == AgentTaskStatus.COMPLETED
        and file_exists
        and file_size > 0
        and "astrarununrelatededitortest" in file_content.lower()
        and len(remaining_npp) == 0
    )

    evidence = {
        "case_id": "CASE_C",
        "application": "notepad++",
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
            "semantic_match": "astrarununrelatededitortest" in file_content.lower(),
        },
        "cleanup": ledger_report,
        "os_residue": {
            "remaining_npp_pids": [p["pid"] for p in remaining_npp],
            "zero_leak": len(remaining_npp) == 0,
        },
        "overall_success": overall_success,
    }

    evidence_path = Path(__file__).resolve().parent.parent / "docs" / "audit" / "F0_24A2_CASE_C_EVIDENCE.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"\nWrote evidence to: {evidence_path}")
    print(f"Overall Case C Success: {overall_success}")
    return 0 if overall_success else 1

if __name__ == "__main__":
    sys.exit(main())
