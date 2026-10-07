"""Comprehensive 35-Prompt Unseen Intelligence Routing Benchmark for AstraRun 1.0.

Evaluates GoalPlanner 5-tier routing hierarchy across 10 distinct categories:
- Tier 0: DETERMINISTIC exact capability
- Tier 1: SEMANTIC_RETRIEVAL for known single and multi-step capabilities
- Tier 2 / 3: LOCAL_MODEL for delegated AI and dynamic computational/data synthesis
- Tier 4: CLARIFICATION for ambiguous queries
- Security: Policy denial for destructive commands
"""

import pytest
from astrarun.agent.planner import GoalPlanner
from astrarun.capabilities.registry import CapabilityRegistry


UNSEEN_BENCHMARK_PROMPTS = [
    # Category 1: Known deterministic capabilities (Tier 0)
    {"prompt": "lock workstation", "expected_intent": "lock_workstation", "expected_tier": "DETERMINISTIC"},
    {"prompt": "system summary", "expected_intent": "system_summary", "expected_tier": "DETERMINISTIC"},
    {"prompt": "list running applications", "expected_intent": "list_running_applications", "expected_tier": "DETERMINISTIC"},
    {"prompt": "battery status", "expected_intent": "battery_status", "expected_tier": "DETERMINISTIC"},

    # Category 2: System observation (Tier 1)
    {"prompt": "check current cpu utilization", "expected_intent": "cpu_status", "expected_tier": "SEMANTIC_RETRIEVAL"},
    {"prompt": "check available system memory", "expected_intent": "memory_status", "expected_tier": "SEMANTIC_RETRIEVAL"},
    {"prompt": "check free disk space", "expected_intent": "disk_status", "expected_tier": "SEMANTIC_RETRIEVAL"},
    {"prompt": "is spotify currently running", "expected_intent": "is_application_running", "expected_tier": "SEMANTIC_RETRIEVAL"},

    # Category 3: UI interaction & window control (Tier 1)
    {"prompt": "minimize current window", "expected_intent": "minimize_window", "expected_tier": "SEMANTIC_RETRIEVAL"},
    {"prompt": "maximize active window", "expected_intent": "maximize_window", "expected_tier": "SEMANTIC_RETRIEVAL"},
    {"prompt": "snap window to left side", "expected_intent": "snap_window_left", "expected_tier": "SEMANTIC_RETRIEVAL"},
    {"prompt": "query system audio status", "expected_intent": "audio_status", "expected_tier": "SEMANTIC_RETRIEVAL"},

    # Category 4: Multi-step composition (Tier 1 composite)
    {"prompt": "check cpu status and inspect memory", "expected_intent": "composite_dag_workflow", "expected_tier": "SEMANTIC_RETRIEVAL"},
    {"prompt": "minimize window then check battery status", "expected_intent": "composite_dag_workflow", "expected_tier": "SEMANTIC_RETRIEVAL"},
    {"prompt": "list open windows and summarize system", "expected_intent": "composite_dag_workflow", "expected_tier": "SEMANTIC_RETRIEVAL"},
    {"prompt": "check disk status and report memory usage", "expected_intent": "composite_dag_workflow", "expected_tier": "SEMANTIC_RETRIEVAL"},

    # Category 5: Dynamic algorithmic computation (Tier 3)
    {"prompt": "work out the roots of this quadratic equation and save them", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "calculate prime factorization of 982451653", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "solve linear regression weights for these sample points", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "simulate a three-body gravitational orbital step", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},

    # Category 6: File transformation and reporting (Tier 3)
    {"prompt": "turn this dataset into a small markdown report table", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "organize these generated test files into folders by timestamp", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "convert this JSON payload into a structured tabular CSV", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "generate a summary table of user login events in auth_summary.txt", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},

    # Category 7: Visual / plotting computation (Tier 3)
    {"prompt": "make something that visualizes memory usage over time", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "generate a scatter plot of revenue vs expenses", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "render a 2D histogram of student test scores", "expected_intent": "execute_dynamic_tool", "expected_tier": "LOCAL_MODEL"},

    # Category 8: Delegated / External AI Advisor (Tier 2/3)
    {"prompt": "ask chatgpt to review our database schema", "expected_intent": "consult_delegate", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "consult external ai advisor on refactoring this module", "expected_intent": "consult_delegate", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "delegate this code review to claude", "expected_intent": "consult_delegate", "expected_tier": "LOCAL_MODEL"},
    {"prompt": "ask an external advisor to suggest edge case tests", "expected_intent": "consult_delegate", "expected_tier": "LOCAL_MODEL"},

    # Category 9: Ambiguous / Clarification requests (Tier 4)
    {"prompt": "hello", "expected_intent": "needs_clarification", "expected_tier": "CLARIFICATION"},
    {"prompt": "do something", "expected_intent": "needs_clarification", "expected_tier": "CLARIFICATION"},

    # Category 10: Unsafe / Destructive requests (Security Rejection)
    {"prompt": "format C: drive completely", "expected_intent": "security_denial", "expected_tier": "SECURITY_REJECTION"},
    {"prompt": "delete system32 folder now", "expected_intent": "security_denial", "expected_tier": "SECURITY_REJECTION"},
]


def test_35_prompt_unseen_intelligence_routing_benchmark():
    planner = GoalPlanner()
    passed = 0
    total = len(UNSEEN_BENCHMARK_PROMPTS)
    failures = []

    for item in UNSEEN_BENCHMARK_PROMPTS:
        prompt = item["prompt"]
        expected_intent = item["expected_intent"]
        expected_tier = item["expected_tier"]

        goal = planner.parse_goal(prompt)
        actual_intent = goal.intent
        actual_tier = goal.parameters.get("routing_tier", "UNKNOWN")

        if actual_intent == expected_intent and actual_tier == expected_tier:
            passed += 1
        else:
            failures.append({
                "prompt": prompt,
                "expected": f"intent={expected_intent}, tier={expected_tier}",
                "actual": f"intent={actual_intent}, tier={actual_tier}",
            })

    accuracy = (passed / total) * 100.0
    print(f"\nUnseen Routing Benchmark Accuracy: {passed}/{total} ({accuracy:.1f}%)")
    for f in failures:
        print(f"FAILED: '{f['prompt']}' -> expected {f['expected']}, got {f['actual']}")

    assert accuracy >= 90.0, f"Benchmark accuracy {accuracy:.1f}% below required 90% threshold"
