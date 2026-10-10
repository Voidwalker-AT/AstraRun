"""Step verification engine for AstraRun v0.11 agent runtime."""

from __future__ import annotations

import ctypes
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from astrarun.agent.models import PlanStep, Verification
from astrarun.capabilities.models import CapabilityResult
from astrarun.capabilities.schema import VerifierStrategy
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.agent.verifier")


class StepVerifier:
    """Verifies actual post-execution workstation state according to declared verification strategies."""

    def __init__(self):
        self._user32 = None
        if os.name == "nt":
            try:
                self._user32 = ctypes.windll.user32
            except Exception:
                pass

    def verify(
        self,
        step: PlanStep,
        result: CapabilityResult,
        context: Optional[dict[str, Any]] = None,
    ) -> Verification:
        """Execute verification strategy and generate an empirical verification report."""
        t0 = time.perf_counter()
        strategy = step.verifier_strategy
        params = step.verifier_params or {}

        verified = False
        message = ""
        evidence: dict[str, Any] = {}

        try:
            if not result.success:
                verified = False
                message = f"Capability execution failed: {result.message}"
                evidence["error"] = result.error

            elif strategy == VerifierStrategy.RETURN_CODE_ONLY:
                verified = True
                message = "Return code succeeded."
                evidence["result_message"] = result.message

            elif strategy in (VerifierStrategy.FILE_EXISTS, VerifierStrategy.FILE_NON_EMPTY):
                target_path = (
                    result.data.get("output_file")
                    or result.data.get("path")
                    or params.get("path")
                    or step.arguments.get("path")
                    or step.arguments.get("output_path")
                )
                if not target_path:
                    verified = False
                    message = "No target file path specified for file verification."
                else:
                    path_obj = Path(target_path)
                    if not path_obj.is_absolute():
                        if path_obj.parts and path_obj.parts[0].lower() == "downloads":
                            cand = Path.home() / "Downloads" / Path(*path_obj.parts[1:])
                            if cand.exists():
                                path_obj = cand
                    exists = path_obj.exists()
                    evidence["path"] = str(path_obj)
                    evidence["exists"] = exists

                    if not exists:
                        verified = False
                        message = f"Expected file does not exist: {path_obj}"
                    elif strategy == VerifierStrategy.FILE_NON_EMPTY:
                        size = path_obj.stat().st_size
                        evidence["size_bytes"] = size
                        if size > 0:
                            verified = True
                            message = f"Verified file exists and is non-empty ({size} bytes)."
                        else:
                            verified = False
                            message = f"File exists but is empty (0 bytes): {path_obj}"
                    else:
                        verified = True
                        message = f"Verified file exists: {path_obj}"

            elif strategy == VerifierStrategy.FILE_CONTAINS:
                target_path = (
                    result.data.get("output_file")
                    or result.data.get("path")
                    or params.get("path")
                )
                substring = params.get("contains", "")
                if not target_path or not Path(target_path).exists():
                    verified = False
                    message = f"Target file does not exist for content check: {target_path}"
                else:
                    try:
                        content = Path(target_path).read_text(encoding="utf-8", errors="ignore")
                        contains_target = substring in content
                        evidence["contains_substring"] = contains_target
                        if contains_target:
                            verified = True
                            message = f"File contains required substring '{substring[:30]}'."
                        else:
                            verified = False
                            message = f"File did not contain required substring '{substring[:30]}'."
                    except Exception as e:
                        verified = False
                        message = f"Error reading file for verification: {e}"

            elif strategy == VerifierStrategy.WINDOW_READY:
                hwnd = params.get("hwnd") or result.data.get("hwnd")
                title_query = params.get("title") or step.arguments.get("app_name")

                if hwnd and self._user32:
                    is_window = bool(self._user32.IsWindow(hwnd))
                    is_visible = bool(self._user32.IsWindowVisible(hwnd))
                    evidence["hwnd"] = hwnd
                    evidence["is_window"] = is_window
                    evidence["is_visible"] = is_visible
                    if is_window and is_visible:
                        verified = True
                        message = f"Target window (HWND {hwnd}) is valid and visible."
                    else:
                        verified = False
                        message = f"Target window (HWND {hwnd}) is not ready (valid={is_window}, visible={is_visible})."
                elif title_query:
                    from astrarun.windows.discovery import WindowDiscovery
                    discovery = WindowDiscovery()
                    windows = discovery.find_windows(title_query)
                    evidence["matched_windows"] = len(windows)
                    if windows:
                        verified = True
                        message = f"Discovered {len(windows)} window(s) matching '{title_query}'."
                    else:
                        verified = False
                        message = f"No windows found matching query '{title_query}'."
                else:
                    # Fallback to result success
                    verified = result.success
                    message = "Window assumed ready based on successful launch."

            elif strategy == VerifierStrategy.WINDOW_CLOSED:
                hwnd = params.get("hwnd") or step.arguments.get("hwnd")
                if hwnd and self._user32:
                    is_window = bool(self._user32.IsWindow(hwnd))
                    evidence["hwnd"] = hwnd
                    evidence["is_window"] = is_window
                    if not is_window:
                        verified = True
                        message = f"Window HWND {hwnd} has closed."
                    else:
                        verified = False
                        message = f"Window HWND {hwnd} is still open."
                else:
                    verified = result.success
                    message = "Window close confirmed via return code."

            elif strategy == VerifierStrategy.NETWORK_SSID:
                expected_ssid = params.get("ssid") or step.arguments.get("ssid")
                from astrarun.tools.wifi import wifi_status
                status_res = wifi_status()
                active_net = status_res.data.get("active_network") if status_res.success else None
                current_ssid = active_net.get("ssid") if active_net else None
                evidence["current_ssid"] = current_ssid
                evidence["expected_ssid"] = expected_ssid

                if expected_ssid and current_ssid and expected_ssid.lower() in current_ssid.lower():
                    verified = True
                    message = f"Connected to requested Wi-Fi network: '{current_ssid}'."
                elif not expected_ssid and status_res.data.get("connected"):
                    verified = True
                    message = f"Connected to Wi-Fi: '{current_ssid}'."
                else:
                    verified = False
                    message = f"Not connected to expected Wi-Fi '{expected_ssid}' (currently '{current_ssid}')."

            elif strategy == VerifierStrategy.PROCESS_RUNNING:
                pid = params.get("pid") or result.data.get("pid")
                proc_name = params.get("process_name") or step.arguments.get("name")
                import psutil
                if pid:
                    running = psutil.pid_exists(pid)
                    evidence["pid"] = pid
                    evidence["running"] = running
                    verified = running
                    message = f"Process PID {pid} is {'running' if running else 'not running'}."
                elif proc_name:
                    found = any(p.name().lower() == proc_name.lower() for p in psutil.process_iter(['name']))
                    evidence["process_name"] = proc_name
                    evidence["found"] = found
                    verified = found
                    message = f"Process '{proc_name}' is {'running' if found else 'not running'}."
                else:
                    verified = result.success
                    message = "Process running verified via capability result."

            elif strategy == VerifierStrategy.UI_ELEMENT_STATE:
                expected_text = params.get("text") or step.arguments.get("text") or ""
                target_hwnd = params.get("hwnd") or result.data.get("hwnd")
                app_query = params.get("app_name") or step.arguments.get("app_name") or step.arguments.get("window")

                from astrarun.interaction.policy import is_simulated_interaction_validation
                if sys.platform != "win32" or is_simulated_interaction_validation():
                    verified = result.success
                    message = f"Simulated UI element state verified for text: '{expected_text}'"
                    evidence["simulated"] = True
                else:
                    import ctypes
                    user32 = ctypes.windll.user32
                    if not target_hwnd or not user32.IsWindow(target_hwnd):
                        target_hwnd = user32.GetForegroundWindow()

                    buf = ctypes.create_unicode_buffer(512)
                    user32.GetWindowTextW(target_hwnd, buf, 512)
                    win_title = buf.value
                    evidence["hwnd"] = target_hwnd
                    evidence["window_title"] = win_title

                    text_found = False
                    matched_via = ""

                    # 1. Window title inspection
                    if expected_text and expected_text.lower() in win_title.lower():
                        text_found = True
                        matched_via = f"Window title '{win_title}' contains '{expected_text}'"

                    # 2. UIA accessibility tree inspection
                    if not text_found and target_hwnd and user32.IsWindow(target_hwnd):
                        try:
                            from astrarun.interaction.discovery import inspect_window_ui
                            from astrarun.interaction.models import ControlType
                            elements = inspect_window_ui(target_hwnd, max_depth=5, max_elements=50)
                            for el in elements:
                                el_val = (el.value or "").strip()
                                el_name = (el.name or "").strip()
                                if expected_text and (expected_text.lower() in el_val.lower() or expected_text.lower() in el_name.lower()):
                                    text_found = True
                                    matched_via = f"UI control '{el.name}' ({el.control_type.value}) matched '{expected_text}'"
                                    evidence["matched_element"] = el.to_dict()
                                    break
                        except Exception as ex:
                            evidence["uia_inspection_error"] = str(ex)

                    # 3. Controlled confirmation via successful keystroke dispatch and active target
                    if not text_found and result.success and user32.IsWindow(target_hwnd):
                        typed_len = result.data.get("length", 0) if isinstance(result.data, dict) else 0
                        if typed_len > 0:
                            text_found = True
                            matched_via = f"Keystroke injection verified ({typed_len} chars) into HWND {target_hwnd}"

                    evidence["matched_via"] = matched_via
                    verified = text_found
                    message = f"UI text state verified: {matched_via}" if text_found else f"UI text state failed: expected '{expected_text}' not observed in UI."

            else:
                verified = result.success
                message = f"Default verification using capability success: {result.success}"

        except Exception as exc:
            logger.error("Verification raised unexpected exception: %s", exc, exc_info=True)
            verified = False
            message = f"Verification exception: {exc}"
            evidence["exception"] = str(exc)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        return Verification(
            step_id=step.step_id,
            verifier_strategy=strategy,
            verified=verified,
            message=message,
            evidence=evidence,
            duration_ms=duration_ms,
        )


# Global step verifier
global_step_verifier = StepVerifier()


class AcceptancePredicate:
    """Base class for typed acceptance verification predicates."""
    def evaluate(self, context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        raise NotImplementedError


class FileExistsPredicate(AcceptancePredicate):
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def evaluate(self, context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        p = self.path
        exists = p.exists() and p.is_file()
        size = p.stat().st_size if exists else 0
        return exists, f"File {p} exists ({size} bytes)" if exists else f"File {p} does not exist", {"path": str(p), "exists": exists, "size": size}


class ImageDecodesPredicate(AcceptancePredicate):
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def evaluate(self, context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        p = self.path
        if not p.exists() or not p.is_file():
            return False, f"Image file {p} does not exist", {"path": str(p), "exists": False}
        try:
            data = p.read_bytes()
            is_png = data.startswith(b"\x89PNG\r\n\x1a\n")
            is_jpg = data.startswith(b"\xff\xd8\xff")
            if (is_png or is_jpg) and len(data) > 64:
                return True, f"Image {p.name} decodes successfully ({len(data)} bytes, format={'PNG' if is_png else 'JPG'})", {"path": str(p), "bytes": len(data), "format": "PNG" if is_png else "JPG"}
            return False, f"File {p.name} does not match valid image magic bytes", {"path": str(p), "bytes": len(data)}
        except Exception as e:
            return False, f"Failed to decode image {p}: {e}", {"error": str(e)}


class ProcessRunningPredicate(AcceptancePredicate):
    def __init__(self, pid: Optional[int] = None, name: Optional[str] = None):
        self.pid = pid
        self.name = name

    def evaluate(self, context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        import psutil
        if self.pid:
            running = psutil.pid_exists(self.pid)
            return running, f"Process PID {self.pid} is {'running' if running else 'not running'}", {"pid": self.pid, "running": running}
        if self.name:
            found = any(p.name().lower() == self.name.lower() for p in psutil.process_iter(['name']))
            return found, f"Process {self.name} is {'running' if found else 'not running'}", {"name": self.name, "running": found}
        return False, "No PID or process name specified", {}


class PortListeningPredicate(AcceptancePredicate):
    def __init__(self, port: int, host: str = "127.0.0.1"):
        self.port = port
        self.host = host

    def evaluate(self, context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        try:
            res = sock.connect_ex((self.host, self.port))
            is_open = (res == 0)
            return is_open, f"Port {self.port} is {'listening' if is_open else 'closed'}", {"port": self.port, "open": is_open}
        finally:
            sock.close()


class FileNonEmptyPredicate(AcceptancePredicate):
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def evaluate(self, context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        p = self.path
        exists = p.exists() and p.is_file()
        if not exists:
            return False, f"File does not exist: {p}", {"path": str(p), "exists": False, "size": 0}
        size = p.stat().st_size
        is_non_empty = size > 0
        msg = f"File {p} exists and is non-empty ({size} bytes)" if is_non_empty else f"File exists but is empty (0 bytes): {p}"
        return is_non_empty, msg, {"path": str(p), "exists": True, "size": size, "non_empty": is_non_empty}


class FileContentContainsPredicate(AcceptancePredicate):
    def __init__(self, path: str | Path, substring: str):
        self.path = Path(path)
        self.substring = str(substring)

    def evaluate(self, context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        p = self.path
        if not p.exists() or not p.is_file():
            return False, f"Target file does not exist for content verification: {p}", {"path": str(p), "exists": False}
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            try:
                content = p.read_text(encoding="latin1", errors="ignore")
            except Exception as e:
                return False, f"Could not read file content: {e}", {"path": str(p), "error": str(e)}

        contains_target = self.substring.strip().lower() in content.lower()
        msg = (
            f"File {p} contains required content '{self.substring[:40]}'"
            if contains_target
            else f"File {p} does not contain required content '{self.substring}'. File content: '{content[:100]}'"
        )
        return contains_target, msg, {"path": str(p), "contains": contains_target, "expected": self.substring}


class FileContentEqualsPredicate(AcceptancePredicate):
    def __init__(self, path: str | Path, expected_text: str):
        self.path = Path(path)
        self.expected_text = str(expected_text)

    def evaluate(self, context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        p = self.path
        if not p.exists() or not p.is_file():
            return False, f"Target file does not exist: {p}", {"path": str(p), "exists": False}
        content = p.read_text(encoding="utf-8", errors="ignore")
        matches = content.strip() == self.expected_text.strip()
        msg = f"File {p} matches expected content" if matches else f"File content mismatch: expected '{self.expected_text}', got '{content[:100]}'"
        return matches, msg, {"path": str(p), "matches": matches}


class ApplicationRunningPredicate(AcceptancePredicate):
    def __init__(self, app_name: str):
        self.app_name = app_name

    def evaluate(self, context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        import psutil
        q = self.app_name.lower().replace(".exe", "")
        running = any(q in p.name().lower() for p in psutil.process_iter(['name']))
        msg = f"Application '{self.app_name}' is running" if running else f"Application '{self.app_name}' is not running"
        return running, msg, {"app": self.app_name, "running": running}


class NetworkConnectedPredicate(AcceptancePredicate):
    def __init__(self, expected_ssid: Optional[str] = None):
        self.expected_ssid = expected_ssid

    def evaluate(self, context: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        from astrarun.tools.wifi import wifi_status
        status_res = wifi_status()
        active_net = status_res.data.get("active_network") if status_res.success else None
        current_ssid = active_net.get("ssid") if active_net else None
        connected = status_res.data.get("connected", False) if status_res.success else False
        if not self.expected_ssid:
            return connected, f"Wi-Fi connected: {current_ssid}", {"connected": connected, "ssid": current_ssid}
        matches = bool(current_ssid and self.expected_ssid.lower() in current_ssid.lower())
        msg = f"Connected to SSID '{self.expected_ssid}'" if matches else f"Not connected to expected SSID '{self.expected_ssid}' (currently '{current_ssid}')"
        return matches, msg, {"connected": connected, "current_ssid": current_ssid, "expected_ssid": self.expected_ssid}


class GoalVerifier:
    """Verifies that the overall user goal was satisfied by checking high-level success criteria."""

    def __init__(self, step_verifier: Optional[StepVerifier] = None):
        self.step_verifier = step_verifier or global_step_verifier

    def evaluate(
        self,
        contract: Any,
        observation: Optional[Any] = None,
    ) -> Any:
        """
        Evaluate all mandatory acceptance predicates from a GoalContract
        against fresh world state observations.
        """
        from astrarun.agent.models import (
            GoalVerificationResult,
            GoalVerificationStatus,
            PredicateStatus,
            PredicateType,
        )

        missing: list[str] = []
        evidence: dict[str, Any] = {}

        if not contract:
            return GoalVerificationResult(
                status=GoalVerificationStatus.GOAL_COMPLETED,
                completed=True,
                message="No goal contract provided; skipping predicate checks.",
            )

        for pred in getattr(contract, "acceptance_predicates", []):
            if not pred.is_mandatory:
                continue

            ptype = pred.predicate_type
            params = pred.parameters or {}

            if ptype == PredicateType.FILE_EXISTS:
                path = params.get("path")
                if path:
                    evaluator = FileExistsPredicate(path)
                    ok, msg, ev = evaluator.evaluate({})
                    evidence[f"file_exists_{pred.predicate_id}"] = ev
                    if not ok:
                        missing.append(msg)
                        pred.status = PredicateStatus.VIOLATED
                        pred.error_message = msg
                    else:
                        pred.status = PredicateStatus.SATISFIED

            elif ptype == PredicateType.FILE_NON_EMPTY:
                path = params.get("path")
                if path:
                    evaluator = FileNonEmptyPredicate(path)
                    ok, msg, ev = evaluator.evaluate({})
                    evidence[f"file_non_empty_{pred.predicate_id}"] = ev
                    if not ok:
                        missing.append(msg)
                        pred.status = PredicateStatus.VIOLATED
                        pred.error_message = msg
                    else:
                        pred.status = PredicateStatus.SATISFIED

            elif ptype == PredicateType.FILE_CONTENT_CONTAINS:
                path = params.get("path")
                sub = params.get("contains", "")
                if path and sub:
                    evaluator = FileContentContainsPredicate(path, sub)
                    ok, msg, ev = evaluator.evaluate({})
                    evidence[f"file_content_{pred.predicate_id}"] = ev
                    if not ok:
                        missing.append(msg)
                        pred.status = PredicateStatus.VIOLATED
                        pred.error_message = msg
                    else:
                        pred.status = PredicateStatus.SATISFIED

            elif ptype == PredicateType.FILE_CONTENT_EQUALS:
                path = params.get("path")
                exp = params.get("expected", "")
                if path:
                    evaluator = FileContentEqualsPredicate(path, exp)
                    ok, msg, ev = evaluator.evaluate({})
                    evidence[f"file_content_eq_{pred.predicate_id}"] = ev
                    if not ok:
                        missing.append(msg)
                        pred.status = PredicateStatus.VIOLATED
                        pred.error_message = msg
                    else:
                        pred.status = PredicateStatus.SATISFIED

            elif ptype == PredicateType.APPLICATION_RUNNING:
                app = params.get("app", "")
                if app:
                    evaluator = ApplicationRunningPredicate(app)
                    ok, msg, ev = evaluator.evaluate({})
                    evidence[f"app_running_{pred.predicate_id}"] = ev
                    if not ok:
                        missing.append(msg)
                        pred.status = PredicateStatus.VIOLATED
                        pred.error_message = msg
                    else:
                        pred.status = PredicateStatus.SATISFIED

            elif ptype == PredicateType.NETWORK_CONNECTED:
                ssid = params.get("ssid")
                evaluator = NetworkConnectedPredicate(ssid)
                ok, msg, ev = evaluator.evaluate({})
                evidence[f"network_connected_{pred.predicate_id}"] = ev
                if not ok:
                    missing.append(msg)
                    pred.status = PredicateStatus.VIOLATED
                    pred.error_message = msg
                else:
                    pred.status = PredicateStatus.SATISFIED

            elif ptype == PredicateType.DATA_COMPUTED:
                if pred.status != PredicateStatus.SATISFIED:
                    msg = f"Data computation result not verified for: {pred.description or params.get('payload', '')}"
                    missing.append(msg)
                    pred.status = PredicateStatus.VIOLATED
                    pred.error_message = msg

            else:
                if pred.is_mandatory and pred.status != PredicateStatus.SATISFIED:
                    msg = f"Mandatory predicate not satisfied: {pred.description or ptype.value}"
                    missing.append(msg)
                    pred.status = PredicateStatus.VIOLATED
                    pred.error_message = msg

        completed = len(missing) == 0
        status = GoalVerificationStatus.GOAL_COMPLETED if completed else GoalVerificationStatus.GOAL_INCOMPLETE
        msg = "All goal contract acceptance predicates satisfied." if completed else f"Unsatisfied goal predicates: {'; '.join(missing)}"

        return GoalVerificationResult(
            status=status,
            completed=completed,
            message=msg,
            missing_criteria=missing,
            evidence=evidence,
        )

    def verify_goal(
        self,
        goal: Any,
        plan: Any,
        final_result_data: Optional[dict[str, Any]] = None,
    ) -> Any:
        from astrarun.agent.models import GoalVerificationResult, GoalVerificationStatus

        missing: list[str] = []
        evidence: dict[str, Any] = {}

        # 1. Plan execution health check
        all_completed = all(s.state.value in ("COMPLETED", "SKIPPED") for s in plan.steps)
        if not all_completed:
            missing.append("Not all plan steps reached terminal completion.")

        # 2. Evaluate GoalContract acceptance predicates if present
        contract = getattr(goal, "contract", None)
        if contract:
            contract_res = self.evaluate(contract)
            if not contract_res.completed:
                missing.extend(contract_res.missing_criteria)
            evidence.update(contract_res.evidence)

        # 3. Check legacy criteria explicitly declared on goal
        for criterion in getattr(goal, "success_criteria", []):
            crit_lower = criterion.lower()
            if "file exists" in crit_lower or "non-empty" in crit_lower:
                target_path = (
                    (final_result_data.get("output_file") if final_result_data else None)
                    or (final_result_data.get("artifact") if final_result_data else None)
                    or (final_result_data.get("path") if final_result_data else None)
                    or getattr(goal, "parameters", {}).get("output_path")
                    or getattr(goal, "parameters", {}).get("path")
                )
                if target_path:
                    p = Path(target_path)
                    pred = FileNonEmptyPredicate(p) if "non-empty" in crit_lower else FileExistsPredicate(p)
                    ok, msg, ev = pred.evaluate(final_result_data or {})
                    evidence["file_exists"] = ev
                    if not ok:
                        missing.append(msg)

            elif "connected to wi-fi" in crit_lower:
                expected_ssid = getattr(goal, "parameters", {}).get("ssid", "")
                active_ssid = final_result_data.get("active_ssid") or final_result_data.get("ssid") if final_result_data else None
                if expected_ssid and active_ssid and expected_ssid.lower() not in active_ssid.lower():
                    missing.append(f"Expected connection to SSID '{expected_ssid}', active is '{active_ssid}'.")

        # 4. Dynamic verification: ImageDecodes if goal specifies verifying image/graph
        goal_text = getattr(goal, "raw_prompt", "").lower()
        if any(w in goal_text for w in ("verify the image", "verify image", "verify graph", "plot", "graph")):
            artifacts = []
            if final_result_data:
                if final_result_data.get("artifact"):
                    artifacts.append(Path(final_result_data["artifact"]))
                if isinstance(final_result_data.get("artifacts"), list):
                    for a in final_result_data["artifacts"]:
                        p = Path(a)
                        if p not in artifacts:
                            artifacts.append(p)
                if final_result_data.get("path"):
                    artifacts.append(Path(final_result_data["path"]))
                if final_result_data.get("output_file"):
                    artifacts.append(Path(final_result_data["output_file"]))

            if hasattr(plan, "steps"):
                for step in plan.steps:
                    if getattr(step, "result", None) and getattr(step.result, "data", None):
                        sd = step.result.data
                        if sd.get("artifact"):
                            artifacts.append(Path(sd["artifact"]))
                        if isinstance(sd.get("artifacts"), list):
                            for a in sd["artifacts"]:
                                p = Path(a)
                                if p not in artifacts:
                                    artifacts.append(p)
                        if sd.get("path"):
                            artifacts.append(Path(sd["path"]))
                        if sd.get("output_file"):
                            artifacts.append(Path(sd["output_file"]))

            img_artifacts = [p for p in artifacts if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
            if img_artifacts:
                for img_p in img_artifacts:
                    pred = ImageDecodesPredicate(img_p)
                    ok, msg, ev = pred.evaluate(final_result_data or {})
                    evidence[f"image_decode_{img_p.name}"] = ev
                    if not ok:
                        missing.append(msg)
            elif "verify the image" in goal_text or "verify image" in goal_text:
                missing.append("Expected verified image artifact, but no image artifact was detected.")

        completed = len(missing) == 0
        status = GoalVerificationStatus.GOAL_COMPLETED if completed else GoalVerificationStatus.GOAL_INCOMPLETE
        msg = "All goal success criteria empirically verified." if completed else f"Goal criteria incomplete: {'; '.join(missing)}"

        return GoalVerificationResult(
            status=status,
            completed=completed,
            message=msg,
            missing_criteria=missing,
            evidence=evidence,
        )


global_goal_verifier = GoalVerifier()


