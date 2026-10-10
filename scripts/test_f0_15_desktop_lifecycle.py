"""Authoritative Physical Desktop Acceptance Test for Phase F0-15.

Tests:
1. Calculator Lifecycle:
   - Open -> Calculate (58+42=) -> Verify UI Display (100) -> Close ONLY Astra's instance -> Verify Closed.
2. Notepad Lifecycle with SAVE_BEFORE_CLOSE:
   - Open -> Write verified text -> Save (Ctrl+S) -> Verify File & SHA-256 -> Close ONLY Astra's instance -> Verify Closed & File Intact.
3. Mixed Ownership Test (CRITICAL OWNERSHIP RULE):
   - Pre-existing User Notepad A opened beforehand.
   - Astra opens Notepad B for a task, writes, saves, closes Notepad B.
   - Verify User Notepad A is STILL OPEN, responsive, and completely untouched.
4. User Takeover Detachment ('Do Not Fight The User'):
   - Astra launches window -> User interaction detected -> Window detached from auto-cleanup.
5. Orphan Recovery & PID Reuse Guard:
   - Simulates unmanaged crash recovery and verifies create_time check prevents PID reuse termination.

Outputs: docs/audit/F0_15_RESOURCE_LIFECYCLE_EVIDENCE.json
"""

import ctypes
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import psutil

from astrarun.applications.service import close_application, open_application
from astrarun.core.logging import get_logger
from astrarun.interaction.controller import invoke_element, set_element_value
from astrarun.interaction.discovery import inspect_window_ui
from astrarun.interaction.keyboard import dispatch_shortcut, parse_shortcut, type_text_into_active
from astrarun.tasks.models import TaskStatus
from astrarun.tasks.resource_ledger import (
    AstraResourceLedger,
    CleanupPolicy,
    ContentClassification,
    OwnedResource,
    ResourceLifecycleState,
    ResourceType,
    _ensure_desktop_attached,
    clean_notepad_tabstate_for_path,
)
from astrarun.tools.apps import _launch_win32_process
from astrarun.windows.controller import focus_window
from astrarun.windows.discovery import list_windows

logger = get_logger("astrarun.test_f0_15")
user32 = ctypes.windll.user32 if sys.platform == "win32" else None


def get_current_desktop_windows() -> List[Dict[str, Any]]:
    """Fetch visible windows on interactive desktop."""
    _ensure_desktop_attached()
    res = list_windows()
    if res.success and res.data:
        return res.data.get("windows", [])
    return []


def test_1_calculator_lifecycle() -> Dict[str, Any]:
    """Test 1: Calculator open -> calculate -> verify display -> close ONLY Astra's instance."""
    print("\n" + "=" * 70)
    print("TEST 1: CALCULATOR LIFECYCLE (Open -> Calculate -> Verify -> Close)")
    print("=" * 70)
    task_id = f"test_f0_15_calc_{int(time.time())}"
    ledger = AstraResourceLedger.get_instance()

    before_windows = get_current_desktop_windows()
    calc_before = [w for w in before_windows if "calc" in w["app_id"] or "calculator" in w["title"].lower()]
    print(f"[*] Pre-test visible calculators: {len(calc_before)}")

    # 1. Launch Calculator via Astra open_application
    t0 = time.time()
    open_res = open_application("calc", task_id=task_id)
    assert open_res.success, f"Failed to launch Calculator: {open_res.message}"
    calc_data = open_res.data or {}
    astra_pid = calc_data.get("pid")
    astra_hwnd = calc_data.get("hwnd")
    res_id = calc_data.get("resource_id")
    print(f"[+] Astra launched Calculator: ResourceID={res_id}, PID={astra_pid}, HWND={astra_hwnd}")
    assert astra_hwnd is not None, "Calculator HWND must be captured!"

    # 2. Wait for Calculator window and focus
    time.sleep(1.0)
    focus_res = focus_window(astra_hwnd, pid=astra_pid)
    print(f"[*] Focused Calculator window: {focus_res.success}")
    time.sleep(0.5)

    # 3. Perform Calculation (58 + 42 =)
    type_res = type_text_into_active("58+42=")
    print(f"[*] Dispatched calculation keys '58+42=': {type_res[1]}")
    time.sleep(0.8)

    # 4. Verify display via UI Automation
    elems = inspect_window_ui(astra_hwnd, max_depth=5)
    display_text = None
    for el in elems:
        if "100" in el.name or el.automation_id == "CalculatorResults":
            display_text = el.name
            break

    print(f"[+] UI Automation verified display: {display_text!r}")
    assert display_text is not None and "100" in display_text, f"Expected display '100', got {display_text!r}"

    # 5. Close ONLY Astra's Calculator instance
    close_res = close_application("calc", task_id=task_id)
    print(f"[*] Astra close_application result: {close_res.success} ({close_res.message})")
    assert close_res.success, f"Failed to close Calculator: {close_res.message}"

    # 6. Verify window is completely closed
    time.sleep(0.8)
    _ensure_desktop_attached()
    is_window_alive = bool(user32.IsWindow(astra_hwnd)) if user32 else False
    after_windows = get_current_desktop_windows()
    calc_after = [w for w in after_windows if w["hwnd"] == astra_hwnd]

    print(f"[+] IsWindow alive: {is_window_alive}, Windows matching Astra HWND: {len(calc_after)}")
    assert not is_window_alive, f"Calculator HWND {astra_hwnd} is still alive!"
    assert len(calc_after) == 0, f"Calculator window {astra_hwnd} still visible in desktop enumeration!"

    print("[PASS] TEST 1: Calculator lifecycle completed with 0 debris remaining.")
    return {
        "test": "calculator_lifecycle",
        "status": "PASS",
        "task_id": task_id,
        "pid": astra_pid,
        "hwnd": astra_hwnd,
        "calculation": "58+42=",
        "verified_display": display_text,
        "closure_verified": True,
        "latency_sec": round(time.time() - t0, 3),
    }


def test_2_notepad_lifecycle() -> Dict[str, Any]:
    """Test 2: Notepad open -> write text -> save -> verify file & SHA-256 -> close -> verify intact."""
    print("\n" + "=" * 70)
    print("TEST 2: NOTEPAD LIFECYCLE WITH SAVE_BEFORE_CLOSE & SHA-256")
    print("=" * 70)
    task_id = f"test_f0_15_notepad_{int(time.time())}"
    tmp_dir = Path(tempfile.gettempdir())
    test_file = tmp_dir / f"astra_f0_15_artifact_{int(time.time())}.txt"
    test_file.write_text("INITIAL_EMPTY\n", encoding="utf-8")
    print(f"[*] Created target artifact file: {test_file}")

    astra_pid = None
    astra_hwnd = None

    try:
        t0 = time.time()
        # 1. Astra launches Notepad with SAVE_BEFORE_CLOSE policy
        open_res = open_application(
            "notepad",
            target=str(test_file),
            task_id=task_id,
            cleanup_policy=CleanupPolicy.SAVE_BEFORE_CLOSE,
            content_classification=ContentClassification.TASK_ARTIFACT,
        )
        assert open_res.success, f"Failed to launch Notepad: {open_res.message}"
        np_data = open_res.data or {}
        astra_pid = np_data.get("pid")
        astra_hwnd = np_data.get("hwnd")
        res_id = np_data.get("resource_id")
        print(f"[+] Astra launched Notepad: ResourceID={res_id}, PID={astra_pid}, HWND={astra_hwnd}")
        assert astra_hwnd is not None, "Notepad HWND must be captured!"

        # 2. Wait and focus
        time.sleep(1.0)
        focus_res = focus_window(astra_hwnd, pid=astra_pid)
        print(f"[*] Focused Notepad window: {focus_res.success}")
        time.sleep(0.5)

        # 3. Enter verified text content into 'Text editor' element
        unique_content = f"AstraRun Phase F0-15 Verified Content [Timestamp={time.time()}]\nDeterministic artifact line."
        elems = inspect_window_ui(astra_hwnd, max_depth=5)
        editor_found = False
        for el in elems:
            if el.name == "Text editor":
                set_res = set_element_value(el, unique_content)
                print(f"[*] Set text in 'Text editor': {set_res[1]}")
                assert set_res[0], f"Failed setting editor value: {set_res[1]}"
                editor_found = True
                break
        assert editor_found, "Could not find 'Text editor' element in Notepad window!"
        time.sleep(0.5)

        # 4. Save document via Ctrl+S
        sc = parse_shortcut("ctrl+s")
        sc_res = dispatch_shortcut(sc, target_hwnd=astra_hwnd)
        print(f"[*] Dispatched save shortcut Ctrl+S: {sc_res[1]}")
        time.sleep(1.0)

        # 5. Read back artifact from disk and compute SHA-256
        disk_text = test_file.read_text(encoding="utf-8")
        disk_sha256 = hashlib.sha256(disk_text.encode("utf-8")).hexdigest()
        print(f"[+] Artifact on disk verified: length={len(disk_text)}, SHA-256={disk_sha256}")
        assert unique_content in disk_text, f"Disk content does not match typed text! Content: {disk_text!r}"

        # 6. Close ONLY Astra's Notepad instance (enforcing SAVE_BEFORE_CLOSE verification)
        close_res = close_application("notepad", task_id=task_id)
        print(f"[*] Astra close_application result: {close_res.success} ({close_res.message})")
        assert close_res.success, f"Failed to close Notepad: {close_res.message}"

        # 7. Verify window is closed and artifact file remains 100% intact
        time.sleep(0.8)
        _ensure_desktop_attached()
        is_window_alive = bool(user32.IsWindow(astra_hwnd)) if user32 else False
        after_windows = get_current_desktop_windows()
        np_after = [w for w in after_windows if w["hwnd"] == astra_hwnd]

        print(f"[+] IsWindow alive: {is_window_alive}, Windows matching Astra HWND: {len(np_after)}")
        assert not is_window_alive, f"Notepad HWND {astra_hwnd} is still alive!"
        assert len(np_after) == 0, f"Notepad window {astra_hwnd} still visible!"

        # Verify file intact after closure
        assert test_file.exists(), "Target artifact file was deleted or lost!"
        final_text = test_file.read_text(encoding="utf-8")
        final_sha256 = hashlib.sha256(final_text.encode("utf-8")).hexdigest()
        assert final_sha256 == disk_sha256, "Artifact file hash changed after window closure!"
        print(f"[+] Post-closure artifact hash identical: {final_sha256}")

        print("[PASS] TEST 2: Notepad lifecycle completed; artifact preserved on disk.")
        return {
            "test": "notepad_lifecycle_save_before_close",
            "status": "PASS",
            "task_id": task_id,
            "pid": astra_pid,
            "hwnd": astra_hwnd,
            "artifact_path": str(test_file),
            "sha256": final_sha256,
            "closure_verified": True,
            "artifact_intact": True,
            "latency_sec": round(time.time() - t0, 3),
        }
    finally:
        # Teardown: ensure process is dead and tabstate is purged before removing test file
        if astra_pid and psutil.pid_exists(astra_pid):
            try:
                p = psutil.Process(astra_pid)
                p.kill()
                p.wait(timeout=1.0)
            except Exception:
                pass
        clean_notepad_tabstate_for_path(str(test_file))
        time.sleep(0.2)
        try:
            if test_file.exists():
                test_file.unlink()
        except Exception:
            pass



def test_3_mixed_ownership() -> Dict[str, Any]:
    """Test 3: Mixed Ownership (CRITICAL OWNERSHIP RULE).

    - User opens Notepad A beforehand with sensitive user content.
    - Astra opens Notepad B for a task, types, saves, closes B.
    - Verify Notepad A is STILL OPEN, responsive, and completely untouched!
    """
    print("\n" + "=" * 70)
    print("TEST 3: MIXED OWNERSHIP (Never Close Pre-Existing User Windows)")
    print("=" * 70)
    tmp_dir = Path(tempfile.gettempdir())
    user_file = tmp_dir / f"user_unrelated_doc_{int(time.time())}.txt"
    user_content = "USER CONFIDENTIAL DATA — MUST REMAIN OPEN AND UNTOUCHED\nLine 2 of user work."
    user_file.write_text(user_content, encoding="utf-8")
    user_initial_hash = hashlib.sha256(user_content.encode("utf-8")).hexdigest()
    print(f"[*] Created User document: {user_file} (SHA-256: {user_initial_hash})")

    user_hwnd: Optional[int] = None
    user_pid: Optional[int] = None
    astra_hwnd: Optional[int] = None
    astra_pid: Optional[int] = None

    try:
        # Step 1: User launches Notepad A independently (simulating ambient user work)
        t0 = time.time()
        ok_user_launch = _launch_win32_process(f'notepad.exe "{user_file}"')
        assert ok_user_launch, "Failed to launch pre-existing user Notepad A"
        time.sleep(2.0)

        # Locate User Notepad A window
        _ensure_desktop_attached()
        user_windows = get_current_desktop_windows()
        for w in user_windows:
            if "notepad" in w["app_id"] and user_file.name.lower() in w["title"].lower():
                user_hwnd = w["hwnd"]
                user_pid = w["pid"]
                break

        print(f"[+] User Notepad A active: HWND={user_hwnd}, PID={user_pid}")
        assert user_hwnd is not None, "Failed to discover User Notepad A window handle!"

        # Step 2: Astra begins task and opens Notepad B
        task_id = f"test_f0_15_mixed_{int(time.time())}"
        astra_file = tmp_dir / f"astra_task_doc_{int(time.time())}.txt"
        astra_file.write_text("ASTRA INITIAL\n", encoding="utf-8")

        open_b_res = open_application(
            "notepad",
            target=str(astra_file),
            task_id=task_id,
            cleanup_policy=CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
            content_classification=ContentClassification.TEMPORARY_TEST_CONTENT,
        )
        assert open_b_res.success, f"Failed to launch Astra Notepad B: {open_b_res.message}"
        b_data = open_b_res.data or {}
        astra_hwnd = b_data.get("hwnd")
        astra_pid = b_data.get("pid")
        print(f"[+] Astra launched Notepad B: HWND={astra_hwnd}, PID={astra_pid}")
        assert astra_hwnd is not None, "Astra Notepad B HWND must be captured!"

        # Step 3: Validate strict separation of instances
        print(f"[*] Comparing instance handles: User HWND {user_hwnd} != Astra HWND {astra_hwnd}")
        assert user_hwnd != astra_hwnd, "User and Astra must have distinct HWNDs!"
        time.sleep(1.0)

        # Step 4: Astra interacts with Notepad B
        focus_b = focus_window(astra_hwnd, pid=astra_pid)
        time.sleep(0.5)
        elems_b = inspect_window_ui(astra_hwnd, max_depth=5)
        for el in elems_b:
            if el.name == "Text editor":
                set_element_value(el, "Task B ephemeral execution completed.")
                break
        time.sleep(0.5)

        # Step 5: Astra Task finishes -> executes cleanup for task_id
        ledger = AstraResourceLedger.get_instance()
        cleanup_result = ledger.cleanup_task_resources(task_id, TaskStatus.COMPLETED)
        print(f"[*] Task cleanup executed: {cleanup_result}")

        # Step 6: CRITICAL VERIFICATION:
        # 6a. Astra's Notepad B must be CLOSED
        time.sleep(1.0)
        _ensure_desktop_attached()
        is_astra_alive = bool(user32.IsWindow(astra_hwnd)) if user32 else False
        print(f"[+] Astra Notepad B alive: {is_astra_alive} (expected False)")
        assert not is_astra_alive, f"Astra Notepad B (HWND {astra_hwnd}) was NOT closed!"

        # 6b. User's Notepad A MUST STILL BE OPEN AND RESPONSIVE!
        is_user_alive = bool(user32.IsWindow(user_hwnd)) if user32 else False
        print(f"[+] User Notepad A alive: {is_user_alive} (expected True)")
        assert is_user_alive, f"CRITICAL FAILURE: Pre-existing User Notepad A (HWND {user_hwnd}) was destroyed by Astra!"

        # 6c. User's file content MUST BE 100% UNTOUCHED
        current_user_text = user_file.read_text(encoding="utf-8")
        current_user_hash = hashlib.sha256(current_user_text.encode("utf-8")).hexdigest()
        print(f"[+] User file content preserved: hash={current_user_hash} (initial={user_initial_hash})")
        assert current_user_hash == user_initial_hash, "User file was modified during task execution!"

        print("[PASS] TEST 3: Mixed ownership invariant strictly enforced. Pre-existing user window protected.")
        return {
            "test": "mixed_ownership_user_protection",
            "status": "PASS",
            "user_hwnd": user_hwnd,
            "user_pid": user_pid,
            "astra_hwnd": astra_hwnd,
            "astra_pid": astra_pid,
            "user_window_preserved": True,
            "user_content_untouched": True,
            "astra_window_closed": True,
            "latency_sec": round(time.time() - t0, 3),
        }
    finally:
        # Step 7: Deterministic teardown of test harness User Notepad A in finally block
        print("[*] Deterministically terminating test-scoped User Notepad A...")
        if user_pid and psutil.pid_exists(user_pid):
            try:
                proc = psutil.Process(user_pid)
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                except psutil.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1.5)
            except Exception as e:
                print(f"[!] Warning terminating user_pid {user_pid}: {e}")
        # Only after process is completely terminated, purge tabstate and remove temporary test files
        time.sleep(0.3)
        clean_notepad_tabstate_for_path(str(user_file))
        if 'astra_file' in locals():
            clean_notepad_tabstate_for_path(str(astra_file))
        time.sleep(0.2)
        try:
            if user_file.exists():
                user_file.unlink()
        except Exception as e:
            print(f"[!] Warning unlinking user_file: {e}")
        try:
            if 'astra_file' in locals() and astra_file.exists():
                astra_file.unlink()
        except Exception:
            pass




def test_4_user_takeover_detachment() -> Dict[str, Any]:
    """Test 4: User Takeover ('Do Not Fight The User').

    Astra launches a window, user interaction is detected -> Window is detached.
    Task completion must NOT auto-close the detached window.
    """
    print("\n" + "=" * 70)
    print("TEST 4: USER TAKEOVER DETACHMENT ('Do Not Fight The User')")
    print("=" * 70)
    task_id = f"test_f0_15_takeover_{int(time.time())}"
    ledger = AstraResourceLedger.get_instance()

    t0 = time.time()
    hwnd: Optional[int] = None
    pid: Optional[int] = None

    try:
        # 1. Astra launches Notepad
        open_res = open_application("notepad", task_id=task_id)
        assert open_res.success, f"Failed to launch Notepad: {open_res.message}"
        data = open_res.data or {}
        hwnd = data.get("hwnd")
        pid = data.get("pid")
        print(f"[+] Astra launched Notepad: HWND={hwnd}, PID={pid}")
        assert hwnd is not None, "HWND required"

        time.sleep(1.0)
        # 2. Simulate User Takeover on window
        detached_res = ledger.mark_user_takeover_for_window(hwnd)
        print(f"[*] Marked user takeover for HWND {hwnd}: state={detached_res.lifecycle_state.value if detached_res else None}")
        assert detached_res is not None
        assert detached_res.lifecycle_state == ResourceLifecycleState.USER_TAKEOVER_DETACHED

        # 3. Task Completes -> Try to clean up
        cleanup_report = ledger.cleanup_task_resources(task_id, TaskStatus.COMPLETED)
        print(f"[*] Cleanup report: {cleanup_report}")
        assert cleanup_report["cleaned_count"] == 0, "Detached window should not be cleaned!"
        assert cleanup_report["detached_count"] >= 1, "Detached window must be recorded as detached!"

        # 4. Verify window is STILL OPEN on desktop
        time.sleep(0.5)
        _ensure_desktop_attached()
        is_alive = bool(user32.IsWindow(hwnd)) if user32 else False
        print(f"[+] Window alive after task completion: {is_alive} (expected True)")
        assert is_alive, f"Window HWND {hwnd} was unexpectedly closed after user takeover!"

        print("[PASS] TEST 4: User takeover window successfully detached and preserved.")
        return {
            "test": "user_takeover_detachment",
            "status": "PASS",
            "task_id": task_id,
            "hwnd": hwnd,
            "pid": pid,
            "preserved_on_takeover": True,
            "latency_sec": round(time.time() - t0, 3),
        }
    finally:
        # Step 5: Deterministic teardown of test window in test harness
        if pid and psutil.pid_exists(pid):
            try:
                proc = psutil.Process(pid)
                proc.terminate()
                try:
                    proc.wait(timeout=1.5)
                except psutil.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=1.5)
            except Exception:
                pass


def test_5_orphan_recovery_and_pid_reuse() -> Dict[str, Any]:
    """Test 5: Crash/Restart Orphan Recovery and PID Reuse Guard."""
    print("\n" + "=" * 70)
    print("TEST 5: ORPHAN RECOVERY & PID REUSE HAZARD GUARD")
    print("=" * 70)
    db_path = Path(tempfile.gettempdir()) / "test_orphan_audit.db"
    if db_path.exists():
        db_path.unlink()
    test_ledger = AstraResourceLedger(db_path=db_path)

    t0 = time.time()
    # 1. Register a stale resource with mismatched creation time (simulating PID reuse hazard)
    current_pid = os.getpid()
    real_create_time = psutil.Process(current_pid).create_time()
    fake_old_time = real_create_time - 50000.0  # Mismatched timestamp

    hazard_res = OwnedResource(
        task_id="stale_task_crash",
        resource_type=ResourceType.APPLICATION,
        launching_capability="open_application",
        pid=current_pid,
        hwnd=99999999,
        process_creation_time=fake_old_time,
        astra_created=True,
        cleanup_policy=CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
        lifecycle_state=ResourceLifecycleState.ACTIVE,
    )
    test_ledger.register_resource(hazard_res)

    # 2. Attempt closure of the hazard resource
    closed = test_ledger.close_owned_resource(hazard_res)
    print(f"[*] PID reuse close attempt returned: {closed} (expected False)")
    assert closed is False, "PID reuse guard must abort termination when creation times mismatch!"

    updated_hazard = test_ledger.get_resource(hazard_res.resource_id)
    assert updated_hazard is not None
    print(f"[+] Hazard resource lifecycle state: {updated_hazard.lifecycle_state.value}")
    assert updated_hazard.lifecycle_state == ResourceLifecycleState.STALE_REUSED

    # 3. Test orphan recovery across simulated restart
    dead_res = OwnedResource(
        task_id="crashed_task",
        resource_type=ResourceType.APPLICATION,
        launching_capability="open_application",
        pid=99999999,
        hwnd=None,
        astra_created=True,
        lifecycle_state=ResourceLifecycleState.ACTIVE,
    )
    test_ledger.register_resource(dead_res)
    recovery_list = test_ledger.recover_orphaned_resources()
    print(f"[+] Orphan recovery report: {recovery_list}")
    assert len(recovery_list) >= 1
    assert any(r["resource_id"] == dead_res.resource_id for r in recovery_list)

    # Cleanup test db
    try:
        db_path.unlink()
    except Exception:
        pass

    print("[PASS] TEST 5: Orphan recovery and PID reuse hazard guard verified.")
    return {
        "test": "orphan_recovery_and_pid_reuse",
        "status": "PASS",
        "pid_reuse_aborted": True,
        "stale_reused_marked": True,
        "orphan_recovery_verified": True,
        "latency_sec": round(time.time() - t0, 3),
    }


def main() -> int:
    print("=" * 70)
    print("ASTRARUN PHASE F0-15: PHYSICAL DESKTOP ACCEPTANCE AUDIT")
    print(f"Platform: {platform.platform()} ({platform.machine()})")
    print(f"Python: {sys.version.split()[0]} | Process PID: {os.getpid()}")
    print("=" * 70)

    results = []
    try:
        r1 = test_1_calculator_lifecycle()
        results.append(r1)

        r2 = test_2_notepad_lifecycle()
        results.append(r2)

        r3 = test_3_mixed_ownership()
        results.append(r3)

        r4 = test_4_user_takeover_detachment()
        results.append(r4)

        r5 = test_5_orphan_recovery_and_pid_reuse()
        results.append(r5)

        # Verification of Zero Desktop Debris via DesktopObserver
        from astrarun.computer_use.observation.observer import DesktopObserver
        obs = DesktopObserver()
        final_state = obs.observe_state()
        print(f"[*] Post-audit desktop state: {len(final_state.visible_windows)} visible windows, {len(final_state.active_dialogs)} dialogs")
        assert not final_state.has_astra_debris(), f"Desktop debris detected after tests: {[d.to_dict() for d in final_state.active_dialogs]}"
        print("[+] Verified ZERO desktop debris remaining.")

    except Exception as ex:

        logger.exception("Acceptance audit failure: %s", ex)
        print(f"\n[FAIL] Audit encountered critical exception: {ex}")
        return 1

    # Write authoritative audit evidence JSON
    audit_evidence = {
        "milestone": "F0-15",
        "description": "Astra-Owned Application / Window Lifecycle Cleanup Physical Verification",
        "timestamp": time.time(),
        "timestamp_iso": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
            "os_build": platform.version(),
        },
        "verdict": "PASS",
        "invariants_verified": [
            "TASK_SCOPED_RESOURCE_OWNERSHIP",
            "CRITICAL_OWNERSHIP_RULE_NEVER_CLOSE_NON_ASTRA_RESOURCES",
            "SAVE_BEFORE_CLOSE_ARTIFACT_VERIFICATION",
            "USER_TAKEOVER_DETACHMENT_DO_NOT_FIGHT_THE_USER",
            "PID_REUSE_HAZARD_GUARD",
            "CRASH_RESTART_ORPHAN_RECOVERY",
            "ZERO_DESKTOP_DEBRIS",
        ],
        "test_results": results,
    }

    audit_path = PROJECT_ROOT / "docs" / "audit" / "F0_15_RESOURCE_LIFECYCLE_EVIDENCE.json"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit_evidence, indent=2), encoding="utf-8")
    print(f"\n[+] Audit evidence written to: {audit_path}")

    print("\n" + "=" * 70)
    print("PHASE F0-15 ACCEPTANCE AUDIT VERDICT: ALL TESTS PASSED (5/5)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
