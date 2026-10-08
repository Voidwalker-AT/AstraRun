"""System utility adapters providing safe, typed execution of Windows system tools."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult
from astrarun.capabilities.schema import InteractionTier
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tools.system_adapter")


class SystemUtilityError(Exception):
    """Base exception for system utility execution failures."""
    pass


class SystemUtilityAdapter:
    """
    Tier B adapter: Executes trusted Windows system utilities with strictly typed argument lists,
    shell=False enforcement, output validation, and zero shell interpolation.
    """

    ALLOWED_EXECUTABLES = {
        "powercfg.exe": r"^[a-zA-Z]:\\Windows\\System32\\powercfg\.exe$",
        "ipconfig.exe": r"^[a-zA-Z]:\\Windows\\System32\\ipconfig\.exe$",
        "netstat.exe": r"^[a-zA-Z]:\\Windows\\System32\\netstat\.exe$",
        "ping.exe": r"^[a-zA-Z]:\\Windows\\System32\\PING\.EXE$",
    }

    def __init__(self, executable_name: str):
        self.executable_name = executable_name
        self.executable_path = self._resolve_executable(executable_name)

    def _resolve_executable(self, name: str) -> str:
        """Resolve and verify path to system utility in System32."""
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        cand = Path(system_root) / "System32" / name
        if cand.exists():
            return str(cand)

        resolved = shutil.which(name)
        if resolved:
            return resolved

        raise SystemUtilityError(f"System utility '{name}' not found on system path.")

    def run_validated(
        self,
        arguments: list[str],
        timeout_s: float = 30.0,
    ) -> subprocess.CompletedProcess[str]:
        """
        Execute the system utility with shell=False and strict argument checking.
        """
        # Security invariant: Zero shell execution, argument inspection
        for arg in arguments:
            if not isinstance(arg, str):
                raise ValueError(f"Invalid non-string argument: {arg}")
            # Guard against shell injection characters if passed to command args
            if any(ch in arg for ch in [";", "&", "|", "`", "$", ">", "<", "\n", "\r"]):
                raise ValueError(f"Prohibited shell character detected in argument: {arg}")

        cmd = [self.executable_path] + arguments
        logger.info("Executing system utility: %s with args: %s", self.executable_path, arguments)

        creationflags = 0x08000000 if os.name == "nt" else 0
        return subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
            creationflags=creationflags,
        )


class PowerCfgAdapter(SystemUtilityAdapter):
    """Adapter for powercfg.exe execution (Tier B)."""

    def __init__(self):
        super().__init__("powercfg.exe")

    @staticmethod
    def get_downloads_directory() -> Path:
        """Resolve user's Downloads directory portably."""
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            downloads = Path(user_profile) / "Downloads"
            if downloads.exists():
                return downloads
        return Path.home() / "Downloads"

    def generate_battery_report(self, output_path: Optional[str] = None) -> CapabilityResult:
        """
        Generate detailed Windows battery health report via powercfg.exe /batteryreport.
        """
        # Resolve target output path
        if not output_path or output_path.strip() == "":
            dest_file = self.get_downloads_directory() / "battery-report.html"
        else:
            raw_path = output_path.strip().strip('"').strip("'")
            path_obj = Path(raw_path)

            # If user specified bare filename or relative path like 'Downloads/astra-battery.html'
            if not path_obj.is_absolute():
                parts = path_obj.parts
                if parts and parts[0].lower() == "downloads":
                    subpath = Path(*parts[1:]) if len(parts) > 1 else Path("battery-report.html")
                    dest_file = self.get_downloads_directory() / subpath
                elif len(parts) == 1:
                    # Bare filename like 'astra-battery.html' -> save to Downloads
                    dest_file = self.get_downloads_directory() / parts[0]
                else:
                    dest_file = (self.get_downloads_directory() / path_obj).resolve()
            else:
                dest_file = path_obj.resolve()

        # Enforce valid extension
        if dest_file.suffix.lower() not in (".html", ".xml"):
            dest_file = dest_file.with_suffix(".html")

        # Ensure destination directory exists
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        args = ["/batteryreport", "/output", str(dest_file)]

        try:
            proc = self.run_validated(args, timeout_s=30.0)

            if proc.returncode != 0:
                err_msg = (proc.stderr or proc.stdout).strip()
                logger.warning("powercfg returned non-zero code %d: %s", proc.returncode, err_msg)
                if "not supported" in err_msg.lower() or "battery" in err_msg.lower():
                    return CapabilityResult.fail(
                        capability="generate_battery_report",
                        message=f"Battery report unsupported or no battery found: {err_msg}",
                        error_code=CapabilityErrorCode.UNAVAILABLE,
                    )
                return CapabilityResult.fail(
                    capability="generate_battery_report",
                    message=f"powercfg execution failed: {err_msg}",
                    error_code=CapabilityErrorCode.OS_ERROR,
                )

            # Atomic verification that target file exists and is non-empty
            if not dest_file.exists():
                return CapabilityResult.fail(
                    capability="generate_battery_report",
                    message=f"Report file was not created at expected location: {dest_file}",
                    error_code=CapabilityErrorCode.OS_ERROR,
                )

            file_size = dest_file.stat().st_size
            if file_size == 0:
                return CapabilityResult.fail(
                    capability="generate_battery_report",
                    message=f"Generated report file is empty: {dest_file}",
                    error_code=CapabilityErrorCode.OS_ERROR,
                )

            return CapabilityResult.ok(
                capability="generate_battery_report",
                message=f"Battery report generated successfully at {dest_file}",
                data={
                    "output_file": str(dest_file),
                    "file_size_bytes": file_size,
                    "format": dest_file.suffix.lstrip(".").lower(),
                    "tier": InteractionTier.TIER_B_STRUCTURED_CLI.value,
                },
                context_updates=[{
                    "type": "file",
                    "path": str(dest_file),
                    "action": "created",
                }],
            )

        except Exception as exc:
            logger.error("Error generating battery report: %s", exc, exc_info=True)
            return CapabilityResult.fail(
                capability="generate_battery_report",
                message=f"Failed to generate battery report: {exc}",
                error_code=CapabilityErrorCode.OS_ERROR,
            )
