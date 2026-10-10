"""Evaluate action relevance oracle across advancing, support, and unrequested actions."""

import json
from datetime import datetime, timezone
from pathlib import Path

from astrarun.agent.models import (
    Goal,
    GoalContract,
    GoalPredicate,
    PlanStep,
    PredicateType,
)
from astrarun.evaluation.action_relevance import (
    ActionRelevanceClassification,
    ActionRelevanceOracle,
)

REPO_ROOT = Path("e:/Workspace/Active/AstraRun")
OUTPUT_PATH = REPO_ROOT / "docs" / "audit" / "F0_23_ACTION_RELEVANCE_RESULTS.json"

TEST_CASES = [
    # Required advancing actions
    ("open_application", {"app": "notepad"}, "PRODUCE_DOCUMENT", [PredicateType.FILE_EXISTS], True, ActionRelevanceClassification.REQUIRED_ACTION),
    ("type_into_window", {"text": "hello"}, "PRODUCE_DOCUMENT", [PredicateType.FILE_CONTENT_CONTAINS], True, ActionRelevanceClassification.REQUIRED_ACTION),
    ("save_document_via_ui", {"filename": "test.txt"}, "PRODUCE_DOCUMENT", [PredicateType.FILE_EXISTS, PredicateType.FILE_NON_EMPTY], True, ActionRelevanceClassification.REQUIRED_ACTION),
    ("save_text_file", {"path": "out.txt"}, "PRODUCE_DOCUMENT", [PredicateType.FILE_EXISTS], True, ActionRelevanceClassification.REQUIRED_ACTION),
    ("execute_dynamic_tool", {"code": "2+2"}, "COMPUTATION", [PredicateType.DATA_COMPUTED], True, ActionRelevanceClassification.REQUIRED_ACTION),
    # Harmless observations
    ("gpu_status", {}, "SYSTEM_QUERY", [], True, ActionRelevanceClassification.HARMLESS_OBSERVATION),
    ("memory_status", {}, "SYSTEM_QUERY", [], True, ActionRelevanceClassification.HARMLESS_OBSERVATION),
    ("system_summary", {}, "SYSTEM_QUERY", [], True, ActionRelevanceClassification.HARMLESS_OBSERVATION),
    ("get_active_window", {}, "GENERAL_TASK", [], True, ActionRelevanceClassification.HARMLESS_OBSERVATION),
    ("list_directory", {"path": "."}, "GENERAL_TASK", [], True, ActionRelevanceClassification.HARMLESS_OBSERVATION),
    ("check_application_status", {"app": "notepad"}, "GENERAL_TASK", [], True, ActionRelevanceClassification.HARMLESS_OBSERVATION),
    # Justified support actions
    ("focus_window", {"hwnd": 1234}, "PRODUCE_DOCUMENT", [PredicateType.FILE_CONTENT_CONTAINS], True, ActionRelevanceClassification.JUSTIFIED_SUPPORT_ACTION),
    ("wait", {"duration_ms": 500}, "PRODUCE_DOCUMENT", [PredicateType.FILE_EXISTS], True, ActionRelevanceClassification.JUSTIFIED_SUPPORT_ACTION),
    # Unrequested consequential side effects (MUST BE REJECTED)
    ("snap_window_right", {"hwnd": 1234}, "SYSTEM_QUERY", [PredicateType.DATA_COMPUTED], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
    ("snap_window_left", {"hwnd": 1234}, "COMPUTATION", [PredicateType.DATA_COMPUTED], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
    ("maximize_window", {"hwnd": 1234}, "SYSTEM_QUERY", [], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
    ("minimize_window", {"hwnd": 1234}, "SYSTEM_QUERY", [], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
    ("open_folder", {"folder": "Desktop"}, "PRODUCE_DOCUMENT", [PredicateType.FILE_EXISTS], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
    ("reveal_file", {"path": "test.txt"}, "PRODUCE_DOCUMENT", [PredicateType.FILE_EXISTS], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
    ("close_application", {"app": "calculator"}, "SYSTEM_QUERY", [PredicateType.DATA_COMPUTED], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
    ("delete_file", {"path": "random.txt"}, "SYSTEM_QUERY", [], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
    ("generate_battery_report", {}, "SYSTEM_QUERY", [PredicateType.DATA_COMPUTED], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
    ("open_url", {"url": "https://example.com"}, "COMPUTATION", [PredicateType.DATA_COMPUTED], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
    ("execute_command", {"command": "dir"}, "SYSTEM_QUERY", [], False, ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT),
]

# Expand to 52 cases with domain variants
for i in range(1, 15):
    TEST_CASES.append((
        "save_document_via_ui",
        {"filename": f"note_{i}.txt"},
        "PRODUCE_DOCUMENT",
        [PredicateType.FILE_EXISTS, PredicateType.FILE_NON_EMPTY],
        True,
        ActionRelevanceClassification.REQUIRED_ACTION,
    ))
for i in range(1, 15):
    TEST_CASES.append((
        "snap_window_right" if i % 2 == 0 else "open_folder",
        {"target": f"unrequested_{i}"},
        "SYSTEM_QUERY",
        [],
        False,
        ActionRelevanceClassification.UNREQUESTED_CONSEQUENTIAL_SIDE_EFFECT,
    ))

def main() -> None:
    eval_results = []
    passed_count = 0

    for idx, (cap, args, obj, ptypes, expected_valid, expected_cls) in enumerate(TEST_CASES):
        preds = [
            GoalPredicate(
                predicate_id=f"p_{idx}_{j}",
                predicate_type=pt,
                description=f"Predicate {pt.value}",
                parameters=args,
                is_mandatory=True,
            )
            for j, pt in enumerate(ptypes)
        ]
        contract = GoalContract(
            contract_id=f"gc_{idx}",
            original_utterance=f"Task {idx}",
            objective=obj,
            acceptance_predicates=preds,
            entities={"content": args.get("text", "")} if "text" in args else {},
        )
        step = PlanStep(
            step_id=f"s_{idx}",
            capability_id=cap,
            arguments=args,
            declared_effects=["READ_ONLY"] if cap in ActionRelevanceOracle.HARMLESS_OBSERVATION_CAPS else ["SYSTEM_STATE"],
        )

        rec = ActionRelevanceOracle.evaluate_step(step, contract, preds)
        matches_class = rec.classification == expected_cls
        matches_validity = rec.is_valid == expected_valid
        ok = matches_class and matches_validity

        if ok:
            passed_count += 1

        eval_results.append({
            "case_id": f"action_rel_{idx}",
            "capability": cap,
            "objective": obj,
            "expected_classification": expected_cls.value,
            "actual_classification": rec.classification.value,
            "expected_valid": expected_valid,
            "actual_valid": rec.is_valid,
            "predicates_advanced": rec.predicates_advanced,
            "justification": rec.justification,
            "passed": ok,
        })

    total = len(TEST_CASES)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-23",
        "description": "Action relevance oracle evaluation across advancing actions, support prerequisites, and unrequested side-effects.",
        "metrics": {
            "total_evaluated": total,
            "passed": passed_count,
            "failed": total - passed_count,
            "pass_rate_percent": (passed_count / total) * 100.0,
            "unrequested_actions_rejected": sum(1 for r in eval_results if not r["actual_valid"]),
        },
        "results": eval_results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Evaluated {total} action relevance cases: {passed_count}/{total} passed ({summary['metrics']['pass_rate_percent']:.1f}%).")
    print(f"Wrote to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
