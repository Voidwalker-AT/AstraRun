"""Evaluate current router on comprehensive development set across all 5 classes and safety gates."""

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from routing_dev_set import DEV_PROMPTS
from astrarun.agent.planner import GoalPlanner
from astrarun.agent.models import Goal

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
    planner = GoalPlanner()
    correct = 0
    total = len(DEV_PROMPTS)
    failures = []

    confusion = {true_c: {pred_c: 0 for pred_c in CLASSES} for true_c in CLASSES}
    class_stats = {c: {"TP": 0, "FP": 0, "FN": 0, "total_true": 0, "total_pred": 0} for c in CLASSES}

    destructive_false_executions = 0
    ungrounded_false_executions = 0

    for item in DEV_PROMPTS:
        prompt_text = item["prompt"]
        exp_class = item["expected_class"]
        is_dest = item.get("is_destructive", False)
        is_ungrounded = item.get("is_ungrounded", False)

        g = planner.parse_goal(prompt_text)
        pred = classify_goal(g)

        is_correct = (pred == exp_class)
        confusion[exp_class][pred] += 1
        class_stats[exp_class]["total_true"] += 1
        class_stats[pred]["total_pred"] += 1

        if is_correct:
            correct += 1
            class_stats[exp_class]["TP"] += 1
        else:
            class_stats[exp_class]["FN"] += 1
            class_stats[pred]["FP"] += 1
            failures.append({
                "id": item["id"],
                "prompt": prompt_text,
                "expected": exp_class,
                "predicted": pred,
                "intent": g.intent,
                "tier": g.parameters.get("routing_tier"),
            })

        # Safety Gates:
        if is_dest and pred in ("DYNAMIC_COMPUTATION", "KNOWN_CAPABILITY", "COMPOSITE"):
            destructive_false_executions += 1

        if is_ungrounded and pred in ("DYNAMIC_COMPUTATION", "KNOWN_CAPABILITY", "COMPOSITE"):
            ungrounded_false_executions += 1

    overall_acc = correct / total
    print(f"GoalPlanner Dev Evaluation: {correct}/{total} ({overall_acc * 100:.2f}%)")
    print(f"Destructive False Executions: {destructive_false_executions}")
    print(f"Ungrounded False Executions: {ungrounded_false_executions}\n")

    per_class_metrics = {}
    f1_list = []
    for c in CLASSES:
        tp = class_stats[c]["TP"]
        fp = class_stats[c]["FP"]
        fn = class_stats[c]["FN"]
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        f1_list.append(f1)
        per_class_metrics[c] = {
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "true_count": class_stats[c]["total_true"],
            "pred_count": class_stats[c]["total_pred"],
        }
        print(f"  {c:25s} | Prec: {prec*100:6.2f}% | Rec: {rec*100:6.2f}% | F1: {f1:5.3f}")

    macro_f1 = sum(f1_list) / len(f1_list)
    print(f"\nMacro F1: {macro_f1:.4f}")

    if failures:
        print("\nFailures:")
        for f in failures:
            print(f"  FAIL {f['id']}: '{f['prompt']}' -> predicted {f['predicted']} (intent={f['intent']}, tier={f['tier']}), expected {f['expected']}")

    report = {
        "phase": "F0-25F.5-DEV",
        "total_prompts": total,
        "correct": correct,
        "overall_accuracy": overall_acc,
        "macro_f1": macro_f1,
        "destructive_false_executions": destructive_false_executions,
        "ungrounded_false_executions": ungrounded_false_executions,
        "per_class_metrics": per_class_metrics,
        "confusion_matrix": confusion,
        "failures": failures,
    }
    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F5_ROUTING_DEV_RESULTS.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved report to {out_file}")


if __name__ == "__main__":
    main()
