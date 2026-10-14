"""Reproduction script for F0-25F.3 pre-fix defect audit.

Empirically demonstrates the 10 pre-fix defects identified by MiMo F0-25F.2:
A. end_run can emit/allow GOAL_COMPLETED without required verified postconditions
B. legacy REQUESTED || PRESENTED acceptance
C. hollow/weak presentation identity edge
D. empty/missing resource path can vacuously dispose
E. Stage-13 causal harness can manufacture/stub causal events
F. routing over-generalization
G. production benchmark fixture contamination
H. production workspace-path contamination
I. fabricated summary attestation values
J. source-freeze sequencing defect
"""

from __future__ import annotations

import json
import os
import sys
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
src_dir = REPO_ROOT / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

def main():
    results = {}

    # =========================================================================
    # DEFECT A: end_run emits GOAL_COMPLETED without required verified postconditions
    # =========================================================================
    from astrarun.core.telemetry import CausalTelemetry, CausalEventType
    telem = CausalTelemetry.get_instance()
    run_id = telem.start_run(query="Test goal without postconditions", task_id="task_test_a")
    ev_end = telem.end_run(status="SUCCESS", message="Finished prematurely")
    
    defect_a_reproduced = (
        ev_end is not None 
        and ev_end.event_type == CausalEventType.GOAL_COMPLETED.value
        and ev_end.data.get("status") == "SUCCESS"
    )
    results["defect_a_unconditional_goal_completed"] = {
        "run_id": run_id,
        "emitted_event_type": ev_end.event_type if ev_end else None,
        "emitted_status": ev_end.data.get("status") if ev_end else None,
        "verified_postconditions_present": False,
        "reproduced": defect_a_reproduced,
        "evidence": "telemetry.end_run emits GOAL_COMPLETED unconditionally with status=SUCCESS despite zero verified postconditions."
    }

    # =========================================================================
    # DEFECT B: Legacy REQUESTED || PRESENTED acceptance
    # =========================================================================
    stage6_path = REPO_ROOT / "scripts" / "verify_f0_25f_complete_physical.py"
    stage6_code = stage6_path.read_text(encoding="utf-8") if stage6_path.exists() else ""
    legacy_or_present = '"RESULT_PRESENTED" in pres_event_types or "RESULT_PRESENTATION_REQUESTED" in pres_event_types' in stage6_code
    
    # Simulate event list with only REQUESTED
    simulated_events = ["REQUEST_RECEIVED", "RESULT_PRESENTATION_REQUESTED"]
    passes_legacy_check = ("RESULT_PRESENTED" in simulated_events or "RESULT_PRESENTATION_REQUESTED" in simulated_events)
    
    results["defect_b_legacy_requested_or_presented"] = {
        "file": "scripts/verify_f0_25f_complete_physical.py:153",
        "legacy_or_in_code": legacy_or_present,
        "simulated_requested_only_passes": passes_legacy_check,
        "reproduced": legacy_or_present and passes_legacy_check,
        "evidence": "verify_f0_25f_complete_physical.py line 153 accepts REQUESTED even when PRESENTED is missing."
    }

    # =========================================================================
    # DEFECT C: Hollow / weak presentation identity edge
    # =========================================================================
    pres_path = REPO_ROOT / "src" / "astrarun" / "ui" / "result_presentation.py"
    pres_code = pres_path.read_text(encoding="utf-8") if pres_path.exists() else ""
    
    # Check explorer window match: is_new_window or title_matches
    explorer_bypass_present = "if is_new_window or title_matches:" in pres_code
    
    results["defect_c_hollow_presentation_identity"] = {
        "file": "src/astrarun/ui/result_presentation.py:326",
        "new_window_bypasses_title_check": explorer_bypass_present,
        "reproduced": explorer_bypass_present,
        "evidence": "In mechanism=='explorer', any new explorer window is accepted (is_new_window or title_matches) even with empty or mismatched title."
    }

    # =========================================================================
    # DEFECT D: Empty/missing resource path can vacuously dispose
    # =========================================================================
    from astrarun.tasks.resource_ledger import AstraResourceLedger, OwnedResource, ResourceType, ResourceLifecycleState
    ledger = AstraResourceLedger.get_instance()
    res_empty = OwnedResource(
        task_id="task_test_d",
        resource_type=ResourceType.SANDBOX_DIR,
        launching_capability="SandboxManager",
        document_path="", # Empty path
    )
    ledger.register_resource(res_empty)
    res_id = res_empty.resource_id
    clean_success = ledger.close_owned_resource(res_empty)
    state_after = ledger.get_resource(res_id).lifecycle_state
    
    defect_d_reproduced = clean_success and state_after == ResourceLifecycleState.CLOSED
    results["defect_d_vacuous_resource_disposal"] = {
        "resource_id": res_id,
        "document_path": "",
        "cleanup_result": clean_success,
        "lifecycle_state_after": state_after.value,
        "reproduced": defect_d_reproduced,
        "evidence": "cleanup_sandbox_directory transitioned empty-path resource to CLOSED and returned True without verifying physical absence."
    }

    # =========================================================================
    # DEFECT E: Stage-13 causal harness manufactures/stubs causal events
    # =========================================================================
    harness_path = REPO_ROOT / "scripts" / "verify_f0_25f1_complete_physical.py"
    harness_code = harness_path.read_text(encoding="utf-8") if harness_path.exists() else ""
    
    broker_override = "executor_override=lambda **_: True" in harness_code
    hardcoded_model = 'model_id="qwen2.5-coder-14b-instruct"' in harness_code
    harness_emits_model = 'event_type=CausalEventType.MODEL_REQUEST.value' in harness_code
    
    results["defect_e_harness_manufactured_causality"] = {
        "file": "scripts/verify_f0_25f1_complete_physical.py",
        "broker_stubbed": broker_override,
        "model_hardcoded": hardcoded_model,
        "harness_emits_model_events": harness_emits_model,
        "reproduced": broker_override and hardcoded_model and harness_emits_model,
        "evidence": "Verification harness directly emitted MODEL_REQUEST/MODEL_RESPONSE and stubbed broker executor."
    }

    # =========================================================================
    # DEFECT F: Routing over-generalization
    # =========================================================================
    from astrarun.agent.planner import GoalPlanner
    from astrarun.capabilities.registry import CapabilityRegistry
    from astrarun.cognition.service import ModelService
    
    planner = GoalPlanner(model_service=ModelService.get_instance())
    test_over_route_prompts = [
        ("summarize the plot of hamlet in one sentence", "execute_dynamic_tool"),
        ("solve this crossword puzzle clue: four-letter word for cat", "execute_dynamic_tool"),
        ("open visual studio code with the current folder", "execute_dynamic_tool"),
        ("search the web for python documentation", "execute_dynamic_tool"),
        ("what python version is installed", "execute_dynamic_tool"),
    ]
    
    over_route_hits = []
    for prompt, expected_bad_route in test_over_route_prompts:
        goal = planner.parse_goal(prompt)
        if goal.intent == expected_bad_route:
            over_route_hits.append({"prompt": prompt, "actual_intent": goal.intent})
            
    results["defect_f_routing_over_generalization"] = {
        "tested_prompts_count": len(test_over_route_prompts),
        "over_routed_count": len(over_route_hits),
        "over_routes": over_route_hits,
        "reproduced": len(over_route_hits) > 0,
        "evidence": f"{len(over_route_hits)}/{len(test_over_route_prompts)} non-dynamic workstation/conversational prompts were over-routed into execute_dynamic_tool."
    }

    # =========================================================================
    # DEFECT G: Production benchmark fixture contamination
    # =========================================================================
    service_path = REPO_ROOT / "src" / "astrarun" / "cognition" / "service.py"
    service_code = service_path.read_text(encoding="utf-8") if service_path.exists() else ""
    
    repair02_contamination = ("'timestamp' is missing but 'time' is present" in service_code or "No timestamp available" in service_code)
    results["defect_g_benchmark_fixture_contamination"] = {
        "file": "src/astrarun/cognition/service.py:531",
        "repair02_literal_present": repair02_contamination,
        "reproduced": repair02_contamination,
        "evidence": "Production repair prompt contains explicit REPAIR-02 fixture dictionary key instructions."
    }

    # =========================================================================
    # DEFECT H: Production workspace-path contamination
    # =========================================================================
    paths_file = REPO_ROOT / "src" / "astrarun" / "core" / "paths.py"
    paths_code = paths_file.read_text(encoding="utf-8") if paths_file.exists() else ""
    
    workspace_path_present = r"E:\Workspace\Agents\AstraRun-Anti\.venv\Scripts\python.exe" in paths_code
    results["defect_h_workspace_path_contamination"] = {
        "file": "src/astrarun/core/paths.py:334",
        "hardcoded_workspace_path_present": workspace_path_present,
        "reproduced": workspace_path_present,
        "evidence": "Production python executable resolution hardcodes developer workspace venv path."
    }

    # =========================================================================
    # DEFECT I: Fabricated summary attestation values
    # =========================================================================
    results_pres_path = REPO_ROOT / "src" / "astrarun" / "ui" / "result_presentation.py"
    results_pres_code = results_pres_path.read_text(encoding="utf-8") if results_pres_path.exists() else ""
    
    fabricated_attestation = (
        'verified_title = "AstraRun"' in results_pres_code 
        and 'verified_class = "QtLauncher"' in results_pres_code
    )
    results["defect_i_fabricated_summary_attestation"] = {
        "file": "src/astrarun/ui/result_presentation.py:269-270",
        "fabricated_literals_present": fabricated_attestation,
        "reproduced": fabricated_attestation,
        "evidence": "Summary attestation hardcodes verified_title='AstraRun' and verified_class='QtLauncher' literals without measuring actual window text/class."
    }

    # =========================================================================
    # DEFECT J: Source-freeze sequencing defect
    # =========================================================================
    freeze_path = REPO_ROOT / "docs" / "audit" / "F0_25F1_SOURCE_FREEZE.json"
    stale_freeze = False
    mismatch_details = []
    if freeze_path.exists():
        import hashlib
        freeze_data = json.loads(freeze_path.read_text(encoding="utf-8"))
        for rel_path, file_entry in freeze_data.get("source_hashes", {}).items():
            frozen_hash = file_entry.get("sha256")
            p = REPO_ROOT / rel_path
            if p.exists():
                curr_hash = hashlib.sha256(p.read_bytes()).hexdigest()
                if curr_hash != frozen_hash:
                    stale_freeze = True
                    mismatch_details.append({"file": rel_path, "frozen": frozen_hash[:16], "current": curr_hash[:16]})
                    
    results["defect_j_source_freeze_sequencing"] = {
        "freeze_file": "docs/audit/F0_25F1_SOURCE_FREEZE.json",
        "stale_files_found": len(mismatch_details),
        "mismatches": mismatch_details[:5],
        "reproduced": stale_freeze,
        "evidence": f"F0-25F.1 freeze contained stale hashes ({len(mismatch_details)} files mismatched) because code was edited after freeze generation."
    }

    # =========================================================================
    # Summary
    # =========================================================================
    reproduced_count = sum(1 for v in results.values() if v.get("reproduced"))
    out = {
        "phase": "F0-25F.3",
        "total_defects_audited": len(results),
        "defects_reproduced": reproduced_count,
        "all_reproduced": reproduced_count == len(results),
        "results": results
    }

    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F3_PRE_FIX_REPRODUCTIONS.json"
    out_file.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Pre-fix reproductions completed: {reproduced_count}/{len(results)} defects reproduced.")
    print(f"Artifact written to {out_file}")

if __name__ == "__main__":
    main()
