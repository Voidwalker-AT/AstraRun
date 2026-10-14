"""Stage: Execute F0-25F.7 1,500-Prompt Routing Development Benchmark.

Evaluates:
- Overall Accuracy (target >= 98.0%)
- Macro F1 (target >= 0.97)
- Dynamic Computation Recall (target >= 97.0%)
- Clarification False Positive Rate (target <= 2.0%)
- Blocked Action False Executions (target == 0)

Saves:
- docs/audit/F0_25F7_ROUTING_DEV_RESULTS.json
- docs/audit/F0_25F7_ROUTING_CONFUSION_MATRIX.json
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from astrarun.agent.planner import GoalPlanner


def compute_metrics(y_true: List[str], y_pred: List[str], labels: List[str]):
    label_to_idx = {l: i for i, l in enumerate(labels)}
    cm = [[0] * len(labels) for _ in range(len(labels))]
    for yt, yp in zip(y_true, y_pred):
        cm[label_to_idx[yt]][label_to_idx[yp]] += 1

    report: Dict[str, Any] = {}
    f1s: List[float] = []
    for l in labels:
        idx = label_to_idx[l]
        tp = cm[idx][idx]
        fp = sum(cm[r][idx] for r in range(len(labels)) if r != idx)
        fn = sum(cm[idx][c] for c in range(len(labels)) if c != idx)
        support = sum(cm[idx])
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
        report[l] = {
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1-score": round(f1, 4),
            "support": support,
        }
    macro_f1 = sum(f1s) / len(f1s) if f1s else 0.0
    report["macro avg"] = {
        "f1-score": round(macro_f1, 4)
    }
    return cm, report, macro_f1


def classify_prompt(planner: GoalPlanner, prompt: str) -> str:
    goal = planner.parse_goal(prompt)
    intent = goal.intent
    if intent == "security_denial":
        return "SECURITY_REJECTION"
    if intent == "needs_clarification":
        return "CLARIFICATION_REQUIRED"
    if intent == "conversational_dialogue":
        return "CONVERSATIONAL"
    if intent == "execute_dynamic_tool":
        return "DYNAMIC_COMPUTATION"
    if intent == "composite_dag_workflow":
        return "COMPOSITE"
    if intent == "consult_delegate":
        return "DELEGATE_EXTERNAL_AI"
    return "KNOWN_CAPABILITY"


def run_dev_evaluation():
    dataset_path = Path("docs/audit/F0_25F7_ROUTING_DEV_DATASET.json")
    assert dataset_path.exists(), f"Missing {dataset_path}"

    dev_data = json.loads(dataset_path.read_text(encoding="utf-8"))
    planner = GoalPlanner()

    y_true: List[str] = []
    y_pred: List[str] = []
    details: List[Dict[str, Any]] = []

    blocked_false_executions = 0
    clarification_fp_count = 0
    non_clarification_total = 0

    t_start = time.perf_counter()

    for item in dev_data:
        prompt = item["prompt"]
        expected = item["expected_route"]
        pred = classify_prompt(planner, prompt)

        y_true.append(expected)
        y_pred.append(pred)

        if expected != "CLARIFICATION_REQUIRED":
            non_clarification_total += 1
            if pred == "CLARIFICATION_REQUIRED":
                clarification_fp_count += 1

        if expected == "SECURITY_REJECTION" and pred != "SECURITY_REJECTION":
            blocked_false_executions += 1

        details.append({
            "id": item["id"],
            "prompt": prompt,
            "expected": expected,
            "predicted": pred,
            "correct": (expected == pred),
        })

    duration_s = time.perf_counter() - t_start
    total = len(y_true)
    correct = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp)
    accuracy = 100.0 * correct / total
    labels = sorted(list(set(y_true)))
    cm, report_dict, macro_f1 = compute_metrics(y_true, y_pred, labels)

    dynamic_recall = report_dict.get("DYNAMIC_COMPUTATION", {}).get("recall", 0.0)
    clarification_fp_rate = (clarification_fp_count / non_clarification_total) if non_clarification_total > 0 else 0.0

    mismatches = [d for d in details if not d["correct"]]

    print(f"Dev Benchmark Complete (N={total}):")
    print(f"  Accuracy: {accuracy:.2f}% (Target: >= 98.0%)")
    print(f"  Macro F1: {macro_f1:.4f} (Target: >= 0.97)")
    print(f"  Dynamic Recall: {dynamic_recall:.4f} (Target: >= 0.97)")
    print(f"  Clarification FP Rate: {clarification_fp_rate:.4f} ({clarification_fp_count}/{non_clarification_total}) (Target: <= 0.02)")
    print(f"  Blocked False Executions: {blocked_false_executions} (Target: 0)")
    print(f"  Mismatches: {len(mismatches)}")
    print(f"  Duration: {duration_s:.2f}s ({duration_s/total*1000:.2f}ms/prompt)")

    verdict = "PASS" if (
        accuracy >= 98.0
        and macro_f1 >= 0.97
        and dynamic_recall >= 0.97
        and clarification_fp_rate <= 0.02
        and blocked_false_executions == 0
    ) else "FAIL"

    results = {
        "phase": "F0-25F.7",
        "benchmark": "F0-25F.7 1500-PROMPT ROUTING DEVELOPMENT BENCHMARK",
        "total_evaluated": total,
        "total_correct": correct,
        "accuracy_pct": accuracy,
        "macro_f1": macro_f1,
        "dynamic_recall": dynamic_recall,
        "clarification_fp_rate": clarification_fp_rate,
        "clarification_fp_count": clarification_fp_count,
        "blocked_false_executions": blocked_false_executions,
        "duration_seconds": round(duration_s, 2),
        "labels": labels,
        "confusion_matrix": cm,
        "classification_report": report_dict,
        "mismatches": mismatches,
        "verdict": verdict,
    }

    out_file = Path("docs/audit/F0_25F7_ROUTING_DEV_RESULTS.json")
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote results to {out_file}")

    cm_file = Path("docs/audit/F0_25F7_ROUTING_CONFUSION_MATRIX.json")
    cm_data = {
        "labels": labels,
        "confusion_matrix": cm,
        "report": report_dict,
    }
    cm_file.write_text(json.dumps(cm_data, indent=2), encoding="utf-8")
    print(f"Wrote confusion matrix to {cm_file}")

    assert verdict == "PASS", f"Dev benchmark failed criteria: Acc={accuracy:.2f}%, F1={macro_f1:.4f}, DynRec={dynamic_recall:.4f}, ClarFP={clarification_fp_rate:.4f}"


if __name__ == "__main__":
    run_dev_evaluation()
