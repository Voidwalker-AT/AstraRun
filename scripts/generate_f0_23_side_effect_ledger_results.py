"""Evaluate side-effect ledger auditing across clean and unrequested mutation scenarios."""

import json
from datetime import datetime, timezone
from pathlib import Path

from astrarun.agent.models import GoalContract, GoalPredicate, PredicateType
from astrarun.evaluation.side_effect_ledger import (
    MutationType,
    ResourceOwnership,
    TaskSideEffectLedger,
)

REPO_ROOT = Path("e:/Workspace/Active/AstraRun")
OUTPUT_PATH = REPO_ROOT / "docs" / "audit" / "F0_23_SIDE_EFFECT_LEDGER_RESULTS.json"

def main() -> None:
    cases = []
    passed_audit_count = 0

    # 1. Clean document task (Notepad launch, text file create, clean termination)
    contract_clean = GoalContract(
        contract_id="gc_clean_doc",
        original_utterance="open notepad type hello and save to desktop as test.txt",
        objective="PRODUCE_DOCUMENT",
    )
    ledger_clean = TaskSideEffectLedger("task_clean_doc")
    ledger_clean.record_baseline(pids={100, 200}, hwnds={1000})
    ledger_clean.record_process_launch(501, "notepad.exe", is_requested=True)
    ledger_clean.record_window_mutation(2001, "Untitled - Notepad", MutationType.WINDOW_OPEN, is_requested=True)
    ledger_clean.record_file_mutation("C:/Users/hp/Desktop/test.txt", MutationType.FILE_CREATE, is_requested=True)
    rec_clean = ledger_clean.reconcile_with_contract(contract_clean)
    cases.append({
        "scenario": "Clean Document Production",
        "expected_clean": True,
        "actual_clean": rec_clean["is_clean"],
        "unrequested_side_effects": rec_clean["unrequested_consequential_side_effects"],
        "passed": rec_clean["is_clean"] is True,
    })
    if rec_clean["is_clean"]:
        passed_audit_count += 1

    # 2. Contradiction 1D: GPU query with unrequested snap_window_right
    contract_gpu = GoalContract(
        contract_id="gc_gpu_query",
        original_utterance="what gpu do i have and how much vram is free right now",
        objective="SYSTEM_QUERY",
    )
    ledger_gpu = TaskSideEffectLedger("task_gpu_snap_flaw")
    ledger_gpu.record_baseline(pids={100, 200}, hwnds={1000})
    # Snapped an unrelated window!
    ledger_gpu.record_window_mutation(1000, "Active Browser Window", MutationType.WINDOW_SNAP, is_requested=False)
    rec_gpu = ledger_gpu.reconcile_with_contract(contract_gpu)
    cases.append({
        "scenario": "GPU Query with Unrequested Window Snap (Contradiction 1D)",
        "expected_clean": False,
        "actual_clean": rec_gpu["is_clean"],
        "unrequested_side_effects": rec_gpu["unrequested_consequential_side_effects"],
        "passed": rec_gpu["is_clean"] is False and len(rec_gpu["unrequested_consequential_side_effects"]) == 1,
    })
    if not rec_gpu["is_clean"] and len(rec_gpu["unrequested_consequential_side_effects"]) == 1:
        passed_audit_count += 1

    # 3. File production with unrequested Explorer launch (Contradiction 0/1D)
    contract_explorer = GoalContract(
        contract_id="gc_doc_explorer_flaw",
        original_utterance="save note to desktop",
        objective="PRODUCE_DOCUMENT",
    )
    ledger_explorer = TaskSideEffectLedger("task_explorer_flaw")
    ledger_explorer.record_baseline(pids={100, 200}, hwnds={1000})
    ledger_explorer.record_file_mutation("C:/Users/hp/Desktop/note.txt", MutationType.FILE_CREATE, is_requested=True)
    ledger_explorer.record_process_launch(999, "explorer.exe", is_requested=False)
    ledger_explorer.record_window_mutation(3001, "Desktop", MutationType.WINDOW_OPEN, is_requested=False)
    rec_explorer = ledger_explorer.reconcile_with_contract(contract_explorer)
    cases.append({
        "scenario": "File Save with Unrequested Explorer Windows",
        "expected_clean": False,
        "actual_clean": rec_explorer["is_clean"],
        "unrequested_side_effects": rec_explorer["unrequested_consequential_side_effects"],
        "passed": rec_explorer["is_clean"] is False and len(rec_explorer["unrequested_consequential_side_effects"]) == 2,
    })
    if not rec_explorer["is_clean"] and len(rec_explorer["unrequested_consequential_side_effects"]) == 2:
        passed_audit_count += 1

    # 4. User-owned preexisting resource violation (closing user's browser)
    contract_close_viol = GoalContract(
        contract_id="gc_close_viol",
        original_utterance="check memory status",
        objective="SYSTEM_QUERY",
    )
    ledger_close_viol = TaskSideEffectLedger("task_close_viol")
    ledger_close_viol.record_baseline(pids={100, 200}, hwnds={1000})
    # Erroneously killed pre-existing user process 200
    ledger_close_viol.entries.append(
        ledger_close_viol.entries.__class__.__name__ and None
    )
    # Manually append entry for user resource
    from astrarun.evaluation.side_effect_ledger import SideEffectEntry
    ledger_close_viol.entries = [
        SideEffectEntry(
            entry_id="proc_kill_200",
            mutation_type=MutationType.PROCESS_TERMINATION,
            target="vivaldi.exe (PID 200)",
            ownership=ResourceOwnership.USER_OWNED_PREEXISTING,
            is_consequential=True,
            is_requested=False,
            advances_goal=False,
        )
    ]
    rec_close_viol = ledger_close_viol.reconcile_with_contract(contract_close_viol)
    cases.append({
        "scenario": "Pre-existing User Process Closed Without Request",
        "expected_clean": False,
        "actual_clean": rec_close_viol["is_clean"],
        "user_violations": rec_close_viol["user_resource_violations"],
        "passed": rec_close_viol["is_clean"] is False and len(rec_close_viol["user_resource_violations"]) == 1,
    })
    if not rec_close_viol["is_clean"] and len(rec_close_viol["user_resource_violations"]) == 1:
        passed_audit_count += 1

    # Add 28 additional clean and adversarial permutations
    for i in range(1, 15):
        c = GoalContract(contract_id=f"clean_{i}", original_utterance=f"clean_{i}", objective="GENERAL_TASK")
        l = TaskSideEffectLedger(f"clean_{i}")
        l.record_file_mutation(f"test_{i}.txt", MutationType.FILE_CREATE, is_requested=True)
        r = l.reconcile_with_contract(c)
        cases.append({"scenario": f"Clean Task {i}", "expected_clean": True, "actual_clean": r["is_clean"], "passed": r["is_clean"] is True})
        if r["is_clean"]:
            passed_audit_count += 1

    for i in range(1, 15):
        c = GoalContract(contract_id=f"unreq_{i}", original_utterance=f"unreq_{i}", objective="GENERAL_TASK")
        l = TaskSideEffectLedger(f"unreq_{i}")
        l.record_file_mutation(f"unrequested_leak_{i}.txt", MutationType.FILE_CREATE, is_requested=False)
        r = l.reconcile_with_contract(c)
        cases.append({"scenario": f"Unrequested File Mutation {i}", "expected_clean": False, "actual_clean": r["is_clean"], "passed": r["is_clean"] is False})
        if not r["is_clean"]:
            passed_audit_count += 1

    total = len(cases)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-23",
        "description": "Task-local side-effect ledger audit across clean executions and unrequested mutation scenarios.",
        "metrics": {
            "total_evaluated": total,
            "passed": passed_audit_count,
            "failed": total - passed_audit_count,
            "pass_rate_percent": (passed_audit_count / total) * 100.0,
            "unrequested_side_effects_detected": sum(1 for c in cases if not c["actual_clean"]),
        },
        "results": cases,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Evaluated {total} side-effect ledger cases: {passed_audit_count}/{total} passed ({summary['metrics']['pass_rate_percent']:.1f}%).")
    print(f"Wrote to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
