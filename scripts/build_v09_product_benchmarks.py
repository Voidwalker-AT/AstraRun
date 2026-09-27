"""Build script generating deterministic AstraRun v0.9 Product Benchmark V1.

Generates 220 structured test cases across 6 core product integration categories:
1. Fast-Path Deterministic Launcher (< 3ms) (50 cases)
2. Direct System Navigation & UI Commands (40 cases)
3. Window Intelligence & Management (40 cases)
4. Workstation Inspection & System Capabilities (40 cases)
5. ActionGate Safety Policies & Confirmations (25 cases)
6. Unconfigured AI Bridge Reasoning Escalation (25 cases)
"""

from __future__ import annotations

import json
from pathlib import Path


def generate_product_cases() -> list[dict]:
    cases: list[dict] = []
    case_idx = 1

    # Category 1: Fast-Path Deterministic Launcher (50 cases)
    fast_apps = [
        ("calc", "open_application"),
        ("notepad", "open_application"),
        ("code", "open_application"),
        ("cmd", "open_application"),
        ("pwsh", "open_application"),
        ("explorer", "open_application"),
        ("calculator", "open_application"),
        ("editor", "open_application"),
        ("notes", "open_application"),
        ("terminal", "open_application"),
    ]
    prefixes = ["", "open ", "launch ", "start ", "run "]
    for app_name, exp_tool in fast_apps:
        for prefix in prefixes:
            query = f"{prefix}{app_name}".strip()
            cases.append({
                "id": f"pb_{case_idx:03d}",
                "category": "fast_path",
                "query": query,
                "expected_type": "fast_path",
                "expected_success": True,
            })
            case_idx += 1

    # Category 2: Direct System Navigation & UI Commands (40 cases)
    direct_commands = [
        # History
        ("history", "command", "open_history"),
        ("open history", "command", "open_history"),
        ("show history", "command", "open_history"),
        # Memory
        ("memory", "command", "open_memory"),
        ("open memory", "command", "open_memory"),
        ("show memory", "command", "open_memory"),
        ("learned aliases", "command", "open_memory"),
        # Skills
        ("skills", "command", "open_skills"),
        ("open skills", "command", "open_skills"),
        ("show skills", "command", "open_skills"),
        ("learned skills", "command", "open_skills"),
        # Settings
        ("settings", "command", "open_settings"),
        ("open settings", "command", "open_settings"),
        ("preferences", "command", "open_settings"),
        ("config", "command", "open_settings"),
        # Diagnostics
        ("diagnostics", "command", "open_diagnostics"),
        ("open diagnostics", "command", "open_diagnostics"),
        ("system diagnostics", "command", "open_diagnostics"),
        ("show diagnostics", "command", "open_diagnostics"),
        # Capabilities / Help
        ("what can you do?", "list_result", "capabilities"),
        ("help", "list_result", "capabilities"),
        ("capabilities", "list_result", "capabilities"),
        ("commands", "list_result", "capabilities"),
        # Undo
        ("undo", "capability_result", "undo"),
        ("undo window", "capability_result", "undo"),
        ("undo last window move", "capability_result", "undo"),
        ("undo layout", "capability_result", "undo"),
    ]
    # Replicate to reach 40
    for i in range(40):
        q, exp_t, exp_m = direct_commands[i % len(direct_commands)]
        cases.append({
            "id": f"pb_{case_idx:03d}",
            "category": "direct_ui_command",
            "query": q,
            "expected_type": exp_t,
            "expected_match": exp_m,
            "expected_success": True,
        })
        case_idx += 1

    # Category 3: Window Intelligence & Management (40 cases)
    window_queries = [
        ("list windows", "list_result", True),
        ("foreground window", "capability_result", True),
        ("snap this window left", "capability_result", True),
        ("snap this window right", "capability_result", True),
        ("maximize this window", "capability_result", True),
        ("minimize this window", "capability_result", True),
        ("restore this window", "capability_result", True),
        ("undo window", "capability_result", True),
    ]
    for i in range(40):
        q, exp_t, exp_s = window_queries[i % len(window_queries)]
        cases.append({
            "id": f"pb_{case_idx:03d}",
            "category": "window_management",
            "query": q,
            "expected_type": exp_t,
            "expected_success": exp_s,
        })
        case_idx += 1

    # Category 4: Workstation Inspection & System Capabilities (40 cases)
    system_queries = [
        ("cpu status", "capability_result"),
        ("memory status", "capability_result"),
        ("disk status", "capability_result"),
        ("battery status", "capability_result"),
        ("gpu status", "capability_result"),
        ("audio status", "capability_result"),
        ("system summary", "capability_result"),
        ("list listening ports", "capability_result"),
        ("list running applications", "capability_result"),
        ("list processes", "capability_result"),
    ]
    for i in range(40):
        q, exp_t = system_queries[i % len(system_queries)]
        cases.append({
            "id": f"pb_{case_idx:03d}",
            "category": "system_inspection",
            "query": q,
            "expected_type": exp_t,
            "expected_success": True,
        })
        case_idx += 1

    # Category 5: ActionGate Safety Policies & Confirmations (25 cases)
    safety_queries = [
        ("terminate process 4", "blocked"),       # System PID 4 blocked
        ("kill process 0", "blocked"),            # System Idle Process blocked
        ("terminate process csrss", "blocked"),    # Protected system process blocked
        ("terminate process lsass", "blocked"),    # Protected system process blocked
        ("close application system", "blocked"),   # Prohibited system close
    ]
    for i in range(25):
        q, exp_t = safety_queries[i % len(safety_queries)]
        cases.append({
            "id": f"pb_{case_idx:03d}",
            "category": "safety_policies",
            "query": q,
            "expected_type": exp_t,
            "expected_blocked": True,
        })
        case_idx += 1

    # Category 6: Unconfigured AI Bridge Reasoning Escalation (25 cases)
    reasoning_queries = [
        "why is the system slow?",
        "diagnose high memory usage and suggest fixes",
        "why is my build failing?",
        "analyze which application is draining my battery",
        "how do I optimize my python performance?",
    ]
    for i in range(25):
        q = reasoning_queries[i % len(reasoning_queries)]
        cases.append({
            "id": f"pb_{case_idx:03d}",
            "category": "reasoning_escalation",
            "query": q,
            "expected_type": "reasoning_required",
            "expected_success": True,
        })
        case_idx += 1

    return cases


def main():
    cases = generate_product_cases()
    out_dir = Path("benchmarks/product")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "product_benchmark_v1.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)

    print(f"[OK] Generated {len(cases)} deterministic product benchmark cases to {out_path}")


if __name__ == "__main__":
    main()
