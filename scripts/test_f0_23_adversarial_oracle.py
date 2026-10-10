"""Adversarial evaluation of the F0-23 Formal Acceptance Oracle against 20 deliberate false-result fixtures."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from astrarun.agent.models import (
    GoalContract,
    GoalPredicate,
    InteractionRequirement,
    PlanStep,
    PredicateType,
)
from astrarun.evaluation.acceptance_model import (
    AcceptanceDimension,
    AcceptancePredicate,
    FormalAcceptanceOracle,
    InteractionModality,
)

REPO_ROOT = Path("e:/Workspace/Active/AstraRun")

def run_adversarial_fixtures() -> List[Dict[str, Any]]:
    oracle = FormalAcceptanceOracle()
    fixtures = []

    # 1. Wrong application launched (e.g. Visual Profiler instead of VS Code)
    p1 = [AcceptancePredicate("p1", "app_identity", AcceptanceDimension.ENTITY_CORRECTNESS, "psutil", "eval", "Wrong app launched", is_mandatory=True, satisfied=False)]
    r1 = oracle.evaluate("fix_01_wrong_app", "open visual studio code", GoalContract("gc1", "open visual studio code", "LAUNCH"), None, None, custom_predicates=p1)
    fixtures.append({"id": "01_wrong_application", "description": "Wrong application launched", "verdict": r1.overall_verdict, "passed": r1.overall_verdict == "FAIL"})

    # 2. Right app name but wrong executable (e.g. spoofed fake notepad.exe)
    p2 = [AcceptancePredicate("p2", "exe_path", AcceptanceDimension.ENTITY_CORRECTNESS, "psutil", "eval", "Executable path does not match canonical identity", is_mandatory=True, satisfied=False)]
    r2 = oracle.evaluate("fix_02_wrong_exe", "open notepad", GoalContract("gc2", "open notepad", "LAUNCH"), None, None, custom_predicates=p2)
    fixtures.append({"id": "02_wrong_executable", "description": "Right app name but wrong executable", "verdict": r2.overall_verdict, "passed": r2.overall_verdict == "FAIL"})

    # 3. Correct file path but 0-byte file (authoritative Notepad regression)
    p3 = [
        AcceptancePredicate("p3a", "file_exists", AcceptanceDimension.OUTPUT_CORRECTNESS, "disk", "eval", "File exists", is_mandatory=True, satisfied=True),
        AcceptancePredicate("p3b", "file_non_empty", AcceptanceDimension.OUTPUT_CORRECTNESS, "disk", "eval", "File is 0 bytes", is_mandatory=True, satisfied=False),
    ]
    r3 = oracle.evaluate("fix_03_zero_byte", "save note with text hello", GoalContract("gc3", "save note", "PRODUCE_DOCUMENT"), None, None, custom_predicates=p3)
    fixtures.append({"id": "03_zero_byte_file", "description": "Correct file path but 0-byte file", "verdict": r3.overall_verdict, "passed": r3.overall_verdict == "FAIL"})

    # 4. Correct file but wrong content
    p4 = [AcceptancePredicate("p4", "content_match", AcceptanceDimension.OUTPUT_CORRECTNESS, "disk", "eval", "File content does not match contract text", is_mandatory=True, satisfied=False)]
    r4 = oracle.evaluate("fix_04_wrong_content", "save note with text hello", GoalContract("gc4", "save note", "PRODUCE_DOCUMENT"), None, None, custom_predicates=p4)
    fixtures.append({"id": "04_wrong_content", "description": "Correct file but wrong content", "verdict": r4.overall_verdict, "passed": r4.overall_verdict == "FAIL"})

    # 5. Correct content but wrong directory
    p5 = [AcceptancePredicate("p5", "path_match", AcceptanceDimension.OUTPUT_CORRECTNESS, "disk", "eval", "File saved in Documents instead of Desktop", is_mandatory=True, satisfied=False)]
    r5 = oracle.evaluate("fix_05_wrong_dir", "save to desktop", GoalContract("gc5", "save to desktop", "PRODUCE_DOCUMENT"), None, None, custom_predicates=p5)
    fixtures.append({"id": "05_wrong_directory", "description": "Correct content but wrong directory", "verdict": r5.overall_verdict, "passed": r5.overall_verdict == "FAIL"})

    # 6. Correct file produced via forbidden direct method when UI_REQUIRED
    p6 = [AcceptancePredicate("p6", "modality_ui", AcceptanceDimension.MODALITY_CORRECTNESS, "ui_trace", "eval", "Direct Path.write_text used when APPLICATION_UI_REQUIRED", is_mandatory=True, satisfied=False)]
    r6 = oracle.evaluate("fix_06_direct_bypass", "type in notepad and save", GoalContract("gc6", "type in notepad and save", "PRODUCE_DOCUMENT", interaction_requirement=InteractionRequirement.APPLICATION_UI_REQUIRED), None, None, custom_predicates=p6)
    fixtures.append({"id": "06_direct_substitution_ui_required", "description": "Correct final file produced through forbidden direct method when UI_REQUIRED", "verdict": r6.overall_verdict, "passed": r6.overall_verdict == "FAIL"})

    # 7. Capability says SUCCESS but world unchanged
    p7 = [AcceptancePredicate("p7", "state_transition", AcceptanceDimension.STATE_TRANSITION_CORRECTNESS, "win32", "eval", "Pre-state and post-state identical despite capability success", is_mandatory=True, satisfied=False)]
    r7 = oracle.evaluate("fix_07_no_state_change", "maximize window", GoalContract("gc7", "maximize window", "WINDOW_ACTION"), None, None, custom_predicates=p7)
    fixtures.append({"id": "07_world_unchanged", "description": "Capability says SUCCESS but world unchanged", "verdict": r7.overall_verdict, "passed": r7.overall_verdict == "FAIL"})

    # 8. Typing returns success but editor is empty
    p8 = [AcceptancePredicate("p8", "editor_text", AcceptanceDimension.STATE_TRANSITION_CORRECTNESS, "uia", "eval", "UIA text value is empty after type_into_window", is_mandatory=True, satisfied=False)]
    r8 = oracle.evaluate("fix_08_empty_editor", "type hello into notepad", GoalContract("gc8", "type hello into notepad", "EDIT_DOCUMENT"), None, None, custom_predicates=p8)
    fixtures.append({"id": "08_empty_editor_after_typing", "description": "Typing returns success but editor is empty", "verdict": r8.overall_verdict, "passed": r8.overall_verdict == "FAIL"})

    # 9. Browser process exists but wrong URL
    p9 = [AcceptancePredicate("p9", "url_match", AcceptanceDimension.STATE_TRANSITION_CORRECTNESS, "browser_cdp", "eval", "Browser loaded about:blank instead of requested target URL", is_mandatory=True, satisfied=False)]
    r9 = oracle.evaluate("fix_09_wrong_url", "open google.com", GoalContract("gc9", "open google.com", "BROWSER_NAV"), None, None, custom_predicates=p9)
    fixtures.append({"id": "09_wrong_browser_url", "description": "Browser process exists but wrong URL", "verdict": r9.overall_verdict, "passed": r9.overall_verdict == "FAIL"})

    # 10. Right URL but requested click never happened
    p10 = [AcceptancePredicate("p10", "dom_click", AcceptanceDimension.STATE_TRANSITION_CORRECTNESS, "browser_dom", "eval", "Target element was never clicked", is_mandatory=True, satisfied=False)]
    r10 = oracle.evaluate("fix_10_missing_click", "click sign in button", GoalContract("gc10", "click sign in button", "BROWSER_ACTION"), None, None, custom_predicates=p10)
    fixtures.append({"id": "10_missing_web_interaction", "description": "Right URL but requested click never happened", "verdict": r10.overall_verdict, "passed": r10.overall_verdict == "FAIL"})

    # 11. Plan correct but execution skipped
    p11 = [AcceptancePredicate("p11", "execution_trace", AcceptanceDimension.EXECUTION_REALITY, "loop", "eval", "Zero plan steps were executed", is_mandatory=True, satisfied=False)]
    r11 = oracle.evaluate("fix_11_exec_skipped", "run task", GoalContract("gc11", "run task", "GENERAL"), None, [], custom_predicates=p11)
    fixtures.append({"id": "11_execution_skipped", "description": "Plan correct but execution skipped", "verdict": r11.overall_verdict, "passed": r11.overall_verdict == "FAIL"})

    # 12. Task output correct but unrelated Explorer window opened
    se12 = [{"action": "open_folder", "is_unexpected": True, "category": "UNREQUESTED_CONSEQUENTIAL"}]
    r12 = oracle.evaluate("fix_12_explorer_opened", "save test.txt", GoalContract("gc12", "save test.txt", "PRODUCE_DOCUMENT"), None, None, side_effects=se12)
    fixtures.append({"id": "12_unrequested_explorer", "description": "Task output correct but unrelated Explorer window opened", "verdict": r12.overall_verdict, "passed": r12.overall_verdict == "FAIL"})

    # 13. Task output correct but unrelated window snapped
    se13 = [{"action": "snap_window_right", "is_unexpected": True, "category": "UNREQUESTED_CONSEQUENTIAL"}]
    r13 = oracle.evaluate("fix_13_window_snapped", "what gpu do i have", GoalContract("gc13", "what gpu do i have", "SYSTEM_QUERY"), None, None, side_effects=se13)
    fixtures.append({"id": "13_unrequested_snap", "description": "Task output correct but unrelated window snapped", "verdict": r13.overall_verdict, "passed": r13.overall_verdict == "FAIL"})

    # 14. Output correct but security broker bypassed
    sec14 = [{"action": "write_file", "gate_authorized": False, "bypassed": True}]
    r14 = oracle.evaluate("fix_14_security_bypass", "save file", GoalContract("gc14", "save file", "PRODUCE_DOCUMENT"), None, None, security_log=sec14)
    fixtures.append({"id": "14_security_bypassed", "description": "Output correct but security broker bypassed", "verdict": r14.overall_verdict, "passed": r14.overall_verdict == "FAIL"})

    # 15. Output correct but task-owned process leaked
    rd15 = {"orphaned_processes": 1, "orphaned_windows": 0}
    r15 = oracle.evaluate("fix_15_process_leaked", "save file and finish", GoalContract("gc15", "save file", "PRODUCE_DOCUMENT"), None, None, resource_delta=rd15)
    fixtures.append({"id": "15_process_leaked", "description": "Output correct but task-owned process leaked", "verdict": r15.overall_verdict, "passed": r15.overall_verdict == "FAIL"})

    # 16. Stale observation reused after world changed
    p16 = [AcceptancePredicate("p16", "observation_freshness", AcceptanceDimension.STATE_TRANSITION_CORRECTNESS, "obs_cache", "eval", "Observation timestamp older than world state mutation", is_mandatory=True, satisfied=False)]
    r16 = oracle.evaluate("fix_16_stale_obs", "click button", GoalContract("gc16", "click button", "UI_ACTION"), None, None, custom_predicates=p16)
    fixtures.append({"id": "16_stale_observation", "description": "Stale observation reused after world changed", "verdict": r16.overall_verdict, "passed": r16.overall_verdict == "FAIL"})

    # 17. Entity resolver returns plausible but wrong app
    p17 = [AcceptancePredicate("p17", "entity_semantic_check", AcceptanceDimension.ENTITY_CORRECTNESS, "resolver", "eval", "Visual Profiler resolved instead of Visual Studio Code", is_mandatory=True, satisfied=False)]
    r17 = oracle.evaluate("fix_17_plausible_wrong_app", "open visual studio code", GoalContract("gc17", "open visual studio code", "LAUNCH"), None, None, custom_predicates=p17)
    fixtures.append({"id": "17_plausible_wrong_app", "description": "Entity resolver returns plausible but wrong app", "verdict": r17.overall_verdict, "passed": r17.overall_verdict == "FAIL"})

    # 18. Application closes before required save
    p18 = [AcceptancePredicate("p18", "app_closed_pre_save", AcceptanceDimension.EXECUTION_REALITY, "process", "eval", "Application process terminated before Save As dialog completed", is_mandatory=True, satisfied=False)]
    r18 = oracle.evaluate("fix_18_premature_close", "save document in app", GoalContract("gc18", "save document", "PRODUCE_DOCUMENT"), None, None, custom_predicates=p18)
    fixtures.append({"id": "18_premature_app_close", "description": "Application closes before required save", "verdict": r18.overall_verdict, "passed": r18.overall_verdict == "FAIL"})

    # 19. User intervention changes target mid-task
    p19 = [AcceptancePredicate("p19", "target_reconciled", AcceptanceDimension.INTENT_CORRECTNESS, "user_event", "eval", "Task continued operating on stale target after conflicting user intervention", is_mandatory=True, satisfied=False)]
    r19 = oracle.evaluate("fix_19_user_conflict", "edit file", GoalContract("gc19", "edit file", "EDIT"), None, None, custom_predicates=p19)
    fixtures.append({"id": "19_unreconciled_user_intervention", "description": "User intervention changes target mid-task", "verdict": r19.overall_verdict, "passed": r19.overall_verdict == "FAIL"})

    # 20. Verifier receives fabricated capability result
    prov20 = {"fabricated": True, "source": "synthetic_mock_injection"}
    r20 = oracle.evaluate("fix_20_fabricated_result", "save file", GoalContract("gc20", "save file", "PRODUCE_DOCUMENT"), None, None, model_provenance=prov20)
    fixtures.append({"id": "20_fabricated_capability_result", "description": "Verifier receives fabricated capability result", "verdict": r20.overall_verdict, "passed": r20.overall_verdict == "FAIL"})

    return fixtures

if __name__ == "__main__":
    results = run_adversarial_fixtures()
    passed_all = all(r["passed"] for r in results)
    print(f"Executed 20 adversarial false-result fixtures. All rejected: {passed_all}")
    for r in results:
        print(f"  [{r['id']}] {r['description']}: {r['verdict']} (Rejected: {r['passed']})")
