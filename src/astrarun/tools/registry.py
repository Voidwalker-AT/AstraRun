"""Central tool registry and policy dispatcher."""

from __future__ import annotations

from typing import Any

from astrarun.core.logging import get_logger
from astrarun.core.models import Decision, ToolMetadata, ToolRisk
from astrarun.tools.apps import open_app
from astrarun.tools.folders import open_folder
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

    def _register_default_tools(self) -> None:
        """Register default v0.1 tools."""
        self.register(
            ToolMetadata(
                name="open_app",
                description="Launch a verified local Windows executable",
                risk=ToolRisk.LOW,
                args_schema={"app": str, "path": str},
                handler=open_app,
            )
        )
        self.register(
            ToolMetadata(
                name="open_folder",
                description="Open a verified directory in File Explorer",
                risk=ToolRisk.LOW,
                args_schema={"folder": str},
                handler=open_folder,
            )
        )
        self.register(
            ToolMetadata(
                name="open_url",
                description="Open a validated HTTP/HTTPS URL in the default browser",
                risk=ToolRisk.LOW,
                args_schema={"url": str},
                handler=open_url,
            )
        )
        self.register(
            ToolMetadata(
                name="refresh_apps",
                description="Rescan installed Windows applications and rebuild the search index",
                risk=ToolRisk.LOW,
                args_schema={},
                handler=lambda **_: True,
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
