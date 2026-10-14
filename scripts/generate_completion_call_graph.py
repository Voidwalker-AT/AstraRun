"""Generate the Completion Call Graph artifact for F0-25F.3 Stage 1."""

import json
from pathlib import Path

def main():
    call_graph = {
        "phase": "F0-25F.3",
        "title": "AstraRun Completion Call Graph and Gate Architecture",
        "completion_emitters": [
            {
                "site": "src/astrarun/core/telemetry.py:end_run",
                "action": "Emits CausalEventType.GOAL_COMPLETED and clears active run scope",
                "defect_identified": "Previously emitted GOAL_COMPLETED unconditionally with status=SUCCESS/FAILED without verifying goal contract postconditions",
                "repair": "Must invoke AuthoritativeCompletionGate.can_complete before emitting GOAL_COMPLETED"
            },
            {
                "site": "src/astrarun/core/telemetry.py:emit",
                "action": "Emits raw CausalEvent to stream and memory",
                "defect_identified": "Allowed direct callers to emit GOAL_COMPLETED bypassing postcondition checks",
                "repair": "Gated: emit() intercepts GOAL_COMPLETED and verifies contract postconditions"
            },
            {
                "site": "src/astrarun/app.py:handle_request",
                "action": "Calls telem.end_run(status='SUCCESS' if res.success else 'FAILED')",
                "defect_identified": "Relies purely on ExecutionResult.success rather than verified contract postconditions",
                "repair": "Calls AuthoritativeCompletionGate.verify_and_complete(goal, execution_result, evidence)"
            },
            {
                "site": "src/astrarun/tasks/runtime.py:execute_task",
                "action": "Transitions task to TaskStatus.COMPLETED and emits TaskEventType.TASK_COMPLETED",
                "defect_identified": "Transitions on action step completion rather than goal contract predicate verification",
                "repair": "Requires postcondition verification before TaskStatus.COMPLETED transition"
            },
            {
                "site": "src/astrarun/tasks/manager.py:complete_task",
                "action": "Transitions task to TaskStatus.COMPLETED",
                "defect_identified": "Transitions directly on result.status",
                "repair": "Enforces contract predicate satisfaction"
            },
            {
                "site": "src/astrarun/agent/verifier.py:verify_goal_contract",
                "action": "Computes GoalVerificationResult and emits POSTCONDITION_VERIFIED",
                "defect_identified": "Did not cover presentation or resource disposition predicates",
                "repair": "Unified with AuthoritativeCompletionGate"
            }
        ],
        "authoritative_completion_gate": {
            "class": "AuthoritativeCompletionGate",
            "module": "src/astrarun/agent/completion_gate.py",
            "method": "can_complete(goal_contract, execution_state, evidence_state)",
            "required_dimensions": [
                "artifact_existence",
                "artifact_content",
                "application_window_state",
                "computation_result",
                "requested_presentation",
                "required_resource_disposition",
                "security_authorization",
                "run_and_task_id_provenance"
            ],
            "invariants": [
                "UNKNOWN != TRUE",
                "MISSING != TRUE",
                "REQUESTED != VERIFIED",
                "ATTEMPTED != VERIFIED",
                "A cleanup failure blocks completion when cleanup/restoration is required",
                "A presentation failure blocks completion when presentation is requested",
                "Deterministic goals only require their relevant predicates"
            ]
        }
    }

    out_path = Path("docs/audit/F0_25F3_COMPLETION_CALL_GRAPH.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(call_graph, indent=2), encoding="utf-8")
    print(f"Saved {out_path}")

if __name__ == "__main__":
    main()
