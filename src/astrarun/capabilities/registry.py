"""Central Capability Registry maintaining typed OS capabilities and safe dispatch."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from astrarun.capabilities.models import (
    Capability,
    CapabilityCategory,
    CapabilityErrorCode,
    CapabilityHealth,
    CapabilityPermission,
    CapabilityResult,
)
from astrarun.capabilities.store import ObservationStore
from astrarun.core.logging import get_logger
from astrarun.core.models import ToolRisk

logger = get_logger("astrarun.capabilities.registry")


class CapabilityRegistry:
    """
    Central registry for typed, policy-controlled OS capabilities.
    Evolves ToolRegistry into a comprehensive, multi-category capability abstraction.
    """

    def __init__(self, observation_store: Optional[ObservationStore] = None) -> None:
        self._capabilities: dict[str, Capability] = {}
        self.observation_store = observation_store or ObservationStore()
        self._register_default_capabilities()

    def register(self, capability: Capability) -> None:
        """Register a new workstation capability."""
        self._capabilities[capability.id] = capability
        logger.debug(
            "Capability registered: %s [category=%s, risk=%s, permission=%s]",
            capability.id,
            capability.category.value,
            capability.risk.value,
            capability.permission.value,
        )

    def get(self, capability_id: str) -> Optional[Capability]:
        """Retrieve capability metadata by ID."""
        return self._capabilities.get(capability_id)

    def list_capabilities(self, category: Optional[CapabilityCategory] = None) -> list[Capability]:
        """Return registered capabilities, optionally filtered by category."""
        if category is not None:
            return [c for c in self._capabilities.values() if c.category == category]
        return list(self._capabilities.values())

    def execute(self, capability_id: str, arguments: Optional[dict[str, Any]] = None) -> CapabilityResult:
        """
        Safely execute a capability by ID with typed arguments.
        Enforces permissions, catches exceptions, records observations, and emits a CapabilityResult.
        """
        t0 = time.perf_counter()
        args = arguments or {}
        cap = self.get(capability_id)

        if not cap:
            logger.warning("Attempted invocation of unregistered capability: %s", capability_id)
            return CapabilityResult.fail(
                capability=capability_id,
                message=f"Capability '{capability_id}' is not registered.",
                error_code=CapabilityErrorCode.NOT_FOUND,
            )

        # Policy & Permission Invariant: Blocked capabilities cannot run
        if cap.permission == CapabilityPermission.BLOCK or cap.risk == ToolRisk.BLOCKED:
            logger.error("Execution blocked for prohibited capability: %s", capability_id)
            return CapabilityResult.fail(
                capability=capability_id,
                message=f"Execution of '{capability_id}' is blocked by policy.",
                error_code=CapabilityErrorCode.BLOCKED,
            )

        logger.info("Executing capability '%s' with args %s", capability_id, args)

        try:
            raw_res = cap.handler(**args)

            # Standardize return type to CapabilityResult
            if isinstance(raw_res, CapabilityResult):
                result = raw_res
            elif isinstance(raw_res, bool):
                if raw_res:
                    result = CapabilityResult.ok(capability_id, "Executed successfully.")
                else:
                    result = CapabilityResult.fail(capability_id, "Execution returned failure.")
            elif isinstance(raw_res, dict):
                msg = raw_res.get("message", "Executed successfully.")
                result = CapabilityResult.ok(capability_id, msg, data=raw_res)
            else:
                result = CapabilityResult.ok(capability_id, "Executed successfully.", data={"result": raw_res})

            result.latency_ms = (time.perf_counter() - t0) * 1000

            # Record structured fact observation into the observation store
            if result.success and cap.read_only:
                self.observation_store.record(
                    obs_type=f"{cap.category.value.lower()}_fact",
                    source=capability_id,
                    data=result.data,
                )

            return result

        except TypeError as err:
            logger.error("Argument mismatch executing capability '%s': %s", capability_id, err)
            return CapabilityResult.fail(
                capability=capability_id,
                message=f"Invalid arguments for '{capability_id}': {err}",
                error_code=CapabilityErrorCode.INVALID_ARGUMENT,
            )
        except Exception as err:
            logger.error("Exception executing capability '%s': %s", capability_id, err, exc_info=True)
            return CapabilityResult.fail(
                capability=capability_id,
                message=f"Error executing '{capability_id}': {err}",
                error_code=CapabilityErrorCode.OS_ERROR,
            )

    def _register_default_capabilities(self) -> None:
        """Register the comprehensive suite of v0.7 workstation capabilities."""
        from astrarun.applications.service import (
            close_application,
            find_application,
            focus_application,
            is_application_running,
            list_running_applications,
            open_application,
        )
        from astrarun.files.service import (
            file_metadata,
            find_file,
            find_latest_file,
            list_recent_files,
            open_file,
            reveal_file,
        )
        from astrarun.network.service import (
            find_process_on_port,
            inspect_port,
            list_listening_ports,
            list_network_connections,
        )
        from astrarun.processes.service import (
            find_process,
            inspect_process,
            list_processes,
            process_children,
            process_parent,
            process_ports,
            process_resource_usage,
            terminate_process,
        )
        from astrarun.projects.service import (
            project_git_status,
            project_ports,
            project_running_processes,
            project_status,
        )
        from astrarun.system.service import (
            audio_status,
            battery_status,
            cpu_status,
            disk_status,
            gpu_status,
            lock_workstation,
            memory_status,
            system_summary,
        )
        from astrarun.tools.folders import open_folder
        from astrarun.tools.projects import open_project_folder, open_project_in_vscode
        from astrarun.tools.web import open_url
        from astrarun.windows.discovery import (
            find_window,
            foreground_window,
            list_windows,
            windows_for_application,
        )

        # ---------------------------------------------------------
        # APPLICATION CAPABILITIES
        # ---------------------------------------------------------
        self.register(Capability(
            id="list_running_applications",
            category=CapabilityCategory.APPLICATION,
            description="List user-facing desktop applications based on visible top-level windows",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=list_running_applications,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="is_application_running",
            category=CapabilityCategory.APPLICATION,
            description="Check if an application is currently running",
            args_schema={"app": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=is_application_running,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="find_application",
            category=CapabilityCategory.APPLICATION,
            description="Find installed application metadata from Start Menu and system paths",
            args_schema={"name": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=find_application,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="open_application",
            category=CapabilityCategory.APPLICATION,
            description="Launch a verified local application executable",
            args_schema={"app": str, "path": Optional[str]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=open_application,
            permission=CapabilityPermission.AUTO,
            context_effects=["application_opened"],
        ))
        self.register(Capability(
            id="focus_application",
            category=CapabilityCategory.APPLICATION,
            description="Focus an open application window, disambiguating multiple windows",
            args_schema={"app": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=focus_application,
            permission=CapabilityPermission.AUTO,
            context_effects=["application_focused"],
        ))
        self.register(Capability(
            id="close_application",
            category=CapabilityCategory.APPLICATION,
            description="Gracefully close an application window via WM_CLOSE (no force-kill)",
            args_schema={"app": str},
            risk=ToolRisk.MEDIUM,
            read_only=False,
            requires_confirmation=False,
            handler=close_application,
            permission=CapabilityPermission.AUTO,
            context_effects=["application_closed"],
        ))

        # ---------------------------------------------------------
        # FILE CAPABILITIES
        # ---------------------------------------------------------
        self.register(Capability(
            id="find_file",
            category=CapabilityCategory.FILE,
            description="Find files by name, extension, or location across configured roots",
            args_schema={"query": str, "extension": Optional[str], "location": Optional[str], "file_type": Optional[str]},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=find_file,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="find_latest_file",
            category=CapabilityCategory.FILE,
            description="Find the single most recently modified file (e.g. latest screenshot or document)",
            args_schema={"extension": Optional[str], "location": Optional[str], "file_type": Optional[str]},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=find_latest_file,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="list_recent_files",
            category=CapabilityCategory.FILE,
            description="List recently modified files across user roots",
            args_schema={"limit": int, "extension": Optional[str], "location": Optional[str], "file_type": Optional[str]},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=list_recent_files,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="open_file",
            category=CapabilityCategory.FILE,
            description="Open a non-executable user file with its default program",
            args_schema={"path": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=open_file,
            permission=CapabilityPermission.AUTO,
            context_effects=["file_opened"],
        ))
        self.register(Capability(
            id="reveal_file",
            category=CapabilityCategory.FILE,
            description="Reveal a file or folder in File Explorer",
            args_schema={"path": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=reveal_file,
            permission=CapabilityPermission.AUTO,
            context_effects=["file_revealed"],
        ))
        self.register(Capability(
            id="file_metadata",
            category=CapabilityCategory.FILE,
            description="Query size, timestamps, and path metadata for a file",
            args_schema={"path": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=file_metadata,
            permission=CapabilityPermission.AUTO,
        ))

        # ---------------------------------------------------------
        # PROCESS CAPABILITIES
        # ---------------------------------------------------------
        self.register(Capability(
            id="list_processes",
            category=CapabilityCategory.PROCESS,
            description="List running processes sorted deterministically by memory, CPU, or recency",
            args_schema={"limit": int, "sort_by": Optional[str], "filter_name": Optional[str]},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=list_processes,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="find_process",
            category=CapabilityCategory.PROCESS,
            description="Find running process by name or PID",
            args_schema={"query": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=find_process,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="inspect_process",
            category=CapabilityCategory.PROCESS,
            description="Query detailed runtime metrics, relationships, and listening ports for a PID",
            args_schema={"pid": int},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=inspect_process,
            permission=CapabilityPermission.AUTO,
            context_effects=["process_inspected"],
        ))
        self.register(Capability(
            id="process_resource_usage",
            category=CapabilityCategory.PROCESS,
            description="Return lightweight CPU, RAM, and thread metrics for a PID",
            args_schema={"pid": int},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=process_resource_usage,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="process_ports",
            category=CapabilityCategory.PROCESS,
            description="Query listening ports owned by a specific process",
            args_schema={"pid": int},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=process_ports,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="process_children",
            category=CapabilityCategory.PROCESS,
            description="List child processes of a process",
            args_schema={"pid": int},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=process_children,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="process_parent",
            category=CapabilityCategory.PROCESS,
            description="Query parent process information for a process",
            args_schema={"pid": int},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=process_parent,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="terminate_process",
            category=CapabilityCategory.PROCESS,
            description="Terminate a verified non-protected process with TOCTOU validation",
            args_schema={"pid": int, "expected_create_time": float, "expected_name": str},
            risk=ToolRisk.HIGH,
            read_only=False,
            requires_confirmation=True,
            handler=terminate_process,
            permission=CapabilityPermission.CONFIRM,
            context_effects=["process_terminated"],
        ))

        # ---------------------------------------------------------
        # NETWORK CAPABILITIES
        # ---------------------------------------------------------
        self.register(Capability(
            id="list_listening_ports",
            category=CapabilityCategory.NETWORK,
            description="List active TCP listening ports and owning processes",
            args_schema={"limit": int},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=list_listening_ports,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="inspect_port",
            category=CapabilityCategory.NETWORK,
            description="Read-only query of process listening on a TCP network port (allows privileged ports)",
            args_schema={"port": int},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=inspect_port,
            permission=CapabilityPermission.AUTO,
            context_effects=["port_inspected"],
        ))
        self.register(Capability(
            id="find_process_on_port",
            category=CapabilityCategory.NETWORK,
            description="Find process listening on a specific network port",
            args_schema={"port": int},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=find_process_on_port,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="list_network_connections",
            category=CapabilityCategory.NETWORK,
            description="List active internet socket connections across the machine",
            args_schema={"limit": int},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=list_network_connections,
            permission=CapabilityPermission.AUTO,
        ))

        # ---------------------------------------------------------
        # SYSTEM CAPABILITIES
        # ---------------------------------------------------------
        self.register(Capability(
            id="system_summary",
            category=CapabilityCategory.SYSTEM,
            description="Consolidated CPU, RAM, disk, GPU, battery, and uptime status",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=system_summary,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="cpu_status",
            category=CapabilityCategory.SYSTEM,
            description="Query CPU utilization and core frequency",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=cpu_status,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="memory_status",
            category=CapabilityCategory.SYSTEM,
            description="Query RAM usage, availability, and percent",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=memory_status,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="disk_status",
            category=CapabilityCategory.SYSTEM,
            description="Query storage free space and utilization",
            args_schema={"drive": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=disk_status,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="battery_status",
            category=CapabilityCategory.SYSTEM,
            description="Query battery level and charging state",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=battery_status,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="gpu_status",
            category=CapabilityCategory.SYSTEM,
            description="Query NVIDIA GPU utilization, VRAM, and temperature with graceful fallback",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=gpu_status,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="audio_status",
            category=CapabilityCategory.AUDIO,
            description="Query audio master volume and mute state",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=audio_status,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="lock_workstation",
            category=CapabilityCategory.SYSTEM,
            description="Lock the workstation session using Windows User32 API",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=lock_workstation,
            permission=CapabilityPermission.AUTO,
        ))

        # ---------------------------------------------------------
        # PROJECT CAPABILITIES
        # ---------------------------------------------------------
        self.register(Capability(
            id="project_status",
            category=CapabilityCategory.PROJECT,
            description="Consolidated status of a workspace project including Git, processes, and ports",
            args_schema={"project_id": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=project_status,
            permission=CapabilityPermission.AUTO,
            context_effects=["project_status_inspected"],
        ))
        self.register(Capability(
            id="project_git_status",
            category=CapabilityCategory.PROJECT,
            description="Query Git branch and modified files using structured argument lists",
            args_schema={"project_id": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=project_git_status,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="project_running_processes",
            category=CapabilityCategory.PROJECT,
            description="Query running processes associated with a project directory",
            args_schema={"project_id": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=project_running_processes,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="project_ports",
            category=CapabilityCategory.PROJECT,
            description="Query listening ports associated with running project processes",
            args_schema={"project_id": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=project_ports,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="open_project_folder",
            category=CapabilityCategory.PROJECT,
            description="Open a verified project directory in File Explorer",
            args_schema={"project_id": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=open_project_folder,
            permission=CapabilityPermission.AUTO,
            context_effects=["project_opened"],
        ))
        self.register(Capability(
            id="open_project_in_vscode",
            category=CapabilityCategory.PROJECT,
            description="Open a verified project directory in Visual Studio Code",
            args_schema={"project_id": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=open_project_in_vscode,
            permission=CapabilityPermission.AUTO,
            context_effects=["project_opened"],
        ))
        self.register(Capability(
            id="open_project",
            category=CapabilityCategory.PROJECT,
            description="Open a verified project workspace (default: VS Code or Folder)",
            args_schema={"project_id": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=open_project_in_vscode,
            permission=CapabilityPermission.AUTO,
            context_effects=["project_opened"],
        ))

        # ---------------------------------------------------------
        # WINDOW CAPABILITIES (Discovery Foundation)
        # ---------------------------------------------------------
        self.register(Capability(
            id="list_windows",
            category=CapabilityCategory.WINDOW,
            description="Enumerate visible top-level desktop windows",
            args_schema={"limit": int},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=list_windows,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="foreground_window",
            category=CapabilityCategory.WINDOW,
            description="Retrieve active focused foreground window information",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=foreground_window,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="find_window",
            category=CapabilityCategory.WINDOW,
            description="Find windows by title or application name",
            args_schema={"query": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=find_window,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="windows_for_application",
            category=CapabilityCategory.WINDOW,
            description="Find open windows for an application",
            args_schema={"app": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=windows_for_application,
            permission=CapabilityPermission.AUTO,
        ))

        # ---------------------------------------------------------
        # WEB & FOLDER PRIMITIVES
        # ---------------------------------------------------------
        self.register(Capability(
            id="open_folder",
            category=CapabilityCategory.FILE,
            description="Open a verified directory in File Explorer",
            args_schema={"folder": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=open_folder,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="open_url",
            category=CapabilityCategory.NETWORK,
            description="Open a validated HTTP/HTTPS URL in default browser",
            args_schema={"url": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=open_url,
            permission=CapabilityPermission.AUTO,
        ))

        # ---------------------------------------------------------
        # HARD POLICY BLOCKS (Never permitted to execute)
        # ---------------------------------------------------------
        self.register(Capability(
            id="shutdown_workstation",
            category=CapabilityCategory.SYSTEM,
            description="System shutdown (Prohibited by hard policy in v0.7)",
            args_schema={},
            risk=ToolRisk.BLOCKED,
            read_only=False,
            permission=CapabilityPermission.BLOCK,
            health=CapabilityHealth.UNAVAILABLE,
            health_reason="Prohibited by hard policy",
        ))
        self.register(Capability(
            id="restart_workstation",
            category=CapabilityCategory.SYSTEM,
            description="System restart (Prohibited by hard policy in v0.7)",
            args_schema={},
            risk=ToolRisk.BLOCKED,
            read_only=False,
            permission=CapabilityPermission.BLOCK,
            health=CapabilityHealth.UNAVAILABLE,
            health_reason="Prohibited by hard policy",
        ))
