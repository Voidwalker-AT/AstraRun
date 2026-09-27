"""Central tool registry and policy dispatcher."""

from __future__ import annotations

from typing import Any

from astrarun.core.logging import get_logger
from astrarun.core.models import Decision, ToolMetadata, ToolRisk
from astrarun.tools.apps import open_app
from astrarun.tools.folders import open_folder
from astrarun.tools.processes import inspect_port, inspect_process, terminate_process
from astrarun.tools.projects import open_project_folder, open_project_in_vscode
from astrarun.tools.web import open_url

logger = get_logger("astrarun.tools.registry")


class ToolRegistry:
    """Registry maintaining available tools, risk classifications, and safe execution dispatch."""

    def __init__(self):
        self._tools: dict[str, ToolMetadata] = {}
        self._register_default_tools()

    def register(self, metadata: ToolMetadata) -> None:
        """Register a new tool metadata and handler."""
        self._tools[metadata.name] = metadata
        logger.debug("Tool registered: %s (risk=%s)", metadata.name, metadata.risk)

    def get(self, name: str) -> ToolMetadata | None:
        """Retrieve tool metadata by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolMetadata]:
        """Return all registered tool metadata descriptors."""
        return list(self._tools.values())

    def _register_default_tools(self) -> None:
        """Register default v0.1-v0.6 tools."""
        self.register(
            ToolMetadata(
                name="open_app",
                description="Launch a verified local Windows executable",
                risk=ToolRisk.LOW,
                args_schema={"app": str, "path": str},
                handler=open_app,
                read_only=False,
                requires_confirmation=False,
            )
        )
        self.register(
            ToolMetadata(
                name="open_folder",
                description="Open a verified directory in File Explorer",
                risk=ToolRisk.LOW,
                args_schema={"folder": str},
                handler=open_folder,
                read_only=True,
                requires_confirmation=False,
            )
        )
        self.register(
            ToolMetadata(
                name="open_url",
                description="Open a validated HTTP/HTTPS URL in the default browser",
                risk=ToolRisk.LOW,
                args_schema={"url": str},
                handler=open_url,
                read_only=True,
                requires_confirmation=False,
            )
        )
        self.register(
            ToolMetadata(
                name="refresh_apps",
                description="Rescan installed Windows applications and rebuild the search index",
                risk=ToolRisk.LOW,
                args_schema={},
                handler=lambda **_: True,
                read_only=True,
                requires_confirmation=False,
            )
        )
        # v0.6 Workstation Tools
        self.register(
            ToolMetadata(
                name="open_project_folder",
                description="Open a verified project directory in File Explorer",
                risk=ToolRisk.LOW,
                args_schema={"project_id": str},
                handler=open_project_folder,
                read_only=True,
                requires_confirmation=False,
                context_effects=["project_opened"],
            )
        )
        self.register(
            ToolMetadata(
                name="open_project_in_vscode",
                description="Open a verified project directory in Visual Studio Code",
                risk=ToolRisk.LOW,
                args_schema={"project_id": str},
                handler=open_project_in_vscode,
                read_only=False,
                requires_confirmation=False,
                context_effects=["project_opened"],
            )
        )
        self.register(
            ToolMetadata(
                name="open_project",
                description="Open a verified project workspace (default: VS Code or Folder)",
                risk=ToolRisk.LOW,
                args_schema={"project_id": str},
                handler=open_project_in_vscode,
                read_only=False,
                requires_confirmation=False,
                context_effects=["project_opened"],
            )
        )
        self.register(
            ToolMetadata(
                name="inspect_port",
                description="Read-only query of process listening on a TCP network port",
                risk=ToolRisk.LOW,
                args_schema={"port": int},
                handler=inspect_port,
                read_only=True,
                requires_confirmation=False,
                context_effects=["port_inspected"],
            )
        )
        self.register(
            ToolMetadata(
                name="inspect_process",
                description="Read-only query of process metadata, CPU, memory, and ports",
                risk=ToolRisk.LOW,
                args_schema={"pid": int},
                handler=inspect_process,
                read_only=True,
                requires_confirmation=False,
                context_effects=["process_inspected"],
            )
        )
        self.register(
            ToolMetadata(
                name="terminate_process",
                description="Terminate a non-protected process with TOCTOU validation",
                risk=ToolRisk.HIGH,
                args_schema={"pid": int, "expected_create_time": float, "expected_name": str},
                handler=terminate_process,
                read_only=False,
                requires_confirmation=True,
                context_effects=["process_terminated"],
            )
        )

    def execute(self, decision: Decision) -> tuple[bool, str]:
        """
        Safely execute a structured Decision through the registered tool handler.
        
        Returns:
            tuple of (success: bool, status_message: str)
        """
        if not decision.is_resolved:
            logger.info("Command unresolved: %s", decision.args.get("request", ""))
            return False, "I don't know how to do that yet."

        tool_meta = self.get(decision.tool)
        if not tool_meta:
            logger.warning("Attempted invocation of unregistered tool: %s", decision.tool)
            return False, f"Tool '{decision.tool}' is not registered."

        if tool_meta.risk == ToolRisk.BLOCKED:
            logger.error("Execution blocked for prohibited tool: %s", decision.tool)
            return False, "This operation is prohibited by policy."

        logger.info(
            "Dispatching tool '%s' with args %s (source=%s)",
            decision.tool, decision.args, decision.source
        )

        try:
            success = tool_meta.handler(**decision.args)
            if success:
                return True, "Executed successfully."
            else:
                # Provide contextual error message without raw tracebacks
                if decision.tool == "open_app":
                    app_name = decision.args.get("app", "Application")
                    return False, f"{app_name.title()} was not found."
                elif decision.tool == "open_folder":
                    return False, "The requested folder could not be found."
                elif decision.tool == "open_url":
                    return False, "Could not open the requested URL."
                return False, "Action failed to execute."
        except TypeError as err:
            logger.error("Argument mismatch executing tool '%s': %s", decision.tool, err)
            return False, "Internal error: invalid arguments for tool."
        except Exception as err:
            logger.error("Exception occurred while executing tool '%s': %s", decision.tool, err, exc_info=True)
            return False, "An unexpected error occurred while executing the command."

    def execute_action(self, tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str, Any]:
        """
        Execute a tool by name and keyword arguments.
        
        Returns:
            (success: bool, message: str, result_data: Any)
        """
        tool_meta = self.get(tool_name)
        if not tool_meta:
            logger.warning("Attempted invocation of unregistered tool: %s", tool_name)
            return False, f"Tool '{tool_name}' is not registered.", None

        if tool_meta.risk == ToolRisk.BLOCKED:
            logger.error("Execution blocked for prohibited tool: %s", tool_name)
            return False, "This operation is prohibited by policy.", None

        logger.info("Executing tool '%s' with args %s", tool_name, arguments)
        try:
            res = tool_meta.handler(**arguments)
            # If handler returns bool
            if isinstance(res, bool):
                if res:
                    return True, "Executed successfully.", res
                else:
                    return False, f"Tool '{tool_name}' execution returned failure.", res
            # If handler returns dict (like inspect_port or inspect_process)
            elif isinstance(res, dict):
                msg = res.get("message", "Executed successfully.")
                return True, msg, res
            else:
                return True, "Executed successfully.", res
        except TypeError as err:
            logger.error("Argument mismatch for '%s': %s", tool_name, err)
            return False, f"Invalid arguments for tool '{tool_name}': {err}", None
        except Exception as err:
            logger.error("Error executing tool '%s': %s", tool_name, err, exc_info=True)
            return False, f"Error executing tool '{tool_name}': {err}", None

