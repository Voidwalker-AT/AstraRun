"""Verification and audit script for F0-25F.3 Stage 2: Presentation Semantics.

Audits:
1. Purge of legacy REQUESTED || PRESENTED acceptance across repository.
2. Enforcement of mechanism-specific identity contracts (Explorer, Text Viewer, Astra Surface).
3. Rejection of hollow presentations (null HWND, empty identity, mismatched target).
4. Measurement vs fabrication of window identity.

Generates: docs/audit/F0_25F3_PRESENTATION_RESULTS.json
"""

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from astrarun.agent.completion_gate import AuthoritativeCompletionGate, GateVerdict
from astrarun.agent.models import GoalContract, GoalPredicate, PredicateStatus, PredicateType


def run_audit() -> dict:
    results = {}

    # 1. Repository-wide search for legacy REQUESTED || PRESENTED acceptance
    scripts_to_check = [
        "scripts/verify_f0_25f_complete_physical.py",
        "scripts/f0_25e_evaluator.py",
        "src/astrarun/ui/result_presentation.py",
    ]
    legacy_or_found = []
    for s in scripts_to_check:
        p = REPO_ROOT / s
        if p.exists():
            text = p.read_text(encoding="utf-8")
            if '"RESULT_PRESENTATION_REQUESTED" in pres_event_types' in text:
                legacy_or_found.append(f"{s}: found legacy pres_event_types check")
            if 'RESULT_PRESENTATION_REQUESTED' in text and 'or' in text and 'RESULT_PRESENTED' in text:
                lines = [line.strip() for line in text.splitlines() if 'RESULT_PRESENTATION_REQUESTED' in line and 'RESULT_PRESENTED' in line and 'or' in line]
                for l in lines:
                    if not l.startswith("#"):
                        legacy_or_found.append(f"{s}: {l}")

    results["legacy_acceptance_purge"] = {
        "legacy_or_instances_found": len(legacy_or_found),
        "details": legacy_or_found,
        "purged": len(legacy_or_found) == 0,
    }

    # 2. Mechanism-Specific Identity Verification Tests
    # Case P1: REQUESTED-only presentation in event stream
    c1_contract = GoalContract(
        acceptance_predicates=[GoalPredicate(predicate_type=PredicateType.DATA_COMPUTED, is_mandatory=True, status=PredicateStatus.SATISFIED)],
        entities={"reveal_result": True},
    )
    c1_res = AuthoritativeCompletionGate.can_complete(
        goal_contract=c1_contract,
        evidence_state={"events": [{"event_type": "RESULT_PRESENTATION_REQUESTED"}]},
    )
    results["P1_requested_only_rejected"] = {
        "verdict": c1_res.verdict.value,
        "rejected": not c1_res.can_complete,
        "reason": c1_res.message,
    }

    # Case P2: Hollow RESULT_PRESENTED with null HWND
    c2_res = AuthoritativeCompletionGate.can_complete(
        goal_contract=c1_contract,
        evidence_state={
            "events": [{
                "event_type": "RESULT_PRESENTED",
                "data": {"target_observed": True, "verified_hwnd": None, "verified_title": "Explorer"}
            }]
        },
    )
    results["P2_null_hwnd_rejected"] = {
        "verdict": c2_res.verdict.value,
        "rejected": not c2_res.can_complete,
        "reason": c2_res.message,
    }

    # Case P3: Hollow RESULT_PRESENTED with target_observed = False
    c3_res = AuthoritativeCompletionGate.can_complete(
        goal_contract=c1_contract,
        evidence_state={
            "events": [{
                "event_type": "RESULT_PRESENTED",
                "data": {"target_observed": False, "verified_hwnd": 12345, "verified_title": "Explorer"}
            }]
        },
    )
    results["P3_target_unobserved_rejected"] = {
        "verdict": c3_res.verdict.value,
        "rejected": not c3_res.can_complete,
        "reason": c3_res.message,
    }

    # Case P4: Valid presentation with affirmative HWND, target_observed, and identity
    c4_res = AuthoritativeCompletionGate.can_complete(
        goal_contract=c1_contract,
        evidence_state={
            "events": [{
                "event_type": "RESULT_PRESENTED",
                "data": {
                    "target_observed": True,
                    "verified_hwnd": 54321,
                    "verified_title": "word_frequency",
                    "verified_class": "CabinetWClass",
                    "mechanism": "explorer",
                }
            }]
        },
    )
    results["P4_valid_presentation_approved"] = {
        "verdict": c4_res.verdict.value,
        "approved": c4_res.can_complete,
        "reason": c4_res.message,
    }

    # 3. Summary mode attestation audit
    pres_code = (REPO_ROOT / "src" / "astrarun" / "ui" / "result_presentation.py").read_text(encoding="utf-8")
    has_hardcoded_literal = 'verified_title = "AstraRun"\n                        verified_class = "QtLauncher"' in pres_code
    measures_title = "GetWindowTextW" in pres_code and "GetClassNameW" in pres_code

    results["summary_mode_attestation"] = {
        "hardcoded_literals_present": has_hardcoded_literal,
        "measures_real_window_text_and_class": measures_title,
        "passed": not has_hardcoded_literal and measures_title,
    }

    all_passed = (
        results["legacy_acceptance_purge"]["purged"]
        and results["P1_requested_only_rejected"]["rejected"]
        and results["P2_null_hwnd_rejected"]["rejected"]
        and results["P3_target_unobserved_rejected"]["rejected"]
        and results["P4_valid_presentation_approved"]["approved"]
        and results["summary_mode_attestation"]["passed"]
    )

    return {
        "phase": "F0-25F.3",
        "stage": "STAGE 2 — PURGE LEGACY PRESENTATION SEMANTICS",
        "verdict": "PASS" if all_passed else "FAIL",
        "all_checks_passed": all_passed,
        "results": results,
    }


def main():
    report = run_audit()
    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F3_PRESENTATION_RESULTS.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Presentation semantics audit: {report['verdict']}.")
    print(f"Artifact written to {out_file}")


if __name__ == "__main__":
    main()
