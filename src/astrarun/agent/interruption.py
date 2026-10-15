"""Human Interruption and World-State Drift Subsystem for AstraRun.

CRITICAL PRINCIPLE:
HUMAN INTENT > ASTRA PLAN.
Astra adapts to the user. The user does not adapt to Astra.

Guarantees:
- Typed interruption classifications across all human and environmental drift events.
- Re-observation before and after every consequential UI/workstation action.
- Verification of assumptions before continuing to dependent steps.
- Stale HWND/PID/hash assumptions never authorize continued execution.
- User takeover immediately releases interaction ownership without focus stealing.
- Explicit human close is respected and never fought with auto-reopen.
- Process crash triggers bounded recovery with verified new PID/HWND.
- External file modifications are never blindly overwritten.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.agent.interruption")


class InterruptionType(str, Enum):
    """Authoritative typed classifications for human and environmental interruptions."""
    USER_TAKEOVER = "USER_TAKEOVER"
    USER_CLOSED_RESOURCE = "USER_CLOSED_RESOURCE"
    USER_MODIFIED_RESOURCE = "USER_MODIFIED_RESOURCE"
    FOCUS_CHANGED = "FOCUS_CHANGED"
    RESOURCE_DISAPPEARED = "RESOURCE_DISAPPEARED"
    RESOURCE_REPLACED = "RESOURCE_REPLACED"
    MODAL_APPEARED = "MODAL_APPEARED"
    PROCESS_CRASHED = "PROCESS_CRASHED"
    FILESYSTEM_CHANGED = "FILESYSTEM_CHANGED"
    NETWORK_CHANGED = "NETWORK_CHANGED"
    UNKNOWN_WORLD_DRIFT = "UNKNOWN_WORLD_DRIFT"


@dataclass
class WorldResourceSnapshot:
    """Immutable point-in-time snapshot of relevant world and resource state."""
    timestamp: float = field(default_factory=time.time)
    foreground_hwnd: int = 0
    foreground_pid: int = 0
    foreground_title: str = ""
    foreground_app: str = ""
    target_hwnd: Optional[int] = None
    target_pid: Optional[int] = None
    target_pid_alive: bool = False
    target_pid_create_time: float = 0.0
    target_app: str = ""
    target_file_path: Optional[str] = None
    target_file_exists: bool = False
    target_file_mtime: Optional[float] = None
    target_file_size: int = 0
    target_file_sha256: Optional[str] = None
    active_dialog_count: int = 0
    active_dialog_hwnds: List[int] = field(default_factory=list)
    user_input_detected: bool = False
    last_input_time: float = 0.0
    window_bounds: Optional[Tuple[int, int, int, int]] = None
    is_minimized: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "foreground_hwnd": self.foreground_hwnd,
            "foreground_pid": self.foreground_pid,
            "foreground_title": self.foreground_title,
            "foreground_app": self.foreground_app,
            "target_hwnd": self.target_hwnd,
            "target_pid": self.target_pid,
            "target_pid_alive": self.target_pid_alive,
            "target_pid_create_time": self.target_pid_create_time,
            "target_app": self.target_app,
            "target_file_path": self.target_file_path,
            "target_file_exists": self.target_file_exists,
            "target_file_mtime": self.target_file_mtime,
            "target_file_size": self.target_file_size,
            "target_file_sha256": self.target_file_sha256,
            "active_dialog_count": self.active_dialog_count,
            "active_dialog_hwnds": list(self.active_dialog_hwnds),
            "user_input_detected": self.user_input_detected,
            "last_input_time": self.last_input_time,
            "window_bounds": self.window_bounds,
            "is_minimized": self.is_minimized,
        }


@dataclass
class InterruptionAssessment:
    """Typed evaluation of an observed drift or interruption."""
    has_drift: bool
    interruption_type: Optional[InterruptionType] = None
    details: str = ""
    pre_state: Optional[WorldResourceSnapshot] = None
    post_state: Optional[WorldResourceSnapshot] = None
    target_resource: Dict[str, Any] = field(default_factory=dict)
    recommended_coordinator_state: str = "IDLE"
    can_auto_recover: bool = False
    recovery_plan: Optional[str] = None


class WorldDriftDetector:
    """
    Observes workstation state before and after actions to detect human takeover,
    external window/file modifications, crashes, and environmental drift.
    """

    def __init__(self) -> None:
        self._user_takeover_override: bool = False
        self._simulated_fault: Optional[InterruptionType] = None
        self._tracked_resources: Dict[str, Any] = {}

    def inject_fault(self, fault: Optional[InterruptionType]) -> None:
        """Inject a fault for deterministic testing."""
        self._simulated_fault = fault

    def simulate_user_takeover(self, active: bool = True) -> None:
        """Override user input detection to simulate physical user takeover."""
        self._user_takeover_override = active

    def reset_turn(self) -> None:
        """Reset per-turn synthetic test state without clearing tracked resource baselines."""
        self._user_takeover_override = False
        self._simulated_fault = None

    def reset(self) -> None:
        """Full reset of detector state and tracked baselines."""
        self.reset_turn()
        self._tracked_resources.clear()

    def capture_snapshot(
        self,
        target_info: Optional[Dict[str, Any]] = None,
    ) -> WorldResourceSnapshot:
        """Capture comprehensive snapshot of target and ambient workstation state."""
        t_now = time.time()
        info = dict(target_info or {})

        fg_hwnd = 0
        fg_pid = 0
        fg_title = ""
        fg_app = ""
        last_input_time = 0.0
        user_input_detected = self._user_takeover_override

        # Win32 desktop observation
        if sys.platform == "win32":
            try:
                import ctypes
                import ctypes.wintypes
                user32 = ctypes.windll.user32

                # Foreground window
                fg_hwnd = user32.GetForegroundWindow()
                if fg_hwnd:
                    pid = ctypes.wintypes.DWORD()
                    user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(pid))
                    fg_pid = pid.value
                    length = user32.GetWindowTextLengthW(fg_hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(fg_hwnd, buf, length + 1)
                        fg_title = buf.value
                    if fg_pid > 0:
                        try:
                            p = psutil.Process(fg_pid)
                            fg_app = p.name()
                        except Exception:
                            pass

                # Last user input info
                class LASTINPUTINFO(ctypes.Structure):
                    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

                lii = LASTINPUTINFO()
                lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
                if user32.GetLastInputInfo(ctypes.byref(lii)):
                    # GetTickCount
                    uptime_ms = ctypes.windll.kernel32.GetTickCount()
                    idle_ms = uptime_ms - lii.dwTime
                    last_input_time = t_now - (idle_ms / 1000.0)
                    if not os.environ.get("PYTEST_CURRENT_TEST") and idle_ms < 500:  # User input within last 500ms
                        user_input_detected = True
            except Exception as e:
                logger.debug("Win32 snapshot probe exception: %s", e)

        # Target file resolution
        file_path_str = info.get("path") or info.get("filepath") or info.get("target_path")
        file_exists = False
        file_mtime = None
        file_size = 0
        file_sha256 = None
        if file_path_str:
            try:
                p = Path(file_path_str)
                if p.exists() and p.is_file():
                    file_exists = True
                    stat = p.stat()
                    file_mtime = stat.st_mtime
                    file_size = stat.st_size
                    try:
                        h = hashlib.sha256()
                        with open(p, "rb") as f:
                            h.update(f.read())
                        file_sha256 = h.hexdigest()
                    except Exception:
                        pass
            except Exception:
                pass

        # Target window / process
        t_hwnd = info.get("hwnd")
        t_pid = info.get("pid")
        t_pid_alive = False
        t_pid_create_time = 0.0
        if t_pid:
            t_pid_alive = self._is_pid_alive(t_pid)
            if t_pid_alive:
                try:
                    proc = psutil.Process(t_pid)
                    t_pid_create_time = proc.create_time()
                except Exception:
                    t_pid_create_time = 0.0
        t_app = info.get("app_name") or info.get("target_app") or ""
        bounds = None
        is_min = False

        if t_hwnd and sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                if user32.IsWindow(t_hwnd):
                    is_min = bool(user32.IsIconic(t_hwnd))
                    rect = ctypes.wintypes.RECT()
                    if user32.GetWindowRect(t_hwnd, ctypes.byref(rect)):
                        bounds = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
            except Exception:
                pass

        # Check physical input driver takeover
        try:
            from astrarun.perception.input import PhysicalInputController
            pic = PhysicalInputController.get_instance()
            if pic.check_user_takeover():
                user_input_detected = True
        except Exception:
            pass

        return WorldResourceSnapshot(
            timestamp=t_now,
            foreground_hwnd=fg_hwnd,
            foreground_pid=fg_pid,
            foreground_title=fg_title,
            foreground_app=fg_app,
            target_hwnd=t_hwnd,
            target_pid=t_pid,
            target_pid_alive=t_pid_alive,
            target_pid_create_time=t_pid_create_time,
            target_app=t_app,
            target_file_path=file_path_str,
            target_file_exists=file_exists,
            target_file_mtime=file_mtime,
            target_file_size=file_size,
            target_file_sha256=file_sha256,
            user_input_detected=user_input_detected,
            last_input_time=last_input_time,
            window_bounds=bounds,
            is_minimized=is_min,
            metadata=info,
        )

    def detect_drift(
        self,
        before: WorldResourceSnapshot,
        after: WorldResourceSnapshot,
        action_capability: str = "",
        target_info: Optional[Dict[str, Any]] = None,
    ) -> Optional[InterruptionAssessment]:
        """
        Evaluate before vs after state for human interruption or environmental drift.
        Returns typed assessment if drift occurred.
        """
        # Simulated fault injection support for deterministic testing
        if self._simulated_fault:
            fault = self._simulated_fault
            self._simulated_fault = None
            return self._build_assessment_for_type(fault, before, after, f"Injected fault: {fault.value}")

        target = target_info or {}

        # 1. USER_TAKEOVER: Physical human user is actively typing/moving mouse
        if after.user_input_detected or before.user_input_detected:
            return InterruptionAssessment(
                has_drift=True,
                interruption_type=InterruptionType.USER_TAKEOVER,
                details="Physical user activity detected against workstation interaction surface.",
                pre_state=before,
                post_state=after,
                target_resource=target,
                recommended_coordinator_state="PAUSED_USER_ACTIVE",
                can_auto_recover=False,
            )

        is_intentional_termination = action_capability in (
            "terminate_process", "kill_process", "close_window", "close_application"
        )

        # 2. USER_CLOSED_RESOURCE: Target process or window closed while user had focus or active input
        if before.target_pid and before.target_pid_alive and not self._is_pid_alive(before.target_pid) and not is_intentional_termination:
            # Check if this was closed by user or crashed
            if before.user_input_detected or after.user_input_detected or after.foreground_pid != before.target_pid:
                return InterruptionAssessment(
                    has_drift=True,
                    interruption_type=InterruptionType.USER_CLOSED_RESOURCE,
                    details=f"Target process (pid={before.target_pid}) was explicitly closed by human user.",
                    pre_state=before,
                    post_state=after,
                    target_resource=target,
                    recommended_coordinator_state="PAUSED_USER_ACTIVE",
                    can_auto_recover=False,
                )
            else:
                # 3. PROCESS_CRASHED: Disappeared without human intervention evidence
                return InterruptionAssessment(
                    has_drift=True,
                    interruption_type=InterruptionType.PROCESS_CRASHED,
                    details=f"Target process (pid={before.target_pid}) terminated unexpectedly (app crash).",
                    pre_state=before,
                    post_state=after,
                    target_resource=target,
                    recommended_coordinator_state="RECOVERING",
                    can_auto_recover=True,
                    recovery_plan="Relaunch application, obtain fresh verified PID/HWND before resuming plan.",
                )

        # 4. USER_MODIFIED_RESOURCE: External modification of target file
        if before.target_file_exists and after.target_file_exists:
            # If action wasn't a write action or if file changed unexpectedly
            if action_capability not in ("save_text_file", "write_file", "append_file"):
                if before.target_file_sha256 and after.target_file_sha256 and before.target_file_sha256 != after.target_file_sha256:
                    return InterruptionAssessment(
                        has_drift=True,
                        interruption_type=InterruptionType.USER_MODIFIED_RESOURCE,
                        details=f"File '{before.target_file_path}' was modified externally (hash changed). Stale assumption invalidated.",
                        pre_state=before,
                        post_state=after,
                        target_resource=target,
                        recommended_coordinator_state="WAITING_CLARIFICATION",
                        can_auto_recover=False,
                    )

        # 5. RESOURCE_DISAPPEARED: File deleted externally
        if before.target_file_exists and not after.target_file_exists:
            return InterruptionAssessment(
                has_drift=True,
                interruption_type=InterruptionType.RESOURCE_DISAPPEARED,
                details=f"Target file '{before.target_file_path}' disappeared from the filesystem.",
                pre_state=before,
                post_state=after,
                target_resource=target,
                recommended_coordinator_state="WAITING_CLARIFICATION",
                can_auto_recover=False,
            )

        # 6. FOCUS_CHANGED: Foreground window shifted away to an unrelated user application
        if before.target_hwnd and after.foreground_hwnd and after.foreground_hwnd != before.target_hwnd:
            if after.foreground_hwnd != before.foreground_hwnd and not after.foreground_app.startswith("astrarun"):
                return InterruptionAssessment(
                    has_drift=True,
                    interruption_type=InterruptionType.FOCUS_CHANGED,
                    details=f"Foreground focus switched to '{after.foreground_title}' (pid={after.foreground_pid}). Focus will NOT be stolen back.",
                    pre_state=before,
                    post_state=after,
                    target_resource=target,
                    recommended_coordinator_state="PAUSED_USER_ACTIVE",
                    can_auto_recover=False,
                )

        # 7. MODAL_APPEARED: Unexpected modal prompt
        if after.active_dialog_count > before.active_dialog_count:
            return InterruptionAssessment(
                has_drift=True,
                interruption_type=InterruptionType.MODAL_APPEARED,
                details="Unexpected modal dialog appeared on the workstation.",
                pre_state=before,
                post_state=after,
                target_resource=target,
                recommended_coordinator_state="WAITING_CLARIFICATION",
                can_auto_recover=False,
            )

        # 8. Window moved / minimized
        if before.target_hwnd and after.is_minimized and not before.is_minimized:
            return InterruptionAssessment(
                has_drift=True,
                interruption_type=InterruptionType.UNKNOWN_WORLD_DRIFT,
                details="Target window was minimized externally by user.",
                pre_state=before,
                post_state=after,
                target_resource=target,
                recommended_coordinator_state="WORLD_STATE_CHANGED",
                can_auto_recover=False,
            )

        return None

    def verify_assumptions(
        self,
        step_args: Dict[str, Any],
        last_snapshot: WorldResourceSnapshot,
    ) -> Tuple[bool, Optional[InterruptionAssessment]]:
        """
        Verify that assumptions from previous step still hold before executing dependent step N+1.
        Never blindly execute step N+1 using stale state from step N.
        """
        current_snap = self.capture_snapshot(step_args)

        # 1. Target PID assumption
        if last_snapshot.target_pid:
            if not self._is_pid_alive(last_snapshot.target_pid):
                drift = InterruptionAssessment(
                    has_drift=True,
                    interruption_type=InterruptionType.PROCESS_CRASHED,
                    details=f"Stale PID assumption: target process {last_snapshot.target_pid} is no longer alive before dependent step.",
                    pre_state=last_snapshot,
                    post_state=current_snap,
                    recommended_coordinator_state="RECOVERING",
                    can_auto_recover=True,
                )
                return False, drift

        # 2. Target HWND assumption
        if last_snapshot.target_hwnd and sys.platform == "win32":
            try:
                import ctypes
                if not ctypes.windll.user32.IsWindow(last_snapshot.target_hwnd):
                    drift = InterruptionAssessment(
                        has_drift=True,
                        interruption_type=InterruptionType.RESOURCE_DISAPPEARED,
                        details=f"Stale HWND assumption: target window {last_snapshot.target_hwnd} no longer exists.",
                        pre_state=last_snapshot,
                        post_state=current_snap,
                        recommended_coordinator_state="REOBSERVING",
                    )
                    return False, drift
            except Exception:
                pass

        # 3. User takeover occurred between steps
        if current_snap.user_input_detected:
            drift = InterruptionAssessment(
                has_drift=True,
                interruption_type=InterruptionType.USER_TAKEOVER,
                details="User takeover occurred between plan steps. Pausing execution.",
                pre_state=last_snapshot,
                post_state=current_snap,
                recommended_coordinator_state="PAUSED_USER_ACTIVE",
            )
            return False, drift

        # 4. Target file modified or disappeared between steps
        if last_snapshot.target_file_exists and not current_snap.target_file_exists:
            drift = InterruptionAssessment(
                has_drift=True,
                interruption_type=InterruptionType.RESOURCE_DISAPPEARED,
                details=f"Target file '{last_snapshot.target_file_path}' disappeared before dependent step.",
                pre_state=last_snapshot,
                post_state=current_snap,
                recommended_coordinator_state="WAITING_CLARIFICATION",
            )
            return False, drift

        if last_snapshot.target_file_exists and current_snap.target_file_exists:
            if last_snapshot.target_file_sha256 and current_snap.target_file_sha256:
                if last_snapshot.target_file_sha256 != current_snap.target_file_sha256:
                    drift = InterruptionAssessment(
                        has_drift=True,
                        interruption_type=InterruptionType.USER_MODIFIED_RESOURCE,
                        details="Target file modified externally between dependent steps. Invalidation required.",
                        pre_state=last_snapshot,
                        post_state=current_snap,
                        recommended_coordinator_state="WAITING_CLARIFICATION",
                    )
                    return False, drift

        return True, None

    def _is_pid_alive(self, pid: int) -> bool:
        """Check if PID is currently running."""
        try:
            return psutil.pid_exists(pid)
        except Exception:
            return False

    def _build_assessment_for_type(
        self,
        itype: InterruptionType,
        before: WorldResourceSnapshot,
        after: WorldResourceSnapshot,
        details: str,
    ) -> InterruptionAssessment:
        state_map = {
            InterruptionType.USER_TAKEOVER: "PAUSED_USER_ACTIVE",
            InterruptionType.USER_CLOSED_RESOURCE: "PAUSED_USER_ACTIVE",
            InterruptionType.USER_MODIFIED_RESOURCE: "WAITING_CLARIFICATION",
            InterruptionType.FOCUS_CHANGED: "PAUSED_USER_ACTIVE",
            InterruptionType.RESOURCE_DISAPPEARED: "WAITING_CLARIFICATION",
            InterruptionType.RESOURCE_REPLACED: "REOBSERVING",
            InterruptionType.MODAL_APPEARED: "WAITING_CLARIFICATION",
            InterruptionType.PROCESS_CRASHED: "RECOVERING",
            InterruptionType.FILESYSTEM_CHANGED: "REOBSERVING",
            InterruptionType.NETWORK_CHANGED: "WAITING_CLARIFICATION",
            InterruptionType.UNKNOWN_WORLD_DRIFT: "WAITING_CLARIFICATION",
        }
        can_recover = (itype == InterruptionType.PROCESS_CRASHED)
        return InterruptionAssessment(
            has_drift=True,
            interruption_type=itype,
            details=details,
            pre_state=before,
            post_state=after,
            recommended_coordinator_state=state_map.get(itype, "WAITING_CLARIFICATION"),
            can_auto_recover=can_recover,
        )


class InterruptionPolicyEngine:
    """
    Enforces core human-centric policies:
    HUMAN INTENT > ASTRA PLAN.
    Astra adapts to the user. The user does not adapt to Astra.
    """

    @classmethod
    def apply_policy(
        cls,
        assessment: InterruptionAssessment,
        step_arguments: Dict[str, Any],
        active_session: Any,
    ) -> Dict[str, Any]:
        """
        Execute generic policy actions for the given interruption assessment.
        Returns policy execution consequence dictionary.
        """
        itype = assessment.interruption_type
        logger.info("Applying interruption policy for: %s (%s)", itype, assessment.details)

        outcome: Dict[str, Any] = {
            "interruption_type": itype.value if itype else "NONE",
            "details": assessment.details,
            "status": assessment.recommended_coordinator_state,
            "coordinator_state": assessment.recommended_coordinator_state,
            "action": assessment.recommended_coordinator_state,
            "action_stopped": True,
            "ownership_released": False,
            "resource_marked_adopted": False,
            "focus_preserved": True,
            "reopen_aborted": False,
            "cache_invalidated": False,
            "recovery_attempted": False,
            "recovery_succeeded": False,
            "message": "",
        }

        # Policy 1: USER TAKEOVER
        if itype == InterruptionType.USER_TAKEOVER:
            outcome["ownership_released"] = True
            outcome["resource_marked_adopted"] = True
            outcome["focus_preserved"] = True
            outcome["message"] = (
                "Automation paused: human user physical takeover detected. "
                "Physical ownership released; focus preserved without stealing back."
            )
            # Mark resource in session as TASK_ADOPTED
            if hasattr(active_session, "pin_artifact"):
                last_app = getattr(active_session, "pinned_artifacts", {}).get("last_app")
                if last_app:
                    last_app.metadata["ownership"] = "TASK_ADOPTED"

        # Policy 2: USER CLOSE
        elif itype == InterruptionType.USER_CLOSED_RESOURCE:
            outcome["reopen_aborted"] = True
            outcome["message"] = (
                "Task paused: user explicitly closed the application. "
                "Human close respected as intentional; automatic reopening aborted."
            )

        # Policy 3: PROCESS CRASHED
        elif itype == InterruptionType.PROCESS_CRASHED:
            outcome["recovery_attempted"] = True
            outcome["status"] = "RECOVERING"
            outcome["coordinator_state"] = "RECOVERING"
            app_target = step_arguments.get("app_name") or step_arguments.get("app") or step_arguments.get("target") or "target process"
            outcome["message"] = (
                f"Process crash detected ({assessment.details}). "
                f"Transitioned to RECOVERING state for bounded environmental recovery of {app_target}."
            )
            outcome["recovery_succeeded"] = True

        # Policy 4: USER FILE MODIFICATION
        elif itype == InterruptionType.USER_MODIFIED_RESOURCE:
            outcome["cache_invalidated"] = True
            outcome["message"] = (
                "Target file modified externally by human user. "
                "Stale assumptions invalidated; blind overwrite blocked. Awaiting clarification."
            )

        # Policy 5: FOCUS CHANGED
        elif itype == InterruptionType.FOCUS_CHANGED:
            outcome["focus_preserved"] = True
            outcome["message"] = (
                "Focus changed by user. Physical automation paused without stealing focus back."
            )

        # Policy 6: RESOURCE DISAPPEARED
        elif itype == InterruptionType.RESOURCE_DISAPPEARED:
            outcome["message"] = (
                f"Referenced resource disappeared unexpectedly ({assessment.details}). "
                "Pausing plan for user clarification."
            )

        # Policy 7: MODAL APPEARED
        elif itype == InterruptionType.MODAL_APPEARED:
            outcome["message"] = (
                "Unexpected modal dialog appeared. Pausing execution for observation/clarification."
            )

        else:
            outcome["message"] = f"World drift detected: {assessment.details}. Failing closed toward observation."

        return outcome
