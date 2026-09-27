"""Benchmark Execution Harness for AstraRun v0.9 Product Integration (Product Benchmark V1).

Evaluates 220 deterministic test cases across 6 core product integration categories.
Verifies Fast-Path Launcher latency (< 3ms routing), 0.00% False Execution Rate,
ActionGate Safety Policies, and Unconfigured AI Bridge Escalation.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from astrarun.app import AstraApplication
from astrarun.capabilities.models import WindowEntity
from astrarun.windows.models import WindowLayoutSnapshot
from astrarun.windows.policy import set_simulated_window_validation

EXPECTED_SHA256 = "a417eacbe201ce4b095286682013c043129ed8d188f56b30b5567d5ff2abb395"


def run_product_benchmark(benchmark_file: Path | str = "benchmarks/product/product_benchmark_v1.json") -> dict[str, Any]:
    file_path = Path(benchmark_file)
    data = file_path.read_bytes()
    actual_sha256 = hashlib.sha256(data).hexdigest()

    cases = json.loads(data.decode("utf-8"))
    total_cases = len(cases)

    # Enable simulated window validation so real OS windows are not moved
    set_simulated_window_validation(True)

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
            app.restore_stack.push(WindowLayoutSnapshot(
                hwnd=1002,
                pid=1100,
                title="Code",
                bounds=(0, 0, 100, 100),
                state="normal",
                monitor_id=1,
            ))

        t0 = time.perf_counter()
        res = app.handle_request(query, origin_window=mock_origin, dry_run=True)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt_ms)

        passed = False

        if cat == "fast_path":
            # Pure deterministic routing check
            t_route_0 = time.perf_counter()
            decision = app.deterministic_router.route(query, app.routing_context)
            fast_path_latencies.append((time.perf_counter() - t_route_0) * 1000.0)

            if res.type == "fast_path" and res.success:
                passed = True

        elif cat == "direct_ui_command":
            if res.type == case["expected_type"] and res.success:
                passed = True

        elif cat == "window_management":
            if res.type in ("capability_result", "list_result", "clarify") and res.success == case["expected_success"]:
                passed = True

        elif cat == "system_inspection":
            if res.type in ("capability_result", "list_result") and res.success:
                passed = True

        elif cat == "safety_policies":
            if res.type in ("blocked", "confirm", "error") and not res.success:
                passed = True
            elif res.success:
                false_executions += 1
                safety_violations += 1

        elif cat == "reasoning_escalation":
            if res.type == "reasoning_required" and res.success and res.data:
                passed = True

        if passed:
            category_passed[cat] = category_passed.get(cat, 0) + 1

    # Reset simulated validation
    set_simulated_window_validation(False)

    total_passed = sum(category_passed.values())
    accuracy_pct = (total_passed / total_cases) * 100.0
    false_exec_rate = (false_executions / total_cases) * 100.0
    avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    mean_fp_latency = sum(fast_path_latencies) / len(fast_path_latencies) if fast_path_latencies else 0.0

    results = {
        "benchmark_file": str(benchmark_file),
        "dataset_sha256": actual_sha256,
        "sha256_match": actual_sha256 == EXPECTED_SHA256,
        "total_cases": total_cases,
        "total_passed": total_passed,
        "accuracy_pct": round(accuracy_pct, 4),
        "false_execution_rate": round(false_exec_rate, 4),
        "safety_violations": safety_violations,
        "mean_latency_ms": round(avg_latency, 4),
        "mean_fast_path_routing_latency_ms": round(mean_fp_latency, 4),
        "category_results": {
            cat: {
                "total": category_counts[cat],
                "passed": category_passed.get(cat, 0),
                "accuracy_pct": round((category_passed.get(cat, 0) / category_counts[cat]) * 100.0, 2),
            }
            for cat in category_counts
        },
    }

    # Write summary
    res_path = Path("benchmarks/product/product_benchmark_results.json")
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results


def main():
    print("=" * 60)
    print("ASTRARUN v0.9 PRODUCT BENCHMARK V1 EVALUATION")
    print("=" * 60)

    res = run_product_benchmark()

    print(f"Total Cases:                      {res['total_cases']}")
    print(f"Passed:                           {res['total_passed']}")
    print(f"Overall Accuracy:                 {res['accuracy_pct']}%")
    print(f"False Execution Rate:             {res['false_execution_rate']}%")
    print(f"Safety Violations:                {res['safety_violations']}")
    print(f"Mean Fast-Path Routing Latency:   {res['mean_fast_path_routing_latency_ms']} ms (< 3ms invariant)")
    print(f"Mean End-to-End Latency:          {res['mean_latency_ms']} ms")
    print(f"Dataset SHA-256 Match:            {res['sha256_match']}")
    print("\nCategory Breakdown:")
    for cat, data in res["category_results"].items():
        print(f"  - {cat:28s}: {data['passed']}/{data['total']} ({data['accuracy_pct']}%)")
    print("=" * 60)

    if res["accuracy_pct"] == 100.0 and res["false_execution_rate"] == 0.0 and res["mean_fast_path_routing_latency_ms"] < 3.0:
        print("[SUCCESS] Product Benchmark V1 PASSED with 100% accuracy, 0.00% False Execution Rate, and < 3ms fast path.")
    else:
        print("[FAILURE] Product Benchmark V1 did not achieve perfect metrics.")
        exit(1)


if __name__ == "__main__":
    main()
