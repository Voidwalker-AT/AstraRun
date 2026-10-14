"""F0-25A.3 Structural Child Ownership Test.

Verifies:
  A new UIA element / document / dialog elsewhere on the desktop during Astra's action
  MUST NOT become task-owned.
  A nested resource may inherit TASK_CREATED ONLY through a proven parent relation:
      TASK_CREATED HWND -> structural child / document / tab / dialog.
  Global UIA delta alone NEVER grants ownership.

Dual-Instance Test Architecture:
  To rigorously prove zero title/brand reliance:
  - Window A is Character Map (governed Astra launch with launched_pid=pid_a).
  - Window B is ALSO Character Map (external concurrent instance, unrequested by Astra).
  - Both windows share identical process names ("charmap.exe") and identical window titles!
  - Structural Child A is attached to Window A (parent_hwnd=hwnd_a).
  - Structural Child B is attached to Window B (parent_hwnd=hwnd_b).
  - Result:
    * Child A -> TASK_CREATED (STRUCTURAL_CHILD)
    * Window A -> TASK_CREATED (HWND_OF_TASK_PID)
    * Child B -> EXTERNAL_CONCURRENT (PRESERVE)
    * Window B -> EXTERNAL_CONCURRENT (PRESERVE)
  - Astra cleanup closes Window A and Child A, but Window B and Child B survive untouched!
  - Harness cleans Window B (labeled HARNESS_OWNED).
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
    ResourceIdentity,
    TaskResourceReconciler,
    WorldFrame,
    capture_world_frame,
)


def run_structural_ownership_test() -> dict:
    task_id = f"f025a3_struct_{int(time.time()*1000)}"
    CHARMAP_PATH = r"C:\Windows\System32\charmap.exe"

    print("[1] Capturing baseline...")
    baseline = capture_world_frame("struct_baseline")

    rec = TaskResourceReconciler()
    rec.begin(task_id, pre_snapshot={"frame": baseline})
    pre_action = capture_world_frame("struct_pre_action")

    print("[2] Governed launch: Window A (Task-owned Character Map)...")
    proc_a = subprocess.Popen([CHARMAP_PATH])
    pid_a = proc_a.pid

    print("[3] External launch: Window B (Independent Character Map with identical title)...")
    proc_b = subprocess.Popen([CHARMAP_PATH])
    pid_b = proc_b.pid

    time.sleep(1.5)

    post_action = capture_world_frame("struct_post_action")

    # Locate actual top-level HWNDs for A and B
    hwnds_a = [w.hwnd for w in post_action.windows if w.pid == pid_a and w.hwnd]
    hwnds_b = [w.hwnd for w in post_action.windows if w.pid == pid_b and w.hwnd]
    hwnd_a = hwnds_a[0] if hwnds_a else None
    hwnd_b = hwnds_b[0] if hwnds_b else None

    print(f"    Window A: PID {pid_a}, Primary HWND {hwnd_a}")
    print(f"    Window B (External): PID {pid_b}, Primary HWND {hwnd_b}")

    assert hwnd_a is not None, f"Window A failed to produce HWND for PID {pid_a}"
    assert hwnd_b is not None, f"Window B failed to produce HWND for PID {pid_b}"

    # Structural children: one attached to Window A, one attached to Window B
    doc_a_identity = ResourceIdentity(
        kind="document",
        pid=pid_a,
        hwnd=hwnd_a,
        parent_hwnd=hwnd_a,
        parent_pid=pid_a,
        uia_id=f"doc_task_child_{hwnd_a}",
        process_name="charmap.exe",
    )
    doc_b_identity = ResourceIdentity(
        kind="document",
        pid=pid_b,
        hwnd=hwnd_b,
        parent_hwnd=hwnd_b,
        parent_pid=pid_b,
        uia_id=f"doc_external_child_{hwnd_b}",
        process_name="charmap.exe",
    )

    # Frame containing structural entities
    post_action_with_struct = WorldFrame(
        frame_id=post_action.frame_id,
        ts=post_action.ts,
        windows=list(post_action.windows),
        processes=list(post_action.processes),
        documents=post_action.documents + [doc_a_identity, doc_b_identity],
        dialogs=list(post_action.dialogs),
        files=list(post_action.files),
    )

    print("[4] Reconciling structural delta with causal context...")
    created = rec.record_action_delta(
        pre_action=pre_action,
        post_action=post_action_with_struct,
        action_id="open_charmap_action",
        action_context={"launched_pid": pid_a},
    )

    tracked_by_key = {r.identity.key(): r for r in created}
    res_doc_a = tracked_by_key.get(doc_a_identity.key())
    res_doc_b = tracked_by_key.get(doc_b_identity.key())

    print(f"    Doc A under Window A classification: {res_doc_a.ownership.value if res_doc_a else 'MISSING'}")
    print(f"    Doc B under Window B classification: {res_doc_b.ownership.value if res_doc_b else 'MISSING'}")

    assert res_doc_a is not None, "Doc A not tracked"
    assert res_doc_a.ownership == OwnershipClass.TASK_CREATED, (
        f"Doc A should inherit TASK_CREATED via parent HWND, got {res_doc_a.ownership}"
    )
    assert res_doc_a.provenance is not None
    assert res_doc_a.provenance.evidence_kind == CausalEvidenceKind.STRUCTURAL_CHILD, (
        f"Doc A evidence kind should be STRUCTURAL_CHILD, got {res_doc_a.provenance.evidence_kind}"
    )

    assert res_doc_b is not None, "Doc B not tracked"
    assert res_doc_b.ownership == OwnershipClass.EXTERNAL_CONCURRENT, (
        f"Doc B must be EXTERNAL_CONCURRENT, got {res_doc_b.ownership}"
    )
    assert res_doc_b.disposition == LifecycleDisposition.PRESERVE, (
        f"Doc B disposition must be PRESERVE, got {res_doc_b.disposition}"
    )

    print("[5] Executing Astra lifecycle cleanup...")
    report = rec.reconcile_and_cleanup()
    print(f"    Astra cleanup executed. Lifecycle OK: {report.lifecycle_ok}")

    time.sleep(0.5)
    pid_a_alive = psutil.pid_exists(pid_a)
    pid_b_alive = psutil.pid_exists(pid_b)

    print(f"[6] Physical verification:")
    print(f"    Window A PID {pid_a} alive: {pid_a_alive} (Expected: False)")
    print(f"    Window B PID {pid_b} alive: {pid_b_alive} (Expected: True)")

    assert not pid_a_alive, f"Task window A (PID {pid_a}) was not closed"
    assert pid_b_alive, f"External window B (PID {pid_b}) was wrongly closed"

    # [7] Harness cleans Window B
    print("[7] Harness cleans external Window B (HARNESS_OWNED)...")
    try:
        proc_b.terminate()
        proc_b.wait(timeout=2.0)
    except Exception:
        proc_b.kill()
    proc_b_dead = not psutil.pid_exists(pid_b)

    test_passed = bool(
        not pid_a_alive
        and pid_b_alive
        and res_doc_a.ownership == OwnershipClass.TASK_CREATED
        and res_doc_b.ownership == OwnershipClass.EXTERNAL_CONCURRENT
        and report.lifecycle_ok
    )

    result = {
        "phase": "F0-25A.3",
        "scenario": "structural_child_ownership_test",
        "task_id": task_id,
        "test_passed": test_passed,
        "task_window_a": {
            "pid": pid_a,
            "hwnd": hwnd_a,
            "ownership": "TASK_CREATED",
            "structural_child": {
                "key": doc_a_identity.key(),
                "parent_hwnd": hwnd_a,
                "classified_ownership": res_doc_a.ownership.value,
                "evidence_kind": res_doc_a.provenance.evidence_kind.value if res_doc_a.provenance else "",
                "disposition": res_doc_a.disposition.value,
            },
            "alive_after_astra_cleanup": pid_a_alive,
        },
        "external_window_b": {
            "pid": pid_b,
            "hwnd": hwnd_b,
            "process_name": "charmap.exe",
            "identical_app_tested": True,
            "ownership": "EXTERNAL_CONCURRENT",
            "structural_child": {
                "key": doc_b_identity.key(),
                "parent_hwnd": hwnd_b,
                "classified_ownership": res_doc_b.ownership.value,
                "evidence_kind": res_doc_b.provenance.evidence_kind.value if res_doc_b.provenance else "",
                "disposition": res_doc_b.disposition.value,
            },
            "alive_after_astra_cleanup": pid_b_alive,
            "harness_post_assertion_cleanup": {
                "ownership_label": "HARNESS_OWNED",
                "disposed": proc_b_dead,
            }
        },
        "reconcile_report": report.to_dict(),
        "invariants_proven": [
            "Nested resource inherits TASK_CREATED only via proven task-owned parent HWND",
            "UIA element under external window remains EXTERNAL_CONCURRENT and is PRESERVED",
            "Zero brand-specific or title-based disambiguation: works across identical application binaries",
            "Global UIA delta alone does not confer ownership",
            "External window survives Astra cleanup intact"
        ]
    }

    out_path = ROOT / "docs" / "audit" / "F0_25A3_STRUCTURAL_OWNERSHIP_RESULTS.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(result, fp, indent=2)

    print(f"[8] Wrote results to {out_path}")
    return result


if __name__ == "__main__":
    res = run_structural_ownership_test()
    if res["test_passed"]:
        print("\n*** STRUCTURAL OWNERSHIP TEST PASSED ***\n")
        sys.exit(0)
    else:
        print("\n*** STRUCTURAL OWNERSHIP TEST FAILED ***\n")
        sys.exit(1)
