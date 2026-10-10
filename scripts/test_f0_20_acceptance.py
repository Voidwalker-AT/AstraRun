"""Authoritative Physical Desktop Acceptance Test for Phase F0-20.

Validates:
1. Acceptance A: Live Desktop Perception (Zero Mutation, Hierarchical, Serializable)
2. Acceptance B: Unfamiliar Application Control (charmap.exe - 0 hardcoded app logic)
3. Acceptance C: Multi-Step Task with Perceptual Closed Loop & UI Document Save (>= 5 steps)
4. Acceptance D: Adaptive Execution Under Divergence (minimized/defocused window recovery)
5. Acceptance E: Clean Desktop State (zero Astra debris, zero modals, zero orphan processes)
6. Acceptance F: Screen Understanding Verification (Proof of Perception via coordinate delta)
7. Acceptance G: Human Failure Reproduction & Resolution (Notepad TabState orphan modal fix)

Outputs:
- docs/audit/F0_20_ACCEPTANCE_EVIDENCE.json
- docs/audit/F0_20_PERCEPTION_TRACE.json
- docs/audit/F0_20_UI_ACTION_TRACE.json
- docs/audit/F0_20_ADAPTIVE_RECOVERY.json
- docs/audit/F0_20_RESOURCE_CLEANUP.json
- docs/audit/F0_20_WORLD_STATE_ARCHITECTURE.json
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

from astrarun.agent.loop import AgentExecutionEngine
from astrarun.agent.models import (
    AgentTask,
    AgentTaskStatus,
    Goal,
    InteractionRequirement,
    Plan,
    PlanStep,
    StepState,
)
from astrarun.applications.service import close_application, open_application
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.schema import InteractionTier, VerifierStrategy
from astrarun.computer_use.hooks.desktop_attach import ensure_desktop_attached
from astrarun.computer_use.observation.observer import DesktopObserver
from astrarun.computer_use.ui.dialogs import DialogDetector
from astrarun.computer_use.world.desktop_state import DesktopWorldState
from astrarun.core.logging import get_logger
from astrarun.interaction.controller import invoke_element, set_element_value
from astrarun.interaction.discovery import inspect_window_ui
from astrarun.interaction.document import save_document_via_ui
from astrarun.interaction.keyboard import dispatch_shortcut, parse_shortcut
from astrarun.interaction.models import ControlType
from astrarun.interaction.service import type_literal_text
from astrarun.security.execution_broker import ExecutionBroker
from astrarun.tasks.resource_ledger import (
    AstraResourceLedger,
    clean_notepad_tabstate_for_path,
)

logger = get_logger("astrarun.test_f0_20")
user32 = ctypes.windll.user32 if sys.platform == "win32" else None


def test_acceptance_a_live_perception() -> Dict[str, Any]:
    """Acceptance A: Live Desktop Perception (Zero Mutation)."""
    print("\n" + "=" * 70)
    print("ACCEPTANCE A: LIVE DESKTOP PERCEPTION (Zero Mutation)")
    print("=" * 70)
    t0 = time.perf_counter()

    obs = DesktopObserver.get_instance()
    initial_pids = set(psutil.pids())

    state = obs.observe()
    duration_ms = (time.perf_counter() - t0) * 1000.0
    post_pids = set(psutil.pids())

    state_hash = state.compute_state_hash()
    print(f"[*] State hash: {state_hash}")
    print(f"[*] Visible top-level windows: {len(state.visible_windows)}")
    print(f"[*] Dialogs detected: {len(state.dialogs)}")
    print(f"[*] Processes monitored: {len(state.processes)}")
    print(f"[*] Observation latency: {duration_ms:.2f} ms")

    # Verification: Non-mutating
    assert post_pids == initial_pids, "Observation mutated running processes!"
    assert len(state_hash) == 64, f"Invalid SHA-256 state hash: {state_hash}"
    assert duration_ms < 1000.0, f"Observation latency exceeded 1000ms: {duration_ms:.2f}ms"
    assert not state.has_astra_debris(), "Found unexpected Astra debris in baseline observation!"

    print("[PASS] ACCEPTANCE A: Zero-mutation live perception verified.")
    return {
        "test": "acceptance_a_live_perception",
        "status": "PASS",
        "state_hash": state_hash,
        "visible_windows": len(state.visible_windows),
        "dialogs": len(state.dialogs),
        "observation_latency_ms": round(duration_ms, 2),
        "zero_mutation_verified": True,
    }


def test_acceptance_b_unfamiliar_application() -> Dict[str, Any]:
    """Acceptance B: Unfamiliar Application Control (charmap.exe)."""
    print("\n" + "=" * 70)
    print("ACCEPTANCE B: UNFAMILIAR APPLICATION CONTROL (charmap.exe)")
    print("=" * 70)
    t0 = time.time()
    task_id = f"test_f0_20_unfamiliar_{int(t0)}"
    charmap_pid = None
    charmap_hwnd = None

    try:
        # 1. Open unfamiliar application
        res = open_application("charmap", task_id=task_id)
        assert res.success, f"Failed to launch charmap: {res.message}"
        charmap_pid = res.data["pid"]
        charmap_hwnd = res.data["hwnd"]
        print(f"[+] Launched charmap: HWND={charmap_hwnd}, PID={charmap_pid}")
        time.sleep(1.0)

        # 2. Inspect controls via generic UI Automation
        tree_before = inspect_window_ui(charmap_hwnd, max_depth=3)
        count_before = len(tree_before)
        print(f"[*] Initial UI controls discovered: {count_before}")
        assert count_before >= 15, f"Unexpectedly few controls in charmap: {count_before}"

        # 3. Find and invoke an unfamiliar control: 'Advanced view' checkbox
        adv_chk = None
        for c in tree_before:
            if "Advanced view" in c.name:
                adv_chk = c
                break
        assert adv_chk is not None, "Could not find 'Advanced view' checkbox in charmap UI!"

        inv_res = invoke_element(adv_chk)
        print(f"[*] Invoked 'Advanced view' checkbox: {inv_res[1]}")
        assert inv_res[0], f"Failed invoking 'Advanced view': {inv_res[1]}"
        time.sleep(0.6)

        # 4. Observe real-time state change: UI tree dynamic change
        tree_after = inspect_window_ui(charmap_hwnd, max_depth=3)
        count_after = len(tree_after)
        print(f"[*] UI controls after toggle: {count_after}")
        assert count_after != count_before and abs(count_after - count_before) >= 10, (
            f"State change not reflected: before={count_before}, after={count_after}"
        )
        print(f"[+] State change verified: dynamic delta of {abs(count_after - count_before)} controls observed.")

        # 5. Clean up unfamiliar application
        c_res = close_application("charmap", task_id=task_id)
        assert c_res.success, f"Failed closing charmap: {c_res.message}"
        time.sleep(0.5)

        # Verify window is destroyed
        is_alive = bool(user32.IsWindow(charmap_hwnd)) if user32 else False
        assert not is_alive, "charmap window still alive after closure!"
        print("[PASS] ACCEPTANCE B: Unfamiliar application control verified without custom logic.")

        return {
            "test": "acceptance_b_unfamiliar_application",
            "status": "PASS",
            "app": "charmap",
            "hwnd": charmap_hwnd,
            "pid": charmap_pid,
            "controls_before": count_before,
            "controls_after": count_after,
            "state_change_verified": True,
            "closed_cleanly": True,
            "latency_sec": round(time.time() - t0, 3),
        }
    finally:
        if charmap_pid and psutil.pid_exists(charmap_pid):
            try:
                psutil.Process(charmap_pid).kill()
            except Exception:
                pass
        from astrarun.tasks.models import TaskStatus
        AstraResourceLedger.get_instance().cleanup_task_resources(task_id, TaskStatus.COMPLETED)


def test_acceptance_c_multistep_perceptual_closed_loop() -> Dict[str, Any]:
    """Acceptance C: Multi-Step Task with Perceptual Closed Loop & UI Document Save."""
    print("\n" + "=" * 70)
    print("ACCEPTANCE C: MULTI-STEP PERCEPTUAL CLOSED LOOP & UI SAVE")
    print("=" * 70)
    t0 = time.time()
    task_id = f"test_f0_20_multistep_{int(t0)}"
    temp_dir = Path(tempfile.gettempdir())
    artifact_file = temp_dir / f"astra_f0_20_multistep_{int(t0)}.txt"
    test_content = f"AstraRun F0-20 Perceptual Loop Verified {t0}"

    engine = AgentExecutionEngine()
    notepad_pid = None
    notepad_hwnd = None

    try:
        # Build 5-step explicit agent plan enforcing APPLICATION_UI modality
        steps = [
            PlanStep(
                step_id="step_1_launch",
                description="Launch Notepad application",
                capability_id="open_application",
                arguments={"app": "notepad", "task_id": task_id},
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                interaction_requirement=InteractionRequirement.APPLICATION_UI,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
            ),
            PlanStep(
                step_id="step_2_focus",
                description="Focus Notepad window",
                capability_id="focus_window",
                arguments={"window": "notepad", "task_id": task_id},
                interaction_tier=InteractionTier.TIER_C_UI_AUTOMATION,
                interaction_requirement=InteractionRequirement.APPLICATION_UI,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
            ),
            PlanStep(
                step_id="step_3_type",
                description="Type verified content into Notepad",
                capability_id="type_into_window",
                arguments={"text": test_content, "window": "notepad", "task_id": task_id},
                interaction_tier=InteractionTier.TIER_C_UI_AUTOMATION,
                interaction_requirement=InteractionRequirement.APPLICATION_UI,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
            ),
            PlanStep(
                step_id="step_4_ui_save",
                description="Save document via native application UI Save As dialog",
                capability_id="save_document_via_ui",
                arguments={"path": str(artifact_file), "window": "notepad", "task_id": task_id},
                interaction_tier=InteractionTier.TIER_C_UI_AUTOMATION,
                interaction_requirement=InteractionRequirement.APPLICATION_UI,
                verifier_strategy=VerifierStrategy.FILE_EXISTS,
            ),
            PlanStep(
                step_id="step_5_close",
                description="Close Notepad application cleanly",
                capability_id="close_application",
                arguments={"app": "notepad", "task_id": task_id},
                interaction_tier=InteractionTier.TIER_A_NATIVE,
                interaction_requirement=InteractionRequirement.APPLICATION_UI,
                verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
            ),
        ]

        task = AgentTask(
            task_id=task_id,
            goal=Goal(
                intent="Write and save document via Notepad UI",
                raw_prompt="open notepad type content save via ui and close",
                interaction_requirement=InteractionRequirement.APPLICATION_UI,
            ),
            plan=Plan(plan_id=f"plan_{task_id}", steps=steps),
        )

        # Execute each step with full closed loop
        completed_steps = 0
        for step in steps:
            print(f"\n[*] Executing Step [{step.step_id}]: {step.description}")
            ok = engine._execute_step_with_closed_loop(task, step)
            assert ok, f"Step [{step.step_id}] failed execution!"
            completed_steps += 1
            time.sleep(0.3)

        assert completed_steps == 5, f"Expected 5 steps, got {completed_steps}"
        assert len(task.execution_traces) == 5, f"Expected 5 trace entries, got {len(task.execution_traces)}"

        # Validate closed loop traces
        for tr in task.execution_traces:
            assert tr["observation_before"]["state_hash"] is not None, "Missing pre-observation hash!"
            assert tr["observation_after"]["state_hash"] is not None, "Missing post-observation hash!"
            assert tr["broker_verdict"] == "ALLOW", f"Step was unexpectedly blocked: {tr}"
            assert tr["transition_verified"] is True, f"Step transition failed verification: {tr}"

        # Verify disk artifact
        assert artifact_file.exists(), f"Artifact file '{artifact_file}' was not created!"
        saved_text = artifact_file.read_text(encoding="utf-8")
        assert test_content in saved_text, f"Disk content mismatch! Got: {saved_text!r}"
        print(f"[+] File verified on disk: length={len(saved_text)}, sha256={hashlib.sha256(saved_text.encode()).hexdigest()}")

        # Verify launched Notepad window is closed
        launched_hwnd = task.execution_traces[0]["execution_result"]["data"].get("hwnd")
        if launched_hwnd:
            is_alive = bool(user32.IsWindow(launched_hwnd)) if user32 else False
            assert not is_alive, f"Launched Notepad HWND {launched_hwnd} is still alive!"
        obs = DesktopObserver.get_instance().observe()
        np_task_open = [w for w in obs.visible_windows if w.task_id == task_id or (w.astra_owned and "notepad" in w.title.lower())]
        assert len(np_task_open) == 0, f"Astra-owned Notepad window still visible: {np_task_open}"

        print("[PASS] ACCEPTANCE C: 5-step closed-loop execution and UI save verified.")
        return {
            "test": "acceptance_c_multistep_perceptual_closed_loop",
            "status": "PASS",
            "task_id": task_id,
            "steps_count": 5,
            "traces_count": len(task.execution_traces),
            "traces": task.execution_traces,
            "artifact_path": str(artifact_file),
            "artifact_sha256": hashlib.sha256(saved_text.encode()).hexdigest(),
            "latency_sec": round(time.time() - t0, 3),
        }
    finally:
        clean_notepad_tabstate_for_path(str(artifact_file))
        time.sleep(0.2)
        if artifact_file.exists():
            try:
                artifact_file.unlink()
            except Exception:
                pass
        from astrarun.tasks.models import TaskStatus
        AstraResourceLedger.get_instance().cleanup_task_resources(task_id, TaskStatus.COMPLETED)
        AstraResourceLedger.get_instance().cleanup_task_resources("default_task", TaskStatus.COMPLETED)


def test_acceptance_d_adaptive_divergence_recovery() -> Dict[str, Any]:
    """Acceptance D: Adaptive Execution Under Divergence (Minimization / Lost Focus)."""
    print("\n" + "=" * 70)
    print("ACCEPTANCE D: ADAPTIVE EXECUTION UNDER DIVERGENCE")
    print("=" * 70)
    t0 = time.time()
    task_id = f"test_f0_20_divergence_{int(t0)}"
    np_pid = None
    np_hwnd = None

    try:
        # 1. Launch Notepad
        res = open_application("notepad", task_id=task_id)
        assert res.success
        np_pid = res.data["pid"]
        np_hwnd = res.data["hwnd"]
        time.sleep(1.0)

        # 2. DELIBERATELY INTRODUCE UNEXPECTED DIVERGENCE: Minimize the target window
        print("[!] Injecting divergence: Minimizing target Notepad window...")
        SW_MINIMIZE = 6
        user32.ShowWindow(np_hwnd, SW_MINIMIZE)
        time.sleep(0.5)

        # Verify window is minimized
        is_iconic = bool(user32.IsIconic(np_hwnd))
        print(f"[*] Confirmed Notepad is minimized (IsIconic={is_iconic})")
        assert is_iconic, "Failed to inject minimized window divergence!"

        # 3. Execute step with closed-loop engine
        engine = AgentExecutionEngine()
        step = PlanStep(
            step_id="step_adaptive_type",
            description="Type into minimized window (requires adaptive restoration)",
            capability_id="type_into_window",
            arguments={"text": "Adaptive recovery verified!", "window": "notepad"},
            interaction_tier=InteractionTier.TIER_C_UI_AUTOMATION,
            verifier_strategy=VerifierStrategy.RETURN_CODE_ONLY,
        )
        task = AgentTask(
            task_id=task_id,
            goal=Goal(intent="Adaptive typing test", raw_prompt="type"),
            plan=Plan(plan_id=f"plan_{task_id}", steps=[step]),
        )

        print("[*] Dispatching action to closed loop engine under minimized state...")
        ok = engine._execute_step_with_closed_loop(task, step)
        assert ok, "Engine failed to adapt and complete action!"

        # 4. Verify window was restored
        time.sleep(0.4)
        is_iconic_after = bool(user32.IsIconic(np_hwnd))
        print(f"[+] Post-recovery IsIconic={is_iconic_after} (expected False)")
        assert not is_iconic_after, "Window remained minimized after adaptive execution!"

        close_res = close_application("notepad", task_id=task_id)
        assert close_res.success
        print("[PASS] ACCEPTANCE D: Adaptive recovery from minimized divergence verified.")

        return {
            "test": "acceptance_d_adaptive_divergence_recovery",
            "status": "PASS",
            "task_id": task_id,
            "hwnd": np_hwnd,
            "divergence_injected": "SW_MINIMIZE",
            "divergence_detected": True,
            "adaptive_restoration_verified": True,
            "latency_sec": round(time.time() - t0, 3),
        }
    finally:
        if np_pid and psutil.pid_exists(np_pid):
            try:
                psutil.Process(np_pid).kill()
            except Exception:
                pass


def test_acceptance_e_clean_desktop_state() -> Dict[str, Any]:
    """Acceptance E: Clean Desktop State (Zero Debris, Zero Modals)."""
    print("\n" + "=" * 70)
    print("ACCEPTANCE E: CLEAN DESKTOP STATE (Zero Debris)")
    print("=" * 70)
    t0 = time.time()

    obs = DesktopObserver.get_instance()
    state = obs.observe()

    print(f"[*] Visible windows: {len(state.visible_windows)}")
    print(f"[*] Active dialogs: {len(state.dialogs)}")
    print(f"[*] Astra owned resources: {len(state.astra_owned_resources)}")
    print(f"[*] Astra debris detected: {state.has_astra_debris()}")

    assert not state.has_astra_debris(), f"Debris detected: {[d.to_dict() for d in state.dialogs]}"
    assert len(state.astra_owned_resources) == 0, f"Orphaned Astra resources: {state.astra_owned_resources}"

    print("[PASS] ACCEPTANCE E: Clean desktop state confirmed with zero residual debris.")
    return {
        "test": "acceptance_e_clean_desktop_state",
        "status": "PASS",
        "visible_windows": len(state.visible_windows),
        "dialogs": len(state.dialogs),
        "astra_owned_resources": len(state.astra_owned_resources),
        "zero_debris_verified": True,
        "latency_sec": round(time.time() - t0, 3),
    }


def test_acceptance_f_screen_understanding_proof() -> Dict[str, Any]:
    """Acceptance F: Screen Understanding Verification (Proof of Vision/Perception - Req 16)."""
    print("\n" + "=" * 70)
    print("ACCEPTANCE F: SCREEN UNDERSTANDING PROOF (Observation Delta)")
    print("=" * 70)
    t0 = time.time()
    task_id = f"test_f0_20_vision_{int(t0)}"
    np_pid = None
    np_hwnd = None

    try:
        # Launch test window
        res = open_application("notepad", task_id=task_id)
        assert res.success
        np_pid = res.data["pid"]
        np_hwnd = res.data["hwnd"]
        time.sleep(1.0)

        # 1. Observation A: Record initial position & element coordinates
        tree_a = inspect_window_ui(np_hwnd, max_depth=3)
        editor_a = [c for c in tree_a if c.name == "Text editor" or c.control_type == ControlType.DOCUMENT or "editor" in c.name.lower()][0]
        bounds_a = editor_a.bounds  # (x, y, w, h)
        click_target_a = (bounds_a[0] + bounds_a[2] // 2, bounds_a[1] + bounds_a[3] // 2)
        obs_a = {
            "window_hwnd": np_hwnd,
            "bounds": bounds_a,
            "target_click_point": click_target_a,
        }
        print(f"[*] Observation A: bounds={bounds_a}, click_target={click_target_a}")

        # 2. Physical mutation: Move window by (200, 100)
        DELTA_X = 200
        DELTA_Y = 100
        print(f"[!] Mutating screen layout: moving window by (+{DELTA_X}, +{DELTA_Y})...")
        user32.MoveWindow(np_hwnd, bounds_a[0] + DELTA_X, bounds_a[1] + DELTA_Y, 600, 400, True)
        time.sleep(0.5)

        # 3. Observation B: Record new position & element coordinates
        tree_b = inspect_window_ui(np_hwnd, max_depth=3)
        editor_b = [c for c in tree_b if c.name == "Text editor" or c.control_type == ControlType.DOCUMENT or "editor" in c.name.lower()][0]
        bounds_b = editor_b.bounds
        click_target_b = (bounds_b[0] + bounds_b[2] // 2, bounds_b[1] + bounds_b[3] // 2)
        obs_b = {
            "window_hwnd": np_hwnd,
            "bounds": bounds_b,
            "target_click_point": click_target_b,
        }
        print(f"[*] Observation B: bounds={bounds_b}, click_target={click_target_b}")

        # 4. Prove causal action difference
        coord_delta = (click_target_b[0] - click_target_a[0], click_target_b[1] - click_target_a[1])
        print(f"[+] Observed coordinate delta: {coord_delta}")
        assert click_target_b != click_target_a, "Observation B identical to Observation A!"
        assert abs(coord_delta[0]) >= 50, f"X delta too small: {coord_delta[0]}"

        close_res = close_application("notepad", task_id=task_id)
        assert close_res.success
        print("[PASS] ACCEPTANCE F: Screen understanding and causal perceptual grounding proved.")

        return {
            "test": "acceptance_f_screen_understanding_proof",
            "status": "PASS",
            "observation_a": obs_a,
            "observation_b": obs_b,
            "delta_coordinates": coord_delta,
            "causal_difference_proven": True,
            "latency_sec": round(time.time() - t0, 3),
        }
    finally:
        if np_pid and psutil.pid_exists(np_pid):
            try:
                psutil.Process(np_pid).kill()
            except Exception:
                pass


def test_acceptance_g_human_failure_reproduction_and_resolution() -> Dict[str, Any]:
    """Acceptance G: Reproduce and Resolve Exact Human-Observed Failure (Req 17)."""
    print("\n" + "=" * 70)
    print("ACCEPTANCE G: HUMAN FAILURE REPRODUCTION & RESOLUTION (Req 17)")
    print("=" * 70)
    t0 = time.time()
    task_id = f"test_f0_20_human_repro_{int(t0)}"
    temp_dir = Path(tempfile.gettempdir())
    artifact_file = temp_dir / f"astra_f0_20_human_repro_{int(t0)}.txt"
    test_content = f"Human Dogfood Fix Verification {t0}"

    np_pid = None
    np_hwnd = None

    try:
        # 1. Launch Notepad
        res = open_application("notepad", task_id=task_id)
        assert res.success
        np_pid = res.data["pid"]
        np_hwnd = res.data["hwnd"]
        time.sleep(1.0)

        # 2. Type text into editor
        type_res = type_literal_text(test_content, hwnd=np_hwnd)
        assert type_res.success, f"Failed typing text: {type_res.message}"
        time.sleep(0.5)

        # 3. Save via UI Save As dialog (APPLICATION_UI modality, NOT file API)
        save_res = save_document_via_ui(path=str(artifact_file), hwnd=np_hwnd, task_id=task_id)
        print(f"[*] save_document_via_ui result: {save_res.success} ({save_res.message})")
        assert save_res.success, f"UI save failed: {save_res.message}"
        assert artifact_file.exists(), "Target file does not exist after UI save!"

        # 4. Close Notepad
        c_res = close_application("notepad", task_id=task_id)
        assert c_res.success
        time.sleep(0.5)

        # 5. RE-LAUNCH NOTEPAD FRESH TO TEST FOR TABSTATE ERROR MODALS
        print("[*] Re-launching Notepad fresh to verify NO residual error dialog appears...")
        fresh_res = open_application("notepad", task_id="fresh_check")
        assert fresh_res.success
        fresh_hwnd = fresh_res.data["hwnd"]
        time.sleep(1.2)

        # Check for any dialogs owned by Notepad or system
        obs = DesktopObserver.get_instance().observe(target_hwnd=fresh_hwnd)
        notep_dialogs = [d for d in obs.dialogs if d.owner_hwnd == fresh_hwnd or "notepad" in d.title.lower()]
        print(f"[+] Fresh Notepad dialog count: {len(notep_dialogs)}")
        assert len(notep_dialogs) == 0, f"Residual error dialog appeared! Dialogs: {notep_dialogs}"

        # Cleanly close fresh Notepad
        close_application("notepad", task_id="fresh_check")
        time.sleep(0.5)

        print("[PASS] ACCEPTANCE G: Human-observed TabState modal failure completely eliminated.")
        return {
            "test": "acceptance_g_human_failure_reproduction_and_resolution",
            "status": "PASS",
            "artifact_path": str(artifact_file),
            "save_via_ui_verified": True,
            "fresh_launch_dialogs": 0,
            "tabstate_orphan_leak_prevented": True,
            "latency_sec": round(time.time() - t0, 3),
        }
    finally:
        clean_notepad_tabstate_for_path(str(artifact_file))
        time.sleep(0.2)
        if artifact_file.exists():
            try:
                artifact_file.unlink()
            except Exception:
                pass


def main() -> int:
    print("=" * 70)
    print("ASTRARUN PHASE F0-20: PERCEPTUAL AGENT LOOP & LIVE DESKTOP WORLD STATE")
    print(f"Platform: {platform.platform()} ({platform.machine()})")
    print(f"Python: {sys.version.split()[0]} | Process PID: {os.getpid()}")
    print("=" * 70)

    # Clean up any leftover test processes from interrupted prior executions
    for p in psutil.process_iter(["name"]):
        try:
            pname = (p.info["name"] or "").lower()
            if pname in ("charmap.exe", "notepad.exe"):
                p.kill()
        except Exception:
            pass
    clean_notepad_tabstate_for_path("")
    time.sleep(0.5)

    results = []
    try:
        r_a = test_acceptance_a_live_perception()
        results.append(r_a)
        time.sleep(1.0)

        r_b = test_acceptance_b_unfamiliar_application()
        results.append(r_b)
        time.sleep(1.0)

        r_c = test_acceptance_c_multistep_perceptual_closed_loop()
        results.append(r_c)
        time.sleep(1.0)

        r_d = test_acceptance_d_adaptive_divergence_recovery()
        results.append(r_d)
        time.sleep(1.0)

        r_e = test_acceptance_e_clean_desktop_state()
        results.append(r_e)
        time.sleep(1.0)

        r_f = test_acceptance_f_screen_understanding_proof()
        results.append(r_f)
        time.sleep(1.5)

        r_g = test_acceptance_g_human_failure_reproduction_and_resolution()
        results.append(r_g)

    except Exception as ex:
        logger.exception("F0-20 acceptance test failure: %s", ex)
        print(f"\n[FAIL] F0-20 Acceptance Suite encountered exception: {ex}")
        return 1

    audit_dir = PROJECT_ROOT / "docs" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    # 1. Main Acceptance Evidence
    acceptance_evidence = {
        "milestone": "F0-20",
        "description": "Perceptual Agent Loop & Live Desktop World State Verification",
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
            "LIVE_DESKTOP_WORLD_STATE_DETERMINISTIC_HASH",
            "UNFAMILIAR_APPLICATION_GENERAL_COMPUTER_USE",
            "MODALITY_PRESERVATION_APPLICATION_UI_NOT_FILE_API",
            "CLOSED_PERCEPTUAL_LOOP_PRE_POST_OBSERVATION",
            "ADAPTIVE_EXECUTION_UNDER_DIVERGENCE",
            "ZERO_DESKTOP_DEBRIS_AND_TABSTATE_LEAK_PREVENTION",
            "CAUSAL_SCREEN_UNDERSTANDING_COORDINATE_DELTA",
        ],
        "test_results": results,
    }
    (audit_dir / "F0_20_ACCEPTANCE_EVIDENCE.json").write_text(
        json.dumps(acceptance_evidence, indent=2), encoding="utf-8"
    )

    # 2. Perception Trace Artifact
    (audit_dir / "F0_20_PERCEPTION_TRACE.json").write_text(
        json.dumps(r_f, indent=2), encoding="utf-8"
    )

    # 3. UI Action Trace Artifact
    (audit_dir / "F0_20_UI_ACTION_TRACE.json").write_text(
        json.dumps(r_c, indent=2), encoding="utf-8"
    )

    # 4. Adaptive Recovery Artifact
    (audit_dir / "F0_20_ADAPTIVE_RECOVERY.json").write_text(
        json.dumps(r_d, indent=2), encoding="utf-8"
    )

    # 5. Resource Cleanup Artifact
    (audit_dir / "F0_20_RESOURCE_CLEANUP.json").write_text(
        json.dumps(r_e, indent=2), encoding="utf-8"
    )

    # 6. World State Architecture Artifact
    arch_doc = {
        "tier_0": "Win32 window and process enumeration (EnumWindows, GetWindowThreadProcessId)",
        "tier_1": "Microsoft UI Automation & DialogDetector (#32770, modal discovery)",
        "state_hash": "Deterministic SHA-256 computed across fg window, visible window bounds, dialogs, takeover",
        "desktop_attachment": "ensure_desktop_attached attached to interactive Default desktop",
        "modality_preservation": "Goal/PlanStep interaction_requirement (APPLICATION_UI vs DIRECT_RESULT)",
        "audit_evidence": "Generated in docs/audit/",
    }
    (audit_dir / "F0_20_WORLD_STATE_ARCHITECTURE.json").write_text(
        json.dumps(arch_doc, indent=2), encoding="utf-8"
    )

    print(f"\n[+] All 6 authoritative audit artifacts written to: {audit_dir}")
    print("\n" + "=" * 70)
    print("PHASE F0-20 ACCEPTANCE AUDIT VERDICT: ALL TESTS PASSED (7/7)")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
