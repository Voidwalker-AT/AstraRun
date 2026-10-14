"""Authoritative One-Shot Execution of Frozen Routing Blind Holdout for F0-25F.4.

Executes the frozen 320-prompt holdout manifest exactly ONCE without iterative tuning.
Computes comprehensive metrics:
- Overall Accuracy
- Macro Precision / Recall / F1
- Dynamic Computation Precision / Recall / F1
- Per-class metrics
- Detailed 4x4 Confusion Matrix
- False Positives and False Negatives lists
- Sub-analysis of lexical collision cases

Generates:
- docs/audit/F0_25F4_ROUTING_BLIND_RESULTS.json
- docs/audit/F0_25F4_ROUTING_CONFUSION_MATRIX.json
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

EXPECTED_MANIFEST_SHA256 = "eb8c72cea888292a7aee834c7fac90ffceb8a2538fae603162b1611b79d778e8"
CLASSES = ["DYNAMIC_COMPUTATION", "KNOWN_CAPABILITY", "CONVERSATIONAL", "CLARIFICATION_REQUIRED"]


def classify_goal(goal: Goal) -> str:
    intent = goal.intent
    tier = goal.parameters.get("routing_tier")
    if intent == "execute_dynamic_tool":
        return "DYNAMIC_COMPUTATION"
    elif intent in ("conversational_dialogue", "explain_concept"):
        return "CONVERSATIONAL"
    elif intent in ("needs_clarification", "security_denial"):
        return "CLARIFICATION_REQUIRED"
    elif tier in ("DETERMINISTIC", "SEMANTIC_RETRIEVAL"):
        return "KNOWN_CAPABILITY"
    else:
        return "KNOWN_CAPABILITY"


def main():
    manifest_path = REPO_ROOT / "docs" / "audit" / "F0_25F4_ROUTING_BLIND_MANIFEST.json"
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
    print(f"Running frozen blind evaluation on {total_prompts} prompts (SHA256 verified: {computed_sha[:16]}...)...")

    planner = GoalPlanner()

    results = []
    confusion = {true_c: {pred_c: 0 for pred_c in CLASSES} for true_c in CLASSES}
    class_counts = defaultdict(lambda: {"TP": 0, "FP": 0, "FN": 0, "total_true": 0, "total_pred": 0})
    collision_correct = 0
    collision_total = 0

    for idx, item in enumerate(prompts, 1):
        prompt_text = item["prompt"]
        exp_class = item["expected_intent_class"]
        is_collision = item.get("is_collision_case", False)

        goal = planner.parse_goal(prompt_text)
        pred_class = classify_goal(goal)

        is_correct = (pred_class == exp_class)
        confusion[exp_class][pred_class] += 1

        class_counts[exp_class]["total_true"] += 1
        class_counts[pred_class]["total_pred"] += 1

        if is_correct:
            class_counts[exp_class]["TP"] += 1
            if is_collision:
                collision_correct += 1
        else:
            class_counts[exp_class]["FN"] += 1
            class_counts[pred_class]["FP"] += 1

        if is_collision:
            collision_total += 1

        results.append({
            "id": item["id"],
            "prompt": prompt_text,
            "expected_class": exp_class,
            "predicted_class": pred_class,
            "intent": goal.intent,
            "tier": goal.parameters.get("routing_tier"),
            "correct": is_correct,
            "is_collision_case": is_collision,
        })

    # Summary metrics
    total_correct = sum(class_counts[c]["TP"] for c in CLASSES)
    overall_acc = total_correct / total_prompts

    per_class_metrics = {}
    macro_p = 0.0
    macro_r = 0.0
    macro_f1 = 0.0

    for c in CLASSES:
        tp = class_counts[c]["TP"]
        fp = class_counts[c]["FP"]
        fn = class_counts[c]["FN"]
        support = class_counts[c]["total_true"]

        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0

        per_class_metrics[c] = {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
            "support": support,
        }
        macro_p += p
        macro_r += r
        macro_f1 += f1

    macro_p /= len(CLASSES)
    macro_r /= len(CLASSES)
    macro_f1 /= len(CLASSES)

    collision_acc = collision_correct / collision_total if collision_total > 0 else 1.0

    dyn_fp = class_counts["DYNAMIC_COMPUTATION"]["FP"]
    dyn_fn = class_counts["DYNAMIC_COMPUTATION"]["FN"]
    dyn_p = per_class_metrics["DYNAMIC_COMPUTATION"]["precision"]
    dyn_r = per_class_metrics["DYNAMIC_COMPUTATION"]["recall"]
    dyn_f1 = per_class_metrics["DYNAMIC_COMPUTATION"]["f1"]

    print("\n================ ROUTING BLIND HOLDOUT RESULTS (F0-25F.4) ================")
    print(f"Total Prompts Evaluated: {total_prompts}")
    print(f"Overall Accuracy:       {total_correct}/{total_prompts} ({overall_acc*100:.2f}%)")
    print(f"Macro Precision:        {macro_p*100:.2f}%")
    print(f"Macro Recall:           {macro_r*100:.2f}%")
    print(f"Macro F1-Score:         {macro_f1*100:.2f}%")
    print(f"Collision Accuracy:     {collision_correct}/{collision_total} ({collision_acc*100:.2f}%)")
    print("--------------------------------------------------------------------------")
    print("DYNAMIC_COMPUTATION Focus:")
    print(f"  Precision:            {dyn_p*100:.2f}% (FP = {dyn_fp})")
    print(f"  Recall:               {dyn_r*100:.2f}% (FN = {dyn_fn})")
    print(f"  F1-Score:             {dyn_f1*100:.2f}%")
    print("==========================================================================\n")

    # Save blind results JSON
    audit_dir = REPO_ROOT / "docs" / "audit"
    out_results = audit_dir / "F0_25F4_ROUTING_BLIND_RESULTS.json"
    results_payload = {
        "phase": "F0-25F.4",
        "stage": "STAGE 5 — ROUTING BLIND HOLDOUT EVALUATION",
        "manifest_sha256": computed_sha,
        "total_prompts": total_prompts,
        "total_correct": total_correct,
        "overall_accuracy": round(overall_acc, 4),
        "macro_metrics": {
            "precision": round(macro_p, 4),
            "recall": round(macro_r, 4),
            "f1": round(macro_f1, 4),
        },
        "dynamic_computation_metrics": {
            "precision": round(dyn_p, 4),
            "recall": round(dyn_r, 4),
            "f1": round(dyn_f1, 4),
            "false_positives_over_routes": dyn_fp,
            "false_negatives": dyn_fn,
        },
        "collision_cases_metrics": {
            "total_collision_cases": collision_total,
            "correct": collision_correct,
            "accuracy": round(collision_acc, 4),
        },
        "per_class_metrics": per_class_metrics,
        "false_positive_count": sum(class_counts[c]["FP"] for c in CLASSES),
        "misclassifications": [r for r in results if not r["correct"]],
    }
    out_results.write_text(json.dumps(results_payload, indent=2), encoding="utf-8")
    print(f"Saved blind results to {out_results}")

    # Save confusion matrix JSON
    out_confusion = audit_dir / "F0_25F4_ROUTING_CONFUSION_MATRIX.json"
    confusion_payload = {
        "phase": "F0-25F.4",
        "manifest_sha256": computed_sha,
        "classes": CLASSES,
        "matrix": confusion,
        "row_labels": "True Class",
        "col_labels": "Predicted Class",
    }
    out_confusion.write_text(json.dumps(confusion_payload, indent=2), encoding="utf-8")
    print(f"Saved confusion matrix to {out_confusion}")


if __name__ == "__main__":
    main()
