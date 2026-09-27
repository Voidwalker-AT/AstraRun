"""Build script for AstraRun v0.8 Task Benchmark V1 (320 deterministic lifecycle test cases)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def generate_cases() -> list[dict]:
    cases = []
    case_idx = 1

    # 1. Single Capability Successful Tasks (60 cases)
    single_success_templates = [
        ("inspect_port", {"port": 3000}, "what is running on port 3000", "Inspect Port 3000", ["port:3000"]),
        ("inspect_port", {"port": 8000}, "who is using port 8000", "Inspect Port 8000", ["port:8000"]),
        ("system_summary", {}, "system status", "System Summary", []),
        ("cpu_status", {}, "cpu status", "Inspect CPU Status", []),
        ("memory_status", {}, "how much memory is used", "Inspect Memory Status", []),
        ("gpu_status", {}, "gpu status", "Inspect GPU Status", []),
        ("battery_status", {}, "battery level", "Battery Status", []),
        ("list_running_applications", {}, "running apps", "List Running Applications", []),
        ("list_listening_ports", {}, "listening ports", "Listening Ports", []),
        ("find_file", {"pattern": "*.py"}, "find file *.py", "Find File", ["pattern:*.py"]),
        ("find_latest_file", {"pattern": "screenshot"}, "open latest screenshot", "Find Latest Screenshot", ["screenshot"]),
        ("list_recent_files", {"limit": 10}, "recent files", "List Recent Files", []),
        ("project_status", {"project_id": "astrarun"}, "status of AstraRun", "Status Of Astrarun", ["project:astrarun"]),
        ("project_git_status", {"project_id": "astrarun"}, "git status AstraRun", "Git Status (Astrarun)", ["project:astrarun"]),
        ("lock_workstation", {}, "lock computer", "Lock Workstation", []),
    ]
    for rep in range(4):
        for cap_id, args, req, title, ents in single_success_templates:
            cases.append({
                "id": f"TASK-SUCC-{case_idx:04d}",
                "category": "single_capability_success",
                "request_text": req if rep == 0 else f"{req} (run {rep})",
                "capability_id": cap_id,
                "arguments": args,
                "expected_title": title,
                "expected_entities": ents,
                "expected_final_status": "COMPLETED",
                "expected_event_sequence": [
                    "TASK_CREATED",
                    "NLP_PARSE_STARTED",
                    "NLP_PARSE_COMPLETED",
                    "ACTION_GATE_ALLOW",
                    "CAPABILITY_STARTED",
                    "CAPABILITY_COMPLETED",
                    "TASK_COMPLETED",
                ],
            })
            case_idx += 1

    # 2. Multi-Step Workflows (40 cases)
    workflow_templates = [
        (
            "open AstraRun and check git status",
            [("open_project_in_vscode", {"project_id": "astrarun"}), ("project_git_status", {"project_id": "astrarun"})],
            "Open Astrarun In VS Code",
            ["project:astrarun"],
        ),
        (
            "check system status and gpu",
            [("system_summary", {}), ("gpu_status", {})],
            "System Summary",
            [],
        ),
        (
            "inspect port 3000 and inspect port 8000",
            [("inspect_port", {"port": 3000}), ("inspect_port", {"port": 8000})],
            "Inspect Port 3000",
            ["port:3000", "port:8000"],
        ),
        (
            "find latest screenshot and list recent files",
            [("find_latest_file", {"pattern": "screenshot"}), ("list_recent_files", {"limit": 5})],
            "Find Latest Screenshot",
            ["screenshot"],
        ),
    ]
    for rep in range(10):
        for req, steps, title, ents in workflow_templates:
            step_events = []
            for s_id, _ in steps:
                step_events.extend([
                    "WORKFLOW_STEP_STARTED",
                    "CAPABILITY_STARTED",
                    "CAPABILITY_COMPLETED",
                    "WORKFLOW_STEP_COMPLETED",
                ])
            cases.append({
                "id": f"TASK-WF-{case_idx:04d}",
                "category": "multi_step_workflow",
                "request_text": req if rep == 0 else f"{req} #{rep}",
                "workflow_steps": steps,
                "expected_title": title,
                "expected_entities": ents,
                "expected_final_status": "COMPLETED",
                "expected_event_sequence": [
                    "TASK_CREATED",
                    "NLP_PARSE_STARTED",
                    "NLP_PARSE_COMPLETED",
                    "WORKFLOW_COMPILED",
                    "WORKFLOW_STARTED",
                    *step_events,
                    "WORKFLOW_COMPLETED",
                    "TASK_COMPLETED",
                ],
            })
            case_idx += 1

    # 3. High-Risk Confirmation Accepted (30 cases)
    confirmation_templates = [
        ("terminate_process", {"pid": 14592, "name": "node.exe"}, "stop process 14592", "Stop Process 14592", ["pid:14592"]),
        ("terminate_process", {"pid": 8920, "name": "python.exe"}, "kill process 8920", "Kill Process 8920", ["pid:8920"]),
        ("terminate_process", {"pid": 3412, "name": "dummy_worker.exe"}, "terminate worker 3412", "Terminate Worker 3412", ["pid:3412"]),
    ]
    for rep in range(10):
        for cap_id, args, req, title, ents in confirmation_templates:
            cases.append({
                "id": f"TASK-CONF-ACC-{case_idx:04d}",
                "category": "high_risk_confirmation_accepted",
                "request_text": f"{req} #{rep}",
                "capability_id": cap_id,
                "arguments": args,
                "user_action": "CONFIRM",
                "expected_title": title,
                "expected_entities": ents,
                "expected_final_status": "COMPLETED",
                "expected_event_sequence": [
                    "TASK_CREATED",
                    "NLP_PARSE_STARTED",
                    "NLP_PARSE_COMPLETED",
                    "ACTION_GATE_CONFIRM",
                    "CONFIRMATION_REQUESTED",
                    "CONFIRMATION_ACCEPTED",
                    "CAPABILITY_STARTED",
                    "CAPABILITY_COMPLETED",
                    "TASK_COMPLETED",
                ],
            })
            case_idx += 1

    # 4. High-Risk Confirmation Rejected (20 cases)
    for rep in range(10):
        for cap_id, args, req, title, ents in confirmation_templates[:2]:
            cases.append({
                "id": f"TASK-CONF-REJ-{case_idx:04d}",
                "category": "high_risk_confirmation_rejected",
                "request_text": f"cancel {req} #{rep}",
                "capability_id": cap_id,
                "arguments": args,
                "user_action": "REJECT",
                "expected_title": title,
                "expected_entities": ents,
                "expected_final_status": "CANCELLED",
                "expected_event_sequence": [
                    "TASK_CREATED",
                    "NLP_PARSE_STARTED",
                    "NLP_PARSE_COMPLETED",
                    "ACTION_GATE_CONFIRM",
                    "CONFIRMATION_REQUESTED",
                    "CONFIRMATION_REJECTED",
                    "TASK_CANCEL_REQUESTED",
                    "TASK_CANCELLED",
                ],
            })
            case_idx += 1

    # 5. Hard Policy Blocked Operations (40 cases)
    blocked_templates = [
        ("shutdown_system", {}, "shutdown my computer", "Shutdown My Computer", "System shutdown is blocked by security policy."),
        ("restart_system", {}, "restart pc", "Restart Pc", "System restart is blocked by security policy."),
        ("execute_shell", {"command": "powershell format C:"}, "format drive c:", "Format Drive C:", "Raw shell execution is strictly prohibited."),
        ("open_file", {"path": "malicious.bat"}, "open malicious.bat", "Open Malicious.bat", "Executable scripts cannot be opened directly."),
    ]
    for rep in range(10):
        for cap_id, args, req, title, reason in blocked_templates:
            cases.append({
                "id": f"TASK-BLOCK-{case_idx:04d}",
                "category": "hard_policy_blocked",
                "request_text": f"{req} #{rep}",
                "capability_id": cap_id,
                "arguments": args,
                "expected_title": title,
                "expected_final_status": "BLOCKED",
                "expected_block_reason": reason,
                "expected_event_sequence": [
                    "TASK_CREATED",
                    "NLP_PARSE_STARTED",
                    "NLP_PARSE_COMPLETED",
                    "ACTION_GATE_BLOCK",
                    "TASK_BLOCKED",
                ],
            })
            case_idx += 1

    # 6. Ambiguous Entity Clarification (30 cases)
    clarify_templates = [
        ("focus_application", {"app": "code"}, "focus vscode", ["AstraRun — VS Code", "AI-Bridge — VS Code"], "Focus Vscode"),
        ("open_project", {"project_id": "sem5"}, "open sem5", ["sem5-yolo", "sem5-crypto", "sem5-research"], "Open Sem5"),
        ("focus_application", {"app": "chrome"}, "focus browser", ["Google Chrome — GitHub", "Google Chrome — Docs"], "Focus Browser"),
    ]
    for rep in range(10):
        for cap_id, args, req, cands, title in clarify_templates:
            cases.append({
                "id": f"TASK-CLARIFY-{case_idx:04d}",
                "category": "ambiguous_entity_clarification",
                "request_text": f"{req} #{rep}",
                "capability_id": cap_id,
                "arguments": args,
                "candidates": cands,
                "selected_candidate_idx": 0,
                "expected_title": title,
                "expected_final_status": "COMPLETED",
                "expected_event_sequence": [
                    "TASK_CREATED",
                    "NLP_PARSE_STARTED",
                    "NLP_PARSE_COMPLETED",
                    "ENTITY_RESOLUTION_STARTED",
                    "ENTITY_AMBIGUOUS",
                    "ACTION_GATE_CLARIFY",
                    "CLARIFICATION_REQUESTED",
                    "CLARIFICATION_RESOLVED",
                    "CAPABILITY_STARTED",
                    "CAPABILITY_COMPLETED",
                    "TASK_COMPLETED",
                ],
            })
            case_idx += 1

    # 7. Cooperative Cancellation (30 cases)
    cancel_templates = [
        ("find_file", {"pattern": "*.log"}, "search all log files", "Search All Log Files"),
        ("list_processes", {"limit": 100}, "list all processes", "List All Processes"),
        ("list_network_connections", {}, "list all tcp connections", "List All Tcp Connections"),
    ]
    for rep in range(10):
        for cap_id, args, req, title in cancel_templates:
            cases.append({
                "id": f"TASK-CANCEL-{case_idx:04d}",
                "category": "cooperative_cancellation",
                "request_text": f"{req} #{rep}",
                "capability_id": cap_id,
                "arguments": args,
                "cancel_point": "BEFORE_COMPLETION",
                "expected_title": title,
                "expected_final_status": "CANCELLED",
                "expected_event_sequence": [
                    "TASK_CREATED",
                    "NLP_PARSE_STARTED",
                    "NLP_PARSE_COMPLETED",
                    "TASK_CANCEL_REQUESTED",
                    "TASK_CANCELLED",
                ],
            })
            case_idx += 1

    # 8. Partial Completion on Step Failure (20 cases)
    for rep in range(10):
        cases.append({
            "id": f"TASK-PARTIAL-{case_idx:04d}",
            "category": "partial_completion_failure",
            "request_text": f"open AstraRun and fail step #{rep}",
            "workflow_steps": [
                ("open_project_in_vscode", {"project_id": "astrarun"}, True),
                ("inspect_port", {"port": -999}, False),  # Failing step
            ],
            "expected_final_status": "PARTIALLY_COMPLETED",
            "expected_event_sequence": [
                "TASK_CREATED",
                "WORKFLOW_STARTED",
                "WORKFLOW_STEP_STARTED",
                "WORKFLOW_STEP_COMPLETED",
                "WORKFLOW_STEP_STARTED",
                "WORKFLOW_STEP_FAILED",
                "WORKFLOW_COMPLETED",
                "TASK_COMPLETED",
            ],
        })
        case_idx += 1

    # 9. Crash Recovery Interrupted Tasks (20 cases)
    for rep in range(20):
        cases.append({
            "id": f"TASK-INTERRUPT-{case_idx:04d}",
            "category": "crash_recovery_interrupted",
            "request_text": f"dangling active request #{rep}",
            "initial_status": "RUNNING",
            "expected_final_status": "INTERRUPTED",
            "expected_error_code": "INTERRUPTED",
        })
        case_idx += 1

    # 10. Semantic Re-Run Evaluation (20 cases)
    rerun_templates = [
        ("stop the process on port 3000", "Inspect Port 3000", "terminate_process", {"pid": 9999}),
        ("open AstraRun in vscode", "Open Astrarun In VS Code", "open_project_in_vscode", {"project_id": "astrarun"}),
    ]
    for rep in range(10):
        for req, title, cap, stale_args in rerun_templates:
            cases.append({
                "id": f"TASK-RERUN-{case_idx:04d}",
                "category": "re_run_semantic_reevaluation",
                "original_request": f"{req} (orig #{rep})",
                "stale_args": stale_args,
                "expected_behavior": "NEW_TASK_WITH_CURRENT_STATE",
                "prohibited_behavior": "REPLAY_STALE_ARGS",
                "expected_final_status": "COMPLETED",
            })
            case_idx += 1

    return cases


def main() -> None:
    cases = generate_cases()
    output_dir = Path(__file__).resolve().parent.parent / "benchmarks" / "tasks"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "task_benchmark_v1.json"

    data = {
        "benchmark_name": "AstraRun Task Benchmark V1",
        "version": "1.0.0",
        "description": "Deterministic lifecycle, state transitions, event sequences, and persistence benchmark.",
        "case_count": len(cases),
        "cases": cases,
    }

    serialized = json.dumps(data, indent=2)
    output_file.write_text(serialized, encoding="utf-8")
    sha256 = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    print(f"Generated {len(cases)} benchmark test cases.")
    print(f"Target: {output_file}")
    print(f"SHA256: {sha256}")


if __name__ == "__main__":
    main()
