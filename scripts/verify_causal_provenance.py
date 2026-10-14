"""Verification and audit script for F0-25F.3 Stage 4: Production-Only Causal Provenance.

Validates that:
1. Evaluator strictly rejects harness_generated / manufactured causal events.
2. Evaluator strictly rejects broker stubs (executor_override) as proof of causal dispatch.
3. Production event producers (planner, model, broker, capability dispatch, verifier, completion gate)
   are the sole legitimate originators of production telemetry.

Generates: docs/audit/F0_25F3_CAUSAL_PROVENANCE.json
"""

import json
from pathlib import Path
import sys
import tempfile

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.f0_25e_evaluator import evaluate_acceptance


class MockEvidencePackage:
    def __init__(self, events=None, model_events=None, broker_events=None, filesystem_events=None, world_frames=None):
        self.events = events or []
        self.model_events = model_events or []
        self.broker_events = broker_events or []
        self.filesystem_events = filesystem_events or []
        self.world_frames = world_frames or []


def run_provenance_audit() -> dict:
    results = {}
    target_dir = Path(tempfile.gettempdir())

    # 1. Test Evaluator Rejection of Harness-Emitted Events
    pkg_harness = MockEvidencePackage(
        events=[
            {"event_type": "REQUEST_RECEIVED", "component": "AstraApplication"},
            {"event_type": "MODEL_REQUEST", "component": "Harness", "data": {"harness_generated": True}},
            {"event_type": "ACTION_DISPATCHED", "component": "ExecutionBroker"},
            {"event_type": "ARTIFACT_CREATED", "component": "SandboxManager"},
        ],
        model_events=[{"event_type": "MODEL_REQUEST", "component": "Harness"}],
        broker_events=[{"event_type": "ACTION_DISPATCHED", "component": "ExecutionBroker"}],
        filesystem_events=[{"event_type": "ARTIFACT_CREATED", "component": "SandboxManager"}],
    )
    matrix_harness = evaluate_acceptance(pkg_harness, target_dir)
    harness_verdict = matrix_harness.get("CAUSAL_PROVENANCE", {}).get("verdict")
    results["T1_harness_generated_rejected"] = {
        "description": "Evaluator must return FAIL when events are harness-generated",
        "verdict": harness_verdict,
        "passed": harness_verdict == "FAIL",
    }

    # 2. Test Evaluator Rejection of Broker Stub (executor_override)
    pkg_stub = MockEvidencePackage(
        events=[
            {"event_type": "REQUEST_RECEIVED", "component": "AstraApplication"},
            {"event_type": "MODEL_REQUEST", "component": "ModelService"},
            {"event_type": "ACTION_AUTHORIZED", "component": "ExecutionBroker", "data": {"executor_override": True}},
            {"event_type": "ARTIFACT_CREATED", "component": "SandboxManager"},
        ],
        model_events=[{"event_type": "MODEL_REQUEST", "component": "ModelService"}],
        broker_events=[{"event_type": "ACTION_AUTHORIZED", "component": "ExecutionBroker"}],
        filesystem_events=[{"event_type": "ARTIFACT_CREATED", "component": "SandboxManager"}],
    )
    matrix_stub = evaluate_acceptance(pkg_stub, target_dir)
    stub_verdict = matrix_stub.get("CAUSAL_PROVENANCE", {}).get("verdict")
    results["T2_broker_stub_rejected"] = {
        "description": "Evaluator must return FAIL when broker was stubbed via executor_override",
        "verdict": stub_verdict,
        "passed": stub_verdict == "FAIL",
    }

    # 3. Test Evaluator Acceptance of Genuine Production Pipeline
    pkg_prod = MockEvidencePackage(
        events=[
            {"event_type": "REQUEST_RECEIVED", "component": "AstraApplication"},
            {"event_type": "GOAL_INTERPRETED", "component": "GoalPlanner"},
            {"event_type": "PLAN_CREATED", "component": "GoalPlanner"},
            {"event_type": "MODEL_REQUEST", "component": "ModelService"},
            {"event_type": "MODEL_RESPONSE", "component": "ModelService"},
            {"event_type": "ACTION_PROPOSED", "component": "ExecutionBroker"},
            {"event_type": "ACTION_AUTHORIZED", "component": "ExecutionBroker"},
            {"event_type": "ACTION_DISPATCHED", "component": "ExecutionBroker"},
            {"event_type": "ARTIFACT_CREATED", "component": "SandboxManager"},
            {"event_type": "STATE_OBSERVED", "component": "GoalVerifier"},
            {"event_type": "POSTCONDITION_VERIFIED", "component": "AuthoritativeCompletionGate"},
            {"event_type": "GOAL_COMPLETED", "component": "AstraApplication", "data": {"status": "SUCCESS"}},
        ],
        model_events=[{"event_type": "MODEL_REQUEST", "component": "ModelService"}],
        broker_events=[{"event_type": "ACTION_DISPATCHED", "component": "ExecutionBroker"}],
        filesystem_events=[{"event_type": "ARTIFACT_CREATED", "component": "SandboxManager"}],
    )
    matrix_prod = evaluate_acceptance(pkg_prod, target_dir)
    prod_verdict = matrix_prod.get("CAUSAL_PROVENANCE", {}).get("verdict")
    results["T3_genuine_production_accepted"] = {
        "description": "Evaluator must return PASS when real production components emit genuine events",
        "verdict": prod_verdict,
        "passed": prod_verdict == "PASS",
    }

    all_passed = all(r["passed"] for r in results.values())
    return {
        "phase": "F0-25F.3",
        "stage": "STAGE 4 — PRODUCTION-ONLY CAUSAL PROVENANCE",
        "verdict": "PASS" if all_passed else "FAIL",
        "all_checks_passed": all_passed,
        "tests": results,
        "authorized_producers": [
            "AstraApplication",
            "GoalPlanner",
            "ModelService",
            "QwenCognitionService",
            "ExecutionBroker",
            "SandboxManager",
            "ResultPresentation",
            "GoalVerifier",
            "AuthoritativeCompletionGate",
        ],
    }


def main():
    report = run_provenance_audit()
    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F3_CAUSAL_PROVENANCE.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Causal provenance audit: {report['verdict']}.")
    print(f"Artifact written to {out_file}")


if __name__ == "__main__":
    main()
