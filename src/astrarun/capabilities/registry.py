"""Central Capability Registry maintaining typed OS capabilities and safe dispatch."""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Union

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

    def get_capability_schema(self, capability_id: str) -> Optional[Any]:
        """Export machine-readable CapabilitySchema for a registered capability."""
        cap = self.get(capability_id)
        if not cap:
            return None

        from astrarun.capabilities.schema import (
            CapabilityFamily,
            CapabilitySchema,
            InteractionTier,
            ParameterSchema,
            PrivilegeLevel,
            SideEffect,
            VerifierStrategy,
        )

        # Infer family
        family_map = {
            CapabilityCategory.SYSTEM: CapabilityFamily.SYSTEM_DIAGNOSTICS,
            CapabilityCategory.NETWORK: CapabilityFamily.NETWORK_MANAGEMENT,
            CapabilityCategory.WINDOW: CapabilityFamily.WINDOW_CONTROL,
            CapabilityCategory.APPLICATION: CapabilityFamily.APPLICATION_LIFECYCLE,
            CapabilityCategory.INTERACTION: CapabilityFamily.UI_INTERACTION,
            CapabilityCategory.FILE: CapabilityFamily.FILE_MANAGEMENT,
            CapabilityCategory.PROJECT: CapabilityFamily.DEVELOPER_TOOLS,
            CapabilityCategory.WORKFLOW: CapabilityFamily.WORKFLOW_AUTOMATION,
        }
        family = family_map.get(cap.category, CapabilityFamily.SYSTEM_DIAGNOSTICS)

        # Infer tier
        if cap.id == "generate_battery_report":
            tier = InteractionTier.TIER_B_STRUCTURED_CLI
        elif cap.category == CapabilityCategory.INTERACTION:
            tier = InteractionTier.TIER_C_UI_AUTOMATION
        else:
            tier = InteractionTier.TIER_A_NATIVE

        # Infer verifier strategy
        if "file" in cap.id or "report" in cap.id:
            verifier_strat = VerifierStrategy.FILE_EXISTS if cap.read_only else VerifierStrategy.FILE_NON_EMPTY
        elif "window" in cap.id or "application" in cap.id:
            verifier_strat = VerifierStrategy.WINDOW_READY
        elif "wifi" in cap.id and "connect" in cap.id:
            verifier_strat = VerifierStrategy.NETWORK_SSID
        else:
            verifier_strat = VerifierStrategy.RETURN_CODE_ONLY

        params = []
        for name, p_type in cap.args_schema.items():
            type_str = getattr(p_type, "__name__", str(p_type))
            is_req = not ("Optional" in str(p_type) or "None" in str(p_type))
            params.append(ParameterSchema(name=name, type_name=type_str, description=f"Parameter {name}", required=is_req))

        effects = [SideEffect.READ_ONLY] if cap.read_only else [SideEffect.SYSTEM_STATE]
        if "file" in cap.id or "report" in cap.id:
            effects = [SideEffect.CREATES_FILE] if not cap.read_only else [SideEffect.READ_ONLY]

        return CapabilitySchema(
            id=cap.id,
            family=family,
            category=cap.category,
            interaction_tier=tier,
            description=cap.description,
            parameters=params,
            side_effects=effects,
            privilege_level=PrivilegeLevel.STANDARD_USER,
            risk=cap.risk,
            reversibility=cap.reversible,
            verifier_strategy=verifier_strat,
        )

    def get_capability_schemas(self) -> list[Any]:
        """Export machine-readable CapabilitySchemas for all registered capabilities."""
        schemas = []
        for cap_id in self._capabilities:
            schema = self.get_capability_schema(cap_id)
            if schema:
                schemas.append(schema)
        return schemas

    def execute(
        self,
        capability_id: str,
        arguments: Optional[dict[str, Any]] = None,
        task_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> CapabilityResult:
        """
        Safely execute a capability by ID with typed arguments.
        Enforces permissions, catches exceptions, records observations, and emits a CapabilityResult.
        Optionally accepts task_id, conversation_id, and correlation_id for tracing.
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

        if task_id:
            logger.info(
                "Executing capability '%s' [task_id=%s, conv_id=%s, corr_id=%s] with args %s",
                capability_id,
                task_id,
                conversation_id,
                correlation_id,
                args,
            )
        else:
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
        from astrarun.windows import (
            arrange_desktop,
            close_window,
            find_window,
            focus_window,
            foreground_window,
            list_windows,
            maximize_window,
            minimize_window,
            move_window,
            move_window_to_monitor,
            resize_window,
            restore_window,
            snap_window,
            snap_window_left,
            snap_window_right,
            undo_last_window_move,
            wait_for_window,
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
        # WINDOW CAPABILITIES (Intelligence & Desktop Control)
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
        self.register(Capability(
            id="wait_for_window",
            category=CapabilityCategory.WINDOW,
            description="Wait for an application window to become visible and ready",
            args_schema={"app": str, "timeout": float, "hwnd": Optional[int]},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=wait_for_window,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_ready"],
        ))
        self.register(Capability(
            id="focus_window",
            category=CapabilityCategory.WINDOW,
            description="Bring a target window to foreground focus",
            args_schema={"hwnd": int, "pid": Optional[int]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=focus_window,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_focused"],
        ))
        self.register(Capability(
            id="minimize_window",
            category=CapabilityCategory.WINDOW,
            description="Minimize an open desktop window",
            args_schema={"hwnd": int, "pid": Optional[int]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=minimize_window,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_minimized"],
        ))
        self.register(Capability(
            id="maximize_window",
            category=CapabilityCategory.WINDOW,
            description="Maximize an open desktop window to fill monitor work area",
            args_schema={"hwnd": int, "pid": Optional[int]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=maximize_window,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_maximized"],
        ))
        self.register(Capability(
            id="restore_window",
            category=CapabilityCategory.WINDOW,
            description="Restore a minimized or maximized window to normal size",
            args_schema={"hwnd": int, "pid": Optional[int]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=restore_window,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_restored"],
        ))
        self.register(Capability(
            id="move_window",
            category=CapabilityCategory.WINDOW,
            description="Move and optionally resize a desktop window",
            args_schema={"hwnd": int, "x": int, "y": int, "width": Optional[int], "height": Optional[int], "pid": Optional[int]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=move_window,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_moved"],
        ))
        self.register(Capability(
            id="resize_window",
            category=CapabilityCategory.WINDOW,
            description="Resize an open desktop window preserving top-left position",
            args_schema={"hwnd": int, "width": int, "height": int, "pid": Optional[int]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=resize_window,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_resized"],
        ))
        self.register(Capability(
            id="move_window_to_monitor",
            category=CapabilityCategory.WINDOW,
            description="Move a desktop window to a target display monitor",
            args_schema={"hwnd": int, "monitor_spec": Union[str, int], "pid": Optional[int]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=move_window_to_monitor,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_moved_monitor"],
        ))
        self.register(Capability(
            id="snap_window_left",
            category=CapabilityCategory.WINDOW,
            description="Snap a window to the left half of the monitor",
            args_schema={"hwnd": int, "monitor_spec": Optional[Union[str, int]], "pid": Optional[int]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=snap_window_left,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_snapped_left"],
        ))
        self.register(Capability(
            id="snap_window_right",
            category=CapabilityCategory.WINDOW,
            description="Snap a window to the right half of the monitor",
            args_schema={"hwnd": int, "monitor_spec": Optional[Union[str, int]], "pid": Optional[int]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=snap_window_right,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_snapped_right"],
        ))
        self.register(Capability(
            id="close_window",
            category=CapabilityCategory.WINDOW,
            description="Gracefully close a window via standard WM_CLOSE messaging (no process termination)",
            args_schema={"hwnd": int, "pid": Optional[int]},
            risk=ToolRisk.MEDIUM,
            read_only=False,
            handler=close_window,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_closed"],
        ))
        self.register(Capability(
            id="undo_window_layout",
            category=CapabilityCategory.WINDOW,
            description="Undo the last window movement or geometry change from the restore stack",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=undo_last_window_move,
            permission=CapabilityPermission.AUTO,
            context_effects=["window_undone"],
        ))
        self.register(Capability(
            id="arrange_desktop",
            category=CapabilityCategory.WINDOW,
            description="Arrange multiple windows atomically according to a composition plan",
            args_schema={"plan": list},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=arrange_desktop,
            permission=CapabilityPermission.AUTO,
            context_effects=["desktop_arranged"],
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

        # ---------------------------------------------------------
        # APPLICATION INTERACTION & UI AUTOMATION CAPABILITIES (v0.10)
        # ---------------------------------------------------------
        from astrarun.interaction.service import (
            click_element,
            focus_control,
            get_clipboard,
            inspect_ui,
            press_shortcut,
            resolve_editable_element,
            scroll_control,
            select_tab,
            set_clipboard,
            set_element_text,
            toggle_checkbox,
            type_literal_text,
        )

        self.register(Capability(
            id="inspect_window_ui",
            category=CapabilityCategory.INTERACTION,
            description="Inspect accessible UI elements and control hierarchy of target or foreground window",
            args_schema={"hwnd": int, "window": str, "max_elements": int, "filter_type": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=inspect_ui,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="resolve_editable_element",
            category=CapabilityCategory.INTERACTION,
            description="Inspect target window UIA tree and resolve primary editable document or text input",
            args_schema={"hwnd": int, "window": str, "target": str},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=resolve_editable_element,
            permission=CapabilityPermission.AUTO,
            context_effects=["editor_resolved"],
        ))
        self.register(Capability(
            id="click_ui_element",
            category=CapabilityCategory.INTERACTION,
            description="Click or invoke a semantic button, menu item, or interactive control",
            args_schema={"target": str, "hwnd": int, "window": str, "force": bool},
            risk=ToolRisk.MEDIUM,
            read_only=False,
            handler=click_element,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="set_ui_element_value",
            category=CapabilityCategory.INTERACTION,
            description="Set text content of an accessible input or edit field",
            args_schema={"target": str, "value": str, "hwnd": int, "window": str},
            risk=ToolRisk.MEDIUM,
            read_only=False,
            handler=set_element_text,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="toggle_ui_element",
            category=CapabilityCategory.INTERACTION,
            description="Toggle a checkbox, switch, or binary toggle control",
            args_schema={"target": str, "hwnd": int, "window": str},
            risk=ToolRisk.MEDIUM,
            read_only=False,
            handler=toggle_checkbox,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="select_ui_element",
            category=CapabilityCategory.INTERACTION,
            description="Select a tab, radio button, or list item",
            args_schema={"target": str, "hwnd": int, "window": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=select_tab,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="focus_ui_element",
            category=CapabilityCategory.INTERACTION,
            description="Assign native keyboard focus to a target control",
            args_schema={"target": str, "hwnd": int, "window": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=focus_control,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="scroll_ui_element",
            category=CapabilityCategory.INTERACTION,
            description="Scroll a container or active window logically",
            args_schema={"direction": str, "target": str, "hwnd": int, "window": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=scroll_control,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="press_keyboard_shortcut",
            category=CapabilityCategory.INTERACTION,
            description="Dispatch a validated keyboard shortcut (e.g. Ctrl+Shift+P) to target or foreground window",
            args_schema={"shortcut": str, "hwnd": int, "window": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=press_shortcut,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="type_text",
            category=CapabilityCategory.INTERACTION,
            description="Type literal text into the active/focused control without shell evaluation",
            args_schema={"text": str, "hwnd": int, "window": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=type_literal_text,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="get_clipboard_content",
            category=CapabilityCategory.INTERACTION,
            description="Read text content from the system clipboard",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=get_clipboard,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="set_clipboard_content",
            category=CapabilityCategory.INTERACTION,
            description="Write text content to the system clipboard",
            args_schema={"text": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=set_clipboard,
            permission=CapabilityPermission.AUTO,
        ))

        # ---------------------------------------------------------
        # V0.11 NATIVE WI-FI & SYSTEM UTILITY CAPABILITIES
        # ---------------------------------------------------------
        from astrarun.tools.system_adapter import PowerCfgAdapter
        powercfg_adapter = PowerCfgAdapter()
        self.register(Capability(
            id="generate_battery_report",
            category=CapabilityCategory.SYSTEM,
            description="Generate comprehensive Windows battery health report via powercfg.exe",
            args_schema={"output_path": Optional[str]},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=powercfg_adapter.generate_battery_report,
            permission=CapabilityPermission.AUTO,
            context_effects=["battery_report_generated"],
        ))

        from astrarun.tools.wifi import wifi_connect, wifi_disconnect, wifi_scan, wifi_status
        self.register(Capability(
            id="wifi_scan",
            category=CapabilityCategory.NETWORK,
            description="Scan and enumerate available 802.11 wireless networks using Native Wi-Fi API",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=wifi_scan,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="wifi_status",
            category=CapabilityCategory.NETWORK,
            description="Query Wi-Fi adapter connection state and active SSID",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=True,
            handler=wifi_status,
            permission=CapabilityPermission.AUTO,
        ))
        self.register(Capability(
            id="wifi_connect",
            category=CapabilityCategory.NETWORK,
            description="Connect to a Wi-Fi network profile using fuzzy SSID matching",
            args_schema={"ssid": str},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=wifi_connect,
            permission=CapabilityPermission.AUTO,
            context_effects=["wifi_connected"],
        ))
        self.register(Capability(
            id="wifi_disconnect",
            category=CapabilityCategory.NETWORK,
            description="Disconnect active Wi-Fi wireless connection",
            args_schema={},
            risk=ToolRisk.LOW,
            read_only=False,
            handler=wifi_disconnect,
            permission=CapabilityPermission.AUTO,
            context_effects=["wifi_disconnected"],
        ))
