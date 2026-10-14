"""Canonical Computer Use Observation Frame and Frame-by-Frame Trace Recorder.

Implements Phase F0-24A.2B requirements:
- Immutable ComputerUseObservationFrame separating RAW observation from DERIVED interpretation.
- DecisionContextSnapshot recording exact model context.
- DecisionRecord, ActionRecord, and StateTransitionRecord.
- Machine-readable trace output under outputs/computer_use_traces/<task_id>/.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

import psutil

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.computer_use.observation.frame")


class ComputerUseObservationFrame:
    """Canonical immutable observation frame capturing desktop information at one decision point."""

    def __init__(
        self,
        frame_id: str,
        timestamp_monotonic: float,
        timestamp_wall: float,
        task_id: str,
        goal_id: Optional[str] = None,
        step_id: Optional[str] = None,
        observation_generation: int = 0,
        raw: Optional[Dict[str, Any]] = None,
        derived: Optional[Dict[str, Any]] = None,
    ):
        self.frame_id = frame_id
        self.timestamp_monotonic = timestamp_monotonic
        self.timestamp_wall = timestamp_wall
        self.task_id = task_id
        if goal_id is not None and not isinstance(goal_id, str):
            self.goal_id = getattr(goal_id, "goal_id", getattr(goal_id, "raw_prompt", str(goal_id)))
        else:
            self.goal_id = goal_id
        self.step_id = step_id
        self.observation_generation = observation_generation
        self.raw = raw or {}
        self.derived = derived or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "timestamp_monotonic": self.timestamp_monotonic,
            "timestamp_wall": self.timestamp_wall,
            "task_id": self.task_id,
            "goal_id": self.goal_id,
            "step_id": self.step_id,
            "observation_generation": self.observation_generation,
            "raw": self.raw,
            "derived": self.derived,
        }


class DecisionContextSnapshot:
    """Exact structured context provided to the decision model at one decision point."""

    def __init__(
        self,
        decision_id: str,
        frame_id: str,
        goal: str,
        remaining_postconditions: List[str],
        current_plan: List[Dict[str, Any]],
        completed_steps: List[Dict[str, Any]],
        failed_attempts: List[Dict[str, Any]],
        bounded_action_history: List[Dict[str, Any]],
        target_identity: str,
        relevant_structural_ui: List[Dict[str, Any]],
        relevant_visual_observations: List[Dict[str, Any]],
        dialog_state: Dict[str, Any],
        resource_ownership: Dict[str, Any],
        user_takeover_state: bool,
        available_generic_capabilities: List[str],
        model_provenance: Optional[Dict[str, Any]] = None,
        parsed_decision: Optional[Dict[str, Any]] = None,
        hermes_experience: Optional[Dict[str, Any]] = None,
        epistemic_uncertainty: Optional[Dict[str, Any]] = None,
        decision_mode: str = "ACT",
    ):
        self.decision_id = decision_id
        self.frame_id = frame_id
        self.goal = goal
        self.remaining_postconditions = remaining_postconditions
        self.current_plan = current_plan
        self.completed_steps = completed_steps
        self.failed_attempts = failed_attempts
        self.bounded_action_history = bounded_action_history
        self.target_identity = target_identity
        self.relevant_structural_ui = relevant_structural_ui
        self.relevant_visual_observations = relevant_visual_observations
        self.dialog_state = dialog_state
        self.resource_ownership = resource_ownership
        self.user_takeover_state = user_takeover_state
        self.available_generic_capabilities = available_generic_capabilities
        self.model_provenance = model_provenance or {}
        self.parsed_decision = parsed_decision or {}
        self.hermes_experience = hermes_experience or {}
        self.epistemic_uncertainty = epistemic_uncertainty or {}
        self.decision_mode = decision_mode

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "frame_id": self.frame_id,
            "goal": self.goal,
            "remaining_postconditions": self.remaining_postconditions,
            "current_plan": self.current_plan,
            "completed_steps": self.completed_steps,
            "failed_attempts": self.failed_attempts,
            "bounded_action_history": self.bounded_action_history,
            "target_identity": self.target_identity,
            "relevant_structural_ui": self.relevant_structural_ui,
            "relevant_visual_observations": self.relevant_visual_observations,
            "dialog_state": self.dialog_state,
            "resource_ownership": self.resource_ownership,
            "user_takeover_state": self.user_takeover_state,
            "available_generic_capabilities": self.available_generic_capabilities,
            "model_provenance": self.model_provenance,
            "parsed_decision": self.parsed_decision,
            "hermes_experience": self.hermes_experience,
            "epistemic_uncertainty": self.epistemic_uncertainty,
            "decision_mode": self.decision_mode,
        }


class DecisionRecord:
    """Decision chosen by the model/planner with operational rationale."""

    def __init__(
        self,
        decision_id: str,
        input_frame_id: str,
        goal: str,
        candidate_actions: List[str],
        selected_action: str,
        target: str,
        reason: str,
        expected_state_transition: str,
        risk: str = "LOW",
        broker_proposal_id: Optional[str] = None,
        action_gate_result: str = "ALLOW",
        confirmation_required: bool = False,
    ):
        self.decision_id = decision_id
        self.input_frame_id = input_frame_id
        self.goal = goal
        self.candidate_actions = candidate_actions
        self.selected_action = selected_action
        self.target = target
        self.reason = reason
        self.expected_state_transition = expected_state_transition
        self.risk = risk
        self.broker_proposal_id = broker_proposal_id
        self.action_gate_result = action_gate_result
        self.confirmation_required = confirmation_required

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "input_frame_id": self.input_frame_id,
            "goal": self.goal,
            "candidate_actions": self.candidate_actions,
            "selected_action": self.selected_action,
            "target": self.target,
            "reason": self.reason,
            "expected_state_transition": self.expected_state_transition,
            "risk": self.risk,
            "broker_proposal_id": self.broker_proposal_id,
            "action_gate_result": self.action_gate_result,
            "confirmation_required": self.confirmation_required,
        }


class ActionRecord:
    """Physical action dispatched to Windows with input mechanism and results."""

    def __init__(
        self,
        action_id: str,
        decision_id: str,
        pre_frame_id: str,
        capability: str,
        parameters: Dict[str, Any],
        target_identity: str,
        mechanism: str,
        dispatch_timestamp: float,
        completion_timestamp: float,
        broker_verdict: str,
        os_return_status: str,
        action_result: Dict[str, Any],
        post_frame_id: str,
        exception: Optional[str] = None,
        user_takeover_detected: bool = False,
    ):
        self.action_id = action_id
        self.decision_id = decision_id
        self.pre_frame_id = pre_frame_id
        self.capability = capability
        self.parameters = parameters
        self.target_identity = target_identity
        self.mechanism = mechanism
        self.dispatch_timestamp = dispatch_timestamp
        self.completion_timestamp = completion_timestamp
        self.broker_verdict = broker_verdict
        self.os_return_status = os_return_status
        self.action_result = action_result
        self.post_frame_id = post_frame_id
        self.exception = exception
        self.user_takeover_detected = user_takeover_detected

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "decision_id": self.decision_id,
            "pre_frame_id": self.pre_frame_id,
            "capability": self.capability,
            "parameters": self.parameters,
            "target_identity": self.target_identity,
            "mechanism": self.mechanism,
            "dispatch_timestamp": self.dispatch_timestamp,
            "completion_timestamp": self.completion_timestamp,
            "broker_verdict": self.broker_verdict,
            "os_return_status": self.os_return_status,
            "action_result": self.action_result,
            "post_frame_id": self.post_frame_id,
            "exception": self.exception,
            "user_takeover_detected": self.user_takeover_detected,
        }


class StateTransitionRecord:
    """Comparison of PRE and POST frames against the expected transition."""

    def __init__(
        self,
        transition_id: str,
        pre_frame_id: str,
        action_id: str,
        post_frame_id: str,
        expected_transition: str,
        observed_transition: str,
        matched: bool,
        divergence_notes: Optional[str] = None,
    ):
        self.transition_id = transition_id
        self.pre_frame_id = pre_frame_id
        self.action_id = action_id
        self.post_frame_id = post_frame_id
        self.expected_transition = expected_transition
        self.observed_transition = observed_transition
        self.matched = matched
        self.divergence_notes = divergence_notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "pre_frame_id": self.pre_frame_id,
            "action_id": self.action_id,
            "post_frame_id": self.post_frame_id,
            "expected_transition": self.expected_transition,
            "observed_transition": self.observed_transition,
            "matched": self.matched,
            "divergence_notes": self.divergence_notes,
        }


class ComputerUseTraceRecorder:
    """Manages recording and persisting all frames, decisions, actions, and transitions for a task."""

    _instances: Dict[str, ComputerUseTraceRecorder] = {}

    def __init__(self, task_id: str, output_root: Optional[Path] = None):
        self.task_id = task_id
        if output_root is None:
            repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            self.trace_dir = repo_root / "outputs" / "computer_use_traces" / task_id
        else:
            self.trace_dir = output_root / task_id

        self.frames_dir = self.trace_dir / "frames"
        self.frames_dir.mkdir(parents=True, exist_ok=True)

        self._frame_counter = 0
        self._frames: List[ComputerUseObservationFrame] = []
        self._decisions: List[DecisionRecord] = []
        self._actions: List[ActionRecord] = []
        self._transitions: List[StateTransitionRecord] = []
        self._artifacts: List[Dict[str, Any]] = []

        # Manifest
        self.manifest_path = self.trace_dir / "task_manifest.json"
        if not self.manifest_path.exists():
            manifest = {
                "task_id": task_id,
                "created_at": time.time(),
                "created_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "status": "INITIALIZED",
            }
            self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    @classmethod
    def get_recorder(cls, task_id: str, output_root: Optional[Path] = None) -> ComputerUseTraceRecorder:
        if task_id not in cls._instances:
            cls._instances[task_id] = cls(task_id, output_root=output_root)
        return cls._instances[task_id]

    def capture_live_frame(
        self,
        step_id: Optional[str] = None,
        goal_id: Optional[str] = None,
        target_hwnd: Optional[int] = None,
        expected_app: Optional[str] = None,
        artifact_path: Optional[str | Path] = None,
        capture_screenshot: bool = True,
    ) -> ComputerUseObservationFrame:
        """Capture comprehensive live desktop state into an immutable ObservationFrame."""
        self._frame_counter += 1
        frame_idx = self._frame_counter
        frame_id = f"frame_{frame_idx:06d}"

        t_mono = time.perf_counter()
        t_wall = time.time()
        obs_gen = int(t_wall * 1000)

        raw_desktop: Dict[str, Any] = {
            "foreground_hwnd": 0,
            "foreground_pid": 0,
            "foreground_process_name": "",
            "foreground_title": "",
            "desktop_bounds": [0, 0, 1920, 1080],
            "cursor_position": [0, 0],
            "modifiers_pressed": [],
            "user_takeover_active": False,
        }
        visible_windows: List[Dict[str, Any]] = []
        target_app_state: Dict[str, Any] = {
            "active_target_hwnd": target_hwnd or 0,
            "active_target_pid": 0,
            "foreground_matches_target": False,
        }
        structural_ui: List[Dict[str, Any]] = []
        dialog_state: Dict[str, Any] = {
            "modal_detected": False,
            "dialog_hwnd": 0,
            "dialog_title": "",
            "dialog_class": "",
            "control_count": 0,
        }
        artifact_state: Dict[str, Any] = {
            "path": str(artifact_path) if artifact_path else None,
            "exists": False,
            "size_bytes": 0,
            "mtime": 0.0,
            "sha256": "",
        }
        resource_state: Dict[str, Any] = {
            "task_owned_pids": [],
            "task_owned_hwnds": [],
            "pre_existing_pids": [],
            "ledger_active_count": 0,
        }
        visual_state: Dict[str, Any] = {
            "screenshot_path": None,
            "screenshot_sha256": "",
            "dimensions": [0, 0],
            "region": None,
            "model_invoked": False,
            "detected_regions": [],
        }

        # 1. Win32 Live Desktop State
        if sys.platform == "win32":
            user32 = ctypes.windll.user32
            fg = user32.GetForegroundWindow()
            raw_desktop["foreground_hwnd"] = fg
            if fg:
                length = user32.GetWindowTextLengthW(fg)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(fg, buf, length + 1)
                    raw_desktop["foreground_title"] = buf.value

                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
                raw_desktop["foreground_pid"] = pid.value
                try:
                    p = psutil.Process(pid.value)
                    raw_desktop["foreground_process_name"] = p.name()
                except Exception:
                    pass

                rc = wintypes.RECT()
                user32.GetWindowRect(fg, ctypes.byref(rc))
                raw_desktop["desktop_bounds"] = [rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top]

            pt = wintypes.POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                raw_desktop["cursor_position"] = [pt.x, pt.y]

            # Physical takeover check
            try:
                from astrarun.perception.input import PhysicalInputController
                raw_desktop["user_takeover_active"] = PhysicalInputController.get_instance().check_user_takeover()
            except Exception:
                pass

            # Enumerate visible top-level windows
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

            def enum_cb(h: int, _: int) -> bool:
                if user32.IsWindowVisible(h):
                    length_w = user32.GetWindowTextLengthW(h)
                    title_w = ""
                    if length_w > 0:
                        buf_w = ctypes.create_unicode_buffer(length_w + 1)
                        user32.GetWindowTextW(h, buf_w, length_w + 1)
                        title_w = buf_w.value

                    rc_w = wintypes.RECT()
                    user32.GetWindowRect(h, ctypes.byref(rc_w))
                    w_dim = rc_w.right - rc_w.left
                    h_dim = rc_w.bottom - rc_w.top
                    if w_dim > 20 and h_dim > 20:
                        pid_w = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(h, ctypes.byref(pid_w))
                        exe_w = ""
                        try:
                            exe_w = psutil.Process(pid_w.value).name()
                        except Exception:
                            pass

                        cls_buf = ctypes.create_unicode_buffer(256)
                        user32.GetClassNameW(h, cls_buf, 256)
                        cls_name = cls_buf.value

                        is_modal = cls_name == "#32770" or (user32.GetWindowLongW(h, -16) & 0x00080000 != 0)
                        owner_h = user32.GetWindow(h, 4)  # GW_OWNER

                        visible_windows.append({
                            "hwnd": h,
                            "pid": pid_w.value,
                            "exe_name": exe_w,
                            "title": title_w,
                            "class_name": cls_name,
                            "bounds": [rc_w.left, rc_w.top, w_dim, h_dim],
                            "is_visible": True,
                            "is_minimized": bool(user32.IsIconic(h)),
                            "is_maximized": bool(user32.IsZoomed(h)),
                            "is_modal": is_modal,
                            "owner_hwnd": owner_h,
                        })

                        if is_modal and not dialog_state["modal_detected"]:
                            dialog_state["modal_detected"] = True
                            dialog_state["dialog_hwnd"] = h
                            dialog_state["dialog_title"] = title_w
                            dialog_state["dialog_class"] = cls_name
                return True

            user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        # 2. Target application resolution
        effective_target_hwnd = target_hwnd or raw_desktop["foreground_hwnd"]
        if effective_target_hwnd:
            target_app_state["active_target_hwnd"] = effective_target_hwnd
            if sys.platform == "win32":
                t_pid = wintypes.DWORD()
                ctypes.windll.user32.GetWindowThreadProcessId(effective_target_hwnd, ctypes.byref(t_pid))
                target_app_state["active_target_pid"] = t_pid.value
            target_app_state["foreground_matches_target"] = (raw_desktop["foreground_hwnd"] == effective_target_hwnd)

        # 3. Structural UI Automation Scan
        if effective_target_hwnd:
            try:
                from astrarun.computer_use.ui.uia_support import get_uia_interface, get_uia_module
                uia = get_uia_interface()
                uia_mod = get_uia_module()
                if uia and uia_mod:
                    elem = uia.ElementFromHandle(effective_target_hwnd)
                    if elem:
                        cond_all = uia.CreateTrueCondition()
                        children = elem.FindAll(uia_mod.TreeScope_Descendants, cond_all)
                        count = children.Length if children else 0
                        max_nodes = min(count, 40)
                        for i in range(max_nodes):
                            c = children.GetElement(i)
                            if not c:
                                continue
                            try:
                                c_type = c.CurrentControlType
                                name_c = c.CurrentName or ""
                                auto_id = c.CurrentAutomationId or ""
                                cls_c = c.CurrentClassName or ""
                                is_ro = False
                                val_str = ""
                                try:
                                    val_pat = c.GetCurrentPattern(uia_mod.UIA_ValuePatternId)
                                    if val_pat:
                                        vp = val_pat.QueryInterface(uia_mod.IUIAutomationValuePattern)
                                        val_str = vp.CurrentValue or ""
                                        is_ro = bool(vp.CurrentIsReadOnly)
                                except Exception:
                                    pass

                                br = c.CurrentBoundingRectangle
                                bounds_c = [br.left, br.top, br.right - br.left, br.bottom - br.top]

                                structural_ui.append({
                                    "runtime_id": f"uia_{effective_target_hwnd}_{i}",
                                    "automation_id": auto_id,
                                    "control_type": str(c_type),
                                    "class_name": cls_c,
                                    "name": name_c,
                                    "value": val_str[:100],
                                    "bounds": bounds_c,
                                    "is_enabled": bool(c.CurrentIsEnabled),
                                    "is_offscreen": bool(c.CurrentIsOffscreen),
                                    "is_focusable": bool(c.CurrentIsKeyboardFocusable),
                                    "is_focused": bool(c.CurrentHasKeyboardFocus),
                                    "is_read_only": is_ro,
                                })
                            except Exception:
                                pass
            except Exception as e:
                logger.debug("Structural UI scan exception: %s", e)

        # 4. Resource Ledger State
        try:
            from astrarun.tasks.resource_ledger import AstraResourceLedger
            ledger = AstraResourceLedger.get_instance()
            resources = ledger.list_resources_for_task(self.task_id)
            resource_state["task_owned_pids"] = [r.pid for r in resources if r.pid]
            resource_state["task_owned_hwnds"] = [r.hwnd for r in resources if r.hwnd]
            resource_state["ledger_active_count"] = len(resources)
            resource_state["pre_existing_pids"] = list(ledger._pre_existing_pids)
        except Exception:
            pass

        # 5. Artifact State
        if artifact_path:
            p_art = Path(artifact_path)
            if p_art.exists():
                artifact_state["exists"] = True
                artifact_state["size_bytes"] = p_art.stat().st_size
                artifact_state["mtime"] = p_art.stat().st_mtime
                try:
                    artifact_state["sha256"] = hashlib.sha256(p_art.read_bytes()).hexdigest()
                except Exception:
                    pass

        # 6. Screenshot Capture (Observability)
        if capture_screenshot:
            img_path = self.frames_dir / f"{frame_id}.png"
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab(all_screens=True)
                img.save(img_path)
                visual_state["screenshot_path"] = str(img_path)
                visual_state["dimensions"] = [img.width, img.height]
                visual_state["screenshot_sha256"] = hashlib.sha256(img_path.read_bytes()).hexdigest()
            except Exception as ex:
                logger.debug("Screenshot capture error: %s", ex)

        # 7. Derived Interpretation
        semantic_role = "IDLE_DESKTOP"
        dialog_classification = "NONE"
        if dialog_state["modal_detected"]:
            semantic_role = "MODAL_DIALOG"
            d_title = dialog_state["dialog_title"].lower()
            if "save as" in d_title:
                dialog_classification = "SAVE_AS"
            elif "save" in d_title:
                dialog_classification = "SAVE"
            elif "open" in d_title:
                dialog_classification = "OPEN"
            elif "confirm" in d_title or "overwrite" in d_title:
                dialog_classification = "OVERWRITE"
            elif "unsaved" in d_title:
                dialog_classification = "UNSAVED_CHANGES"
            else:
                dialog_classification = "UNKNOWN_MODAL"
        elif target_app_state["active_target_hwnd"]:
            semantic_role = "APPLICATION_WINDOW"

        target_ownership = "UNKNOWN"
        target_pid = target_app_state.get("active_target_pid")
        if target_pid:
            if target_pid in resource_state["task_owned_pids"]:
                target_ownership = "TASK_OWNED"
            elif target_pid in resource_state["pre_existing_pids"]:
                target_ownership = "PRE_EXISTING_USER"

        derived_data: Dict[str, Any] = {
            "semantic_role": semantic_role,
            "target_ownership": target_ownership,
            "dialog_classification": dialog_classification,
            "editable_surface_available": any(
                el.get("is_focusable") and not el.get("is_read_only") for el in structural_ui
            ),
            "can_receive_input": not raw_desktop["user_takeover_active"] and target_app_state["foreground_matches_target"],
            "confidence": 0.95 if target_app_state["foreground_matches_target"] else 0.60,
            "evidence_sources": ["Win32_GetForegroundWindow", "Win32_EnumWindows", "UIA_FindAll", "AstraResourceLedger"],
        }

        raw_data: Dict[str, Any] = {
            "desktop_state": raw_desktop,
            "window_state": visible_windows,
            "target_app_state": target_app_state,
            "structural_ui": structural_ui,
            "visual_state": visual_state,
            "dialog_state": dialog_state,
            "artifact_state": artifact_state,
            "resource_state": resource_state,
        }

        frame = ComputerUseObservationFrame(
            frame_id=frame_id,
            timestamp_monotonic=t_mono,
            timestamp_wall=t_wall,
            task_id=self.task_id,
            goal_id=goal_id,
            step_id=step_id,
            observation_generation=obs_gen,
            raw=raw_data,
            derived=derived_data,
        )

        # Persist frame JSON
        frame_json_path = self.frames_dir / f"{frame_id}.json"
        frame_json_path.write_text(json.dumps(frame.to_dict(), indent=2), encoding="utf-8")
        self._frames.append(frame)

        return frame

    def record_decision(self, decision: DecisionRecord) -> None:
        """Persist decision record to decisions.jsonl."""
        self._decisions.append(decision)
        decisions_file = self.trace_dir / "decisions.jsonl"
        with open(decisions_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(decision.to_dict()) + "\n")

    def record_decision_context(self, context_snapshot: DecisionContextSnapshot) -> None:
        """Persist exact model context snapshot."""
        ctx_file = self.trace_dir / "decision_contexts.jsonl"
        with open(ctx_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(context_snapshot.to_dict()) + "\n")

    def record_action(self, action: ActionRecord) -> None:
        """Persist action record to actions.jsonl."""
        self._actions.append(action)
        actions_file = self.trace_dir / "actions.jsonl"
        with open(actions_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(action.to_dict()) + "\n")

    def record_transition(self, transition: StateTransitionRecord) -> None:
        """Persist state transition record to transitions.jsonl."""
        self._transitions.append(transition)
        trans_file = self.trace_dir / "transitions.jsonl"
        with open(trans_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(transition.to_dict()) + "\n")

    def record_artifact(self, artifact_info: Dict[str, Any]) -> None:
        """Persist final verified artifact information."""
        self._artifacts.append(artifact_info)
        art_file = self.trace_dir / "artifacts.json"
        art_file.write_text(json.dumps(self._artifacts, indent=2), encoding="utf-8")

    def finalize_trace(self, verdict: str = "COMPLETED", notes: str = "") -> Dict[str, Any]:
        """Produce trace_summary.json concluding the machine-readable task record."""
        summary = {
            "task_id": self.task_id,
            "verdict": verdict,
            "total_frames": len(self._frames),
            "total_decisions": len(self._decisions),
            "total_actions": len(self._actions),
            "total_transitions": len(self._transitions),
            "transitions_matched": sum(1 for t in self._transitions if t.matched),
            "artifacts_produced": len(self._artifacts),
            "notes": notes,
            "completed_at": time.time(),
            "completed_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        summary_path = self.trace_dir / "trace_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        # Update manifest
        manifest = {
            "task_id": self.task_id,
            "status": verdict,
            "frames_count": len(self._frames),
            "decisions_count": len(self._decisions),
            "actions_count": len(self._actions),
            "summary_path": str(summary_path),
        }
        self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return summary
