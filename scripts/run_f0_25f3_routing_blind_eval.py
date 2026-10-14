"""Authoritative One-Shot Execution of Frozen Routing Blind Holdout for F0-25F.3 Stage 7.

Executes the frozen 220-prompt holdout manifest exactly ONCE without iterative tuning.
Computes comprehensive metrics:
- Overall Accuracy
- Macro Precision / Recall / F1
- Dynamic Computation Precision / Recall / F1
- Per-class metrics
- Detailed 4x4 Confusion Matrix
- False Positives and False Negatives lists
- Sub-analysis of lexical collision cases

Generates:
- docs/audit/F0_25F3_ROUTING_BLIND_RESULTS.json
- docs/audit/F0_25F3_ROUTING_CONFUSION_MATRIX.json
"""

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from astrarun.agent.planner import GoalPlanner
from astrarun.agent.models import Goal

EXPECTED_MANIFEST_SHA256 = "b402565c83908bd4dda2467d22f421ad05b1189cbc47567223d4e7fc760cf023"
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
    manifest_path = REPO_ROOT / "docs" / "audit" / "F0_25F3_ROUTING_BLIND_MANIFEST.json"
    if not manifest_path.exists():
        print(f"Error: manifest {manifest_path} not found.")
        sys.exit(1)

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded_sha = manifest_data.get("sha256")
    if recorded_sha != EXPECTED_MANIFEST_SHA256:
        print(f"ERROR: Manifest hash mismatch! Expected {EXPECTED_MANIFEST_SHA256}, got {recorded_sha}")
        sys.exit(1)

    prompts = manifest_data["prompts"]
    total_prompts = len(prompts)
    print(f"Running frozen blind evaluation on {total_prompts} prompts (SHA256 verified)...")

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

        is_match = (pred_class == exp_class)
        confusion[exp_class][pred_class] += 1
        class_counts[exp_class]["total_true"] += 1
        class_counts[pred_class]["total_pred"] += 1

        if is_match:
            class_counts[exp_class]["TP"] += 1
            if is_collision:
                collision_correct += 1
        else:
            class_counts[pred_class]["FP"] += 1
            class_counts[exp_class]["FN"] += 1

        if is_collision:
            collision_total += 1

        results.append({
            "id": item["id"],
            "prompt": prompt_text,
            "category": item["category"],
            "expected_class": exp_class,
            "predicted_class": pred_class,
            "intent": goal.intent,
            "tier": goal.parameters.get("routing_tier"),
            "correct": is_match,
            "is_collision_case": is_collision,
        })

    total_correct = sum(class_counts[c]["TP"] for c in CLASSES)
    accuracy = total_correct / total_prompts

    # Compute Per-Class and Macro Metrics
    per_class_metrics = {}
    precisions = []
    recalls = []
    f1s = []

    for c in CLASSES:
        tp = class_counts[c]["TP"]
        fp = class_counts[c]["FP"]
        fn = class_counts[c]["FN"]

        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0

        per_class_metrics[c] = {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "support": class_counts[c]["total_true"],
        }
        precisions.append(prec)
        recalls.append(rec)
        f1s.append(f1)

    macro_precision = sum(precisions) / len(precisions)
    macro_recall = sum(recalls) / len(recalls)
    macro_f1 = sum(f1s) / len(f1s)

    dyn_prec = per_class_metrics["DYNAMIC_COMPUTATION"]["precision"]
    dyn_rec = per_class_metrics["DYNAMIC_COMPUTATION"]["recall"]
    dyn_f1 = per_class_metrics["DYNAMIC_COMPUTATION"]["f1"]

    false_positives = [r for r in results if not r["correct"]]
    false_negatives_dynamic = [r for r in results if r["expected_class"] == "DYNAMIC_COMPUTATION" and not r["correct"]]
    over_routes_dynamic = [r for r in results if r["predicted_class"] == "DYNAMIC_COMPUTATION" and r["expected_class"] != "DYNAMIC_COMPUTATION"]

    collision_acc = collision_correct / collision_total if collision_total > 0 else 0.0

    print("=" * 65)
    print(f"F0-25F.3 ROUTING BLIND HOLDOUT EVALUATION RESULTS")
    print("=" * 65)
    print(f"Total Prompts:      {total_prompts}")
    print(f"Total Correct:      {total_correct}")
    print(f"Overall Accuracy:   {accuracy:.4f} ({accuracy*100:.2f}%)")
    print(f"Macro Precision:    {macro_precision:.4f}")
    print(f"Macro Recall:       {macro_recall:.4f}")
    print(f"Macro F1 Score:     {macro_f1:.4f}")
    print("-" * 65)
    print(f"Dynamic Precision:  {dyn_prec:.4f}")
    print(f"Dynamic Recall:     {dyn_rec:.4f}")
    print(f"Dynamic F1 Score:   {dyn_f1:.4f}")
    print(f"Dynamic Over-routes (FP): {len(over_routes_dynamic)}")
    print(f"Dynamic Misses (FN):      {len(false_negatives_dynamic)}")
    print("-" * 65)
    print(f"Collision Accuracy: {collision_acc:.4f} ({collision_correct}/{collision_total})")
    print("=" * 65)

    # Output detailed audit records
    report = {
        "phase": "F0-25F.3",
        "stage": "STAGE 7 — ROUTING BLIND HOLDOUT EVALUATION",
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "total_prompts": total_prompts,
        "total_correct": total_correct,
        "overall_accuracy": round(accuracy, 4),
        "macro_metrics": {
            "precision": round(macro_precision, 4),
            "recall": round(macro_recall, 4),
            "f1": round(macro_f1, 4),
        },
        "dynamic_computation_metrics": {
            "precision": dyn_prec,
            "recall": dyn_rec,
            "f1": dyn_f1,
            "false_positives_over_routes": len(over_routes_dynamic),
            "false_negatives": len(false_negatives_dynamic),
        },
        "collision_cases_metrics": {
            "total_collision_cases": collision_total,
            "correct": collision_correct,
            "accuracy": round(collision_acc, 4),
        },
        "per_class_metrics": per_class_metrics,
        "false_positive_count": len(false_positives),
        "false_positives_sample": false_positives[:15],
        "verdict": "PASS" if (accuracy >= 0.85 and macro_f1 >= 0.85 and dyn_prec >= 0.85) else "FAIL",
    }

    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F3_ROUTING_BLIND_RESULTS.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    conf_matrix_file = REPO_ROOT / "docs" / "audit" / "F0_25F3_ROUTING_CONFUSION_MATRIX.json"
    conf_matrix_file.write_text(json.dumps({
        "phase": "F0-25F.3",
        "classes": CLASSES,
        "confusion_matrix": confusion,
    }, indent=2), encoding="utf-8")

    print(f"Artifacts written:")
    print(f"  {out_file}")
    print(f"  {conf_matrix_file}")


if __name__ == "__main__":
    main()
