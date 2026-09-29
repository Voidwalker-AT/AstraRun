"""AstraRun v0.10.3 — Neural NLP Benchmark Runner.

Evaluates the NeuralStructureEngine against frozen benchmark datasets:
- Dev set: benchmarks/nlp_neural/neural_nlp_dev_v1.json (520 items)
- Test set: benchmarks/nlp_neural/neural_nlp_test_v1.json (320 items)

Target Acceptance Invariants:
- Intent Accuracy: >= 95.0%
- Negation Accuracy: >= 98.0%
- Literal Payload Preservation: 100.0%
- Latency (p95): < 50.0ms
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from astrarun.nlp.structure_engine import NeuralStructureEngine


def canonicalize_intent(intent: str) -> str:
    """Canonicalize specific sub-intents to benchmark reference taxonomy."""
    intent_norm = intent.lower().strip()
    if intent_norm.startswith("snap_window"):
        return "snap_window"
    if intent_norm in ("cpu_status", "memory_status", "gpu_status", "battery_status", "system_summary", "disk_status"):
        return "system_status"
    if intent_norm in ("close_application", "kill_process", "terminate_process"):
        return "close_app" if "app" in intent_norm or "process" in intent_norm else "close_window"
    if intent_norm in ("open_application", "open_project"):
        return "open_app"
    if intent_norm in ("click_ui_element", "ui_click"):
        return "ui_click"
    if intent_norm in ("press_keyboard_shortcut", "press_key"):
        return "press_key"
    if intent_norm in ("focus_ui_element", "ui_focus"):
        return "ui_focus"
    if intent_norm in ("select_ui_element", "ui_select"):
        return "ui_select"
    if intent_norm in ("unsupported", "unknown"):
        return "unknown"
    if intent_norm in ("focus_application", "focus_window"):
        return "focus_window"
    if intent_norm in ("search_web", "open_url"):
        return "open_url"
    return intent_norm


@dataclass
class SplitMetrics:
    split_name: str
    total_samples: int
    compound_accuracy: float
    negation_accuracy: float
    intent_accuracy: float
    literal_preservation_rate: float
    span_exactness_rate: float
    latency_mean_ms: float
    latency_p50_ms: float
    latency_p90_ms: float
    latency_p95_ms: float
    latency_max_ms: float
    targets_met: bool


def evaluate_split(
    engine: NeuralStructureEngine,
    dataset_path: str,
    split_name: str
) -> tuple[SplitMetrics, list[dict[str, Any]]]:
    """Evaluate a single dataset split and return detailed metrics."""
    with open(dataset_path, "r", encoding="utf-8") as f:
        samples = json.load(f)

    total = len(samples)
    compound_correct = 0
    negation_correct = 0
    intent_correct = 0
    total_clauses = 0

    literal_expected_count = 0
    literal_exact_count = 0
    span_exact_count = 0

    latencies: list[float] = []
    failures: list[dict[str, Any]] = []

    # Warmup
    engine.parse("open notepad and type warmup")

    for sample in samples:
        query = sample["query"]
        t0 = time.perf_counter()
        parsed = engine.parse(query)
        t_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(t_ms)

        # 1. Compound detection
        is_comp_match = (parsed.is_compound == sample["is_compound"])
        if is_comp_match:
            compound_correct += 1

        # 2. Negation detection
        neg_match = (parsed.has_negation == sample["has_negation"])
        if neg_match:
            negation_correct += 1

        # 3. Intent accuracy across clauses
        sample_clauses = sample["clauses"]
        clause_intent_ok = True

        for idx, exp_c in enumerate(sample_clauses):
            total_clauses += 1
            exp_intent = canonicalize_intent(exp_c["intent"])

            if idx < len(parsed.clauses):
                actual_clause = parsed.clauses[idx]
                act_intent = canonicalize_intent(actual_clause.intent)
                if act_intent == exp_intent:
                    intent_correct += 1
                else:
                    clause_intent_ok = False
            else:
                clause_intent_ok = False

        # 4. Literal payload preservation
        for idx, exp_c in enumerate(sample_clauses):
            exp_payload = exp_c.get("payload")
            if exp_payload:
                literal_expected_count += 1
                if idx < len(parsed.clauses):
                    actual_clause = parsed.clauses[idx]
                    if actual_clause.payload is not None:
                        # Verbatim match
                        if actual_clause.payload.text == exp_payload["text"]:
                            literal_exact_count += 1
                        # Exact character span slice match
                        span = actual_clause.payload.source_span
                        if query[span.start:span.end] == exp_payload["text"]:
                            span_exact_count += 1

        if not (is_comp_match and neg_match and clause_intent_ok):
            failures.append({
                "id": sample["id"],
                "query": query,
                "category": sample.get("category", ""),
                "expected_intent": [canonicalize_intent(c["intent"]) for c in sample_clauses],
                "actual_intent": [canonicalize_intent(c.intent) for c in parsed.clauses],
                "expected_negation": sample["has_negation"],
                "actual_negation": parsed.has_negation,
            })

    # Sort latencies for percentiles
    latencies.sort()
    p50 = latencies[int(0.50 * total)]
    p90 = latencies[int(0.90 * total)]
    p95 = latencies[int(0.95 * total)]
    mean_lat = sum(latencies) / total
    max_lat = latencies[-1]

    comp_acc = (compound_correct / total) * 100.0
    neg_acc = (negation_correct / total) * 100.0
    intent_acc = (intent_correct / total_clauses) * 100.0 if total_clauses else 100.0

    literal_rate = (literal_exact_count / literal_expected_count) * 100.0 if literal_expected_count else 100.0
    span_rate = (span_exact_count / literal_expected_count) * 100.0 if literal_expected_count else 100.0

    targets_met = (
        intent_acc >= 95.0
        and neg_acc >= 98.0
        and literal_rate == 100.0
        and span_rate == 100.0
        and p95 < 50.0
    )

    metrics = SplitMetrics(
        split_name=split_name,
        total_samples=total,
        compound_accuracy=round(comp_acc, 2),
        negation_accuracy=round(neg_acc, 2),
        intent_accuracy=round(intent_acc, 2),
        literal_preservation_rate=round(literal_rate, 2),
        span_exactness_rate=round(span_rate, 2),
        latency_mean_ms=round(mean_lat, 2),
        latency_p50_ms=round(p50, 2),
        latency_p90_ms=round(p90, 2),
        latency_p95_ms=round(p95, 2),
        latency_max_ms=round(max_lat, 2),
        targets_met=targets_met,
    )

    return metrics, failures


def main() -> int:
    print("=" * 80)
    print("ASTRARUN v0.10.3 — NEURAL NLP BENCHMARK RUNNER")
    print("=" * 80)

    base_dir = Path(__file__).resolve().parent
    dev_path = base_dir / "neural_nlp_dev_v1.json"
    test_path = base_dir / "neural_nlp_test_v1.json"

    if not dev_path.exists() or not test_path.exists():
        print(f"Error: Dataset files not found at {base_dir}")
        return 1

    engine = NeuralStructureEngine()

    print(f"\n[1/2] Evaluating Dev Split ({dev_path.name})...")
    dev_metrics, dev_failures = evaluate_split(engine, str(dev_path), "dev_v1")

    print(f"[2/2] Evaluating Test Split ({test_path.name})...")
    test_metrics, test_failures = evaluate_split(engine, str(test_path), "test_v1")

    # Display results table
    print("\n" + "=" * 80)
    print(f"{'Metric':<32} | {'Target':<10} | {'Dev Split':<14} | {'Test Split':<14}")
    print("-" * 80)
    print(f"{'Total Samples':<32} | {'--':<10} | {dev_metrics.total_samples:<14} | {test_metrics.total_samples:<14}")
    print(f"{'Compound Accuracy':<32} | {'>= 95.0%':<10} | {dev_metrics.compound_accuracy:>6.2f}%       | {test_metrics.compound_accuracy:>6.2f}%")
    print(f"{'Negation Accuracy':<32} | {'>= 98.0%':<10} | {dev_metrics.negation_accuracy:>6.2f}%       | {test_metrics.negation_accuracy:>6.2f}%")
    print(f"{'Intent Accuracy':<32} | {'>= 95.0%':<10} | {dev_metrics.intent_accuracy:>6.2f}%       | {test_metrics.intent_accuracy:>6.2f}%")
    print(f"{'Literal Preservation':<32} | {'100.0%':<10} | {dev_metrics.literal_preservation_rate:>6.2f}%       | {test_metrics.literal_preservation_rate:>6.2f}%")
    print(f"{'Span Exactness (Offsets)':<32} | {'100.0%':<10} | {dev_metrics.span_exactness_rate:>6.2f}%       | {test_metrics.span_exactness_rate:>6.2f}%")
    print(f"{'Latency p50':<32} | {'--':<10} | {dev_metrics.latency_p50_ms:>6.2f}ms       | {test_metrics.latency_p50_ms:>6.2f}ms")
    print(f"{'Latency p95':<32} | {'< 50.0ms':<10} | {dev_metrics.latency_p95_ms:>6.2f}ms       | {test_metrics.latency_p95_ms:>6.2f}ms")
    print(f"{'Latency Max':<32} | {'--':<10} | {dev_metrics.latency_max_ms:>6.2f}ms       | {test_metrics.latency_max_ms:>6.2f}ms")
    print("=" * 80)

    all_passed = dev_metrics.targets_met and test_metrics.targets_met
    print(f"\nFinal Acceptance Verdict: {'PASSED [ALL TARGETS MET]' if all_passed else 'FAILED [TARGETS NOT MET]'}")

    # Save JSON summary
    summary_path = base_dir / "benchmark_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump({
            "dev_metrics": asdict(dev_metrics),
            "test_metrics": asdict(test_metrics),
            "dev_failures_count": len(dev_failures),
            "test_failures_count": len(test_failures),
            "passed": all_passed,
            "timestamp": time.time(),
        }, f, indent=2)
    print(f"Summary persisted to {summary_path}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
