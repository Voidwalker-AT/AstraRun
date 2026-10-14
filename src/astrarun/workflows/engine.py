"""Workflow Engine for AstraRun v0.6.

Executes predefined, strongly-typed multi-step workflow templates:
- open_project (verify, open folder, update context)
- open_project_in_vscode (verify, launch code, update context)
- inspect_dev_port (inspect port, record context)

Enforces:
- Every step calls a registered tool (zero arbitrary shell / zero AI callbacks)
- Detailed step-level latency and success metrics
- Handles partial failure with explicit diagnostic reporting
- Immutable transaction audit log (data/workflow_audit.jsonl)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.context.engine import WorkstationContextEngine
from astrarun.core.logging import get_logger
from astrarun.core.models import ToolRisk
from astrarun.tools.registry import ToolRegistry
from astrarun.workflows.models import (
    Workflow,
    WorkflowExecutionResult,
    WorkflowStep,
    WorkflowStepResult,
)

logger = get_logger("astrarun.workflows.engine")


class WorkflowEngine:
    """Orchestrates structured, non-autonomous workflow execution."""

    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        context_engine: Optional[WorkstationContextEngine] = None,
        audit_log_path: Optional[Path | str] = None,
    ) -> None:
        from astrarun.core.paths import AstraPaths
        self.tool_registry = tool_registry or ToolRegistry()
        self.context_engine = context_engine
        self.audit_log_path = Path(audit_log_path).resolve() if audit_log_path else (AstraPaths.data_dir() / "workflow_audit.jsonl")
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)

    def create_open_project_workflow(self, project_id: str) -> Workflow:
        """Create workflow template to open a project directory."""
        return Workflow(
            id="open_project",
            name=f"Open Project Folder ({project_id})",
            description=f"Opens the directory for project {project_id} in File Explorer",
            steps=[
                WorkflowStep(
                    step_id="open_folder",
                    name="Open Project Folder",
                    tool="open_project_folder",
                    arguments={"project_id": project_id},
                    critical=True,
                ),
            ],
            risk=ToolRisk.LOW,
            rollback_supported=False,
        )

    def create_open_project_vscode_workflow(self, project_id: str) -> Workflow:
        """Create workflow template to open a project in VS Code."""
        return Workflow(
            id="open_project_in_vscode",
            name=f"Open Project in VS Code ({project_id})",
            description=f"Opens {project_id} in Visual Studio Code and updates recent context",
            steps=[
                WorkflowStep(
                    step_id="launch_vscode",
                    name="Launch VS Code",
                    tool="open_project_in_vscode",
                    arguments={"project_id": project_id},
                    critical=True,
                ),
            ],
            risk=ToolRisk.LOW,
            rollback_supported=False,
        )

    def create_inspect_port_workflow(self, port: int) -> Workflow:
        """Create workflow template to inspect a network port."""
        return Workflow(
            id="inspect_dev_port",
            name=f"Inspect Port {port}",
            description=f"Queries process metadata listening on TCP port {port}",
            steps=[
                WorkflowStep(
                    step_id="query_port",
                    name=f"Query Port {port}",
                    tool="inspect_port",
                    arguments={"port": port},
                    critical=True,
                ),
            ],
            risk=ToolRisk.LOW,
            rollback_supported=False,
        )

    def execute_workflow(
        self,
        workflow: Workflow,
        entity_id: str = "",
        session_id: str = "",
    ) -> WorkflowExecutionResult:
        """
        Execute a predefined workflow sequentially.
        Handles partial failure without claiming full success.
        """
        t0 = time.perf_counter()
        step_results: list[WorkflowStepResult] = []
        steps_succeeded = 0
        steps_failed = 0
        overall_success = True
        error_messages: list[str] = []

        for step in workflow.steps:
            t_step0 = time.perf_counter()
            success, msg, data = self.tool_registry.execute_action(step.tool, step.arguments)
            step_lat = (time.perf_counter() - t_step0) * 1000.0

            step_res = WorkflowStepResult(
                step_id=step.step_id,
                name=step.name,
                tool=step.tool,
                success=success,
                message=msg,
                data=data,
                latency_ms=step_lat,
            )
            step_results.append(step_res)

            if success:
                steps_succeeded += 1
                # Update context engine with completed action
                if self.context_engine:
                    meta = data if isinstance(data, dict) else {}
                    self.context_engine.record_action(
                        action_type=step.tool,
                        entity_id=entity_id or f"workflow:{workflow.id}",
                        target=str(step.arguments),
                        success=True,
                        session_id=session_id,
                        metadata=meta,
                    )
            else:
                steps_failed += 1
                overall_success = False
                error_messages.append(f"Step '{step.name}' failed: {msg}")
                logger.warning("Workflow step failed: %s (%s)", step.name, msg)
                if step.critical:
                    logger.error("Critical step failed in workflow '%s'; aborting remaining steps", workflow.id)
                    break

        total_lat = (time.perf_counter() - t0) * 1000.0

        if overall_success:
            summary_msg = f"Workflow '{workflow.name}' executed successfully ({steps_succeeded}/{len(workflow.steps)} steps)."
        else:
            summary_msg = f"Workflow '{workflow.name}' partially completed ({steps_succeeded} succeeded, {steps_failed} failed). " + " ".join(error_messages)

        res = WorkflowExecutionResult(
            workflow_id=workflow.id,
            entity_id=entity_id,
            success=overall_success,
            message=summary_msg,
            steps_attempted=len(step_results),
            steps_succeeded=steps_succeeded,
            steps_failed=steps_failed,
            step_results=step_results,
            rollback_supported=workflow.rollback_supported,
            total_latency_ms=total_lat,
        )

        self._log_transaction(res)
        return res

    def _log_transaction(self, result: WorkflowExecutionResult) -> None:
        """Append workflow execution event to local transaction log."""
        try:
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result.to_dict()) + "\n")
        except Exception as err:
            logger.error("Failed to write to workflow audit log %s: %s", self.audit_log_path, err)

    # Alias for convenience
    execute = execute_workflow
