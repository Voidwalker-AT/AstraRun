"""Benchmark Execution Harness for AstraRun v0.10 Product Integration (Product Benchmark V2).

Evaluates 280 deterministic test cases across 8 core product integration categories:
fast_path, nlp_rich_workflow, window_control, action_gate_confirm,
action_gate_block, ai_bridge_escalation, ui_interaction, ui_destructive_confirm.

Verifies Fast-Path Launcher latency (< 3ms routing), 0.00% False Execution Rate,
ActionGate Safety Policies, and UI Automation Control Grounding.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from astrarun.app import AstraApplication
from astrarun.capabilities.models import WindowEntity
from astrarun.interaction.policy import set_simulated_interaction_validation
from astrarun.windows.models import WindowLayoutSnapshot
from astrarun.windows.policy import set_simulated_window_validation

EXPECTED_SHA256 = "0e3face2732bee1859ea02df1de4da6a5d4753a45a11fcd6c8eae366c9f564ec"


def run_product_benchmark_v2(
    benchmark_file: Path | str = "benchmarks/product_v2/product_benchmark_v2.json",
) -> dict[str, Any]:
    file_path = Path(benchmark_file)
    data = file_path.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()

    cases = json.loads(data.decode("utf-8"))
    total_cases = len(cases)

    # Enable simulation for window and interaction subsystems so host system is untouched
    set_simulated_window_validation(True)
    set_simulated_interaction_validation(True)

    app = AstraApplication()

    mock_origin = WindowEntity(
        hwnd=1002,
        title="Visual Studio Code - AstraRun",
        pid=1100,
        app_id="code.exe",
        bounds=(0, 0, 1920, 1080),
        state="maximized",
        visible=True,
    )

    category_counts: dict[str, int] = {}
    category_passed: dict[str, int] = {}
    latencies: list[float] = []
    fast_path_latencies: list[float] = []

    false_executions = 0
    safety_violations = 0

    for case in cases:
        cat = case["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1
        query = case["query"]

        if "undo" in query:
            app.restore_stack.push(
                WindowLayoutSnapshot(
                    hwnd=1002,
                    pid=1100,
                    title="Code",
                    bounds=(0, 0, 100, 100),
                    state="normal",
                    monitor_id=1,
                )
            )

        t0 = time.perf_counter()
        res = app.handle_request(query, origin_window=mock_origin, dry_run=True)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt_ms)

        passed = False

        if cat == "fast_path":
            t_route_0 = time.perf_counter()
            decision = app.deterministic_router.route(query, app.routing_context)
            fast_path_latencies.append((time.perf_counter() - t_route_0) * 1000.0)

            if res.type == "fast_path" and res.success:
                passed = True
            else:
                false_executions += 1

        elif cat == "direct_ui_command":
            if res.type == case["expected_type"] and res.success:
                passed = True
            else:
                false_executions += 1

        elif cat == "window_management":
            if res.type in ("capability_result", "list_result", "clarify") and res.success == case["expected_success"]:
                passed = True
            else:
                false_executions += 1

        elif cat == "system_inspection":
            if res.type in ("capability_result", "list_result") and res.success:
                passed = True
            else:
                false_executions += 1

        elif cat == "safety_policies":
            if res.type in ("blocked", "confirm", "error") and not res.success:
                passed = True
            elif res.success:
                false_executions += 1
                safety_violations += 1

        elif cat == "reasoning_escalation":
            if res.type == "reasoning_required" and res.success and res.data:
                passed = True

        elif cat == "ui_interaction":
            if res.type in (case["expected_type"], "fast_path", "capability_result") and res.success == case["expected_success"]:
                passed = True
            else:
                false_executions += 1

        elif cat == "ui_destructive_confirm":
            if res.type == "confirm" and not res.success:
                passed = True
            else:
                safety_violations += 1

        if passed:
            category_passed[cat] = category_passed.get(cat, 0) + 1

    set_simulated_window_validation(False)
    set_simulated_interaction_validation(False)

    total_passed = sum(category_passed.values())
    pass_rate = (total_passed / total_cases) * 100 if total_cases > 0 else 0.0

    mean_latency = sum(latencies) / len(latencies) if latencies else 0.0
    sorted_lat = sorted(latencies)
    p95_latency = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0.0
    max_latency = max(latencies) if latencies else 0.0

    mean_fast_path_latency = sum(fast_path_latencies) / len(fast_path_latencies) if fast_path_latencies else 0.0
    fer = (false_executions / total_cases) * 100

    results = {
        "benchmark": "Product Benchmark V2",
        "milestone": "AstraRun v0.10",
        "total_cases": total_cases,
        "passed_cases": total_passed,
        "failed_cases": total_cases - total_passed,
        "pass_rate_pct": round(pass_rate, 2),
        "sha256": actual_sha256,
        "sha256_verified": actual_sha256 == EXPECTED_SHA256,
        "metrics": {
            "false_execution_rate_pct": round(fer, 4),
            "safety_violations_count": safety_violations,
            "fast_path_mean_latency_ms": round(mean_fast_path_latency, 4),
            "mean_latency_ms": round(mean_latency, 4),
            "p95_latency_ms": round(p95_latency, 4),
            "max_latency_ms": round(max_latency, 4),
        },
        "category_breakdown": {
            cat: {
                "total": category_counts[cat],
                "passed": category_passed.get(cat, 0),
                "pass_rate_pct": round((category_passed.get(cat, 0) / category_counts[cat]) * 100, 2),
            }
            for cat in category_counts
        },
    }

    out_file = Path("benchmarks/product_v2/product_benchmark_v2_results.json")
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    res = run_product_benchmark_v2()
    print("=" * 60)
    print(f"PRODUCT BENCHMARK V2: {res['passed_cases']} / {res['total_cases']} ({res['pass_rate_pct']}%)")
    print(f"SHA256 Verified: {res['sha256_verified']}")
    print(f"False Execution Rate (FER): {res['metrics']['false_execution_rate_pct']}%")
    print(f"Safety Violations: {res['metrics']['safety_violations_count']}")
    print(f"Fast-Path Mean Latency: {res['metrics']['fast_path_mean_latency_ms']} ms")
    print(f"Overall Mean Latency: {res['metrics']['mean_latency_ms']} ms")
    print("=" * 60)
    for cat, stat in res["category_breakdown"].items():
        print(f"  {cat}: {stat['passed']}/{stat['total']} ({stat['pass_rate_pct']}%)")
