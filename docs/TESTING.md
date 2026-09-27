# AstraRun Testing & Verification Report

> **Version**: 0.5.0  
> **Status**: VERIFIED & PASSING  
> **Execution Date**: 2026-09-27  

---

## 1. Test Suite Architecture

The AstraRun test suite contains **79 automated tests across 14 modules**:

1. **Laya Ensemble & Fusion Tests (v0.5)**:
   - `tests/test_v05_ensemble.py`:
     - `test_jsd_identical_distributions`: Verifies Jensen-Shannon divergence equals 0.0 for identical probability distributions.
     - `test_jsd_orthogonal_distributions`: Verifies Jensen-Shannon divergence reaches theoretical maximum ($\approx \ln(2)$) for orthogonal distributions.
     - `test_shannon_entropy`: Validates information entropy for deterministic and uniform distributions.
     - `test_fusion_mode_e0_generic`: Verifies zero-shot generic Laya output preservation.
     - `test_fusion_mode_e1_finetuned`: Verifies domain-adapted AstraRun-Laya output preservation.
     - `test_fusion_mode_e2_equal_blend`: Verifies 50/50 probability blending and proper Top-1 normalization.
     - `test_fusion_mode_e3_confidence_weighted`: Verifies dynamic weighting proportional to model confidence.
     - `test_fusion_mode_e4_disagreement_gated_abstention`: Validates that divergence exceeding $\tau_{\text{JS}} = 0.25$ forces safe `unknown` abstention.
     - `test_fusion_mode_e4_agreement_pass`: Validates that low-divergence inputs pass through cleanly.
     - `test_fusion_mode_e5_ambiguity_gated_abstention`: Verifies ambiguity $\ge 0.50$ triggers safe abstention.
     - `test_fusion_mode_e5_risk_gated_abstention`: Verifies high consequence risk triggers safe abstention.
     - `test_entity_resolver_project`: Verifies exact and fuzzy resolution to `workspace.json` projects.
     - `test_entity_resolver_app`: Verifies resolution to Start Menu applications.
     - `test_entity_resolver_port`: Verifies extraction of non-privileged network ports (e.g., 3000, 8080).
     - `test_entity_resolver_privileged_port_blocked`: **HARD POLICY**: Blocks ports $\le 1023$ (e.g., port 80, 443, 22).
     - `test_entity_resolver_protected_process_blocked`: **HARD POLICY**: Blocks system-critical processes (`system`, `registry`, `lsass`, `csrss`).
     - `test_entity_resolver_destructive_command_blocked`: **HARD POLICY**: Blocks destructive commands (`rmdir /s /q`, `format`, `del system32`).
     - `test_jev_router_disabled_and_mock`: Validates safe fallback when disabled and deterministic mock simulation for offline testing.

2. **Kev Router & Shadow Mode Tests (v0.4)**:
   - `tests/test_kev_router.py`:
     - `test_kev_router_disabled`: Verifies abstention when disabled without loading model weights.
     - `test_kev_router_construction`: Validates device/mode configuration and threshold.
     - `test_kev_router_load_failure_resilience`: Validates graceful fallback on model load failure.
     - `test_kev_router_inference_exception_resilience`: Verifies graceful unknown return on inference failure.
     - `test_kev_router_intent_mapping`: Verifies 10-class intent schema and execution authority flags.
     - `test_kev_confidence_preservation`: Verifies probability distribution and softmax normalization.
     - `test_kev_shadow_event_collector`: Verifies JSONL append, schema, and regex credential redaction.
     - `test_shadow_mode_safety_zero_execution_authority`: **CRITICAL SAFETY INVARIANT**: Verifies that even if Kev predicts `open_app` with 0.99 confidence, when production is `unknown`, **NO OS APPLICATION IS LAUNCHED**.
     - `test_kev_formatting_delimiters`: Verifies Qwen FIM/box delimiters (`<|fim_prefix|>`, `<|fim_middle|>`, `<|box_start|>`, `<|box_end|>`, `<|fim_suffix|>`).

3. **Laya Router & Shadow Mode Tests (v0.3)**:
   - `tests/test_laya_router.py`:
     - `test_laya_router_disabled`: Verifies abstention when disabled without loading model.
     - `test_laya_router_construction`: Validates device/mode configuration and threshold.
     - `test_laya_router_load_failure_resilience`: Validates graceful fallback on model load failure.
     - `test_laya_router_inference_exception_resilience`: Verifies graceful unknown return on inference failure.
     - `test_laya_router_intent_mapping`: Verifies 10-class intent schema and execution authority flags.
     - `test_laya_confidence_preservation`: Verifies choice and probability preservation.
     - `test_laya_shadow_event_collector`: Verifies JSONL append, schema, and regex credential redaction.
     - `test_shadow_mode_safety_zero_execution_authority`: **CRITICAL SAFETY INVARIANT**: Verifies that Laya predictions NEVER execute and ToolRegistry only executes production decisions.

4. **Unit Tests (v0.1 & v0.2)**:
   - `tests/test_routing.py`: Request normalization (`open`, `launch`, `start`, `go to`, `show`), application/folder/URL routing, and unknown rejection.
   - `tests/test_config.py`: Default and custom configuration loading, corrupted JSON resilience.
   - `tests/test_tools.py`: Tool registry validation, missing tool blocks, risk tier enforcement (`LOW`, `MEDIUM`, `HIGH`, `BLOCKED`).
   - `tests/test_search.py`: Acronym extraction, subsequence matching, fuzzy scoring hierarchy, bounded usage boost, and textual dominance over frequency.
   - `tests/test_usage.py`: Usage store lifecycle, atomic persistence, corrupted JSON recovery.
   - `tests/test_telemetry.py`: Credential redaction (`sk-...`, Bearer tokens, passwords), local logging, disabled mode, and omit-raw-request mode.
   - `tests/test_positioning.py`: Window positioning calculations and target screen geometry fallbacks.
   - `tests/test_security_regression.py`: Prevention of command injection metacharacters (`&`, `|`, `;`, `$`, `%`) and URL protocol verification.

5. **UI Tests**:
   - `tests/test_ui.py`: Window show/dismiss, Escape key handling, initial state, suggestions generation, feedback messages.
   - `tests/test_ui_v02.py`: Keyboard arrow navigation (`Up`/`Down`), Tab autocompletion, weak suggestion rejection on Enter.

6. **Integration Tests**:
   - `tests/test_integration.py`: Live Windows application discovery (~400 apps cached), dynamic known folders, live routing.

---

## 2. Automated Test Execution & Results

```powershell
.venv\Scripts\pytest -v
```

### Results Summary
- **Total Tests Collected**: 79
- **Passed**: 79
- **Failed**: 0
- **Duration**: ~0.85s (without heavy model weights loaded during testing)

```text
tests/test_config.py::test_load_default_config PASSED                    [  1%]
tests/test_config.py::test_load_custom_config PASSED                     [  2%]
tests/test_config.py::test_corrupted_json_resilience PASSED              [  3%]
tests/test_integration.py::test_live_app_discovery PASSED                [  5%]
tests/test_integration.py::test_live_folder_discovery PASSED             [  6%]
tests/test_integration.py::test_live_routing_apps PASSED                 [  7%]
tests/test_integration.py::test_live_routing_folders PASSED              [  8%]
tests/test_integration.py::test_live_routing_urls PASSED                 [ 10%]
tests/test_integration.py::test_live_routing_unknown PASSED              [ 11%]
tests/test_positioning.py::test_compute_launcher_position PASSED         [ 12%]
tests/test_positioning.py::test_target_screen_geometry PASSED            [ 13%]
tests/test_routing.py::test_normalization PASSED                         [ 15%]
tests/test_routing.py::test_route_applications PASSED                    [ 16%]
tests/test_routing.py::test_route_folders PASSED                         [ 17%]
tests/test_routing.py::test_route_urls PASSED                            [ 18%]
tests/test_routing.py::test_route_unknown PASSED                         [ 20%]
tests/test_search.py::test_acronym_extraction PASSED                     [ 21%]
tests/test_search.py::test_subsequence PASSED                            [ 22%]
tests/test_search.py::test_fuzzy_scorer_hierarchy PASSED                 [ 24%]
tests/test_search.py::test_usage_boost_bounded PASSED                    [ 25%]
tests/test_search.py::test_textual_match_dominates_usage PASSED          [ 26%]
tests/test_search.py::test_search_index_operations PASSED                [ 27%]
tests/test_security_regression.py::test_command_injection_symbols_are_not_evaluated PASSED [ 29%]
tests/test_security_regression.py::test_url_tool_blocks_dangerous_schemes PASSED [ 30%]
tests/test_security_regression.py::test_url_tool_allows_safe_schemes PASSED [ 31%]
tests/test_telemetry.py::test_redact_sensitive_text PASSED               [ 32%]
tests/test_telemetry.py::test_telemetry_collector_logging PASSED         [ 34%]
tests/test_telemetry.py::test_telemetry_disabled PASSED                  [ 35%]
tests/test_telemetry.py::test_telemetry_no_raw_request PASSED            [ 36%]
tests/test_tools.py::test_registry_default_tools PASSED                  [ 37%]
tests/test_tools.py::test_registry_blocks_unknown PASSED                 [ 39%]
tests/test_tools.py::test_registry_blocks_unregistered PASSED            [ 40%]
tests/test_tools.py::test_registry_enforces_blocked_risk PASSED          [ 41%]
tests/test_mock_tool_execution PASSED                                     [ 43%]
tests/test_ui.py::test_launcher_initial_state PASSED                     [ 44%]
tests/test_ui.py::test_launcher_show_and_dismiss PASSED                  [ 45%]
tests/test_ui.py::test_launcher_escape_key PASSED                        [ 46%]
tests/test_ui.py::test_launcher_suggestions PASSED                       [ 48%]
tests/test_ui.py::test_launcher_feedback_message PASSED                  [ 49%]
tests/test_ui_v02.py::test_arrow_key_navigation PASSED                   [ 50%]
tests/test_ui_v02.py::test_tab_completion PASSED                         [ 51%]
tests/test_ui_v02.py::test_weak_result_rejected_on_enter PASSED          [ 53%]
tests/test_usage.py::test_usage_store_lifecycle PASSED                   [ 54%]
tests/test_usage.py::test_corrupted_usage_file PASSED                    [ 55%]
tests/test_kev_router.py::test_kev_router_disabled PASSED                [ 56%]
tests/test_kev_router.py::test_kev_router_construction PASSED            [ 58%]
tests/test_kev_router.py::test_kev_router_load_failure_resilience PASSED [ 59%]
tests/test_kev_router.py::test_kev_router_inference_exception_resilience PASSED [ 60%]
tests/test_kev_router.py::test_kev_router_intent_mapping PASSED          [ 62%]
tests/test_kev_confidence_preservation PASSED                            [ 63%]
tests/test_kev_shadow_event_collector PASSED                            [ 64%]
tests/test_shadow_mode_safety_zero_execution_authority PASSED            [ 65%]
tests/test_kev_formatting_delimiters PASSED                              [ 67%]
tests/test_laya_router.py::test_laya_router_disabled PASSED              [ 68%]
tests/test_laya_router.py::test_laya_router_construction PASSED          [ 69%]
tests/test_laya_router.py::test_laya_router_load_failure_resilience PASSED [ 70%]
tests/test_laya_router.py::test_laya_router_inference_exception_resilience PASSED [ 72%]
tests/test_laya_router.py::test_laya_router_intent_mapping PASSED        [ 73%]
tests/test_laya_confidence_preservation PASSED                           [ 74%]
tests/test_laya_shadow_event_collector PASSED                           [ 75%]
tests/test_shadow_mode_safety_zero_execution_authority PASSED           [ 77%]
tests/test_v05_ensemble.py::test_jsd_identical_distributions PASSED      [ 78%]
tests/test_v05_ensemble.py::test_jsd_orthogonal_distributions PASSED     [ 79%]
tests/test_v05_ensemble.py::test_shannon_entropy PASSED                  [ 81%]
tests/test_v05_ensemble.py::test_fusion_mode_e0_generic PASSED           [ 82%]
tests/test_v05_ensemble.py::test_fusion_mode_e1_finetuned PASSED         [ 83%]
tests/test_v05_ensemble.py::test_fusion_mode_e2_equal_blend PASSED       [ 84%]
tests/test_v05_ensemble.py::test_fusion_mode_e3_confidence_weighted PASSED [ 86%]
tests/test_v05_ensemble.py::test_fusion_mode_e4_disagreement_gated_abstention PASSED [ 87%]
tests/test_v05_ensemble.py::test_fusion_mode_e4_agreement_pass PASSED    [ 88%]
tests/test_v05_ensemble.py::test_fusion_mode_e5_ambiguity_gated_abstention PASSED [ 89%]
tests/test_v05_ensemble.py::test_fusion_mode_e5_risk_gated_abstention PASSED [ 91%]
tests/test_v05_ensemble.py::test_entity_resolver_project PASSED          [ 92%]
tests/test_v05_ensemble.py::test_entity_resolver_app PASSED              [ 93%]
tests/test_v05_ensemble.py::test_entity_resolver_port PASSED             [ 94%]
tests/test_v05_ensemble.py::test_entity_resolver_privileged_port_blocked PASSED [ 96%]
tests/test_v05_ensemble.py::test_entity_resolver_protected_process_blocked PASSED [ 97%]
tests/test_v05_ensemble.py::test_entity_resolver_destructive_command_blocked PASSED [ 98%]
tests/test_v05_ensemble.py::test_jev_router_disabled_and_mock PASSED     [100%]
```

---

## 3. Standardized Routing Evaluation Benchmark

```powershell
.venv\Scripts\python benchmarks\routing\run_benchmark.py
```

### Benchmark Metric Highlights (88 Curated Test Cases)
- **Overall Accuracy**: **100.0%** (88 / 88)
- **Exact Resolution Accuracy**: **100.0%** (20 / 20)
- **Fuzzy Resolution Accuracy**: **100.0%** (20 / 20)
- **Unresolved Rejection Accuracy**: **100.0%** (18 / 18)
- **FALSE EXECUTION RATE**: **0.0%** (0 / 18 false triggers)
- **Mean Search Latency**: **3.03 ms**
- **p50 Search Latency**: **21.7 µs**
- **p95 Search Latency**: **16.8 ms**

---

## 4. Empirical Manual Verification Matrix

| Query Executed | Expected Category & Target | Result Observed | Verification Status |
| :--- | :--- | :--- | :--- |
| `notepad` | `open_app(notepad)` | Notepad launched immediately | **PASSED** |
| `notpad` (typo) | `open_app(notepad)` via typo score 0.86 | Notepad launched immediately | **PASSED** |
| `calc` | `open_app(calc)` | Windows Calculator opened | **PASSED** |
| `vscode` | `open_app(code)` via alias | VS Code launched | **PASSED** |
| `refresh apps` | `refresh_apps()` internal tool | App discovery cache re-scanned in UI | **PASSED** |
| `downloads` | `open_folder(Downloads)` | File Explorer opened Downloads | **PASSED** |
| `github` | `open_url(github.com)` | Web browser opened GitHub | **PASSED** |
| `kill port 3000` | Rejection (`unknown`) | Rejected with feedback in UI, no process killed | **PASSED** |
| `delete system32` | Rejection (`unknown`) | Rejected with feedback in UI, zero side-effects | **PASSED** |
| `asdfgh` | Rejection (`unknown`) | Rejected with feedback in UI | **PASSED** |
| `open the project from yesterday` | Rejection (`unknown`) | Quarantined for future AI classifier | **PASSED** |
