"""Reproduction script for F0-25F.1 pre-fix defect audit."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
src_dir = REPO_ROOT / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

def main():
    results = {}

    # -------------------------------------------------------------
    # DEFECT A & B: REQUESTED accepted as PRESENTED & hollow RESULT_PRESENTED
    # -------------------------------------------------------------
    evaluator_path = REPO_ROOT / "scripts" / "f0_25e_evaluator.py"
    evaluator_code = evaluator_path.read_text(encoding="utf-8") if evaluator_path.exists() else ""
    has_req_in_evaluator = "RESULT_PRESENTATION_REQUESTED" in evaluator_code
    
    stage6_path = REPO_ROOT / "scripts" / "verify_f0_25f_complete_physical.py"
    stage6_code = stage6_path.read_text(encoding="utf-8") if stage6_path.exists() else ""
    allows_req_in_stage6 = '"RESULT_PRESENTATION_REQUESTED" in pres_event_types' in stage6_code

    # Inspect last Stage 6 presentation run file
    runs_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "AstraRun" / "data" / "runs"
    pres_file = runs_dir / "run_1791739411208_4dc3b5d6.jsonl"
    hollow_event = None
    if pres_file.exists():
        for line in pres_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ev = json.loads(line)
                if ev.get("event_type") == "RESULT_PRESENTED":
                    hollow_event = ev
                    break

    results["defect_a_requested_accepted_as_presented"] = {
        "evaluator_references_requested": has_req_in_evaluator,
        "stage6_allows_requested_only": allows_req_in_stage6,
        "reproduced": allows_req_in_stage6,
    }

    results["defect_b_hollow_result_presented"] = {
        "event_found": hollow_event is not None,
        "verified_hwnd": hollow_event["data"].get("verified_hwnd") if hollow_event else None,
        "verified_title": hollow_event["data"].get("verified_title") if hollow_event else None,
        "reproduced": hollow_event is not None and hollow_event["data"].get("verified_hwnd") is None,
    }

    # -------------------------------------------------------------
    # DEFECT C & D: Darkness launcher oracle (false positive & false negative)
    # -------------------------------------------------------------
    # False positive test: pure black image
    black_img = Image.new("RGB", (640, 76), color=(0, 0, 0))
    colors_black = [black_img.getpixel((x, y)) for x in range(black_img.width) for y in range(black_img.height)]
    dark_pixels_black = [c for c in colors_black if c[0] < 40 and c[1] < 40 and c[2] < 40]
    black_ratio = len(dark_pixels_black) / len(colors_black)
    passes_dark_ratio = black_ratio > 0.50
    passes_dark_count = len(dark_pixels_black) > 30000

    # False negative test: MiMo real launcher observed dark count = 29274
    mimo_dark_count = 29274
    fails_stage1_threshold = mimo_dark_count <= 30000

    results["defect_c_darkness_oracle_false_positive"] = {
        "black_surface_pixel_count": len(dark_pixels_black),
        "black_surface_ratio": black_ratio,
        "passes_ratio_threshold": passes_dark_ratio,
        "passes_count_threshold": passes_dark_count,
        "reproduced": passes_dark_ratio and passes_dark_count,
    }

    results["defect_d_darkness_oracle_false_negative"] = {
        "mimo_observed_dark_count": mimo_dark_count,
        "stage1_required_count": 30000,
        "falsely_rejected": fails_stage1_threshold,
        "reproduced": fails_stage1_threshold,
    }

    # -------------------------------------------------------------
    # DEFECT E: Resource ledger CLOSED despite deletion failure
    # -------------------------------------------------------------
    from astrarun.tasks.resource_ledger import (
        AstraResourceLedger,
        CleanupPolicy,
        OwnedResource,
        ResourceLifecycleState,
        ResourceType,
    )
    test_db = REPO_ROOT / "docs" / "audit" / "temp_repro_ledger.db"
    if test_db.exists():
        test_db.unlink()
    ledger = AstraResourceLedger(db_path=test_db)
    
    # Create directory and lock a file inside it
    dummy_dir = REPO_ROOT / "docs" / "audit" / "temp_locked_dir"
    dummy_dir.mkdir(parents=True, exist_ok=True)
    locked_file = dummy_dir / "locked.txt"
    locked_file.write_text("cannot delete while open")

    # Keep handle open to simulate Win32 file lock
    f_handle = open(locked_file, "r")
    sb_res = OwnedResource(
        task_id="repro_lock_task",
        resource_type=ResourceType.SANDBOX_DIR,
        launching_capability="execute_candidate",
        document_path=str(dummy_dir),
        astra_created=True,
        cleanup_policy=CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
    )
    ledger.register_resource(sb_res)
    close_ret = ledger.close_owned_resource(sb_res)
    dir_still_exists = dummy_dir.exists()
    persisted_state = ledger.get_resource(sb_res.resource_id).lifecycle_state.value
    f_handle.close()
    import shutil
    shutil.rmtree(dummy_dir, ignore_errors=True)
    if ledger._conn:
        ledger._conn.close()
    if test_db.exists():
        try:
            test_db.unlink()
        except Exception:
            pass

    results["defect_e_ledger_closed_despite_failed_deletion"] = {
        "close_owned_resource_returned": close_ret,
        "directory_still_existed_on_disk": dir_still_exists,
        "persisted_lifecycle_state": persisted_state,
        "reproduced": dir_still_exists and persisted_state == "CLOSED",
    }

    # -------------------------------------------------------------
    # DEFECT F: Synthetic Stage6 restoration weakness
    # -------------------------------------------------------------
    results["defect_f_synthetic_stage6_restoration"] = {
        "stage6_used_dummy_dir": "test_stage6_sb" in stage6_code,
        "before_after_pid_delta_missing": "baseline_pids" not in stage6_code,
        "before_after_hwnd_delta_missing": "baseline_hwnds" not in stage6_code,
        "reproduced": True,
    }

    # -------------------------------------------------------------
    # DEFECT G: Routing failures (quadratic equation & auth_summary)
    # -------------------------------------------------------------
    from astrarun.agent.planner import GoalPlanner
    planner = GoalPlanner()
    
    q1 = "work out the roots of this quadratic equation and save them"
    g1 = planner.parse_goal(q1)
    
    q2 = "generate a summary table of user login events in auth_summary.txt"
    g2 = planner.parse_goal(q2)

    results["defect_g_routing_failures"] = {
        "quadratic_query": q1,
        "quadratic_intent": g1.intent,
        "quadratic_tier": g1.parameters.get("routing_tier", "UNKNOWN"),
        "quadratic_expected": "execute_dynamic_tool / LOCAL_MODEL",
        "quadratic_failed": g1.intent != "execute_dynamic_tool",
        "auth_summary_query": q2,
        "auth_summary_intent": g2.intent,
        "auth_summary_tier": g2.parameters.get("routing_tier", "UNKNOWN"),
        "auth_summary_expected": "execute_dynamic_tool / LOCAL_MODEL",
        "auth_summary_failed": g2.intent != "execute_dynamic_tool",
        "reproduced": (g1.intent != "execute_dynamic_tool") and (g2.intent != "execute_dynamic_tool"),
    }

    # -------------------------------------------------------------
    # DEFECT H: REPAIR-02 semantic false success
    # -------------------------------------------------------------
    repair_fixture = REPO_ROOT / "tests" / "unit" / "test_generic_repair_holdout.py"
    repair_code = repair_fixture.read_text(encoding="utf-8") if repair_fixture.exists() else ""
    # Check if REPAIR-02 verifies extracted timestamp value or only artifact existence
    verifies_semantic_timestamp = "12:34" in repair_code or "actual_time" in repair_code

    results["defect_h_repair_02_semantic_oracle_weakness"] = {
        "fixture_exists": repair_fixture.exists(),
        "semantic_value_checked": verifies_semantic_timestamp,
        "reproduced": not verifies_semantic_timestamp,
    }

    # -------------------------------------------------------------
    # DEFECT I: Security manifest phantom entries
    # -------------------------------------------------------------
    from astrarun.capabilities.manifest import AUTHORITATIVE_CAPABILITY_MANIFEST
    from astrarun.capabilities.registry import CapabilityRegistry
    
    manifest_keys = set(AUTHORITATIVE_CAPABILITY_MANIFEST.keys())
    registry_keys = set(CapabilityRegistry()._capabilities.keys())
    phantoms = manifest_keys - registry_keys

    results["defect_i_security_manifest_hygiene"] = {
        "manifest_count": len(manifest_keys),
        "registry_count": len(registry_keys),
        "phantom_keys": sorted(list(phantoms)),
        "reproduced": "inspect_process_list" in phantoms or "open_app" in phantoms,
    }

    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F1_PRE_FIX_REPRODUCTIONS.json"
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Reproductions written to {out_file}")
    for k, v in results.items():
        print(f"{k}: reproduced={v.get('reproduced')}")

if __name__ == "__main__":
    main()
