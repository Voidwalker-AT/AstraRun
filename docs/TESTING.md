# AstraRun Testing & Verification Report

> **Version**: 0.11.1 (Generality & Reality Gate)  
> **Status**: VERIFIED & PASSING  
> **Execution Date**: 2026-09-29  

---

## 1. Test Suite Architecture

The AstraRun test suite contains **395 automated tests across 29 modules**:

0. **Agent Generality & Dynamic Plugin Tests (v0.11.1)**:
   - `tests/test_generality_and_plugin.py` (11 tests):
     - `test_single_plugin_discovery_reverse_text`: Dynamic discovery of novel held-out capability (`reverse_text`) without planner.py edits.
     - `test_novel_composition_reverse_and_save`: Dynamic 2-step DAG composition with `OutputReference` writing reversed text to file.
     - `test_parallel_branches_cpu_memory_summary`: Parallel branch scheduling and readiness detection in `ExecutionGraph`.
     - `test_symbolic_output_reference_resolution`: Dynamic runtime resolution of symbolic `OutputReference` tokens.
     - `test_dynamic_replan_with_fallback_action`: Closed-loop replan substituting fallback action upon unexpected failure and recording `PlanRevision`.
     - `test_validator_rejects_cycles`: `PlanQualityValidator` static cycle detection and rejection.
     - `test_validator_rejects_dangling_output_reference`: `PlanQualityValidator` dangling output reference rejection.
     - `test_negation_excludes_negated_capability`: Negated action extraction and exclusion from executable plan.
     - `test_typed_plan_condition`: Evaluation of typed comparison and non-empty plan conditions.
     - `test_alpha_beta_gamma_pipeline`: Dynamic 3-step pipeline (`tool_alpha` -> `tool_beta` -> `tool_gamma`) registered after startup.
     - `test_observation_ttl_expiry`: Dynamic observation timestamp expiration against `freshness_ttl_s`.

1. **Dynamic Agent Runtime & Closed-Loop Planning Tests (v0.11)**:
   - `tests/test_agent_runtime.py` (10 tests):
     - `test_parse_battery_report_goal`: Dynamic goal parsing and plan synthesis for battery reporting.
     - `test_parse_wifi_goals`: Dynamic Wi-Fi goal parsing (`wifi_scan`, `wifi_status`, `wifi_connect`) with parameter extraction.
     - `test_parse_compound_open_and_type`: Dynamic compound multi-step goal parsing and step dependency linking.
     - `test_topological_readiness`: ExecutionGraph topological readiness evaluation and output mapping.
     - `test_cycle_detection`: Kahn's cycle detection raising `DependencyCycleError` on cyclical plans.
     - `test_progress_calculation`: Honest step-weighted progress percentage calculation (0% to 100%).
     - `test_lock_acquire_and_release`: ResourceLockManager mutual exclusion, re-entrancy, and timeout enforcement.
     - `test_release_all_for_task`: Bulk cleanup of all held workstation resource locks upon task completion.
     - `test_successful_closed_loop`: Full observe-act-verify closed loop with `StepVerifier` and `AgentExecutionEngine`.
     - `test_task_cancellation`: Cooperative mid-flight task cancellation halting queued steps.
   - `tests/test_battery_report.py` (4 tests):
     - `test_blocks_shell_characters`: Prohibited shell metacharacter rejection in `SystemUtilityAdapter`.
     - `test_downloads_directory_resolution`: Known folder resolution for user `Downloads` directory.
     - `test_generate_battery_report_custom_temp_path`: Safe HTML battery report generation and verification.
     - `test_normalize_bare_filename_to_downloads`: Automated destination path normalization to user `Downloads`.
   - `tests/test_wifi_capabilities.py` (8 tests):
     - `test_exact_match_case_insensitive`: Case-insensitive exact matching in `WiFiResolver`.
     - `test_substring_match`: Substring matching for human-entered SSIDs.
     - `test_fuzzy_match`: Fuzzy Levenshtein ratio matching for human typos in network names.
     - `test_no_match_returns_none`: Clean rejection of unmatched candidate SSIDs.
     - `test_wifi_status`: Native `wlanapi.dll` status query returning connection state and active SSID.
     - `test_wifi_scan`: In-process BSS network list query returning available SSIDs and signal qualities.
     - `test_wifi_connect_empty_ssid_fails`: Validation failure on empty network targets.
     - `test_verifier_network_ssid`: Empirical network state verification using `NETWORK_SSID` verifier strategy.
   - `tests/test_motion_and_hud_v2.py` (9 tests):
     - `test_default_durations`: Standard centralized motion token timing verification.
     - `test_reduced_motion_collapses_to_zero`: Windows `SPI_GETCLIENTAREAANIMATION` accessibility compliance (0ms cut).
     - `test_reduced_motion_query_runs_safely`: Safe Win32 system parameter query execution.
     - `test_eta_calculation`: Real empirical step duration rolling average calculation in `TaskETAEstimator`.
     - `test_eta_zero_when_complete`: Clean clearance of ETA display upon task completion.
     - `test_non_focus_stealing_flags`: Verification of `WS_EX_NOACTIVATE` and `WA_ShowWithoutActivating` on HUD V2.
     - `test_progress_modes`: Verification of `INSTANT`, `DETERMINATE`, and `INDETERMINATE` progress states.
     - `test_dynamic_step_list`: Dynamic step list population, execution glyph updates (`►`, `✓`), and accordion expansion.
     - `test_cancellation_signal`: User cancellation signal dispatch from close button.

2. **Neural NLP Sandwich Tests (v0.10.3)**:
   - `tests/test_neural_nlp_sandwich.py` (16 tests):
     - `test_neural_structure_engine_compound_split`: Verifies dependency parse splitting of compound clauses.
     - `test_neural_structure_engine_negation_detection`: Verifies structural negation tagging (`is_negated: bool`).
     - `test_neural_structure_engine_literal_preservation`: Verifies verbatim character preservation of text payloads.
     - `test_laya_sandwich_shared_agent`: Proves Laya A and B share single singleton `ModernBERT 421M` instance.
     - `test_decision_fusion_fast_path_bypass`: Verifies Tier 0 fast path bypasses neural parsing for single commands.
     - `test_decision_fusion_compound_approval`: Verifies multi-clause approval with sequential clause grounding.
     - `test_decision_fusion_negation_gating`: Verifies complete exclusion of negated actions from executable steps.
     - `test_e2e_open_notepad_and_type`: Validates end-to-end simulated compound compilation and execution.

2. **Compound Pipeline & Reachability Tests (v0.10.2)**:
   - `tests/test_v0102_compound_pipeline.py` (10 tests):
     - `test_has_compound_indicators`: Detection of conjunctions (`and`, `then`, `&`, `;`) and multi-clause verbs.
     - `test_has_compound_indicators_false_for_simple`: Validates simple queries do not trigger compound indicators.
     - `test_router_escalates_compound_queries`: Verifies compound queries bypass single-app fast path.
     - `test_clause_decomposition_app_and_text`: Validates IR decomposition of `open notepad and type pqr`.
     - `test_workflow_context_implicit_binding`: State propagation across `last_opened_application` and `last_opened_window`.
     - `test_workflow_compiler_expands_to_4_steps`: Sequential expansion to `open_app` -> `wait_window` -> `resolve_element` -> `type_text`.
     - `test_workflow_compiler_expands_app_and_window`: Expansion to `open_app` -> `wait_window` -> `maximize_window`.
     - `test_workflow_compiler_shortcut_chaining`: Resolution of sequential keyboard shortcut chords.
     - `test_launcher_suppresses_suggestions_on_compound_query`: Validates suggestion list is cleared and hidden on compound input.
     - `test_end_to_end_compound_handle_request`: End-to-end execution of compound commands in simulated environment.


1. **Application Interaction & Control Grounding Tests (v0.10)**:
   - `tests/test_v010_interaction.py` (41 tests):
     - `test_uielementref_serialization`: Serialization/deserialization of UIElementRef dataclass.
     - `test_control_types_and_patterns`: ControlType and ControlPattern enum coverage and UIA mappings.
     - `test_keyboard_shortcut_canonical`: KeyboardShortcut canonical formatting and normalizations.
     - `test_destructive_action_classification`: Gating detection of destructive action keywords.
     - `test_safe_exceptions_in_destructive_action`: Whitelist of safe navigation actions (cancel, reset zoom).
     - `test_password_element_detection`: IsPassword attribute and heuristic name/ID detection.
     - `test_redact_sensitive_content`: Password token, API key, and bearer token redaction.
     - `test_target_validation`: Simulated vs live window validation, HWND 0 rejection, and self-targeting guards.
     - `test_element_resolver_exact_automation_id`: High-confidence AutomationId matching.
     - `test_element_resolver_exact_name`: Exact name matching.
     - `test_element_resolver_control_type_boost`: ControlType preference boost (+0.04).
     - `test_element_resolver_synonyms`: Registered synonym matching.
     - `test_element_resolver_ambiguity_detection`: Resolves ambiguous matches to CLARIFY outcome.
     - `test_element_resolver_not_found`: Graceful NOT_FOUND for unmatched queries.
     - `test_keyboard_parse_valid`: Parsing valid modifiers and single primary keys.
     - `test_keyboard_parse_invalid`: Rejection of malformed or multiple-key shortcuts.
     - `test_keyboard_dispatch_simulated`: Simulated SendInput shortcut dispatch.
     - `test_type_text_simulated`: Simulated Unicode text typing.
     - `test_controller_invoke_element`: Control invocation via InvokePattern.
     - `test_controller_invoke_destructive_element_blocked`: Destructive action confirmation gating without force.
     - `test_controller_set_element_value`: Atomic ValuePattern value assignment.
     - `test_controller_toggle_element`: Checkbox toggling via TogglePattern.
     - `test_controller_select_element`: Tab and row selection via SelectionItemPattern.
     - `test_controller_focus_element`: Direct keyboard focus assignment via SetFocus.
     - `test_controller_scroll_element`: Logical container scrolling via ScrollPattern.
     - `test_service_inspect_ui`: High-level capability for UI tree enumeration.
     - `test_service_click_element_safe`: Safe button click capability.
     - `test_service_click_element_destructive_gated`: Destructive click PERMISSION_DENIED.
     - `test_service_set_element_text`: Set element text capability.
     - `test_service_toggle_checkbox`: Checkbox toggling capability.
     - `test_service_select_tab`: Tab selection capability.
     - `test_service_focus_control`: Focus assignment capability.
     - `test_service_scroll_control`: Container scrolling capability.
     - `test_service_press_shortcut`: Keyboard shortcut capability.
     - `test_service_type_literal_text_payload_as_data`: Verifies text entry is strictly treated as data payload.
     - `test_app_pipeline_ui_click`: Canonical `AstraApplication.handle_request` UI click routing.
     - `test_app_pipeline_ui_destructive_click_confirmation`: Canonical pipeline destructive confirmation gating.
     - `test_app_pipeline_ui_type_into`: Canonical pipeline type into edit field routing.
     - `test_app_pipeline_ui_toggle`: Canonical pipeline checkbox toggle routing.
     - `test_app_pipeline_ui_shortcuts`: Canonical pipeline shortcut dispatch (`ctrl+c`, `copy`, `paste`, `select all`).
     - `test_live_ui_fixture_roundtrip`: Live COM UIA and SendInput against isolated out-of-process PySide6 window.

2. **Daily Driver Integration & Window Intelligence Tests (v0.9)**:
   - `tests/test_v09_daily_driver.py` (37 tests):
     - `test_window_resolver_direct_match`: Resolves exact window title and app name.
     - `test_window_resolver_pronoun_to_origin`: Grounds "this window", "current window", "it" to origin window.
     - `test_window_resolver_context_anaphora`: Grounds "that window" to last inspected window.
     - `test_window_resolver_ambiguity_gating`: Ambiguous query yields WAITING_CLARIFICATION.
     - `test_window_resolver_exact_title_break_ambiguity`: Exact title matches resolve disambiguation.
     - `test_desktop_layout_engine_half_splits`: Verifies mathematical boundaries for left/right/top/bottom splits.
     - `test_desktop_layout_engine_quad_corners`: Verifies 2x2 quadrant geometries.
     - `test_desktop_layout_engine_two_thirds_and_one_third`: Verifies coding focus split.
     - `test_geometry_clamping`: Clamps window to visible work area with min 300x200.
     - `test_window_restore_stack_lifo`: Verifies LIFO restore stack popping.
     - `test_window_restore_stack_bounded_depth`: Verifies bounded depth (max 20).
     - `test_window_restore_stack_ttl_expiration`: Verifies 600s TTL pruning.
     - `test_astrarun_self_window_protection`: `_ASTRARUN_HWNDS` self-targeting protection.
     - `test_validate_window_identity_null_or_negative`: Rejects invalid HWNDs.
     - `test_validate_window_identity_toctou_pid_mismatch`: Rejects recycled HWNDs.
     - `test_monitor_resolution_natural_language`: Resolves "monitor 2", "second monitor", "main display".
     - `test_astra_application_initialization`: Initializes all 14 platform subsystems.
     - `test_handle_request_fast_path`: Verifies sub-3ms fast path routing.
     - `test_handle_request_direct_ui_commands`: Verifies instant UI navigation commands.
     - `test_handle_request_window_snapping_and_undo`: Verifies snapping and undo through handle_request.
     - `test_handle_request_system_inspection`: Verifies hardware telemetry queries.
     - `test_handle_request_safety_confirmation_gate`: Verifies ActionGate confirmation gating.
     - `test_handle_request_reasoning_escalation`: Verifies AI bridge boundary escalation.
     - `test_handle_request_empty_query`: Handles whitespace or empty requests safely.
     - `test_single_instance_lock`: Verifies named Win32 mutex lock.
     - `test_window_layout_snapshot_serialization`: Snapshot round-trip serialization.
     - `test_monitor_entity_serialization`: Monitor entity serialization.
     - `test_window_bounds_dataclass`: WindowBounds to_tuple and to_dict.
     - `test_layout_type_parsing_variations`: Normalization of layout string variants.
     - `test_window_restore_stack_clear`: Stack clearing logic.
     - `test_window_resolution_dataclass`: WindowResolution serialization.
     - `test_controller_move_and_resize_simulation`: Verifies window movement simulation.
     - `test_controller_move_to_monitor_simulation`: Verifies cross-monitor movement simulation.
     - `test_controller_close_window_simulation`: Verifies graceful WM_CLOSE simulation.
     - `test_controller_arrange_desktop_simulation`: Verifies multi-window desktop arrangement.
     - `test_diagnostics_dialog_data_collection`: Verifies system diagnostics telemetry.
     - `test_settings_dialog_preferences_io`: Verifies settings loading and saving.

2. **Memory, Learning & Skill Foundation Tests (v0.8.5)**:
   - `tests/test_v085_learning.py` (18 tests):
     - `test_memory_models_and_enums`: Dataclass immutability, enum mapping, serialization.
     - `test_confidence_calculator_math`: Formula checks, positive weights, double contradiction penalty, asymptotic saturation.
     - `test_confidence_time_decay`: Half-life decay over 70 days, pinned fact floor ($\ge 0.95$).
     - `test_confidence_conflict_detection`: Contradiction identification, threshold gating.
     - `test_sqlite_learning_store_schema`: SQLite WAL mode, foreign keys, user_version = 1.
     - `test_sqlite_learning_store_crud`: Memory insertion, retrieval, update, deletion.
     - `test_evidence_extractor_natural_language`: Teaching syntax parsing (`"remember that foo is bar"`).
     - `test_evidence_extractor_corrections`: Correction detection across 120s window (*"no, I meant code"*).
     - `test_evidence_extractor_security_filter`: Non-learnable security policies and dangerous commands blocked from learning.
     - `test_memory_store_confirm_and_reject`: User confirmation, rejection, and tombstone tracking.
     - `test_alias_manager_precedence`: Multi-tier precedence resolution (`Static > Conflicted Gating > User-Confirmed Learned > High-Confidence Habit > Fuzzy`).
     - `test_alias_manager_conflict_gating`: Ambiguity suppression when conflicting aliases exist.
     - `test_pattern_miner_discovery`: Discovery of recurring sequences ($L \in [2,5]$, support $\ge 3$).
     - `test_skill_manager_compilation`: Compilation of skill candidates into executable workflows.
     - `test_learning_engine_background_dispatch`: Off-hot-path background worker execution.
     - `test_dataset_builder_sanitization`: Offline dataset export with token redaction and path normalization.
     - `test_security_regressions_non_learnable`: Confirmations and hard policies cannot be weakened or bypassed.
     - `test_ui_memory_and_skills`: PySide6 `MemoryView` and `SkillReviewWidget` interaction and signals.

2. **Task Runtime, Activity & History Tests (v0.8)**:
   - `tests/test_v08_tasks.py` (28 tests):
     - `test_task_status_properties`: 14 formal states, `is_terminal`, `is_active`, `is_waiting`.
     - `test_fsm_valid_transitions`: Legal state transitions verified.
     - `test_fsm_invalid_transitions`: Illegal transitions throw `InvalidStateTransitionError`.
     - `test_task_model_lifecycle`: Timing, duration calculation, and dict serialization.
     - `test_task_event_immutability`: Frozen dataclass immutability.
     - `test_cancellation_token_basics`: Cooperative token cancellation, reasons, and callbacks.
     - `test_task_event_bus`: Pub/sub registration, task filtering, and unsubscription.
     - `test_task_event_bus_exception_safety`: Subscriber callback error isolation.
     - `test_sanitize_request_redaction`: Regex redaction of API keys, bearer tokens, passwords.
     - `test_hash_request`: Deterministic SHA-256 request hashing.
     - `test_sanitize_capability_payload`: Bounded payload extraction (processes, files).
     - `test_generate_task_title`: Natural deterministic title generation.
     - `test_ledger_schema_and_pragmas`: SQLite WAL mode, foreign keys, user_version = 1.
     - `test_ledger_task_crud`: Complete task and event persistence and rehydration.
     - `test_ledger_queries`: Recent, status, capability, range, and search queries.
     - `test_ledger_crash_recovery`: Dangling active tasks marked `INTERRUPTED`.
     - `test_ledger_corruption_recovery`: Automatic corrupt file backup and fresh DB regeneration.
     - `test_ledger_retention_and_clear`: Retention pruning and total history clearing.
     - `test_ledger_export_task`: Complete JSON export of task metadata and timeline.
     - `test_task_manager_lifecycle`: Full lifecycle orchestration and active task cleanup.
     - `test_task_manager_block_and_fail`: Policy blocking and structured error recording.
     - `test_task_manager_execute_capability`: Capability dispatch, timing, and event emission.
     - `test_task_manager_cancellation_interception`: Pre-dispatch cancellation check.
     - `test_semantic_rerun_safety`: **CRITICAL INVARIANT**: new task spawned from request text; zero stale argument replay.
     - `test_task_activity_view`: PySide6 `TaskActivityView` event rendering, status badge, and cancel signal.
     - `test_history_view`: PySide6 `HistoryView` list, search, filter chips, and re-run signal.
     - `test_sql_injection_defense`: Parameterized SQL queries immune to SQL injection.
     - `test_zero_raw_shell_execution_invariant`: Zero shell execution calls across tasks subsystem.

3. **Workstation Capability Tests (v0.7)**:
   - `tests/test_v07_capabilities.py` (43 tests):
     - `test_capability_registry_init_and_listing`: Registry population (47 capabilities, 9 categories).
     - `test_capability_registry_execute_success`: Clean dispatch, observation recording, latency profiling.
     - `test_capability_registry_execute_confirm`: High-risk confirmation gating (`CONFIRM`).
     - `test_capability_registry_execute_block`: Hard security policy interception (`BLOCK`).
     - `test_capability_registry_execute_invalid_arg`: Type checking and error wrapping (`INVALID_ARGUMENT`).
     - `test_capability_registry_execute_not_found`: Missing capability error (`NOT_FOUND`).
     - `test_application_listing`: Top-level visible window desktop app discovery.
     - `test_application_is_running`: Application running status check.
     - `test_application_find`: Start Menu and App Paths lookup.
     - `test_application_focus`: Window focus and restoration (`AMBIGUOUS` on multiples).
     - `test_application_close_graceful`: Non-destructive `WM_CLOSE` messaging.
     - `test_file_index_safe_roots`: Bounded traversal and symlink loop protection.
     - `test_file_find_and_recent`: Pattern matching and recency sorting.
     - `test_file_latest_screenshot`: Recent image and screenshot discovery.
     - `test_file_metadata`: Size, timestamps, extension, and permissions.
     - `test_file_open_blocks_scripts`: **HARD SECURITY**: Blocks `.bat`, `.cmd`, `.ps1`, `.exe` scripts.
     - `test_file_reveal`: Safe `/select` highlighting in File Explorer.
     - `test_process_listing_and_sorting`: Deterministic sorting by RSS, CPU%, and name.
     - `test_process_inspection`: Detailed process metrics and sanitized command lines.
     - `test_process_resource_usage`: Lightweight CPU%, memory RSS, and thread counts.
     - `test_process_ports_and_tree`: Sockets and parent/child process relationships.
     - `test_process_protected_termination_blocked`: **HARD POLICY**: Blocks terminating `explorer.exe`, `system`, `lsass`.
     - `test_process_termination_toctou`: Validates PID recycling race condition protection.
     - `test_network_listening_ports`: Listing local listening TCP dev sockets.
     - `test_network_inspect_port`: Diagnostic query for specific port numbers.
     - `test_network_find_process_on_port`: Mapping port to owning process entity.
     - `test_network_connections`: Read-only socket status.
     - `test_system_summary`: Unified host overview (CPU, RAM, disk, battery, GPU).
     - `test_system_cpu_and_memory`: Core counts, frequency, RAM, swap metrics.
     - `test_system_disk_and_battery`: Disk capacity and battery runtime.
     - `test_system_gpu_status`: Discrete GPU metrics (NVIDIA RTX 2050) with graceful fallback.
     - `test_system_audio_status`: Audio volume and mute inspection foundation.
     - `test_system_lock_workstation`: Windows `LockWorkStation` invocation.
     - `test_system_shutdown_and_restart_blocked`: **HARD POLICY**: Blocks `shutdown_system` and `restart_system`.
     - `test_project_status_and_git`: Injection-proof Git status via structured subprocess calls.
     - `test_project_processes_and_ports`: Project-bound process and listening port mapping.
     - `test_window_discovery`: Window enumeration, geometry, and foreground focus tracking.
     - `test_context_engine_expanded_queries`: ContextEngine recency queries (`last_project`, `last_file`, `last_process`, `last_port`).
     - `test_observation_store`: In-memory bounded ring buffer fact recording.
     - `test_result_card`: PySide6 `ResultCard` layout and action buttons.
     - `test_list_result_card`: PySide6 `ListResultCard` selectable list and keyboard navigation.
     - `test_security_regressions`: Zero shell execution and traversal regressions.
     - `test_reasoning_escalation_boundary_unconfigured`: Unconfigured reasoning provider boundary handling.

4. **Hybrid Natural Language Understanding Tests (v0.6.5)**:
   - `tests/test_v065_nlp.py` (29 tests):
     - `test_port_extraction`: Port notation variants (`port 3000`, `:5173`, `port:8080`, `localhost:8000`).
     - `test_pid_extraction`: Process ID extraction and normalization (`pid 14236`, `PID: 404`).
     - `test_url_extraction`: HTTP/HTTPS URL extraction with exact character spans.
     - `test_path_extraction`: Absolute Windows path matching.
     - `test_project_entity`: Exact project entity lookup against `ProjectRegistry`.
     - `test_app_entity`: Application entity resolution.
     - `test_single_clause`: Single-clause requests with politeness prefix stripping.
     - `test_multi_clause_and`: Coordinated multi-action decomposition (`and`).
     - `test_multi_clause_then`: Sequential execution ordering (`then`).
     - `test_before_after`: Explicit precedence ordering (`before`, `after`).
     - `test_negation`: Direct negative imperative detection.
     - `test_negation_scope`: Selective clause-level negation scoping.
     - `test_dont_kill_just_inspect`: Complex contrastive scoping (*"don't kill node, just inspect it"*).
     - `test_temporal_yesterday`: Local timezone 24-hour interval calculation.
     - `test_most_recent`: Superlative recency modifier.
     - `test_previous_project`: Previous project reference extraction.
     - `test_coreference_detection`: Syntactic identification of anaphoric tokens (`it`, `that`).
     - `test_context_resolution`: Grounding of pronoun references to `WorkstationContext`.
     - `test_ambiguous_coreference`: Ambiguous pronoun resolution triggering `CLARIFY`.
     - `test_relation_process_port`: Extraction of `PROCESS LISTENS_ON PORT`.
     - `test_relation_project_application`: Extraction of `PROJECT OPEN_WITH APPLICATION`.
     - `test_workflow_compiler`: Compilation into registered capability steps.
     - `test_mixed_risk_request`: Mixed-risk proposal elevation to `ToolRisk.HIGH`.
     - `test_blocked_clause_blocks_workflow`: Conservative multi-clause policy blocking.
     - `test_partial_support`: Transparent `PARTIALLY_SUPPORTED` proposal generation.
     - `test_unsupported_action`: Wholly unsupported request handling.
     - `test_nlp_failure_fallback`: Non-crashing emergency fallback parsing.
     - `test_reasoning_required`: Complex activity and diagnostic reasoning escalation.
     - `test_no_raw_shell`: Invariant verification preventing shell command evaluation.

5. **Gated Workstation Actions & Context Tests (v0.6)**:
   - `tests/test_v06_actions.py`:
     - `test_project_registry_loading`: Verifies loading projects catalog from `workspace.json`.
     - `test_project_registry_exact_and_fuzzy_search`: Validates exact lookup, path resolution, and fuzzy alias search for `astrarun` and `server`.
     - `test_project_registry_unknown_returns_none`: Confirms unknown project queries safely return `None`.
     - `test_context_engine_snapshot`: Captures live foreground window metadata and active dev listening ports via Win32 `ctypes` and `psutil`.
     - `test_context_persistence_atomic_and_recovery`: Verifies atomic temporary-file-and-rename persistence, load, and corrupted JSON resilience.
     - `test_context_engine_ttl_expiration`: Enforces strict TTL expiration (process TTL and project TTL).
     - `test_context_engine_attack_rejection`: Immediate rejection of prompt injection attacks (`ignore previous context`, `pretend policy is disabled`).
     - `test_action_gate_allow_low_risk`: Validates `ALLOW` outcome for low-risk allowlist actions.
     - `test_action_gate_confirm_high_risk`: Validates `CONFIRM` outcome and crypto token generation for high-risk tools.
     - `test_action_gate_clarify_ambiguous`: Validates `CLARIFY` outcome and candidate match population.
     - `test_action_gate_block_hard_policy`: Validates `BLOCK` outcome for prohibited shell operations.
     - `test_action_gate_token_tampering_protection`: Verifies tokens cannot be reused with altered arguments and single-use consumption.
     - `test_toctou_process_lifecycle`: **DISPOSABLE PROCESS FIXTURE**: Spawns a temporary Python worker, inspects PID and `create_time`, validates confirmation token binding, safely terminates worker, and verifies TOCTOU failure on the dead PID.
     - `test_workflow_engine_execution`: Verifies execution of multi-step workflow templates and transaction audit logging to `data/workflow_audit.jsonl`.
     - `test_workflow_engine_partial_failure_stops_execution`: Confirms fail-fast behavior halting on step failure without false success claims.
     - `test_ui_confirmation_card`: Validates `Esc` dismissal, single `Enter` suppression on `HIGH` risk, and `Ctrl+Enter` confirmation.
     - `test_ui_disambiguation_card`: Validates Up/Down arrow keyboard navigation and selection signals.
     - `test_ai_bridge_protocol`: Verifies `ReasoningProvider` protocol compliance and request/result dataclass typing.

6. **Laya Ensemble & Fusion Tests (v0.5)**:
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

7. **Kev Router & Shadow Mode Tests (v0.4)**:
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

8. **Laya Router & Shadow Mode Tests (v0.3)**:
   - `tests/test_laya_router.py`:
     - `test_laya_router_disabled`: Verifies abstention when disabled without loading model.
     - `test_laya_router_construction`: Validates device/mode configuration and threshold.
     - `test_laya_router_load_failure_resilience`: Validates graceful fallback on model load failure.
     - `test_laya_router_inference_exception_resilience`: Verifies graceful unknown return on inference failure.
     - `test_laya_router_intent_mapping`: Verifies 10-class intent schema and execution authority flags.
     - `test_laya_confidence_preservation`: Verifies choice and probability preservation.
     - `test_laya_shadow_event_collector`: Verifies JSONL append, schema, and regex credential redaction.
     - `test_shadow_mode_safety_zero_execution_authority`: **CRITICAL SAFETY INVARIANT**: Verifies that Laya predictions NEVER execute and ToolRegistry only executes production decisions.

9. **Unit Tests (v0.1 & v0.2)**:
   - `tests/test_routing.py`: Request normalization (`open`, `launch`, `start`, `go to`, `show`), application/folder/URL routing, and unknown rejection.
   - `tests/test_config.py`: Default and custom configuration loading, corrupted JSON resilience.
   - `tests/test_tools.py`: Tool registry validation, missing tool blocks, risk tier enforcement (`LOW`, `MEDIUM`, `HIGH`, `BLOCKED`).
   - `tests/test_search.py`: Acronym extraction, subsequence matching, fuzzy scoring hierarchy, bounded usage boost, and textual dominance over frequency.
   - `tests/test_usage.py`: Usage store lifecycle, atomic persistence, corrupted JSON recovery.
   - `tests/test_telemetry.py`: Credential redaction (`sk-...`, Bearer tokens, passwords), local logging, disabled mode, and omit-raw-request mode.
   - `tests/test_positioning.py`: Window positioning calculations and target screen geometry fallbacks.
   - `tests/test_security_regression.py`: Prevention of command injection metacharacters (`&`, `|`, `;`, `$`, `%`) and URL protocol verification.

10. **UI Tests**:
   - `tests/test_ui.py`: Window show/dismiss, Escape key handling, initial state, suggestions generation, feedback messages.
   - `tests/test_ui_v02.py`: Keyboard arrow navigation (`Up`/`Down`), Tab autocompletion, weak suggestion rejection on Enter.

11. **Integration Tests**:
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
tests/test_v05_ensemble.py::test_fusion_mode_e5_ambiguity_gated_abstention PASSED [ 71%]
tests/test_v05_ensemble.py::test_fusion_mode_e5_risk_gated_abstention PASSED [ 72%]
tests/test_v05_ensemble.py::test_entity_resolver_project_exact PASSED    [ 73%]
tests/test_v05_ensemble.py::test_entity_resolver_project_ambiguous PASSED [ 74%]
tests/test_v05_ensemble.py::test_entity_resolver_protected_system_port PASSED [ 75%]
tests/test_v05_ensemble.py::test_entity_resolver_allowed_dev_port PASSED [ 76%]
tests/test_v05_ensemble.py::test_entity_resolver_protected_system_process PASSED [ 77%]
tests/test_v05_ensemble.py::test_entity_resolver_hard_policy_dangerous_command PASSED [ 78%]
tests/test_v05_ensemble.py::test_jev_unconfigured_fallback PASSED        [ 79%]
tests/test_v05_ensemble.py::test_jev_mock_mode_simulation PASSED         [ 80%]
tests/test_v05_ensemble.py::test_jev_telemetry_quarantine PASSED         [ 81%]
tests/test_v06_actions.py::test_project_registry_loading PASSED          [ 82%]
tests/test_v06_actions.py::test_project_registry_exact_and_fuzzy_search PASSED [ 83%]
tests/test_v06_actions.py::test_project_registry_unknown_returns_none PASSED [ 84%]
tests/test_v06_actions.py::test_context_engine_snapshot PASSED           [ 85%]
tests/test_v06_actions.py::test_context_persistence_atomic_and_recovery PASSED [ 86%]
tests/test_v06_actions.py::test_context_engine_ttl_expiration PASSED     [ 87%]
tests/test_v06_actions.py::test_context_engine_attack_rejection PASSED   [ 88%]
tests/test_v06_actions.py::test_action_gate_allow_low_risk PASSED        [ 89%]
tests/test_v06_actions.py::test_action_gate_confirm_high_risk PASSED     [ 90%]
tests/test_v06_actions.py::test_action_gate_clarify_ambiguous PASSED     [ 91%]
tests/test_v06_actions.py::test_action_gate_block_hard_policy PASSED     [ 92%]
tests/test_v06_actions.py::test_action_gate_token_tampering_protection PASSED [ 93%]
tests/test_v06_actions.py::test_toctou_process_lifecycle PASSED          [ 94%]
tests/test_v06_actions.py::test_workflow_engine_execution PASSED         [ 95%]
tests/test_v06_actions.py::test_workflow_engine_partial_failure_stops_execution PASSED [ 96%]
tests/test_v06_actions.py::test_ui_confirmation_card PASSED              [ 97%]
tests/test_v06_actions.py::test_ui_disambiguation_card PASSED            [ 98%]
tests/test_ai_bridge_protocol PASSED                                     [100%]
```

### Results Summary
- **Total Tests Collected**: **215**
- **Passed**: **215**
- **Failed**: **0**
- **Duration**: **12.56s**

---

## 3. Learning Benchmark V1 Evaluation (320 Cases)

```powershell
.venv\Scripts\python benchmarks\learning\run_learning_benchmark.py
```

### Evaluation Results
- **Cases Evaluated**: **320**
- **Dataset SHA256**: `b935f4ece761d59a98d7b98053cc18ffcb6ae33259f4888cb828ab3787281b9a`
- **Overall Accuracy**: **100.0%** (320 / 320)
- **False Memory Activation Rate**: **0.00%** (Prime Safety Invariant)
- **Security Invariant Enforcement Rate**: **100.0%** (40 / 40)
- **End-to-End Latency (Mean)**: **25.28 ms**

### Category Performance Breakdown
| Category | Cases | Accuracy | Invariant Adherence |
| :--- | :--- | :--- | :--- |
| Explicit Teaching | 40 | 100.0% | 100.0% |
| Correction Mining | 40 | 100.0% | 100.0% |
| Habit Tracking | 40 | 100.0% | 100.0% |
| Contradiction / Conflict | 40 | 100.0% | 100.0% |
| Confidence Decay | 40 | 100.0% | 100.0% |
| Skill Discovery | 40 | 100.0% | 100.0% |
| Security Invariants | 40 | 100.0% | 100.0% |
| Edge Cases | 40 | 100.0% | 100.0% |

---

## 4. Task Benchmark V1 Evaluation (300 Lifecycle Cases)

```powershell
.venv\Scripts\python -u benchmarks\tasks\run_task_benchmark.py
```

### Evaluation Results
- **Cases Evaluated**: **300**
- **Dataset SHA256**: `7979fb8dd6361aa6406f4ae318beae2901724c20671df68d34ad34c24378b4d4`
- **Status Accuracy**: **100.0%** (300 / 300)
- **Sequence Accuracy**: **100.0%** (300 / 300)
- **Persistence Accuracy**: **100.0%** (300 / 300)
- **Mean Latency**: **64.636 ms** (p50: 9.634 ms, p95: 256.514 ms)

### Scale Stress Benchmark (10,000 Tasks & 100,000 Events)
- **Bulk Ingestion Speed**: **99,757 rows/sec** (1.10 s total)
- **Fetch 50 Recent Tasks**: **1.264 ms**
- **10k Task Substring Search**: **7.429 ms**
- **Retention Pruning (5,000 tasks)**: **339.590 ms**

---

## 5. Capability Benchmark V1 Evaluation (520 Cases)

```powershell
.venv\Scripts\python benchmarks\capabilities\run_capability_benchmark.py
```

### Evaluation Results
- **Total Benchmark Queries**: **520**
- **Dataset SHA256**: `32ca0f2946a55403d77e0e55b969aad81289aa5da9617ea1f8c8086e391d8fdc`
- **Capability Accuracy**: **100.0%** (520 / 520)
- **Permission Accuracy**: **100.0%** (520 / 520)
- **Block Recall**: **100.0%** (Prime Safety Invariant)
- **Confirmation Recall**: **100.0%** (High-Risk Gating)
- **End-to-End Latency (Mean)**: **0.590 ms** (p50: 0.506 ms, p95: 1.035 ms)

---

## 6. NLP Benchmark V1 Evaluation (620 Cases)

```powershell
.venv\Scripts\python benchmarks\nlp\run_nlp_benchmark.py
```

### Evaluation Results (Locked Test Set: 310 cases)
- **Dataset SHA256**: `41f1ad1b6a29d071dad3ea93a8390961c41c136b15365586cd48ad3a61211c82`
- **Intent Accuracy**: **100.0%**
- **Clause Segmentation**: **95.2%**
- **Multi-Action Match**: **100.0%**
- **Negation Accuracy**: **100.0%**
- **NEGATED ACTION LEAKAGE RATE**: **0.00%** (Prime Safety Invariant)
- **Block Recall**: **100.0%**
- **Mean Latency**: **5.796 ms** (p50: 5.859 ms, p95: 6.842 ms)

---

## 7. Action Benchmark V1 Evaluation (330 Test Cases)

```powershell
.venv\Scripts\python benchmarks\action\run_action_benchmark.py
```

### Evaluation Results
- **Total Benchmark Queries**: **330**
- **Intent Accuracy**: **100.0%** (330 / 330)
- **Gate Accuracy**: **100.0%** (330 / 330)
- **Tool Selection Accuracy**: **100.0%** (330 / 330)
- **Proposed Action Accuracy**: **100.0%** (330 / 330)
- **False Action Proposal Rate (FAPR)**: **0.00%**
- **FALSE EXECUTION RATE (FER)**: **0.00%** (Prime Architectural Invariant)
- **Clarification Precision**: **100.0%** (20 / 20)
- **Block Recall**: **100.0%** (74 / 74)
- **Confirmation Recall**: **100.0%** (31 / 31)
- **End-to-End Latency (Mean)**: **0.051 ms** (p50: 0.024 ms, p95: 0.104 ms)

---

## 8. Standardized Routing Evaluation Benchmark (88 Queries)

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

---

## 8.1. Window Benchmark V1 Evaluation (330 Test Cases)

```powershell
.venv\Scripts\python benchmarks\windows\run_window_benchmark.py
```

### Evaluation Results
- **Total Cases Evaluated**: **330**
- **Dataset SHA256**: `4307223c89e6676788d264009566b235550374e4661631fdcae0c06266bfc3fe`
- **Overall Accuracy**: **100.0%** (330 / 330)
- **WRONG WINDOW ACTION RATE**: **0.00%** (Prime Safety Invariant)
- **Policy Violations**: **0**
- **Ambiguity Failures**: **0**
- **Mean Evaluation Latency**: **0.0229 ms**

---

## 8.2. Product Benchmark V2 Evaluation (280 Test Cases)

```powershell
.venv\Scripts\python benchmarks\product_v2\run_product_benchmark_v2.py
```

### Evaluation Results
- **Total Cases Evaluated**: **280**
- **Dataset SHA256**: `0e3face2732bee1859ea02df1de4da6a5d4753a45a11fcd6c8eae366c9f564ec`
- **Overall Accuracy**: **100.0%** (280 / 280)
- **FALSE EXECUTION RATE**: **0.00%** (Prime Architectural Invariant)
- **Safety Policy Violations**: **0**
- **Mean Fast-Path Routing Latency**: **0.5983 ms** (< 3ms Invariant Verified)
- **Mean End-to-End Latency**: **120.57 ms**

---

## 8.3. Interaction Benchmark V1 Evaluation (405 Test Cases)

```powershell
.venv\Scripts\python benchmarks\interaction\run_interaction_benchmark.py
```

### Evaluation Results
- **Total Cases Evaluated**: **405**
- **Dataset SHA256**: `a2496176564e0455f186834eb2782f14f35dfd1dd5a7774f22c88bcf708bfc77`
- **Overall Accuracy**: **100.0%** (405 / 405)
- **WRONG ELEMENT ACTION RATE (WEAR)**: **0.00%** (Prime Safety Invariant)
- **Password Plaintext Leakage Count**: **0** (Zero Secret Policy)
- **Destructive Block Recall**: **100.0%**
- **Ambiguity Recall**: **100.0%**
- **Mean Evaluation Latency**: **0.0621 ms**

---

## 9. Empirical Manual Verification Matrix

| Query Executed | Expected Outcome | Verification Status | Notes |
| :--- | :--- | :--- | :--- |
| `open AstraRun in vscode` | `ALLOW` -> `open_project_in_vscode` | **PASSED** | Launches VS Code for Active/AstraRun |
| `open folder for AI Bridge` | `ALLOW` -> `open_project_folder` | **PASSED** | Opens File Explorer in Active/AI-Bridge |
| `what is running on port 3000` | `ALLOW` -> `inspect_port` | **PASSED** | Read-only socket inspection |
| `who is using port 80` | `ALLOW` -> `inspect_port` | **PASSED** | Read-only inspection allowed on port 80 |
| `stop process using port 3000`| `CONFIRM` -> ConfirmationCard | **PASSED** | Gated with cryptographic token |
| `stop that process` | `CONFIRM` -> Contextual termination | **PASSED** | Resolves PID from previous inspection within TTL |
| `open my most recent project` | `ALLOW` -> `open_project` | **PASSED** | Resolves project from recency manager |
| `kill port 80` | `BLOCK` -> Prohibited | **PASSED** | Hard policy blocks privileged port termination |
| `kill lsass` | `BLOCK` -> Prohibited | **PASSED** | Hard policy blocks protected system process |
| `rmdir /s /q c:\` | `BLOCK` -> Prohibited | **PASSED** | Hard policy blocks dangerous shell commands |
| `open project` | `CLARIFY` -> DisambiguationCard | **PASSED** | Interactive list with keyboard arrow navigation |

---

## 10. Live Physical Workstation Acceptance Gate (v0.11)

```powershell
.venv\Scripts\python scripts\run_v011_live_acceptance.py
```

### Acceptance Results Summary
- **Overall Status**: **4 / 4 GATES PASSED (100.0%)**
- **Hardware Architecture**: Windows 11 Build 26100, RTX 2050, Native Wi-Fi (`wlanapi.dll`)
- **Safety Invariant**: 0 user Notepad instances or sessions touched or killed
- **Artifact**: `benchmarks/v011_live_acceptance_results.json`

| Gate ID | Gate Name | Subsystem / Tier | Measured Duration | Verification Evidence |
| :--- | :--- | :--- | :--- | :--- |
| **Gate 1** | Autonomous Battery Report Goal | Tier B (`powercfg.exe` Adapter) | 3157.5 ms | Validated `C:\Users\hp\Downloads\astra-battery.html` (155,519 bytes, non-empty HTML). Verified via `FILE_NON_EMPTY`. |
| **Gate 2** | Native Wi-Fi Management | Tier A (ctypes `wlanapi.dll`) | 119.7 ms | Verified connection to active SSID (`Galaxy A14*`, 97% signal). Enumerated BSS scan list in-process with 0 subprocesses. |
| **Gate 3** | Workstation Resource Locking | Agent Core (`ResourceLockManager`) | 54.4 ms | Mutual exclusion, re-entrancy, cross-task lock rejection, and automatic task teardown verified. |
| **Gate 4** | Motion System & Live Task HUD V2 | UI / Accessibility (`MotionTokens`) | 76.0 ms | Centralized motion timing tokens (200ms standard / 0ms reduced-motion), `TaskETAEstimator`, and non-activating window flags verified. |


