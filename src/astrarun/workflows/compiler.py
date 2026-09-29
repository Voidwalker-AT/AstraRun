"""Workflow Compiler: Translates StructuredUtterance into WorkflowProposal.

Enforces:
1. Capability boundary: Only maps to registered tools (zero code generation).
2. Negation safety: Negated clauses are completely excluded from executable steps.
3. Multi-clause policy: If any clause is blocked, the ENTIRE proposal is blocked.
4. Mixed-risk requests: Combined risk calculated; HIGH risk triggers confirmation.
5. Partial capability: Distinguishes fully supported from partially supported workflows.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from astrarun.core.models import ToolRisk
from astrarun.nlp.models import (
    Clause,
    NLPEntity,
    NLPEntityType,
    RelationType,
    StructuredUtterance,
)
from astrarun.workflows.models import WorkflowProposal, WorkflowStep
from astrarun.nlp.negation import verify_negation_safety

logger = logging.getLogger(__name__)

# System paths and processes strictly blocked by policy
_PROTECTED_PROCESSES = {
    "system", "system32", "registry", "lsass", "csrss", "smss",
    "services.exe", "services", "svchost.exe", "svchost", "wininit",
    "winlogon", "dwm", "explorer.exe", "explorer",
}

_PROHIBITED_COMMAND_PATTERNS = [
    re.compile(r'(?i)\b(?:format\s+[a-z]:?|rm\s+-rf|del\s+/[sfq]|system32|powershell\s+-enc|powershell\.exe|cmd\.exe)'),
    re.compile(r'(?i)\b(?:delete\s+system32|kill\s+lsass|kill\s+system|close\s+lsass|close\s+system|format\s+c)'),
    re.compile(r'(?i)\b(?:shutdown|shut\s+down|restart\s+workstation|reboot\b)'),
    re.compile(r'(?i)\b(?:open\s+(?:file\s+)?.*?\.(?:exe|bat|cmd|ps1|msi|scr|com))\b'),
    re.compile(r'(?i)(?:\.\.[\\/]|windows[\\/]system32)'),
]


class WorkflowCompiler:
    """Safe compiler mapping linguistic semantics to registered capabilities."""

    def __init__(self, tool_registry: Any = None):
        self.tool_registry = tool_registry

    def compile(self, utterance: StructuredUtterance) -> WorkflowProposal:
        """Compile a StructuredUtterance into a validated WorkflowProposal."""
        steps: list[WorkflowStep] = []
        blocked_reasons: list[str] = []
        unsupported_clauses: list[str] = []
        overall_risk = ToolRisk.LOW
        has_ambiguity = utterance.ambiguity > 0.6
        preview_lines: list[str] = []

        # 1. Global & Clause-level Hard Policy Check
        raw_lower = utterance.raw_text.lower()
        if re.search(r'\b(?:ignore\s+policy|bypass\s+policy|override\s+safety)\b', raw_lower):
            blocked_reasons.append("Prompt injection / policy bypass attempt detected.")

        for pat in _PROHIBITED_COMMAND_PATTERNS:
            if pat.search(raw_lower):
                blocked_reasons.append("Utterance contains prohibited destructive system command pattern.")

        for proc_name in _PROTECTED_PROCESSES:
            if re.search(r'\b(?:kill|terminate|stop|end|close)\s+(?:process\s+)?' + re.escape(proc_name) + r'\b', raw_lower):
                blocked_reasons.append(f"Attempting to terminate protected system process '{proc_name}'.")

        for clause in utterance.clauses:
            text_lower = clause.text.lower()
            for pat in _PROHIBITED_COMMAND_PATTERNS:
                if pat.search(text_lower):
                    blocked_reasons.append(
                        f"Clause {clause.idx} ('{clause.text}') violates hard security policy."
                    )

            # Check protected process targets
            for entity in clause.entities:
                if entity.type == NLPEntityType.PROCESS:
                    val_str = str(entity.normalized).lower()
                    if val_str in _PROTECTED_PROCESSES:
                        blocked_reasons.append(
                            f"Process '{val_str}' in clause {clause.idx} is a protected system process."
                        )

            # Check port termination on privileged ports <= 1023
            if clause.action == "terminate_process":
                for entity in clause.entities:
                    if entity.type == NLPEntityType.PORT and isinstance(entity.normalized, int):
                        if entity.normalized <= 1023:
                            blocked_reasons.append(
                                f"Termination of process on privileged port {entity.normalized} is prohibited."
                            )

        # If any clause is blocked, BLOCK THE ENTIRE REQUEST (Conservative Invariant)
        if blocked_reasons:
            return WorkflowProposal(
                status="BLOCKED",
                steps=[],
                overall_risk=ToolRisk.HIGH,
                requires_confirmation=False,
                blocked_reasons=blocked_reasons,
                unsupported_clauses=unsupported_clauses,
                preview="Request blocked by hard security policy.",
                utterance=utterance,
            )

        # 2. Compile each Clause into a Registered Capability
        step_counter = 1
        for clause in utterance.clauses:
            # SAFETY INVARIANT: Negated clauses must NEVER become executable proposals
            if clause.negated:
                preview_lines.append(f"(Skipped negated action: {clause.text})")
                continue

            # Check if this clause has open-ended AI query semantics
            if clause.action == "ai_query":
                unsupported_clauses.append(clause.text)
                continue

            # A. Open Project (in VS Code or Explorer)
            if clause.action == "open_project":
                proj_ent = next((e for e in clause.entities if e.type == NLPEntityType.PROJECT), None)
                app_ent = next((e for e in clause.entities if e.type == NLPEntityType.APPLICATION), None)
                
                # Check for contextual project reference
                if not proj_ent and clause.contextual_references:
                    ref = clause.contextual_references[0]
                    if ref.resolved_id:
                        proj_id = ref.resolved_id
                    elif ref.ambiguous:
                        has_ambiguity = True
                        proj_id = None
                    else:
                        proj_id = None
                else:
                    proj_id = proj_ent.normalized if proj_ent else None

                if proj_id:
                    has_vscode = (app_ent and app_ent.normalized == "vscode") or "vscode" in clause.text.lower() or "vs code" in clause.text.lower()
                    if has_vscode:
                        steps.append(WorkflowStep(
                            step_id=f"step_{step_counter}",
                            name=f"Open {proj_id} in VS Code",
                            tool="open_project_in_vscode",
                            arguments={"project_id": proj_id},
                            critical=True,
                            source_clause_idx=clause.idx,
                        ))
                        preview_lines.append(f"{step_counter}. Open {proj_id} in VS Code")
                    else:
                        steps.append(WorkflowStep(
                            step_id=f"step_{step_counter}",
                            name=f"Open {proj_id} folder",
                            tool="open_project_folder",
                            arguments={"project_id": proj_id},
                            critical=True,
                            source_clause_idx=clause.idx,
                        ))
                        preview_lines.append(f"{step_counter}. Open {proj_id} folder")
                    step_counter += 1
                else:
                    if not has_ambiguity:
                        unsupported_clauses.append(clause.text)

            # B. Inspect Port
            elif clause.action == "inspect_port":
                port_ent = next((e for e in clause.entities if e.type == NLPEntityType.PORT), None)
                if port_ent and isinstance(port_ent.normalized, int):
                    port_val = port_ent.normalized
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Inspect port {port_val}",
                        tool="inspect_port",
                        arguments={"port": port_val},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. Inspect port {port_val}")
                    step_counter += 1
                else:
                    unsupported_clauses.append(clause.text)

            # C. Inspect Process
            elif clause.action == "inspect_process":
                pid_ent = next((e for e in clause.entities if e.type == NLPEntityType.PROCESS), None)
                pid_val = pid_ent.normalized if pid_ent and isinstance(pid_ent.normalized, int) else None

                if pid_val is None and clause.contextual_references:
                    ref = clause.contextual_references[0]
                    if ref.resolved_value:
                        pid_val = ref.resolved_value
                    elif ref.ambiguous:
                        has_ambiguity = True

                if pid_val is not None:
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Inspect process {pid_val}",
                        tool="inspect_process",
                        arguments={"pid": pid_val},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. Inspect process {pid_val}")
                    step_counter += 1
                else:
                    if not has_ambiguity:
                        unsupported_clauses.append(clause.text)

            # D. Terminate Process (HIGH RISK)
            elif clause.action == "terminate_process":
                pid_ent = next((e for e in clause.entities if e.type == NLPEntityType.PROCESS), None)
                pid_val = pid_ent.normalized if pid_ent and isinstance(pid_ent.normalized, int) else None

                if pid_val is None and clause.contextual_references:
                    ref = clause.contextual_references[0]
                    if ref.resolved_value:
                        pid_val = ref.resolved_value
                    elif ref.ambiguous:
                        has_ambiguity = True

                if pid_val is not None:
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Terminate process {pid_val}",
                        tool="terminate_process",
                        arguments={"pid": pid_val},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    overall_risk = ToolRisk.HIGH
                    preview_lines.append(f"{step_counter}. Terminate process {pid_val} [HIGH RISK - REQUIRES CONFIRMATION]")
                    step_counter += 1
                else:
                    if not has_ambiguity:
                        unsupported_clauses.append(clause.text)

            # E. Application Management (focus / close / running list)
            elif clause.action == "focus_application":
                app_ent = next((e for e in clause.entities if e.type == NLPEntityType.APPLICATION), None)
                app_name = app_ent.normalized if app_ent else None
                if app_name:
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Focus application {app_name}",
                        tool="focus_application",
                        arguments={"app": app_name},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. Focus application {app_name}")
                    step_counter += 1
                else:
                    unsupported_clauses.append(clause.text)

            elif clause.action == "close_application":
                app_ent = next((e for e in clause.entities if e.type == NLPEntityType.APPLICATION), None)
                app_name = app_ent.normalized if app_ent else None
                if app_name:
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Close application {app_name}",
                        tool="close_application",
                        arguments={"app": app_name},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. Close application {app_name}")
                    step_counter += 1
                else:
                    unsupported_clauses.append(clause.text)

            elif clause.action == "list_running_applications":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="List running applications",
                    tool="list_running_applications",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. List running applications")
                step_counter += 1

            elif clause.action in ("open_app", "open_application"):
                app_ent = next((e for e in clause.entities if e.type == NLPEntityType.APPLICATION), None)
                app_name = app_ent.normalized if app_ent else None
                if not app_name:
                    m = re.search(r'\b(?:open|launch|start|run)\s+([a-zA-Z0-9_\-\.]+)', clause.text, re.I)
                    if m:
                        app_name = m.group(1).lower()
                if app_name:
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Open {app_name}",
                        tool="open_application",
                        arguments={"app": app_name},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. Open application {app_name}")
                    step_counter += 1

                    # Check for subsequent dependent interaction or window actions
                    subsequent_clauses = [c for c in utterance.clauses if c.idx > clause.idx]
                    has_subsequent_interaction = any(
                        c.action in ("type_text", "press_keyboard_shortcut", "click_ui_element", "set_ui_element_value", "toggle_ui_element", "select_ui_element", "focus_ui_element")
                        for c in subsequent_clauses
                    )
                    has_subsequent_window_action = any(
                        c.action in ("maximize_window", "minimize_window", "restore_window", "snap_window_left", "snap_window_right", "move_window", "move_window_to_monitor", "close_window")
                        for c in subsequent_clauses
                    )
                    has_subsequent_text_entry = any(
                        c.action in ("type_text", "set_ui_element_value")
                        for c in subsequent_clauses
                    )

                    if has_subsequent_interaction or has_subsequent_window_action:
                        # 1. Bounded window readiness synchronization
                        steps.append(WorkflowStep(
                            step_id=f"step_{step_counter}",
                            name=f"Wait for {app_name} window",
                            tool="wait_for_window",
                            arguments={"app": app_name, "timeout": 10.0},
                            critical=True,
                            source_clause_idx=clause.idx,
                        ))
                        preview_lines.append(f"{step_counter}. Wait for {app_name} window")
                        step_counter += 1

                        # 2. Text editing control resolution (for type_text / set_ui_element_value)
                        if has_subsequent_text_entry:
                            steps.append(WorkflowStep(
                                step_id=f"step_{step_counter}",
                                name=f"Resolve editor in {app_name}",
                                tool="resolve_editable_element",
                                arguments={"window": app_name},
                                critical=True,
                                source_clause_idx=clause.idx,
                            ))
                            preview_lines.append(f"{step_counter}. Resolve editor in {app_name}")
                            step_counter += 1
                else:
                    unsupported_clauses.append(clause.text)

            # F. System Health & Performance
            elif clause.action == "system_summary":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="System health summary",
                    tool="system_summary",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Show system summary")
                step_counter += 1

            elif clause.action == "gpu_status":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="GPU status",
                    tool="gpu_status",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Show GPU status")
                step_counter += 1

            elif clause.action == "memory_status":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Memory status",
                    tool="memory_status",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Show memory status")
                step_counter += 1

            elif clause.action == "cpu_status":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="CPU status",
                    tool="cpu_status",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Show CPU status")
                step_counter += 1

            elif clause.action == "disk_status":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Disk status",
                    tool="disk_status",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Show disk status")
                step_counter += 1

            elif clause.action == "battery_status":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Battery status",
                    tool="battery_status",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Show battery status")
                step_counter += 1

            elif clause.action == "audio_status":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Audio status",
                    tool="audio_status",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Show audio status")
                step_counter += 1

            # G. Network Port Listing & Connections
            elif clause.action == "list_listening_ports":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="List listening ports",
                    tool="list_listening_ports",
                    arguments={"limit": 20},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. List listening ports")
                step_counter += 1

            elif clause.action in ("list_network_connections", "network_connections"):
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="List network connections",
                    tool="list_network_connections",
                    arguments={"limit": 20},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. List network connections")
                step_counter += 1

            # H. Process Listing
            elif clause.action == "list_processes":
                filter_name = None
                if "node" in clause.text.lower():
                    filter_name = "node"
                elif "python" in clause.text.lower():
                    filter_name = "python"
                sort_by = "cpu" if "cpu" in clause.text.lower() else "memory"
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name=f"List processes (filter={filter_name})",
                    tool="list_processes",
                    arguments={"limit": 10, "sort_by": sort_by, "filter_name": filter_name},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. List processes")
                step_counter += 1

            # I. Project Status / Git
            elif clause.action == "project_status":
                proj_ent = next((e for e in clause.entities if e.type == NLPEntityType.PROJECT), None)
                proj_id = proj_ent.normalized if proj_ent else None
                if proj_id:
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Project status for {proj_id}",
                        tool="project_status",
                        arguments={"project_id": proj_id},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. Show status of {proj_id}")
                    step_counter += 1
                else:
                    unsupported_clauses.append(clause.text)

            elif clause.action == "project_git_status":
                proj_ent = next((e for e in clause.entities if e.type == NLPEntityType.PROJECT), None)
                proj_id = proj_ent.normalized if proj_ent else None
                if proj_id:
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Git status for {proj_id}",
                        tool="project_git_status",
                        arguments={"project_id": proj_id},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. Show Git status of {proj_id}")
                    step_counter += 1
                else:
                    unsupported_clauses.append(clause.text)

            # J. Window Discovery
            elif clause.action in ("windows_for_application", "list_windows"):
                app_ent = next((e for e in clause.entities if e.type == NLPEntityType.APPLICATION), None)
                app_name = app_ent.normalized if app_ent else ""
                if app_name:
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Show windows for {app_name}",
                        tool="windows_for_application",
                        arguments={"app": app_name},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. Show windows for {app_name}")
                    step_counter += 1
                else:
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name="List desktop windows",
                        tool="list_windows",
                        arguments={"limit": 20},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. List desktop windows")
                    step_counter += 1

            elif clause.action == "foreground_window":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Get foreground window",
                    tool="foreground_window",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Get active foreground window")
                step_counter += 1

            elif clause.action == "focus_window":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Focus window",
                    tool="focus_window",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Focus window")
                step_counter += 1

            elif clause.action == "minimize_window":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Minimize window",
                    tool="minimize_window",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Minimize window")
                step_counter += 1

            elif clause.action == "maximize_window":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Maximize window",
                    tool="maximize_window",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Maximize window")
                step_counter += 1

            elif clause.action == "restore_window":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Restore window",
                    tool="restore_window",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Restore window size and position")
                step_counter += 1

            elif clause.action == "snap_window_left":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Snap window left",
                    tool="snap_window_left",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Snap window to left half")
                step_counter += 1

            elif clause.action == "snap_window_right":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Snap window right",
                    tool="snap_window_right",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Snap window to right half")
                step_counter += 1

            elif clause.action == "move_window_to_monitor":
                mon_match = re.search(r'\b(?:monitor|screen)\s*(\d+|left|right|primary|secondary)\b', clause.text, re.I)
                mon_spec = mon_match.group(1) if mon_match else "next"
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name=f"Move window to monitor {mon_spec}",
                    tool="move_window_to_monitor",
                    arguments={"monitor_spec": mon_spec},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Move window to monitor {mon_spec}")
                step_counter += 1

            elif clause.action == "move_window":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Move window",
                    tool="move_window",
                    arguments={"x": 100, "y": 100, "width": 800, "height": 600},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Move window")
                step_counter += 1

            elif clause.action == "resize_window":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Resize window",
                    tool="resize_window",
                    arguments={"width": 800, "height": 600},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Resize window")
                step_counter += 1

            elif clause.action == "close_window":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Close window",
                    tool="close_window",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Close window gracefully")
                step_counter += 1

            elif clause.action == "arrange_desktop":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Arrange desktop windows",
                    tool="arrange_desktop",
                    arguments={"layout": "tile_grid"},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Arrange desktop windows")
                step_counter += 1

            elif clause.action == "undo_last_window_move":
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name="Undo window layout",
                    tool="undo_last_window_move",
                    arguments={},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Undo last window layout")
                step_counter += 1

            # L. UI Automation & Control Grounding (v0.10)
            elif clause.action == "type_text":
                raw = clause.text
                if " into " in raw.lower():
                    parts = re.split(r'\s+into\s+', raw, flags=re.I)
                    val = re.sub(r'^(?:type|enter text)\s+', '', parts[0], flags=re.I).strip().strip('"\'')
                    target_field = parts[1].strip()
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Set text in {target_field}",
                        tool="set_ui_element_value",
                        arguments={"target": target_field, "value": val},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. Set '{val}' in {target_field}")
                else:
                    val = re.sub(r'^(?:type|enter text)\s+', '', raw, flags=re.I).strip().strip('"\'')
                    steps.append(WorkflowStep(
                        step_id=f"step_{step_counter}",
                        name=f"Type '{val}'",
                        tool="type_text",
                        arguments={"text": val},
                        critical=True,
                        source_clause_idx=clause.idx,
                    ))
                    preview_lines.append(f"{step_counter}. Type '{val}'")
                step_counter += 1

            elif clause.action in ("press_keyboard_shortcut", "press_key"):
                raw_sc = clause.text.strip().lower()
                if "copy" in raw_sc:
                    sc_val = "Ctrl+C"
                elif "paste" in raw_sc:
                    sc_val = "Ctrl+V"
                elif "select all" in raw_sc:
                    sc_val = "Ctrl+A"
                elif "delete" in raw_sc:
                    sc_val = "Delete"
                else:
                    sc_val = re.sub(r'^(?:press|shortcut)\s+', '', clause.text, flags=re.I).strip()

                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name=f"Press {sc_val}",
                    tool="press_keyboard_shortcut",
                    arguments={"shortcut": sc_val},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Press shortcut {sc_val}")
                step_counter += 1

            elif clause.action in ("click_ui_element", "ui_click"):
                target_btn = re.sub(r'^(?:click|press)\s+', '', clause.text, flags=re.I).strip()
                steps.append(WorkflowStep(
                    step_id=f"step_{step_counter}",
                    name=f"Click '{target_btn}'",
                    tool="click_ui_element",
                    arguments={"target": target_btn, "force": False},
                    critical=True,
                    source_clause_idx=clause.idx,
                ))
                preview_lines.append(f"{step_counter}. Click '{target_btn}'")
                step_counter += 1

            # M. Unsupported / Open-ended action
            else:
                unsupported_clauses.append(clause.text)

        # 3. Assert Negation Safety
        verify_negation_safety(utterance.clauses, steps)

        # 4. Determine Proposal Status
        requires_conf = (overall_risk == ToolRisk.HIGH)

        if has_ambiguity:
            status = "CLARIFY"
            preview = "Ambiguous target requires clarification."
        elif not steps and not unsupported_clauses:
            status = "EMPTY"
            preview = "No active executable actions requested."
        elif not steps and unsupported_clauses:
            status = "UNSUPPORTED"
            preview = f"Requested capability is not supported: {', '.join(unsupported_clauses)}"
        elif steps and unsupported_clauses:
            status = "PARTIALLY_SUPPORTED"
            preview = (
                f"Partially supported request.\n"
                f"Planned actions:\n" + "\n".join(preview_lines) +
                f"\nUnsupported clauses: {', '.join(unsupported_clauses)}"
            )
        else:
            status = "READY"
            preview = "I'll:\n" + "\n".join(f"  {line}" for line in preview_lines)

        return WorkflowProposal(
            status=status,
            steps=steps,
            overall_risk=overall_risk,
            requires_confirmation=requires_conf,
            blocked_reasons=blocked_reasons,
            unsupported_clauses=unsupported_clauses,
            preview=preview,
            utterance=utterance,
        )
