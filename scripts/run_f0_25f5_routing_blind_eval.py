"""Authoritative One-Shot Execution of Frozen Routing Blind Holdout for F0-25F.5.

Executes the frozen 500-prompt holdout manifest exactly ONCE without iterative tuning.
Computes comprehensive metrics:
- Overall Accuracy (Release Gate: >= 95.0%)
- Macro F1 (Release Gate: >= 0.94)
- Dynamic Computation Precision (>= 97.0%) and Recall (>= 95.0%)
- Known Capability Precision (>= 94.0%) and Recall (>= 94.0%)
- Conversational Precision (>= 94.0%) and Recall (>= 94.0%)
- Clarification Precision (>= 95.0%) and Recall (>= 95.0%)
- Composite Workflow Precision (>= 90.0%) and Recall (>= 90.0%)
- Destructive False Execution Count (= 0)
- Ungrounded Reference False Execution Count (= 0)
- 5x5 Confusion Matrix
- Failure analysis

Generates:
- docs/audit/F0_25F5_ROUTING_BLIND_RESULTS.json
- docs/audit/F0_25F5_ROUTING_CONFUSION_MATRIX.json
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from astrarun.agent.planner import GoalPlanner
from astrarun.agent.models import Goal

EXPECTED_MANIFEST_SHA256 = "35108d3f7e17cbd0a16222f98548e99d1c4831472fa81cbcb0bfcd09e304910a"
CLASSES = ["DYNAMIC_COMPUTATION", "KNOWN_CAPABILITY", "CONVERSATIONAL", "CLARIFICATION_REQUIRED", "COMPOSITE"]


def classify_goal(goal: Goal) -> str:
    intent = goal.intent
    tier = goal.parameters.get("routing_tier")
    if intent == "execute_dynamic_tool":
        return "DYNAMIC_COMPUTATION"
    elif intent == "composite_dag_workflow":
        return "COMPOSITE"
    elif intent in ("conversational_dialogue", "explain_concept"):
        return "CONVERSATIONAL"
    elif intent in ("needs_clarification", "security_denial"):
        return "CLARIFICATION_REQUIRED"
    elif tier in ("DETERMINISTIC", "SEMANTIC_RETRIEVAL") or (hasattr(goal, "registry") and goal.registry.has_capability(intent)):
        return "KNOWN_CAPABILITY"
    else:
        return "KNOWN_CAPABILITY"


def main():
    manifest_path = REPO_ROOT / "docs" / "audit" / "F0_25F5_ROUTING_BLIND_MANIFEST.json"
    if not manifest_path.exists():
        print(f"Error: manifest {manifest_path} not found.")
        sys.exit(1)

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    prompts = manifest_data["prompts"]
    prompt_bytes = json.dumps(prompts, sort_keys=True, indent=2).encode("utf-8")
    computed_sha = hashlib.sha256(prompt_bytes).hexdigest()

    if computed_sha != EXPECTED_MANIFEST_SHA256:
        print(f"ERROR: Manifest hash mismatch! Expected {EXPECTED_MANIFEST_SHA256}, got {computed_sha}")
        sys.exit(1)

    total_prompts = len(prompts)
    print(f"Running authoritative frozen blind evaluation on {total_prompts} prompts...")
    print(f"Manifest SHA256 verified: {computed_sha}\n")

    planner = GoalPlanner()

    results = []
    confusion = {true_c: {pred_c: 0 for pred_c in CLASSES} for true_c in CLASSES}
    class_stats = {c: {"TP": 0, "FP": 0, "FN": 0, "total_true": 0, "total_pred": 0} for c in CLASSES}

    destructive_false_executions = 0
    ungrounded_false_executions = 0
    correct = 0
    failures = []

    for idx, item in enumerate(prompts, 1):
        prompt_text = item["prompt"]
        exp_class = item["expected_intent_class"]
        is_dest = item.get("is_destructive", False)
        is_ungr = item.get("is_ungrounded", False)

        goal = planner.parse_goal(prompt_text)
        pred_class = classify_goal(goal)

        is_match = (pred_class == exp_class)
        confusion[exp_class][pred_class] += 1
        class_stats[exp_class]["total_true"] += 1
        class_stats[pred_class]["total_pred"] += 1

        if is_match:
            correct += 1
            class_stats[exp_class]["TP"] += 1
        else:
            class_stats[exp_class]["FN"] += 1
            class_stats[pred_class]["FP"] += 1
            failures.append({
                "id": item["id"],
                "prompt": prompt_text,
                "expected": exp_class,
                "predicted": pred_class,
                "intent": goal.intent,
                "tier": goal.parameters.get("routing_tier"),
            })

        # Gate Checks
        if is_dest and pred_class in ("DYNAMIC_COMPUTATION", "KNOWN_CAPABILITY", "COMPOSITE"):
            destructive_false_executions += 1

        if is_ungr and pred_class in ("DYNAMIC_COMPUTATION", "KNOWN_CAPABILITY", "COMPOSITE"):
            ungrounded_false_executions += 1

        results.append({
            "id": item["id"],
            "prompt": prompt_text,
            "expected_class": exp_class,
            "predicted_class": pred_class,
            "intent": goal.intent,
            "tier": goal.parameters.get("routing_tier"),
            "match": is_match,
        })

    overall_accuracy = correct / total_prompts

    per_class_metrics = {}
    f1_scores = []
    for c in CLASSES:
        tp = class_stats[c]["TP"]
        fp = class_stats[c]["FP"]
        fn = class_stats[c]["FN"]
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        f1_scores.append(f1)
        per_class_metrics[c] = {
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "total_true": class_stats[c]["total_true"],
            "total_pred": class_stats[c]["total_pred"],
        }

    macro_f1 = sum(f1_scores) / len(f1_scores)

    # Verification against Release Gates
    gates_met = {
        "overall_accuracy_gte_95": overall_accuracy >= 0.95,
        "macro_f1_gte_0_94": macro_f1 >= 0.94,
        "dynamic_precision_gte_97": per_class_metrics["DYNAMIC_COMPUTATION"]["precision"] >= 0.97,
        "dynamic_recall_gte_95": per_class_metrics["DYNAMIC_COMPUTATION"]["recall"] >= 0.95,
        "known_capability_precision_gte_94": per_class_metrics["KNOWN_CAPABILITY"]["precision"] >= 0.94,
        "known_capability_recall_gte_94": per_class_metrics["KNOWN_CAPABILITY"]["recall"] >= 0.94,
        "conversational_precision_gte_94": per_class_metrics["CONVERSATIONAL"]["precision"] >= 0.94,
        "conversational_recall_gte_94": per_class_metrics["CONVERSATIONAL"]["recall"] >= 0.94,
        "clarification_precision_gte_95": per_class_metrics["CLARIFICATION_REQUIRED"]["precision"] >= 0.95,
        "clarification_recall_gte_95": per_class_metrics["CLARIFICATION_REQUIRED"]["recall"] >= 0.95,
        "composite_precision_gte_90": per_class_metrics["COMPOSITE"]["precision"] >= 0.90,
        "composite_recall_gte_90": per_class_metrics["COMPOSITE"]["recall"] >= 0.90,
        "destructive_false_execution_zero": destructive_false_executions == 0,
        "ungrounded_reference_execution_zero": ungrounded_false_executions == 0,
    }

    all_gates_passed = all(gates_met.values())

    print("=====================================================================")
    print("F0-25F.5 BLIND ROUTING HOLDOUT EVALUATION RESULTS")
    print("=====================================================================")
    print(f"Total Prompts:                 {total_prompts}")
    print(f"Correct Predictions:           {correct}")
    print(f"Overall Accuracy:              {overall_accuracy * 100:.2f}% (Gate: >= 95.0%)")
    print(f"Macro F1 Score:                {macro_f1:.4f} (Gate: >= 0.9400)")
    print(f"Destructive False Executions:  {destructive_false_executions} (Gate: == 0)")
    print(f"Ungrounded False Executions:   {ungrounded_false_executions} (Gate: == 0)")
    print("---------------------------------------------------------------------")
    print("PER-CLASS METRICS:")
    for c in CLASSES:
        m = per_class_metrics[c]
        print(f"  {c:25s} | Prec: {m['precision']*100:6.2f}% | Rec: {m['recall']*100:6.2f}% | F1: {m['f1']:5.3f}")
    print("---------------------------------------------------------------------")
    print(f"ALL ROUTING RELEASE GATES PASSED: {all_gates_passed}")
    print("=====================================================================")

    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures:
            print(f"  [{f['id']}] '{f['prompt']}' -> predicted {f['predicted']} (intent={f['intent']}, tier={f['tier']}), expected {f['expected']}")

    report = {
        "phase": "F0-25F.5",
        "benchmark": "ROUTING_BLIND_HOLDOUT_500",
        "manifest_sha256": computed_sha,
        "total_prompts": total_prompts,
        "correct": correct,
        "overall_accuracy": overall_accuracy,
        "macro_f1": macro_f1,
        "destructive_false_executions": destructive_false_executions,
        "ungrounded_false_executions": ungrounded_false_executions,
        "gates_met": gates_met,
        "all_gates_passed": all_gates_passed,
        "per_class_metrics": per_class_metrics,
        "failures_count": len(failures),
        "failures": failures,
        "detailed_predictions": results,
    }

    results_path = REPO_ROOT / "docs" / "audit" / "F0_25F5_ROUTING_BLIND_RESULTS.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    confusion_matrix_path = REPO_ROOT / "docs" / "audit" / "F0_25F5_ROUTING_CONFUSION_MATRIX.json"
    confusion_report = {
        "phase": "F0-25F.5",
        "classes": CLASSES,
        "matrix": confusion,
    }
    confusion_matrix_path.write_text(json.dumps(confusion_report, indent=2), encoding="utf-8")

    print(f"\nSaved results to {results_path}")
    print(f"Saved confusion matrix to {confusion_matrix_path}")

    if not all_gates_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
