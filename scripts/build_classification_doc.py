import json
import os

def build_classification():
    with open("docs/audit/F0_25F5_FAILURE_REPRODUCTION.json", "r", encoding="utf-8") as f:
        reprod_data = json.load(f)

    classified = []
    classification_counts = {
        "REAL_PRODUCT_DEFECT": 0,
        "TEST_DEFECT": 0,
        "ENVIRONMENTAL": 0
    }

    for item in reprod_data:
        test_id = item["test_id"]
        msg = item.get("original_message", "")
        summary = item.get("error_summary", "")

        category = "REAL_PRODUCT_DEFECT"
        root_cause_file = ""
        root_cause_symbol = ""
        root_cause_line = 0
        root_cause_desc = ""
        proposed_fix = ""
        scope_of_impact = ""
        is_invariant_violation = False

        if "test_laya_router.py" in test_id:
            category = "ENVIRONMENTAL"
            root_cause_file = "tests/test_laya_router.py"
            root_cause_symbol = "import laya"
            root_cause_line = 1
            root_cause_desc = "Optional neural dependency 'laya' is not installed in the Windows Python runtime (.venv)."
            proposed_fix = "Add pytest.importorskip('laya') to guard tests when optional ML framework is absent."
            scope_of_impact = "tests/test_laya_router.py"
        elif "test_milestone4_perception_control.py" in test_id:
            category = "ENVIRONMENTAL"
            root_cause_file = "tests/test_milestone4_perception_control.py"
            root_cause_symbol = "import ultralytics"
            root_cause_line = 1
            root_cause_desc = "Optional computer-vision dependency 'ultralytics' (YOLO) is not installed in local runtime."
            proposed_fix = "Add pytest.importorskip('ultralytics') to skip perception CV tests when library is absent."
            scope_of_impact = "tests/test_milestone4_perception_control.py"
        elif "test_neural_nlp_sandwich.py" in test_id:
            category = "ENVIRONMENTAL"
            root_cause_file = "tests/test_neural_nlp_sandwich.py"
            root_cause_symbol = "import spacy"
            root_cause_line = 1
            root_cause_desc = "Optional NLP dependency 'spacy' is not installed in local runtime."
            proposed_fix = "Add pytest.importorskip('spacy') to skip spaCy tests when library is absent."
            scope_of_impact = "tests/test_neural_nlp_sandwich.py"
        elif "test_f0_24a1_adversarial_oracle.py::test_close_owned_resource_returns_false_when_process_remains" in test_id:
            category = "TEST_DEFECT"
            root_cause_file = "tests/eval_v1/test_f0_24a1_adversarial_oracle.py"
            root_cause_symbol = "test_close_owned_resource_returns_false_when_process_remains"
            root_cause_line = 70
            root_cause_desc = "Test asserted 'ok is True' when closing an un-materialized resource, which contradicts Invariant 4 (resource closure returns False if resource was not materialized or already dead)."
            proposed_fix = "Update assertion to assert ok is False in accordance with Invariant 4."
            scope_of_impact = "tests/eval_v1/test_f0_24a1_adversarial_oracle.py"
            is_invariant_violation = True
        elif "test_child_process_tree_termination_zero_orphans" in test_id:
            category = "TEST_DEFECT"
            root_cause_file = "tests/test_milestone1_security_runtime.py"
            root_cause_symbol = "test_child_process_tree_termination_zero_orphans"
            root_cause_line = 162
            root_cause_desc = "Test scanned all system-wide processes named 'powershell.exe' (including user terminal sessions), failing if any unrelated PowerShell process was running on the workstation."
            proposed_fix = "Scope orphan process verification to the specific process tree PIDs spawned during the test."
            scope_of_impact = "tests/test_milestone1_security_runtime.py"
        elif "test_task_watch_set" in test_id:
            category = "TEST_DEFECT"
            root_cause_file = "tests/test_milestone7a_adaptive_resilience.py"
            root_cause_symbol = "test_task_watch_set"
            root_cause_line = 35
            root_cause_desc = "Test assumed 'notepad.exe' was not running on the host system, failing if user had a notepad instance open."
            proposed_fix = "Check relative change in process tracking or use a non-standard mock process name."
            scope_of_impact = "tests/test_milestone7a_adaptive_resilience.py"
        elif "test_acceptance_3d_vis.py" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/cognition/service.py"
            root_cause_symbol = "CognitiveService.classify_intent"
            root_cause_line = 445
            root_cause_desc = "Regex for dynamic computation did not recognize '3d visualization' or 'program that generates', producing an empty plan."
            proposed_fix = "Extend pattern matching in cognition service and planner for 3D visualization and program generation."
            scope_of_impact = "src/astrarun/cognition/service.py, src/astrarun/agent/planner.py"
        elif "test_delegated_orchestration_loop_multi_turn_repair_and_approval" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/delegation/mock.py"
            root_cause_symbol = "MockDelegatedLLM.respond"
            root_cause_line = 135
            root_cause_desc = "Mock delegated LLM did not generate code writing trajectory.csv on repair turns for projectile motion tasks."
            proposed_fix = "Enhance rule-based mock in delegation loop to output projectile trajectory script creating trajectory.csv."
            scope_of_impact = "src/astrarun/delegation/mock.py"
        elif "test_agent_execution_engine_delegated_prompt_integration" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/agent/planner.py"
            root_cause_symbol = "GoalPlanner.replan"
            root_cause_line = 1164
            root_cause_desc = "In GoalPlanner.replan, 'candidates' iteration was executed outside the 'else' block, raising UnboundLocalError when capability was consult_delegate."
            proposed_fix = "Move candidates loop inside 'else' branch and guard with 'if not target_alt:'."
            scope_of_impact = "src/astrarun/agent/planner.py"
        elif "test_dogfood_chatgpt_workflow" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/security/execution_broker.py"
            root_cause_symbol = "ExecutionBroker.submit"
            root_cause_line = 107
            root_cause_desc = "ExecutionBroker lacked 'submit' method and AffordanceRisk enum mapping was mismatched."
            proposed_fix = "Add ExecutionBroker.submit and map AffordanceRisk appropriately."
            scope_of_impact = "src/astrarun/security/execution_broker.py"
        elif "test_holdout_class_02_csv_data_transform" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/sandbox/manager.py"
            root_cause_symbol = "DynamicExecutionRuntime._get_python_path"
            root_cause_line = 240
            root_cause_desc = "Executable Python path resolution in sandbox runtime failed to locate valid Python binary on Windows when sys.executable is inside virtualenv."
            proposed_fix = "Use sys.executable directly or resolve canonical Windows Python path."
            scope_of_impact = "src/astrarun/sandbox/manager.py"
        elif "test_holdout_class_07_autonomous_repair" in test_id or "test_dynamic_tool_builder_pipeline_and_repair" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/agent/planner.py"
            root_cause_symbol = "GoalPlanner.replan"
            root_cause_line = 1164
            root_cause_desc = "Autonomous tool repair failed due to UnboundLocalError 'candidates' in GoalPlanner.replan."
            proposed_fix = "Fix GoalPlanner.replan indentation and fallback alternative resolution."
            scope_of_impact = "src/astrarun/agent/planner.py"
        elif "test_adversarial_artifact_in_wrong_directory" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/agent/verifier.py"
            root_cause_symbol = "GoalVerifier.verify_goal"
            root_cause_line = 819
            root_cause_desc = "Verifier mutated contract path constraint (p.parameters['path'] = str(real_art)) when file was absent at specified path, allowing wrong-directory artifacts to falsely pass."
            proposed_fix = "Only populate p.parameters['path'] if path was not specified; never overwrite existing path constraint."
            scope_of_impact = "src/astrarun/agent/verifier.py"
            is_invariant_violation = True
        elif "test_holdout_novel_computation_and_save" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/agent/planner.py"
            root_cause_symbol = "GoalPlanner.extract_contract"
            root_cause_line = 232
            root_cause_desc = "Planner omitted required_content from semantic constraints when code intent lacked full file path, causing content verification failure."
            proposed_fix = "Extract required_content into entities['payload'] / entities['content'] and create SemanticConstraint."
            scope_of_impact = "src/astrarun/agent/planner.py"
        elif "test_generality_and_plugin.py" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/agent/verifier.py"
            root_cause_symbol = "GoalVerifier._verify_step_with_predicates"
            root_cause_line = 57
            root_cause_desc = "Verifier unconditionally rejected RETURN_CODE_ONLY on in-memory tasks (reverse text, parallel DAG branches) with no required file side effects."
            proposed_fix = "Only reject RETURN_CODE_ONLY when task or contract requires file postconditions or mutating side effects."
            scope_of_impact = "src/astrarun/agent/verifier.py"
        elif "test_milestone1_security_runtime.py" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            if "shutil_rmtree" in test_id:
                root_cause_file = "src/astrarun/tools/ast_inspector.py"
                root_cause_symbol = "FORBIDDEN_ATTR_CALLS"
                root_cause_line = 60
                root_cause_desc = "'rmtree' was absent from FORBIDDEN_ATTR_CALLS in AST inspector."
                proposed_fix = "Add 'rmtree' to FORBIDDEN_ATTR_CALLS."
                scope_of_impact = "src/astrarun/tools/ast_inspector.py"
            elif "eval_exec" in test_id:
                root_cause_file = "src/astrarun/security/policies.py"
                root_cause_symbol = "ASTCodePolicy.evaluate_code"
                root_cause_line = 302
                root_cause_desc = "ASTCodePolicy returned DENY for eval/exec instead of REQUIRE_CONFIRMATION."
                proposed_fix = "Return REQUIRE_CONFIRMATION when violations are exclusively eval or exec."
                scope_of_impact = "src/astrarun/security/policies.py"
            else:
                root_cause_file = "src/astrarun/security/action_gate.py"
                root_cause_symbol = "ActionGateConfig.permissions"
                root_cause_line = 68
                root_cause_desc = "ActionGate default permissions omit 'file_system' and 'execution_runtime', causing DefaultDenyPolicy to reject proposals."
                proposed_fix = "Add 'file_system': 'AUTO' and 'execution_runtime': 'AUTO' to ActionGateConfig."
                scope_of_impact = "src/astrarun/security/action_gate.py"
        elif "test_milestone7a_adaptive_resilience.py" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/runtime/task_runtime.py"
            root_cause_symbol = "TaskRuntime.init"
            root_cause_line = 45
            root_cause_desc = "TaskRuntime required an active ExecutionBroker even when initialized in test harness without explicit broker."
            proposed_fix = "Provide fallback or instantiate default ExecutionBroker in TaskRuntime when None provided."
            scope_of_impact = "src/astrarun/runtime/task_runtime.py"
        elif "test_v0101_hotfix_dwell.py" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/ui/launcher_window.py"
            root_cause_symbol = "LauncherWindow.changeEvent"
            root_cause_line = 120
            root_cause_desc = "Launcher window dismissed immediately on focus loss without respecting dwell hotfix timer."
            proposed_fix = "Enforce dwell timer before dismissing launcher on focus out."
            scope_of_impact = "src/astrarun/ui/launcher_window.py"
        elif "test_v0101_launcher_hud.py" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/hotkey/manager.py"
            root_cause_symbol = "HotkeyManager.get_diagnostics"
            root_cause_line = 180
            root_cause_desc = "HotkeyManager diagnostics dictionary missing 'last_signal_delivered_timestamp' key."
            proposed_fix = "Include 'last_signal_delivered_timestamp' in diagnostics dictionary."
            scope_of_impact = "src/astrarun/hotkey/manager.py"
        elif "test_v0101_resident_lifecycle.py" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/resident/lifecycle.py"
            root_cause_symbol = "ResidentLifecycle"
            root_cause_line = 95
            root_cause_desc = "Readiness state file creation path or stale readiness PID check logic issue."
            proposed_fix = "Align readiness state file path handling and stale PID cleanup."
            scope_of_impact = "src/astrarun/resident/lifecycle.py"
        elif "test_v0102_compound_pipeline.py" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/security/execution_broker.py"
            root_cause_symbol = "ExecutionBroker.submit"
            root_cause_line = 107
            root_cause_desc = "ExecutionBroker missing 'submit' method; AffordanceRisk string 'LOW' not converted to enum."
            proposed_fix = "Add ExecutionBroker.submit and convert risk string to AffordanceRisk enum."
            scope_of_impact = "src/astrarun/security/execution_broker.py"
        elif "test_v010_interaction.py" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/pipeline/app_pipeline.py"
            root_cause_symbol = "AppPipeline.handle_request"
            root_cause_line = 210
            root_cause_desc = "Destructive click confirmation returned 'error' status instead of 'confirm' result type."
            proposed_fix = "Return confirmation result type on destructive UI actions."
            scope_of_impact = "src/astrarun/pipeline/app_pipeline.py"
        elif "test_v09_daily_driver.py" in test_id:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_file = "src/astrarun/pipeline/app_pipeline.py"
            root_cause_symbol = "AppPipeline"
            root_cause_line = 250
            root_cause_desc = "Direct UI commands / snapping message formatting / SettingsDialog property differences."
            proposed_fix = "Fix message strings and UI dialog attributes (e.g. startup_cb vs launch_on_startup_cb)."
            scope_of_impact = "src/astrarun/pipeline/app_pipeline.py, src/astrarun/ui/settings.py"
        else:
            category = "REAL_PRODUCT_DEFECT"
            root_cause_desc = f"{msg}"
            scope_of_impact = "src/astrarun/"

        classification_counts[category] += 1

        classified.append({
            "test_id": test_id,
            "classification": category,
            "error_summary": summary,
            "original_message": msg,
            "root_cause_file": root_cause_file,
            "root_cause_symbol": root_cause_symbol,
            "root_cause_line": root_cause_line,
            "root_cause_description": root_cause_desc,
            "is_invariant_violation": is_invariant_violation,
            "proposed_fix": proposed_fix,
            "scope_of_impact": scope_of_impact
        })

    result = {
        "phase": "F0-25F.5",
        "total_failures_classified": len(classified),
        "classification_summary": classification_counts,
        "failures": classified
    }

    with open("docs/audit/F0_25F5_FAILURE_CLASSIFICATION.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print("Successfully generated docs/audit/F0_25F5_FAILURE_CLASSIFICATION.json")
    print("Classification summary:", classification_counts)

if __name__ == "__main__":
    build_classification()
