"""Audit the test oracles, verifiers, validators, and evaluation assertions across AstraRun."""

import ast
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path("e:/Workspace/Active/AstraRun")
OUTPUT_PATH = REPO_ROOT / "docs" / "audit" / "F0_23_ORACLE_INVENTORY.json"

ORACLE_KEYWORDS = [
    "assert", "passed =", "status = \"PASS\"", "status == \"SUCCESS\"",
    "verified =", "verification_passed", "is_success", "goal completed",
    "GoalVerifier", "StepVerifier", "validator", "acceptance",
    "benchmark", "holdout", "stress", "evidence", "success_rate", "false_completion"
]

def analyze_file_oracles(filepath: Path) -> List[Dict[str, Any]]:
    rel_path = str(filepath.relative_to(REPO_ROOT)).replace("\\", "/")
    is_prod = rel_path.startswith("src/")
    try:
        content = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []

    if not any(k in content for k in ["assert", "passed", "status", "verify", "validate", "success", "oracle"]):
        return []

    try:
        tree = ast.parse(content, filename=str(filepath))
    except Exception:
        return []

    oracles: List[Dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if name.startswith("test_") or "verify" in name or "validate" in name or "audit" in name or "check" in name:
                func_code = ast.get_source_segment(content, node) or ""
                asserts_count = len([n for n in ast.walk(node) if isinstance(n, ast.Assert)])
                has_pass_assign = bool(re.search(r'\b(?:passed|status|verified|is_valid)\b', func_code))
                
                if asserts_count > 0 or has_pass_assign or "GoalVerifier" in func_code:
                    # Determine properties
                    trusts_cap = "result.success" in func_code or "status == \"SUCCESS\"" in func_code or "exit_code == 0" in func_code
                    trusts_plan = "plan.steps" in func_code or "capability_id" in func_code or "validator.validate" in func_code
                    observes_phys = "exists()" in func_code or "read_text" in func_code or "psutil" in func_code or "pywinauto" in func_code
                    observes_semantic = "target_application" in func_code or "resolved.name" in func_code or "content" in func_code
                    observes_unintended = "unrequested" in func_code or "side_effects" in func_code or "residue" in func_code or "ledger" in func_code
                    is_mock = "mock" in func_code.lower() or "patch(" in func_code or "MagicMock" in func_code

                    # Classification logic
                    if is_mock:
                        classification = "MOCK_ONLY"
                    elif observes_phys and observes_semantic and observes_unintended:
                        classification = "SOUND_FOR_CLAIM"
                    elif observes_phys and observes_semantic:
                        classification = "PARTIAL_ORACLE"
                    elif trusts_plan and not observes_phys:
                        classification = "PLAN_ONLY"
                    elif trusts_cap and not observes_phys and not observes_semantic:
                        classification = "RESULT_ONLY"
                    elif "is_valid" in func_code and not observes_phys:
                        classification = "STRUCTURAL_ONLY"
                    elif not observes_semantic and (trusts_plan or trusts_cap):
                        classification = "UNSOUND"
                    else:
                        classification = "PARTIAL_ORACLE"

                    can_fp = classification in ("UNSOUND", "PLAN_ONLY", "RESULT_ONLY", "STRUCTURAL_ONLY", "MOCK_ONLY")
                    can_fn = classification in ("UNSOUND", "MOCK_ONLY")

                    oracles.append({
                        "name": name,
                        "file": rel_path,
                        "symbol": f"{rel_path}:{node.lineno}:{name}",
                        "test_or_eval_class": "PRODUCTION_VERIFIER" if is_prod else ("TEST_CASE" if name.startswith("test_") else "EVAL_HARNESS"),
                        "inputs": [arg.arg for arg in node.args.args],
                        "assertions": f"{asserts_count} asserts found" if asserts_count > 0 else "status assignment logic",
                        "evidence_consumed": [
                            k for k, v in [
                                ("physical_disk", "exists()" in func_code),
                                ("content_bytes", "read_text" in func_code or "read_bytes" in func_code),
                                ("win32_process", "psutil" in func_code),
                                ("plan_structure", trusts_plan),
                                ("capability_return", trusts_cap),
                            ] if v
                        ],
                        "evidence_not_consumed": [
                            k for k, v in [
                                ("unintended_side_effects", not observes_unintended),
                                ("physical_os_state", not observes_phys),
                                ("semantic_identity", not observes_semantic),
                            ] if v
                        ],
                        "side_effects": "harmless_verification" if not ("write" in func_code or "subprocess.run" in func_code) else "may_invoke_subprocesses",
                        "production_or_harness": "production" if is_prod else "harness",
                        "can_false_positive": can_fp,
                        "can_false_negative": can_fn,
                        "trusts_capability_return": trusts_cap,
                        "trusts_plan_shape": trusts_plan,
                        "observes_physical_state": observes_phys,
                        "observes_semantic_identity": observes_semantic,
                        "observes_unintended_effects": observes_unintended,
                        "evidence_class_emitted": "PHYSICAL_OS_EXECUTION" if observes_phys else ("PLAN_ONLY" if trusts_plan else "MOCK_EXECUTION"),
                        "classification": classification,
                    })

    return oracles

def main() -> None:
    all_oracles: List[Dict[str, Any]] = []

    scan_dirs = [
        REPO_ROOT / "src" / "astrarun" / "agent",
        REPO_ROOT / "src" / "astrarun" / "security",
        REPO_ROOT / "src" / "astrarun" / "tasks",
        REPO_ROOT / "src" / "astrarun" / "brain",
        REPO_ROOT / "tests",
        REPO_ROOT / "scripts",
    ]

    for sdir in scan_dirs:
        if not sdir.exists():
            continue
        for root, _, files in os.walk(sdir):
            for file in files:
                if file.endswith(".py"):
                    fpath = Path(root) / file
                    items = analyze_file_oracles(fpath)
                    all_oracles.extend(items)

    classifications: Dict[str, int] = {}
    for o in all_oracles:
        c = o["classification"]
        classifications[c] = classifications.get(c, 0) + 1

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-23",
        "description": "Comprehensive audit of all verification mechanisms, test assertions, and evaluation oracles in AstraRun.",
        "total_oracles_inventoried": len(all_oracles),
        "classifications": classifications,
        "oracle_entries": all_oracles,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Inventoried {len(all_oracles)} oracles across codebase. Wrote to {OUTPUT_PATH}")
    for k, v in sorted(classifications.items()):
        print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
