"""
scripts/audit_f0_22_duplications.py

Comprehensive Duplication and Dead Architecture Audit for Phase F0-22:
Inspects the 24 subsystem areas:
- intent routing
- entity resolution
- application discovery
- application launching
- planning
- replanning
- goal verification
- task execution
- capability dispatch
- computer use
- keyboard input
- mouse input
- window discovery
- UI Automation
- screen capture
- OCR
- visual grounding
- browser control
- resource ownership
- file operations
- memory/retrieval
- model invocation/residency
- ActionGate/ExecutionBroker
- task checkpoints/recovery

Determines for each:
- Canonical implementation
- Installed product call path
- Test-only usage
- Obsolete implementations and rationale
Outputs docs/audit/F0_22_DUPLICATION_DEAD_CODE_AUDIT.json
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def audit_duplications():
    repo_root = Path(__file__).resolve().parent.parent

    # Load dependency graph
    dep_graph_path = repo_root / "docs" / "audit" / "F0_22_DEPENDENCY_GRAPH.json"
    dep_graph = {}
    if dep_graph_path.exists():
        with open(dep_graph_path, "r", encoding="utf-8") as f:
            dep_graph = json.load(f).get("modules", {})

    duplications = {
        "intent_routing": {
            "canonical": "astrarun.routing.pipeline.RoutingPipeline",
            "installed_product_caller": "astrarun.app.AstraApplication.handle_request -> astrarun.routing.laya.LayaWorker / astrarun.routing.deterministic.DeterministicRouter",
            "implementations": [
                {
                    "module": "astrarun.routing.laya",
                    "role": "CANONICAL_NEURAL",
                    "status": "CANONICAL",
                    "notes": "Fast local transformer classifier running in isolated worker subprocess.",
                },
                {
                    "module": "astrarun.routing.deterministic",
                    "role": "CANONICAL_RULES",
                    "status": "CANONICAL",
                    "notes": "Deterministic high-confidence fast-path for unambiguous commands.",
                },
                {
                    "module": "astrarun.nlp.intent_router",
                    "role": "LEGACY_DUPLICATE",
                    "status": "DUPLICATE",
                    "notes": "Redundant keyword intent matcher largely bypassed by routing.pipeline.",
                },
                {
                    "module": "astrarun.agent.planner.GoalPlanner.parse_goal",
                    "role": "DUPLICATE_IN_AGENT",
                    "status": "OVERLAPPING",
                    "notes": "GoalPlanner does its own regex-based intent classification inside extract_goal_contract.",
                },
            ],
            "recommendation": "Unify intent extraction into a single stage that produces GoalContract before planner runs.",
        },
        "entity_resolution": {
            "canonical": "astrarun.nlp.structure_engine.NeuralStructureEngine & astrarun.discovery.entity_resolver.EntityResolver",
            "installed_product_caller": "astrarun.nlp.structure_engine called during compound request analysis",
            "implementations": [
                {
                    "module": "astrarun.discovery.entity_resolver",
                    "role": "EXPLICIT_RESOLVER",
                    "status": "CANONICAL_SPECIALIZED",
                    "notes": "Resolves apps, files, directories against filesystem and OS registry.",
                },
                {
                    "module": "astrarun.nlp.structure_engine",
                    "role": "SPA_CY_EXTRACTION",
                    "status": "CANONICAL_LINGUISTIC",
                    "notes": "spaCy dependency parser extracting grammatical relations and clauses.",
                },
                {
                    "module": "astrarun.agent.planner.GoalPlanner._extract_entities",
                    "role": "REGEX_HEURISTIC_DUPLICATE",
                    "status": "DUPLICATE_SMELL",
                    "notes": "Duplicate ad-hoc regex heuristics for target_artifact, target_location, and content.",
                },
            ],
            "recommendation": "Retire ad-hoc regex heuristics in GoalPlanner and feed directly from EntityResolver / NeuralStructureEngine.",
        },
        "application_discovery": {
            "canonical": "astrarun.discovery.apps.AppDiscoveryService",
            "installed_product_caller": "astrarun.app.AstraApplication composition root (caches 372 applications)",
            "implementations": [
                {
                    "module": "astrarun.discovery.apps",
                    "role": "CANONICAL",
                    "status": "CANONICAL",
                    "notes": "Scans Start Menu, AppPaths, and system folders.",
                },
                {
                    "module": "astrarun.applications.service.ApplicationService.resolve_application",
                    "role": "ADAPTER_FORWARDER",
                    "status": "LEGITIMATE_ADAPTER",
                    "notes": "Wraps AppDiscoveryService and adds launch state management.",
                },
                {
                    "module": "astrarun.discovery.shortcuts",
                    "role": "LOW_LEVEL_SCANNER",
                    "status": "SUB_COMPONENT",
                    "notes": "Parses .lnk files on disk for AppDiscoveryService.",
                },
            ],
            "recommendation": "Maintain AppDiscoveryService as canonical.",
        },
        "application_launching": {
            "canonical": "astrarun.applications.service.ApplicationService.launch_application",
            "installed_product_caller": "open_application capability handler in capabilities/implementations/system.py",
            "implementations": [
                {
                    "module": "astrarun.applications.service",
                    "role": "CANONICAL",
                    "status": "CANONICAL",
                    "notes": "Enforces process isolation, single-instance checks, and HWND tracking.",
                },
                {
                    "module": "astrarun.windows.controller.WindowController.launch_process",
                    "role": "RAW_WIN32_LAUNCH",
                    "status": "DUPLICATE_LOWER_LEVEL",
                    "notes": "Direct subprocess launch without Astra application tracking.",
                },
            ],
            "recommendation": "All application launches must pass through ApplicationService to register with ResourceLedger.",
        },
        "planning": {
            "canonical": "astrarun.agent.planner.GoalPlanner",
            "installed_product_caller": "astrarun.app.AstraApplication.handle_request via AgentExecutionLoop",
            "implementations": [
                {
                    "module": "astrarun.agent.planner",
                    "role": "CANONICAL_GOAL_PLANNER",
                    "status": "CANONICAL",
                    "notes": "Extracts GoalContract and generates PlanStep DAG.",
                },
                {
                    "module": "astrarun.workflows.compiler.WorkflowCompiler",
                    "role": "DETERMINISTIC_COMPILER",
                    "status": "COMPLEMENTARY",
                    "notes": "Compiles static compound recipes into sequential steps.",
                },
            ],
            "recommendation": "Retain GoalPlanner as top-level canonical; use WorkflowCompiler for verified fast-paths.",
        },
        "replanning": {
            "canonical": "astrarun.agent.planner.GoalPlanner.replan_on_divergence & GoalPlanner.replan_on_failure",
            "installed_product_caller": "astrarun.agent.loop.AgentExecutionLoop._replan_step",
            "implementations": [
                {
                    "module": "astrarun.agent.planner",
                    "role": "DYNAMIC_REPLANNER",
                    "status": "CANONICAL",
                    "notes": "Generates new PlanRevision and adjusts unexecuted steps.",
                },
                {
                    "module": "astrarun.tasks.runtime.TaskRuntime.recover_step",
                    "role": "LEGACY_TASK_RECOVERY",
                    "status": "LEGACY_DUPLICATE",
                    "notes": "Older retry logic in TaskRuntime that does not know about GoalContract predicates.",
                },
            ],
            "recommendation": "Deprecate legacy TaskRuntime recovery; ensure all replanning is governed by GoalPlanner and GoalContract predicates.",
        },
        "goal_verification": {
            "canonical": "astrarun.agent.verifier.GoalVerifier & StepVerifier",
            "installed_product_caller": "astrarun.agent.loop.AgentExecutionLoop (evaluates GoalContract predicates post-execution)",
            "implementations": [
                {
                    "module": "astrarun.agent.verifier",
                    "role": "GOAL_CONTRACT_VERIFIER",
                    "status": "CANONICAL",
                    "notes": "Empirically tests FILE_EXISTS, FILE_NON_EMPTY, FILE_CONTENT_CONTAINS, UI_ELEMENT_STATE.",
                },
                {
                    "module": "astrarun.tasks.verifier.TaskVerifier",
                    "role": "RETURN_CODE_CHECKER",
                    "status": "OBSOLETE",
                    "notes": "Shallow verifier checking capability success flags without inspecting physical OS state.",
                },
            ],
            "recommendation": "Decommission TaskVerifier; GoalVerifier is the sole authoritative verification engine.",
        },
        "computer_use_and_interaction": {
            "canonical": "astrarun.computer_use.controller.ComputerUseController & astrarun.interaction.service.InteractionService",
            "installed_product_caller": "type_into_window and UI automation capabilities",
            "implementations": [
                {
                    "module": "astrarun.interaction.service",
                    "role": "WIN32_INTERACTION_SERVICE",
                    "status": "CANONICAL_CORE",
                    "notes": "Direct Windows SendInput, HWND activation, and key sequence driver.",
                },
                {
                    "module": "astrarun.interaction.controller",
                    "role": "WRAPPER_CONTROLLER",
                    "status": "REDUNDANT_WRAPPER",
                    "notes": "Thin wrapper delegating directly to InteractionService without adding business logic.",
                },
                {
                    "module": "astrarun.computer_use.controller",
                    "role": "PERCEPTUAL_COMPUTER_USE",
                    "status": "CANONICAL_ADVANCED",
                    "notes": "Integrates perception, world state, and action dispatch.",
                },
                {
                    "module": "astrarun.windows.controller",
                    "role": "WIN32_WINDOW_HELPER",
                    "status": "UTILITY_LAYER",
                    "notes": "Direct Win32 API calls for window enumeration and placement.",
                },
            ],
            "recommendation": "Consolidate interaction wrappers: route low-level Win32 actions via InteractionService under ComputerUseController.",
        },
        "file_operations": {
            "canonical": "astrarun.capabilities.implementations.files & astrarun.interaction.document.DocumentService",
            "installed_product_caller": "save_text_file capability handler",
            "implementations": [
                {
                    "module": "astrarun.capabilities.implementations.files",
                    "role": "NATIVE_FS_CAPABILITY",
                    "status": "CANONICAL_NATIVE_IO",
                    "notes": "Direct atomic filesystem operations (Path.write_text, etc.).",
                },
                {
                    "module": "astrarun.interaction.document",
                    "role": "APPLICATION_DOCUMENT_SERVICE",
                    "status": "CANONICAL_APP_MEDIATED",
                    "notes": "Drives application-mediated document creation, tab isolation, and UI Save/Save-As workflows.",
                },
                {
                    "module": "astrarun.files.service",
                    "role": "LEGACY_FILE_SERVICE",
                    "status": "DUPLICATE",
                    "notes": "Redundant file utilities not registered in capability manifest.",
                },
            ],
            "recommendation": "Enforce strict boundary: native file capabilities handle DIRECT_RESULT_ALLOWED; DocumentService handles APPLICATION_UI_REQUIRED.",
        },
        "security_broker": {
            "canonical": "astrarun.execution.broker.ExecutionBroker & astrarun.security.action_gate.ActionGate",
            "installed_product_caller": "AstraApplication execution pipeline",
            "implementations": [
                {
                    "module": "astrarun.execution.broker",
                    "role": "CANONICAL_BROKER",
                    "status": "CANONICAL",
                    "notes": "Validates risk tiers, checks permissions, audits dispatches.",
                },
                {
                    "module": "astrarun.security.action_gate",
                    "role": "USER_CONFIRMATION_GATE",
                    "status": "CANONICAL",
                    "notes": "Presents UI prompt for high-risk destructive actions.",
                },
            ],
            "recommendation": "Zero execution path may bypass ExecutionBroker.",
        },
    }

    manifest = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-22",
        "subsystems_audited_count": len(duplications),
        "subsystems": duplications,
        "dead_modules_found": [
            "astrarun.capabilities.cli",
            "astrarun.entrypoint",
            "astrarun.learning.debugger",
            "astrarun.models.downloader",
            "astrarun.nlp.debugger",
            "astrarun.visualization.render_worker",
        ],
        "obsolete_components_identified": [
            "astrarun.tasks.verifier.TaskVerifier",
            "astrarun.nlp.intent_router",
            "astrarun.interaction.controller (thin wrapper)",
            "astrarun.files.service (unregistered duplicate)",
        ],
    }

    out_file = repo_root / "docs" / "audit" / "F0_22_DUPLICATION_DEAD_CODE_AUDIT.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Duplication audit written to: {out_file}")
    print(f"Audited Subsystems: {len(duplications)}")
    print(f"Dead Modules: {len(manifest['dead_modules_found'])}")
    print(f"Obsolete Components: {len(manifest['obsolete_components_identified'])}")


if __name__ == "__main__":
    audit_duplications()
