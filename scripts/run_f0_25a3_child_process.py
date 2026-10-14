"""F0-25A.3 Child Process Test.

Proves Astra can trace genuine causal descendants via OS process tree ancestry
without claiming every new process globally.

Workflow:
1. Capture baseline.
2. Governed Astra action launches a launcher process that spawns a legitimate child process.
3. Concurrently during the action window, an independent third process is spawned by harness.
4. All three appear in observational delta.
5. Causal reconciler evaluates:
   - Parent launcher -> TASK_CREATED
   - Spawned child -> TASK_DESCENDANT (provenance: DESCENDANT_PROCESS)
   - Independent process -> EXTERNAL_CONCURRENT
6. Astra cleanup runs:
   - Parent and child terminated.
   - Independent process survives.
7. Harness cleans independent process (labeled HARNESS_OWNED).
8. Produce docs/audit/F0_25A3_CHILD_PROCESS_RESULTS.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import psutil

from astrarun.hermes.resource_lifecycle import (
    CausalEvidenceKind,
    LifecycleDisposition,
    OwnershipClass,
    TaskResourceReconciler,
    capture_world_frame,
    compare_world_state,
)


def run_child_process_test() -> dict:
    task_id = f"f025a3_child_{int(time.time()*1000)}"
    print("[1] Capturing baseline...")
    baseline = capture_world_frame("child_baseline")

    rec = TaskResourceReconciler()
    rec.begin(task_id, pre_snapshot={"frame": baseline})
    pre_action = capture_world_frame("child_pre_action")

    # Script for parent launcher that spawns a legitimate child
    parent_script = """
import subprocess, sys, time
child_cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
p = subprocess.Popen(child_cmd)
with open("child_pid.txt", "w") as f:
    f.write(str(p.pid))
time.sleep(60)
"""
    parent_script_path = ROOT / "scratch_parent_launcher.py"
    with open(parent_script_path, "w", encoding="utf-8") as f:
        f.write(parent_script)

    print("[2] Executing governed launch: Parent launcher (which spawns child worker)...")
    parent_proc = subprocess.Popen([sys.executable, str(parent_script_path)])
    parent_pid = parent_proc.pid

    # Wait for child to spawn and record its PID
    child_pid_file = ROOT / "child_pid.txt"
    child_pid = None
    for _ in range(30):
        if child_pid_file.exists():
            try:
                with open(child_pid_file, "r") as f:
                    child_pid = int(f.read().strip())
                break
            except Exception:
                pass
        time.sleep(0.1)

    print(f"    Parent launcher PID: {parent_pid}")
    print(f"    Child worker PID: {child_pid}")

    print("[3] Spawning independent concurrent process (unrelated sibling)...")
    unrelated_proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    unrelated_pid = unrelated_proc.pid
    print(f"    Unrelated independent PID: {unrelated_pid}")

    time.sleep(1.0)

    print("[4] Capturing post-action world frame...")
    post_action = capture_world_frame("child_post_action")

    print("[5] Reconciling observational delta...")
    created = rec.record_action_delta(
        pre_action=pre_action,
        post_action=post_action,
        action_id="launch_parent_action",
        action_context={"launched_pid": parent_pid},
    )

    tracked_dict = {r.identity.pid: r for r in created if r.identity.pid}
    parent_tracked = tracked_dict.get(parent_pid)
    child_tracked = tracked_dict.get(child_pid)
    unrelated_tracked = tracked_dict.get(unrelated_pid)

    print(f"    Parent PID {parent_pid} class: {parent_tracked.ownership.value if parent_tracked else 'MISSING'}")
    print(f"    Child PID {child_pid} class: {child_tracked.ownership.value if child_tracked else 'MISSING'}")
    print(f"    Unrelated PID {unrelated_pid} class: {unrelated_tracked.ownership.value if unrelated_tracked else 'MISSING'}")

    assert parent_tracked is not None, f"Parent PID {parent_pid} not tracked"
    assert parent_tracked.ownership == OwnershipClass.TASK_CREATED, (
        f"Parent should be TASK_CREATED, got {parent_tracked.ownership}"
    )

    assert child_tracked is not None, f"Child PID {child_pid} not tracked"
    assert child_tracked.ownership == OwnershipClass.TASK_DESCENDANT, (
        f"Child should be TASK_DESCENDANT, got {child_tracked.ownership}"
    )
    assert child_tracked.provenance is not None
    assert child_tracked.provenance.evidence_kind == CausalEvidenceKind.DESCENDANT_PROCESS, (
        f"Child evidence kind should be DESCENDANT_PROCESS, got {child_tracked.provenance.evidence_kind}"
    )

    assert unrelated_tracked is not None, f"Unrelated PID {unrelated_pid} not tracked"
    assert unrelated_tracked.ownership == OwnershipClass.EXTERNAL_CONCURRENT, (
        f"Unrelated should be EXTERNAL_CONCURRENT, got {unrelated_tracked.ownership}"
    )

    print("[6] Running Astra lifecycle cleanup...")
    report = rec.reconcile_and_cleanup()
    print(f"    Cleanup completed. Lifecycle OK: {report.lifecycle_ok}")

    time.sleep(0.5)
    parent_alive = psutil.pid_exists(parent_pid)
    child_alive = psutil.pid_exists(child_pid) if child_pid else False
    unrelated_alive = psutil.pid_exists(unrelated_pid)

    print(f"[7] Physical verification:")
    print(f"    Parent PID {parent_pid} alive: {parent_alive} (Expected: False)")
    print(f"    Child PID {child_pid} alive: {child_alive} (Expected: False)")
    print(f"    Unrelated PID {unrelated_pid} alive: {unrelated_alive} (Expected: True)")

    assert not parent_alive, f"Parent process {parent_pid} was not terminated"
    assert not child_alive, f"Child process {child_pid} was not terminated"
    assert unrelated_alive, f"Unrelated process {unrelated_pid} was wrongly terminated"

    # [8] Post-assertion cleanup by harness
    print("[8] Disposing harness-owned unrelated process (HARNESS_OWNED)...")
    try:
        unrelated_proc.terminate()
        unrelated_proc.wait(timeout=2.0)
    except Exception:
        unrelated_proc.kill()
    unrelated_cleaned = not psutil.pid_exists(unrelated_pid)

    # Clean temporary files
    for p in (parent_script_path, child_pid_file):
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass

    test_passed = bool(
        not parent_alive
        and not child_alive
        and unrelated_alive
        and parent_tracked.ownership == OwnershipClass.TASK_CREATED
        and child_tracked.ownership == OwnershipClass.TASK_DESCENDANT
        and unrelated_tracked.ownership == OwnershipClass.EXTERNAL_CONCURRENT
        and report.lifecycle_ok
    )

    result = {
        "phase": "F0-25A.3",
        "scenario": "child_process_ancestry_test",
        "task_id": task_id,
        "test_passed": test_passed,
        "parent_launcher": {
            "pid": parent_pid,
            "ownership": parent_tracked.ownership.value,
            "evidence_kind": parent_tracked.provenance.evidence_kind.value if parent_tracked.provenance else "",
            "cleaned_up": not parent_alive,
        },
        "child_worker": {
            "pid": child_pid,
            "ownership": child_tracked.ownership.value,
            "evidence_kind": child_tracked.provenance.evidence_kind.value if child_tracked.provenance else "",
            "parent_link": f"process:{parent_pid}",
            "cleaned_up": not child_alive,
        },
        "unrelated_concurrent_process": {
            "pid": unrelated_pid,
            "ownership": unrelated_tracked.ownership.value,
            "evidence_kind": unrelated_tracked.provenance.evidence_kind.value if unrelated_tracked.provenance else "",
            "survived_astra_cleanup": unrelated_alive,
            "harness_post_assertion_cleanup": {
                "ownership_label": "HARNESS_OWNED",
                "disposed": unrelated_cleaned,
            }
        },
        "reconcile_report": report.to_dict(),
        "invariants_proven": [
            "Astra traces legitimate child processes via OS process tree ancestry",
            "Descendants inherit TASK_DESCENDANT and are cleaned up with parent",
            "Unrelated concurrent processes without ancestry remain EXTERNAL_CONCURRENT and are preserved"
        ]
    }

    out_path = ROOT / "docs" / "audit" / "F0_25A3_CHILD_PROCESS_RESULTS.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(result, fp, indent=2)

    print(f"[9] Wrote results to {out_path}")
    return result


if __name__ == "__main__":
    res = run_child_process_test()
    if res["test_passed"]:
        print("\n*** CHILD PROCESS TEST PASSED ***\n")
        sys.exit(0)
    else:
        print("\n*** CHILD PROCESS TEST FAILED ***\n")
        sys.exit(1)
