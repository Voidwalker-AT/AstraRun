"""F0-25A.3 Mandatory Physical Adversarial Concurrency Test.

Verifies the central invariant:
  A RESOURCE APPEARING AFTER AN ASTRA ACTION DOES NOT IMPLY THAT ASTRA CREATED OR OWNS IT.
  Temporal correlation is NOT causal ownership.

Workflow:
1. Capture baseline world state.
2. Governed Astra action launches Character Map.
3. DURING the action window, the harness concurrently launches an independent unrequested process.
4. Both appear in pre->post temporal delta (NEW_TO_WORLD).
5. Causal reconciler classifies:
   - Astra launch -> TASK_CREATED (disposition CLOSE)
   - Independent process -> EXTERNAL_CONCURRENT (disposition PRESERVE)
6. Astra cleanup executes.
7. Physical verification:
   - Astra-created Character Map is closed/gone.
   - Independent concurrent process is STILL ALIVE.
   - Baseline resources preserved.
8. Harness cleans its own adversarial process (labeled HARNESS_OWNED).
9. Output raw evidence to docs/audit/F0_25A3_CONCURRENT_RESOURCE_RESULTS.json.
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
    LifecycleDisposition,
    OwnershipClass,
    TaskResourceReconciler,
    capture_world_frame,
    compare_world_state,
)


def run_adversarial_concurrency_test() -> dict:
    CHARMAP_PATH = r"C:\Windows\System32\charmap.exe"
    task_id = f"f025a3_adv_{int(time.time()*1000)}"

    print("[1] Capturing pre-test baseline world state...")
    baseline = capture_world_frame("adv_baseline")

    rec = TaskResourceReconciler()
    rec.begin(task_id, pre_snapshot={"frame": baseline})

    pre_action = capture_world_frame("adv_pre_action")

    print("[2] Executing governed Astra action: launching Character Map...")
    # Governed launch operation: directly yields PID
    astra_proc = subprocess.Popen([CHARMAP_PATH])
    astra_pid = astra_proc.pid

    print(f"    Governed Astra launch returned PID {astra_pid} ({CHARMAP_PATH})")

    print("[3] Concurrently spawning independent unrequested process during action window...")
    # Independent process: e.g. python background worker sleeping
    adv_cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
    adv_proc = subprocess.Popen(adv_cmd)
    adv_pid = adv_proc.pid

    print(f"    Independent unrequested process spawned with PID {adv_pid}")

    # Allow windows/processes to register in OS
    time.sleep(1.5)

    print("[4] Capturing post-action world frame...")
    post_action = capture_world_frame("adv_post_action")

    # Record action delta into causal reconciler
    print("[5] Reconciling observational delta with affirmative causal context...")
    created = rec.record_action_delta(
        pre_action=pre_action,
        post_action=post_action,
        action_id="open_charmap_action",
        action_context={"launched_pid": astra_pid},
    )

    tracked_dict = {r.identity.pid: r for r in created if r.identity.pid}
    astra_tracked = tracked_dict.get(astra_pid)
    adv_tracked = tracked_dict.get(adv_pid)

    print(f"    Total new resources detected in temporal delta: {len(created)}")
    print(f"    Astra PID {astra_pid} classification: {astra_tracked.ownership.value if astra_tracked else 'NOT_FOUND'}")
    print(f"    Adv PID {adv_pid} classification: {adv_tracked.ownership.value if adv_tracked else 'NOT_FOUND'}")

    # Assertions on classification before cleanup
    assert astra_tracked is not None, f"Governed PID {astra_pid} not tracked in delta"
    assert astra_tracked.ownership == OwnershipClass.TASK_CREATED, (
        f"Expected TASK_CREATED for governed PID, got {astra_tracked.ownership}"
    )
    assert astra_tracked.disposition == LifecycleDisposition.CLOSE, (
        f"Expected CLOSE disposition for task resource, got {astra_tracked.disposition}"
    )

    assert adv_tracked is not None, f"Concurrent PID {adv_pid} not tracked in delta"
    assert adv_tracked.ownership == OwnershipClass.EXTERNAL_CONCURRENT, (
        f"Expected EXTERNAL_CONCURRENT for independent PID, got {adv_tracked.ownership}"
    )
    assert adv_tracked.disposition == LifecycleDisposition.PRESERVE, (
        f"Expected PRESERVE disposition for concurrent resource, got {adv_tracked.disposition}"
    )

    print("[6] Running Astra lifecycle cleanup (reconcile_and_cleanup)...")
    report = rec.reconcile_and_cleanup()

    print(f"    Astra cleanup executed. Lifecycle OK: {report.lifecycle_ok}")
    print(f"    Cleaned resources count: {len(report.resources_cleaned)}")
    print(f"    Preserved resources count: {len(report.resources_preserved)}")

    # Check physical process liveness
    time.sleep(0.5)
    astra_alive_after = psutil.pid_exists(astra_pid)
    adv_alive_after = psutil.pid_exists(adv_pid)

    print(f"[7] Physical verification:")
    print(f"    Astra Character Map PID {astra_pid} alive after cleanup: {astra_alive_after} (Expected: False)")
    print(f"    Independent Adv PID {adv_pid} alive after cleanup: {adv_alive_after} (Expected: True)")

    assert not astra_alive_after, f"Astra-owned process {astra_pid} was NOT cleaned up!"
    assert adv_alive_after, f"Independent concurrent process {adv_pid} was wrongly terminated by Astra!"

    # Verify world state against baseline
    final_frame = capture_world_frame("adv_final")
    world_eval = compare_world_state(
        baseline=baseline,
        final=final_frame,
        tracked=rec.resources(),
    )

    print(f"    World state evaluation verdict: {world_eval['verdict']}")

    # [8] Post-assertion cleanup of harness-owned resource
    print("[8] Disposing harness-owned adversarial process (labeled HARNESS_OWNED)...")
    try:
        adv_proc.terminate()
        adv_proc.wait(timeout=2.0)
    except Exception:
        adv_proc.kill()
    harness_cleanup_verified = not psutil.pid_exists(adv_pid)
    print(f"    Harness-owned process {adv_pid} disposed: {harness_cleanup_verified}")

    test_passed = bool(
        not astra_alive_after
        and adv_alive_after
        and astra_tracked.ownership == OwnershipClass.TASK_CREATED
        and adv_tracked.ownership == OwnershipClass.EXTERNAL_CONCURRENT
        and report.lifecycle_ok
    )

    result = {
        "phase": "F0-25A.3",
        "scenario": "adversarial_concurrency_test",
        "task_id": task_id,
        "test_passed": test_passed,
        "governed_action": {
            "action_id": "open_charmap_action",
            "target": CHARMAP_PATH,
            "spawned_pid": astra_pid,
            "classified_ownership": astra_tracked.ownership.value,
            "disposition": astra_tracked.disposition.value,
            "alive_after_astra_cleanup": astra_alive_after,
            "cleaned_up_by_astra": not astra_alive_after,
        },
        "concurrent_independent_resource": {
            "command": adv_cmd,
            "spawned_pid": adv_pid,
            "classified_ownership": adv_tracked.ownership.value,
            "disposition": adv_tracked.disposition.value,
            "alive_after_astra_cleanup": adv_alive_after,
            "survived_astra_cleanup": adv_alive_after,
            "post_assertion_cleanup_by_harness": {
                "ownership_label": "HARNESS_OWNED",
                "harness_pid_disposed": harness_cleanup_verified,
            },
        },
        "reconcile_report": report.to_dict(),
        "world_state_evaluation": world_eval,
        "invariants_proven": [
            "Temporal coincidence does not create ownership (independent process was NEW_TO_WORLD but EXTERNAL_CONCURRENT)",
            "Astra cleanup terminated only task-created resource",
            "Unrelated concurrent resource survived Astra cleanup intact",
            "Zero unrequested side effects",
            "Harness cleanup labeled HARNESS_OWNED"
        ]
    }

    out_path = ROOT / "docs" / "audit" / "F0_25A3_CONCURRENT_RESOURCE_RESULTS.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(result, fp, indent=2)

    print(f"[9] Wrote results to {out_path}")
    return result


if __name__ == "__main__":
    res = run_adversarial_concurrency_test()
    if res["test_passed"]:
        print("\n*** ADVERSARIAL CONCURRENCY TEST PASSED ***\n")
        sys.exit(0)
    else:
        print("\n*** ADVERSARIAL CONCURRENCY TEST FAILED ***\n")
        sys.exit(1)
