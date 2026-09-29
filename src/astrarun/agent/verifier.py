"""Step verification engine for AstraRun v0.11 agent runtime."""

from __future__ import annotations

import ctypes
import os
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
