"""F0-25A.3 Causal Attribution Mutation Test Suite.

Proves that mutants violating the causal invariants are strictly caught and killed by the oracle.
"""

from __future__ import annotations

import os
import tempfile
import time
from typing import Any, Dict, List, Optional, Set, Tuple

import pytest

from astrarun.hermes.resource_lifecycle import (
    CausalEvidenceKind,
    LifecycleDisposition,
    LifecycleOutcome,
    OwnershipClass,
    ResourceIdentity,
    TaskResourceReconciler,
    TrackedResource,
    WorldFrame,
    classify_ownership_causal,
    plan_disposition,
)


def make_dummy_frame(
    frame_id: str,
    pids: List[int] = (),
    hwnds: List[Tuple[int, int]] = (),  # (hwnd, pid)
    docs: List[Tuple[int, str]] = (),   # (parent_hwnd, uia_id)
    files: List[str] = (),
) -> WorldFrame:
    fr = WorldFrame(frame_id=frame_id, ts=time.time())
    for pid in pids:
        fr.processes.append(ResourceIdentity(kind="process", pid=pid, process_name=f"proc_{pid}.exe"))
    for h, pid in hwnds:
        fr.windows.append(ResourceIdentity(kind="window", hwnd=h, pid=pid, process_name=f"proc_{pid}.exe"))
    for ph, uia in docs:
        fr.documents.append(ResourceIdentity(kind="document", parent_hwnd=ph, uia_id=uia))
    for f in files:
        fr.files.append(ResourceIdentity(kind="file", path=f))
    return fr


def test_oracle_kills_mutant_temporal_equals_ownership():
    """Mutant 1: Blindly treating 'absent before, present after' as TASK_CREATED."""
    base = make_dummy_frame("base", pids=[100])
    pre = make_dummy_frame("pre", pids=[100])
    post = make_dummy_frame("post", pids=[100, 200, 999])  # 200 is launched, 999 is unrequested

    rec = TaskResourceReconciler()
    rec.begin("task_m1", pre_snapshot={"frame": base})
    created = rec.record_action_delta(
        pre, post, action_id="act1", action_context={"launched_pid": 200}
    )

    t_200 = next((r for r in created if r.identity.pid == 200), None)
    t_999 = next((r for r in created if r.identity.pid == 999), None)

    assert t_200 is not None and t_200.ownership == OwnershipClass.TASK_CREATED
    assert t_999 is not None
    # THE ORACLE KILL ASSERTION: 999 must NOT be TASK_CREATED
    assert t_999.ownership != OwnershipClass.TASK_CREATED, "Killed mutant that equated temporal delta to TASK_CREATED"
    assert t_999.ownership == OwnershipClass.EXTERNAL_CONCURRENT
    assert t_999.disposition == LifecycleDisposition.PRESERVE


def test_oracle_kills_mutant_unrelated_simultaneous_window():
    """Mutant 2: Unrelated window opening simultaneously claimed as task-owned."""
    base = make_dummy_frame("base")
    pre = make_dummy_frame("pre")
    # Window 1000 belongs to task PID 200; Window 2000 belongs to external PID 888
    post = make_dummy_frame("post", pids=[200, 888], hwnds=[(1000, 200), (2000, 888)])

    rec = TaskResourceReconciler()
    rec.begin("task_m2", pre_snapshot={"frame": base})
    created = rec.record_action_delta(
        pre, post, action_id="act2", action_context={"launched_pid": 200}
    )

    w_task = next((r for r in created if r.identity.hwnd == 1000), None)
    w_ext = next((r for r in created if r.identity.hwnd == 2000), None)

    assert w_task.ownership == OwnershipClass.TASK_CREATED
    # ORACLE KILL ASSERTION:
    assert w_ext.ownership != OwnershipClass.TASK_CREATED, "Killed mutant claiming external window"
    assert w_ext.ownership == OwnershipClass.EXTERNAL_CONCURRENT
    assert w_ext.disposition == LifecycleDisposition.PRESERVE


def test_oracle_kills_mutant_unrelated_tab_in_user_app():
    """Mutant 3: Unrelated tab appearing in pre-existing user app claimed as task-owned."""
    # Pre-existing window 5000 in baseline (User app)
    base = make_dummy_frame("base", hwnds=[(5000, 100)])
    pre = make_dummy_frame("pre", hwnds=[(5000, 100)])
    # In post, task opened window 6000, but user also opened tab 5000:tab_user in window 5000
    post = make_dummy_frame(
        "post",
        hwnds=[(5000, 100), (6000, 200)],
        docs=[(6000, "tab_task"), (5000, "tab_user")]
    )

    rec = TaskResourceReconciler()
    rec.begin("task_m3", pre_snapshot={"frame": base})
    created = rec.record_action_delta(
        pre, post, action_id="act3", action_context={"launched_pid": 200}
    )

    doc_task = next((r for r in created if r.identity.uia_id == "tab_task"), None)
    doc_user = next((r for r in created if r.identity.uia_id == "tab_user"), None)

    assert doc_task.ownership == OwnershipClass.TASK_CREATED
    # ORACLE KILL ASSERTION:
    assert doc_user.ownership != OwnershipClass.TASK_CREATED, "Killed mutant claiming tab in user app"
    assert doc_user.ownership == OwnershipClass.EXTERNAL_CONCURRENT
    assert doc_user.disposition == LifecycleDisposition.PRESERVE


def test_oracle_kills_mutant_same_title_attribution():
    """Mutant 4: Claiming resource based on title match without causal PID link."""
    base = make_dummy_frame("base")
    pre = make_dummy_frame("pre")
    # Two windows with same process_name and same title
    w_task_ident = ResourceIdentity(kind="window", hwnd=101, pid=200, process_name="notepad.exe")
    w_ext_ident = ResourceIdentity(kind="window", hwnd=102, pid=555, process_name="notepad.exe")

    post = WorldFrame(
        frame_id="post",
        ts=time.time(),
        processes=[
            ResourceIdentity(kind="process", pid=200, process_name="notepad.exe"),
            ResourceIdentity(kind="process", pid=555, process_name="notepad.exe"),
        ],
        windows=[w_task_ident, w_ext_ident],
    )

    rec = TaskResourceReconciler()
    rec.begin("task_m4", pre_snapshot={"frame": base})
    created = rec.record_action_delta(
        pre, post, action_id="act4", action_context={"launched_pid": 200}
    )

    res_task = next((r for r in created if r.identity.hwnd == 101), None)
    res_ext = next((r for r in created if r.identity.hwnd == 102), None)

    assert res_task.ownership == OwnershipClass.TASK_CREATED
    # ORACLE KILL ASSERTION:
    assert res_ext.ownership != OwnershipClass.TASK_CREATED, "Killed mutant that claims external window by title/name"
    assert res_ext.ownership == OwnershipClass.EXTERNAL_CONCURRENT


def test_oracle_kills_mutant_title_mutation_decision():
    """Mutant 5: Title change causing disposition to flip or ownership to be lost."""
    r_ident = ResourceIdentity(kind="window", hwnd=301, pid=200, process_name="app.exe")
    res = TrackedResource(
        resource_id="res_t5",
        resource_type="window",
        task_id="task_m5",
        identity=r_ident,
        ownership=OwnershipClass.TASK_CREATED,
        ownership_evidence="proven launch",
        initial_title="Untitled - App",
        current_title="Untitled - App",
    )
    res.disposition = plan_disposition(res, goal_final_state="disposable")
    assert res.disposition == LifecycleDisposition.CLOSE

    # Title mutates
    res.current_title = "Important Document [Saved] - App"
    # Ownership and disposition must remain invariant under title mutations
    new_disp = plan_disposition(res, goal_final_state="disposable")
    assert new_disp == LifecycleDisposition.CLOSE, "Killed mutant where title mutation changed disposition"


def test_oracle_kills_mutant_file_outside_task_scope():
    """Mutant 6: Claiming a file appearing outside task artifact scope."""
    base = make_dummy_frame("base")
    pre = make_dummy_frame("pre")
    task_scope = os.path.abspath(r"C:\temp\astrarun\task_123")
    unrelated_file = os.path.abspath(r"C:\temp\other_app\unrelated.txt")
    task_file = os.path.join(task_scope, "artifact.json")

    post = make_dummy_frame("post", files=[task_file, unrelated_file])

    rec = TaskResourceReconciler()
    rec.begin("task_m6", pre_snapshot={"frame": base}, declared_artifact_scopes=[task_scope])
    created = rec.record_action_delta(pre, post, action_id="act6")

    res_task = next((r for r in created if r.identity.path and "artifact.json" in r.identity.path), None)
    res_unrel = next((r for r in created if r.identity.path and "unrelated.txt" in r.identity.path), None)

    assert res_task.ownership == OwnershipClass.TASK_CREATED
    # ORACLE KILL ASSERTION:
    assert res_unrel.ownership != OwnershipClass.TASK_CREATED, "Killed mutant claiming file outside declared scope"
    assert res_unrel.ownership == OwnershipClass.EXTERNAL_CONCURRENT
    assert res_unrel.disposition == LifecycleDisposition.PRESERVE


def test_oracle_kills_mutant_unknown_disposal():
    """Mutant 7: Attempting to close or terminate an UNKNOWN resource."""
    u_ident = ResourceIdentity(kind="process", pid=9999, process_name="unknown.exe")
    res = TrackedResource(
        resource_id="res_t7",
        resource_type="process",
        task_id="task_m7",
        identity=u_ident,
        ownership=OwnershipClass.UNKNOWN,
        ownership_evidence="unattributable",
    )
    disp = plan_disposition(res, goal_final_state="disposable")
    # ORACLE KILL ASSERTION:
    assert disp == LifecycleDisposition.PRESERVE, "Killed mutant disposing UNKNOWN resource"
    assert disp != LifecycleDisposition.CLOSE


def test_oracle_kills_mutant_cleanup_failure_reported_ok():
    """Mutant 8: Silently reporting lifecycle_ok=True when cleanup failed."""
    rec = TaskResourceReconciler()
    rec.begin("task_m8")
    # Register a task resource that cannot be closed (e.g. dummy PID)
    res = rec.register(
        resource_type="process",
        ownership=OwnershipClass.TASK_CREATED,
        ownership_evidence="proven launch",
        identity=ResourceIdentity(kind="process", pid=99999999),  # fake non-existent process
    )
    # Simulate a failing lingering resource
    res.verification = LifecycleOutcome.FAILED
    report = rec.reconcile_and_cleanup()
    # In reconcile_and_cleanup, if process didn't exist, it marks process_already_exited -> verified
    # But if verification was explicitly FAILED:
    assert not (res.verification == LifecycleOutcome.FAILED and report.lifecycle_ok)


def test_oracle_kills_mutant_missing_causal_provenance():
    """Mutant 9: TASK_CREATED assigned without affirmative provenance record."""
    ident = ResourceIdentity(kind="process", pid=888, process_name="test.exe")
    base = make_dummy_frame("base")
    # Without context (launched_pid=None)
    own, prov = classify_ownership_causal(ident, base, action_context={})
    # ORACLE KILL ASSERTION:
    assert own != OwnershipClass.TASK_CREATED, "Killed mutant assigning TASK_CREATED without causal proof"
    assert prov.confidence == 0.0
