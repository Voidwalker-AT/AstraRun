"""F0-25A.3R World Restoration Oracle Verification.

Verifies:
1. Forensic audit of why total_active_windows=0 was reported in F0_25A3_FINAL_WORLD_STATE.json:
   Win32 EnumWindows is desktop-specific. The agent process executes in an isolated sandbox desktop
   (WinSta0\\exebox-*). In this desktop, when no application windows are open, the window count is legitimately 0.
2. Evaluates ownership-relative restoration rather than "desktop empty":
   world_restored = (task_owned_remaining == 0)
                and (harness_owned_remaining == 0)
                and (protected_baseline_resources_missing == 0)
                and (external_concurrent_resources_modified_by_astra == 0)
                and (unknown_modified_by_astra == 0)
3. Records all required metrics and writes docs/audit/F0_25A3R_WORLD_RESTORATION.json.
"""

from __future__ import annotations

import ctypes
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


def get_desktop_environment_info() -> dict:
    """Audit the Win32 Desktop station and thread desktop."""
    out = {
        "is_win32": sys.platform == "win32",
        "winstation_name": "unknown",
        "thread_desktop_name": "unknown",
        "enumwindows_desktop_scope": "Calling thread's current desktop only",
    }
    if sys.platform != "win32":
        return out

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    name_buf = ctypes.create_unicode_buffer(512)
    hwinsta = user32.GetProcessWindowStation()
    if hwinsta and user32.GetUserObjectInformationW(hwinsta, 2, name_buf, 1024, None):
        out["winstation_name"] = name_buf.value

    tid = kernel32.GetCurrentThreadId()
    hdesk = user32.GetThreadDesktop(tid)
    if hdesk and user32.GetUserObjectInformationW(hdesk, 2, name_buf, 1024, None):
        out["thread_desktop_name"] = name_buf.value

    out["audit_explanation"] = (
        f"The agent process executes in window station '{out['winstation_name']}' on thread desktop "
        f"'{out['thread_desktop_name']}'. In Windows Win32 API, EnumWindows enumerates top-level windows "
        f"belonging strictly to the desktop associated with the calling thread. In an isolated execution "
        f"desktop ({out['thread_desktop_name']}), there are zero pre-existing shell/explorer windows; only windows "
        f"created by processes running on that desktop exist. Once test-launched windows close, the window count "
        f"on this desktop returns to 0. A naive 'desktop_clean' metric conflated this isolation with world emptiness. "
        f"The oracle must judge restoration relative to task and harness ownership, not global desktop vacancy."
    )
    return out


def run_world_restoration_verification() -> dict:
    CHARMAP_PATH = r"C:\Windows\System32\charmap.exe"
    task_id = f"f025a3r_world_{int(time.time()*1000)}"

    desktop_env = get_desktop_environment_info()
    print(f"[Desktop Audit] Station: {desktop_env['winstation_name']}, Desktop: {desktop_env['thread_desktop_name']}")

    # 1. Baseline capture
    print("[1] Capturing baseline world frame...")
    baseline_frame = capture_world_frame("world_restoration_baseline")
    baseline_process_count = len(baseline_frame.processes)
    baseline_window_count = len(baseline_frame.windows)

    # Protected baseline processes: sample persistent system / agent parent processes
    protected_baseline_pids = set()
    for p in psutil.process_iter(["pid", "name"]):
        try:
            pname = (p.info.get("name") or "").lower()
            if pname in ("explorer.exe", "svchost.exe", "system", "registry", "services.exe", "lsass.exe", "code.exe"):
                protected_baseline_pids.add(p.pid)
            elif p.pid == os.getpid() or p.pid == psutil.Process(os.getpid()).ppid():
                protected_baseline_pids.add(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print(f"    Baseline: {baseline_process_count} processes, {baseline_window_count} windows")
    print(f"    Tracking {len(protected_baseline_pids)} protected baseline identities")

    # 2. Reconciler begin
    rec = TaskResourceReconciler()
    rec.begin(task_id, pre_snapshot={"frame": baseline_frame})
    pre_action = capture_world_frame("world_pre_action")

    # 3. Governed action: launch Task-owned application (Charmap A)
    print("[2] Governed action: launching Task Window A (PID_A)...")
    action_id = "governed_open_charmap_a"
    proc_a = subprocess.Popen([CHARMAP_PATH])
    pid_a = proc_a.pid
    rec.register_launched_process(pid_a, action_id=action_id)

    # 4. Adversarial / concurrent unrequested action: launch External Window B (Charmap B)
    print("[3] Adversarial action: harness launches unrequested External Window B (PID_B)...")
    proc_b = subprocess.Popen([CHARMAP_PATH])
    pid_b = proc_b.pid

    # Let UI stabilize
    time.sleep(1.5)

    post_action = capture_world_frame("world_post_action")

    # 5. Observe delta and perform causal attribution
    print("[4] Recording action delta and classifying ownership...")
    action_context = {"launched_pid": pid_a, "action_id": action_id}
    new_resources = rec.record_action_delta(pre_action, post_action, action_id=action_id, action_context=action_context)

    # Separate task-owned, external concurrent, and unknown
    task_created_tracked = [
        r for r in rec.observed_resources()
        if r.ownership in (OwnershipClass.TASK_CREATED, OwnershipClass.TASK_DESCENDANT)
    ]
    external_concurrent_tracked = [
        r for r in rec.observed_resources()
        if r.ownership == OwnershipClass.EXTERNAL_CONCURRENT
    ]
    unknown_tracked = [
        r for r in rec.observed_resources()
        if r.ownership == OwnershipClass.UNKNOWN
    ]

    print(f"    Tracked {len(task_created_tracked)} task-owned resources")
    print(f"    Tracked {len(external_concurrent_tracked)} external concurrent resources")
    print(f"    Tracked {len(unknown_tracked)} unknown resources")

    # Assert causal classification invariants
    task_pids = {r.identity.pid for r in task_created_tracked if r.identity.pid}
    external_pids = {r.identity.pid for r in external_concurrent_tracked if r.identity.pid}
    assert pid_a in task_pids, f"Task PID {pid_a} missing from task_created_tracked"
    assert pid_b in external_pids, f"External PID {pid_b} missing from external_concurrent_tracked"
    assert pid_b not in task_pids, f"External PID {pid_b} falsely classified as TASK_CREATED!"

    # 6. Astra Cleanup: only Astra's task-owned resources must be disposed
    print("[5] Executing Astra cleanup (ownership-governed)...")
    reconcile_report = rec.reconcile_and_cleanup(goal_final_state="disposable")
    time.sleep(1.0)

    # Check state after Astra cleanup
    proc_a_alive_after_astra = psutil.pid_exists(pid_a)
    proc_b_alive_after_astra = psutil.pid_exists(pid_b)
    print(f"    After Astra cleanup: Task PID {pid_a} alive={proc_a_alive_after_astra}, External PID {pid_b} alive={proc_b_alive_after_astra}")

    assert not proc_a_alive_after_astra, f"Task PID {pid_a} still alive after Astra cleanup!"
    assert proc_b_alive_after_astra, f"External PID {pid_b} was destroyed by Astra cleanup! VIOLATION!"

    # Verify task residue
    task_owned_expected_disposed = len([r for r in task_created_tracked if r.disposition == LifecycleDisposition.CLOSE])
    task_owned_remaining_list = [r for r in task_created_tracked if r.identity.pid and psutil.pid_exists(r.identity.pid)]
    task_owned_remaining = len(task_owned_remaining_list)

    # Verify external concurrent resources touched by Astra
    # (Since proc_b is alive and was never targeted, touched count is 0)
    external_concurrent_modified_by_astra = 0
    for r in external_concurrent_tracked:
        if r.verification not in (None, LifecycleDisposition.PRESERVE, "preserve_untouched") and r.cleanup_action != "preserve_untouched":
            external_concurrent_modified_by_astra += 1

    unknown_modified_by_astra = 0
    for r in unknown_tracked:
        if r.cleanup_action != "preserve_untouched":
            unknown_modified_by_astra += 1

    # 7. Harness cleanup of its own adversarial resource
    print("[6] Harness executing post-assertion cleanup for its own adversarial resource...")
    harness_owned_identities = [f"process:{pid_b}"]
    harness_owned_expected_disposed = len(harness_owned_identities)
    try:
        proc_b.terminate()
        proc_b.wait(timeout=2.0)
    except Exception:
        proc_b.kill()

    time.sleep(0.5)
    proc_b_alive_after_harness = psutil.pid_exists(pid_b)
    harness_owned_remaining = 1 if proc_b_alive_after_harness else 0
    print(f"    After Harness cleanup: External PID {pid_b} alive={proc_b_alive_after_harness}")
    assert harness_owned_remaining == 0, f"Harness failed to dispose external PID {pid_b}"

    # 8. Final world state capture
    print("[7] Capturing final world state...")
    final_frame = capture_world_frame("world_restoration_final")
    final_process_count = len(final_frame.processes)
    final_window_count = len(final_frame.windows)

    # 9. Verify protected baseline resources
    missing_protected_baseline = []
    for ppid in protected_baseline_pids:
        if not psutil.pid_exists(ppid):
            missing_protected_baseline.append(ppid)
    protected_baseline_resources_missing = len(missing_protected_baseline)

    # 10. Compute ownership-relative restoration
    world_restored = (
        task_owned_remaining == 0
        and harness_owned_remaining == 0
        and protected_baseline_resources_missing == 0
        and external_concurrent_modified_by_astra == 0
        and unknown_modified_by_astra == 0
    )

    verdict = "PASS" if world_restored else "FAIL"

    evidence = {
        "phase": "F0-25A.3R",
        "title": "Ownership-Relative World Restoration Oracle Verification",
        "timestamp": time.time(),
        "task_id": task_id,
        "oracle_semantics": {
            "definition": (
                "world_restored = (task_owned_remaining == 0) "
                "AND (harness_owned_remaining == 0) "
                "AND (protected_baseline_resources_missing == 0) "
                "AND (external_concurrent_resources_modified_by_astra == 0) "
                "AND (unknown_modified_by_astra == 0)"
            ),
            "replaces_legacy": "desktop_clean (which naively conflated desktop isolation with emptiness)",
        },
        "desktop_environment_audit": desktop_env,
        "world_counts": {
            "baseline_process_count": baseline_process_count,
            "baseline_window_count": baseline_window_count,
            "final_process_count": final_process_count,
            "final_window_count": final_window_count,
        },
        "task_owned_accounting": {
            "task_owned_identities_expected_disposed": task_owned_expected_disposed,
            "task_owned_identities_remaining": task_owned_remaining,
            "task_owned_remaining_details": [r.to_dict() for r in task_owned_remaining_list],
        },
        "harness_owned_accounting": {
            "harness_owned_adversarial_identities": harness_owned_identities,
            "harness_owned_identities_expected_disposed": harness_owned_expected_disposed,
            "harness_owned_identities_remaining": harness_owned_remaining,
        },
        "protected_baseline_accounting": {
            "protected_baseline_tracked_count": len(protected_baseline_pids),
            "pre_existing_user_identities_unexpectedly_missing": protected_baseline_resources_missing,
            "missing_protected_identities": missing_protected_baseline,
        },
        "external_concurrent_accounting": {
            "external_concurrent_tracked_count": len(external_concurrent_tracked),
            "external_concurrent_identities_modified_or_disposed_by_astra": external_concurrent_modified_by_astra,
        },
        "unknown_accounting": {
            "unknown_tracked_count": len(unknown_tracked),
            "unknown_identities_modified_or_disposed_by_astra": unknown_modified_by_astra,
        },
        "world_restored": world_restored,
        "oracle_verdict": verdict,
    }

    out_path = ROOT / "docs" / "audit" / "F0_25A3R_WORLD_RESTORATION.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)

    print(f"\n[DONE] Wrote {out_path}")
    print(f"Result: world_restored={world_restored}, verdict={verdict}")
    return evidence


if __name__ == "__main__":
    run_world_restoration_verification()
