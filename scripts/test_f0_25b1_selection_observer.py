"""Isolated Bounded Diagnostic Script for F0-25B.1 Generic Selection Observation.

Validates:
1. Strict timeout bounds (watchdog + bounded loops)
2. Generic selection observation across UIA TextPattern and Scintilla adapter
3. Semantic verification of SELECT_ALL (selected_length == document_length > 0)
4. Negative mutation proving the verifier fails when selection is cleared
5. Affirmative resource lifecycle tracking and cleanup
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional

import psutil

# Add src to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from astrarun.computer_use.ui.editable_surface import (
    discover_editable_surface,
    observe_surface_selection,
    verify_select_all_predicate,
    execute_select_all_strategy,
    clear_selection_strategy,
    SelectionObservation,
)
from astrarun.hermes.resource_lifecycle import TaskResourceReconciler, capture_world_frame
from astrarun.interaction.keyboard import dispatch_shortcut, parse_shortcut

NPP_PATH = r"C:\Program Files\Notepad++\notepad++.exe"
user32 = ctypes.windll.user32


def log_stage(t0: float, stage: str, details: str = "") -> None:
    elapsed = time.time() - t0
    msg = f"[{elapsed:5.2f}s] {stage}"
    if details:
        msg += f" -> {details}"
    print(msg, flush=True)


def ensure_clean_npp(t0: float) -> None:
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] and "notepad++" in proc.info["name"].lower():
                log_stage(t0, "CLEANUP_PRE", f"Terminating lingering Notepad++ PID {proc.pid}")
                proc.terminate()
                proc.wait(timeout=2.0)
        except Exception:
            pass


def main() -> int:
    t0 = time.time()
    task_id = f"test_sel_obs_{int(t0 * 1000)}"

    # 1. Arm fail-safe watchdog timer (20 seconds hard deadline)
    def _watchdog_timer():
        time.sleep(20.0)
        print("\n[CRITICAL FAIL-SAFE] 20.0s hard watchdog fired! Terminating process tree immediately.", flush=True)
        ensure_clean_npp(t0)
        os._exit(42)

    watchdog_th = threading.Thread(target=_watchdog_timer, daemon=True, name="SelectionWatchdog")
    watchdog_th.start()
    log_stage(t0, "WATCHDOG_ARMED", "Fail-safe 20.0s watchdog active")

    results: Dict[str, Any] = {
        "phase": "F0-25B.1",
        "task_id": task_id,
        "start_time": t0,
        "environment": "Notepad++ (Win32 Scintilla Host)",
        "watchdog_timeout_sec": 20.0,
        "stages": {},
        "selection_pre": None,
        "selection_post": None,
        "selection_negative_control": None,
        "predicate_evaluation": {},
        "resource_cleanup": {},
        "verdict": "FAILED",
    }

    reconciler = TaskResourceReconciler()
    npp_proc: Optional[subprocess.Popen] = None
    target_hwnd: Optional[int] = None
    target_pid: Optional[int] = None

    try:
        # Pre-cleanup
        ensure_clean_npp(t0)
        baseline = capture_world_frame("sel_test_baseline")
        reconciler.begin(task_id, pre_snapshot={"frame": baseline})
        log_stage(t0, "BASELINE_CAPTURED", f"Existing windows: {len(baseline.windows)}")

        # 2. Governed Launch
        log_stage(t0, "LAUNCHING_APP", f"Starting '{NPP_PATH}' (-nosession -multiInst)")
        npp_proc = subprocess.Popen([NPP_PATH, "-nosession", "-multiInst"])
        target_pid = npp_proc.pid
        reconciler.register_launched_process(target_pid, action_id="test_launch_npp")
        log_stage(t0, "PROCESS_SPAWNED", f"PID: {target_pid}")

        # 3. Discover main window HWND with bounded poll
        deadline = t0 + 5.0
        while time.time() < deadline:
            hwnds = []
            @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            def _find_cb(h, _l):
                if user32.IsWindow(h) and user32.IsWindowVisible(h):
                    wpid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(wpid))
                    if wpid.value == target_pid:
                        cbuf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(h, cbuf, 256)
                        if "notepad++" in cbuf.value.lower():
                            hwnds.append(h)
                return True
            user32.EnumWindows(_find_cb, 0)
            if hwnds:
                target_hwnd = hwnds[0]
                break
            time.sleep(0.1)

        if not target_hwnd:
            raise RuntimeError(f"Could not discover visible Notepad++ window for PID {target_pid} within 5.0s")

        log_stage(t0, "WINDOW_DISCOVERED", f"HWND: 0x{target_hwnd:x}")
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(0.3)

        # 4. Insert canary content
        canary_text = "ASTRA_SELECTION_PROBE_7F3A91\nSecond canary line for exact buffer calculation\n"
        log_stage(t0, "INJECTING_CANARY", f"Length: {len(canary_text)} chars")

        # Find child editable surface
        surface = discover_editable_surface(target_hwnd, timeout_sec=2.0)
        if not surface:
            raise RuntimeError("discover_editable_surface failed to return an editable surface")
        log_stage(t0, "SURFACE_DISCOVERED", f"type={surface.control_type}, class={surface.class_name}, hwnd=0x{surface.hwnd:x}")

        # Inject characters via WM_CHAR
        dest_hwnd = surface.hwnd if (surface.hwnd and surface.hwnd != target_hwnd) else target_hwnd
        for ch in canary_text:
            user32.SendMessageW(dest_hwnd, 0x0102, ord(ch), 0)
            time.sleep(0.002)
        time.sleep(0.4)
        log_stage(t0, "CANARY_INJECTED", "WM_CHAR dispatch complete")

        # 5. Capture BEFORE Observation
        sel_pre = observe_surface_selection(target_hwnd=target_hwnd, surface=surface)
        pred_pre = verify_select_all_predicate(sel_pre)
        results["selection_pre"] = {
            "observable": sel_pre.observable,
            "source": sel_pre.source,
            "start": sel_pre.start,
            "end": sel_pre.end,
            "selected_length": sel_pre.selected_length,
            "document_length": sel_pre.document_length,
            "evidence_reference": sel_pre.evidence_reference,
            "predicate_result": pred_pre,
        }
        log_stage(t0, "OBSERVE_PRE", f"source={sel_pre.source}, sel_len={sel_pre.selected_length}, doc_len={sel_pre.document_length}, predicate={pred_pre}")
        assert sel_pre.observable, "Pre-observation failed: selection is not observable"
        assert sel_pre.document_length is not None and sel_pre.document_length > 0, "Document length should be > 0 after canary insertion"
        assert not pred_pre, f"verify_select_all_predicate should be FALSE before Ctrl+A, got {pred_pre}"

        # 6. Dispatch SELECT_ALL via Generic Strategy Ladder
        log_stage(t0, "DISPATCHING_SELECT_ALL", "Using execute_select_all_strategy ladder")
        ok_a, mechanism_a = execute_select_all_strategy(surface=surface, target_hwnd=target_hwnd)
        time.sleep(0.3)
        log_stage(t0, "SELECT_ALL_EXECUTED", f"ok={ok_a}, mechanism={mechanism_a}")
        results["action_execution"] = {"success": ok_a, "mechanism": mechanism_a}

        # 7. Capture AFTER Observation
        sel_post = observe_surface_selection(target_hwnd=target_hwnd, surface=surface)
        pred_post = verify_select_all_predicate(sel_post)
        results["selection_post"] = {
            "observable": sel_post.observable,
            "source": sel_post.source,
            "start": sel_post.start,
            "end": sel_post.end,
            "selected_length": sel_post.selected_length,
            "document_length": sel_post.document_length,
            "evidence_reference": sel_post.evidence_reference,
            "predicate_result": pred_post,
        }
        log_stage(t0, "OBSERVE_POST", f"source={sel_post.source}, sel_len={sel_post.selected_length}, doc_len={sel_post.document_length}, predicate={pred_post}")
        assert sel_post.observable, "Post-observation failed: selection is not observable"
        assert sel_post.selected_length == sel_post.document_length, f"selected_length ({sel_post.selected_length}) must equal document_length ({sel_post.document_length})"
        assert pred_post, f"verify_select_all_predicate should be TRUE after Ctrl+A, got {pred_post}"

        # 8. Mandatory Negative Control (Mutation: clear selection)
        log_stage(t0, "NEGATIVE_MUTATION", "Using clear_selection_strategy")
        ok_r, mechanism_r = clear_selection_strategy(surface=surface, target_hwnd=target_hwnd)
        time.sleep(0.2)
        log_stage(t0, "SELECTION_CLEARED", f"ok={ok_r}, mechanism={mechanism_r}")
        sel_neg = observe_surface_selection(target_hwnd=target_hwnd, surface=surface)
        pred_neg = verify_select_all_predicate(sel_neg)
        results["selection_negative_control"] = {
            "observable": sel_neg.observable,
            "source": sel_neg.source,
            "start": sel_neg.start,
            "end": sel_neg.end,
            "selected_length": sel_neg.selected_length,
            "document_length": sel_neg.document_length,
            "evidence_reference": sel_neg.evidence_reference,
            "predicate_result": pred_neg,
        }
        log_stage(t0, "OBSERVE_MUTATION", f"source={sel_neg.source}, sel_len={sel_neg.selected_length}, doc_len={sel_neg.document_length}, predicate={pred_neg}")
        assert sel_neg.observable, "Negative control observation failed: selection is not observable"
        assert sel_neg.selected_length == 0, f"Expected selected_length == 0 after caret move, got {sel_neg.selected_length}"
        assert not pred_neg, f"verify_select_all_predicate MUST be FALSE on negative control, got {pred_neg}"

        results["predicate_evaluation"] = {
            "pre_action_verified": not pred_pre,
            "post_action_verified": pred_post,
            "negative_control_verified": not pred_neg,
            "semantic_closure_proven": True,
        }
        results["verdict"] = "PASSED"
        log_stage(t0, "VERDICT", "ALL SELECTION OBSERVER & PREDICATE ASSERTIONS PASSED")

    except Exception as ex:
        log_stage(t0, "ERROR", str(ex))
        results["error"] = str(ex)
        results["verdict"] = "FAILED"
        return 1

    finally:
        # 9. Affirmative Resource Cleanup
        log_stage(t0, "CLEANUP_BEGIN", "Disposing task-owned Notepad++ instance")
        cleanup_success = True
        if target_hwnd and user32.IsWindow(target_hwnd):
            user32.PostMessageW(target_hwnd, 0x0010, 0, 0)  # WM_CLOSE
            time.sleep(0.3)

        if target_pid and psutil.pid_exists(target_pid):
            try:
                p = psutil.Process(target_pid)
                p.terminate()
                p.wait(timeout=2.0)
                log_stage(t0, "PROCESS_TERMINATED", f"PID {target_pid} cleanly exited")
            except Exception as ex:
                log_stage(t0, "PROCESS_CLEANUP_WARN", str(ex))
                cleanup_success = False

        # Verify no remaining task-owned Notepad++ processes
        npp_remaining = [p.pid for p in psutil.process_iter(["name"]) if p.info["name"] and "notepad++" in p.info["name"].lower()]
        results["resource_cleanup"] = {
            "target_pid": target_pid,
            "target_hwnd": f"0x{target_hwnd:x}" if target_hwnd else None,
            "target_pid_exited": not psutil.pid_exists(target_pid) if target_pid else True,
            "remaining_npp_pids": npp_remaining,
            "cleanup_verified": len(npp_remaining) == 0,
        }
        log_stage(t0, "CLEANUP_END", f"Remaining Notepad++ PIDs: {npp_remaining}")

        # Write audit output
        results["duration_seconds"] = round(time.time() - t0, 3)
        audit_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "docs", "audit", "F0_25B1_SELECTION_OBSERVER_RESULTS.json"))
        with open(audit_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        log_stage(t0, "AUDIT_PERSISTED", audit_path)

    return 0 if results["verdict"] == "PASSED" else 1


if __name__ == "__main__":
    sys.exit(main())
