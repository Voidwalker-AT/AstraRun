"""Phase F0-22 Consolidation Plan Script.

Synthesizes findings from inventory, dependency graph, duplications, and boundaries
to create a structured, safe consolidation plan:
- KEEP: Canonical production modules (244 modules)
- DELETE: Completely dead modules with zero runtime and zero test callers
- MERGE: Duplicated subsystems that can be unified into canonical targets
- DEPRECATE_SHIM: Legacy adapters retained as light shims to avoid breaking imports
- MOVE: Files that belong in cleaner architectural namespaces

Outputs:
  docs/audit/F0_22_CONSOLIDATION_PLAN.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def generate_consolidation_plan():
    repo_root = Path(__file__).resolve().parent.parent

    # Actions planned
    actions = {
        "DELETE": [
            {
                "file": "src/astrarun/entrypoint.py",
                "rationale": "Obsolete redundant entrypoint; astrarun.__main__ is canonical.",
                "risk": "NONE",
            },
            {
                "file": "src/astrarun/capabilities/cli.py",
                "rationale": "Dead CLI capability stub; superseded by system_control and broker capabilities.",
                "risk": "NONE",
            },
            {
                "file": "src/astrarun/learning/debugger.py",
                "rationale": "Dead debugging artifact with zero production or test consumers.",
                "risk": "NONE",
            },
            {
                "file": "src/astrarun/nlp/debugger.py",
                "rationale": "Dead debugging artifact with zero production or test consumers.",
                "risk": "NONE",
            },
            {
                "file": "src/astrarun/models/downloader.py",
                "rationale": "Obsolete model downloader; canonical utility is in tools/model_downloader.py.",
                "risk": "NONE",
            },
            {
                "file": "src/astrarun/visualization/render_worker.py",
                "rationale": "Dead visualization worker duplicate; renderer.py is canonical.",
                "risk": "NONE",
            },
        ],
        "MERGE": [
            {
                "source": "src/astrarun/policy/action_gate.py",
                "target": "src/astrarun/security/action_gate.py",
                "rationale": "Unify policy/action_gate (17-line forwarding shim) into canonical security/action_gate. Retain thin backward-compatibility import in policy.",
                "risk": "LOW",
            },
            {
                "source": "src/astrarun/nlp/intent_router.py",
                "target": "src/astrarun/routing/pipeline.py",
                "rationale": "Dead duplicate intent router in nlp/; routing logic is canonically owned by routing/ package.",
                "risk": "LOW",
            },
            {
                "source": "src/astrarun/interaction/controller.py",
                "target": "src/astrarun/computer_use/controller.py",
                "rationale": "Redundant forwarding controller; unify with computer_use.controller.",
                "risk": "LOW",
            },
            {
                "source": "src/astrarun/tasks/verifier.py",
                "target": "src/astrarun/planning/verification.py",
                "rationale": "Shallow return-code verifier in tasks/ must delegate to empirical predicate GoalVerifier in planning/.",
                "risk": "LOW",
            },
            {
                "source": "src/astrarun/tasks/replanner.py",
                "target": "src/astrarun/planning/replanning.py",
                "rationale": "tasks/replanner is an older adapter; route all replan decisions through planning/replanning.GoalReplanner.",
                "risk": "LOW",
            },
        ],
        "DEPRECATE_SHIM": [
            {
                "file": "src/astrarun/policy/__init__.py",
                "action": "Maintain forward imports to astrarun.security.* with deprecation warning for legacy callers.",
                "rationale": "Preserves backward compatibility while migrating callers to canonical security package.",
            },
            {
                "file": "src/astrarun/tools/registry.py",
                "action": "Forward execution to astrarun.capabilities.registry.CapabilityRegistry via ExecutionBroker.",
                "rationale": "Prevents legacy Launcher fallback from bypassing ExecutionBroker.",
            },
        ],
        "CANONICAL_SUBSYSTEMS": {
            "routing": "astrarun.routing.pipeline.RoutingPipeline",
            "planning": "astrarun.planning.goal_planner.GoalPlanner",
            "replanning": "astrarun.planning.replanning.GoalReplanner",
            "verification": "astrarun.planning.verification.GoalVerifier",
            "computer_use": "astrarun.computer_use.controller.ComputerUseController",
            "window_management": "astrarun.windows.controller.WindowController",
            "security_governance": "astrarun.security.execution_broker.ExecutionBroker -> ActionGate",
            "execution_runtime": "astrarun.tasks.runtime.TaskRuntime & astrarun.agent.loop.AgentExecutionEngine",
        },
    }

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-22",
        "total_delete_targets": len(actions["DELETE"]),
        "total_merge_targets": len(actions["MERGE"]),
        "total_deprecate_shims": len(actions["DEPRECATE_SHIM"]),
        "actions": actions,
    }

    out_file = repo_root / "docs" / "audit" / "F0_22_CONSOLIDATION_PLAN.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Generated {out_file} with {len(actions['DELETE'])} deletes and {len(actions['MERGE'])} merges planned.")


if __name__ == "__main__":
    generate_consolidation_plan()
