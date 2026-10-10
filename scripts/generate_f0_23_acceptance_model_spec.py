"""Generate formal acceptance model specification artifact for Phase F0-23."""

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path("e:/Workspace/Active/AstraRun")
OUTPUT_PATH = REPO_ROOT / "docs" / "audit" / "F0_23_ACCEPTANCE_MODEL.json"

def main() -> None:
    spec = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-23",
        "description": "Formal multi-dimensional task acceptance specification and predicate architecture.",
        "architecture": {
            "core_principle": "A task may PASS only when every mandatory dimension passes. A task cannot PASS merely because 'something succeeded', 'a file exists', 'a plan looked correct', or 'a capability returned success'.",
            "dimensions": {
                "INTENT_CORRECTNESS": {
                    "question": "Did Astra understand what the user asked?",
                    "mandatory": True,
                    "evidence_sources": ["GoalContract", "NLPStructureEngine", "SemanticConstraints"]
                },
                "ENTITY_CORRECTNESS": {
                    "question": "Did Astra resolve the correct real-world entities (applications, files, controls)?",
                    "mandatory": True,
                    "evidence_sources": ["SemanticEntityResolver", "AppDiscoveryCache", "ProcessImageName", "WindowHWND"]
                },
                "MODALITY_CORRECTNESS": {
                    "question": "Did Astra use the requested interaction modality (UI vs direct)?",
                    "mandatory": True,
                    "evidence_sources": ["InteractionRequirement", "PlanStepCapabilities", "UIInteractionTrace"]
                },
                "PLAN_RELEVANCE": {
                    "question": "Does every consequential step plausibly advance a mandatory goal predicate?",
                    "mandatory": True,
                    "evidence_sources": ["ActionRelevanceOracle", "GoalPredicateMapping"]
                },
                "EXECUTION_REALITY": {
                    "question": "Did the actions actually occur on the physical machine?",
                    "mandatory": True,
                    "evidence_sources": ["Win32API", "UIAElementState", "FileSysystemMtime", "ProcessPIDs"]
                },
                "STATE_TRANSITION_CORRECTNESS": {
                    "question": "Did the world change as expected from pre-state to post-state?",
                    "mandatory": True,
                    "evidence_sources": ["PrePostStateDelta", "UIObservationDiff"]
                },
                "OUTPUT_CORRECTNESS": {
                    "question": "Is the final artifact/state semantically correct and non-empty?",
                    "mandatory": True,
                    "evidence_sources": ["FileSizeBytes", "FileSHA256", "FileContentAnalysis", "AppDocumentState"]
                },
                "SIDE_EFFECT_CLEANLINESS": {
                    "question": "Were there unrequested consequential actions or window mutations?",
                    "mandatory": True,
                    "evidence_sources": ["SideEffectLedger", "ConsequentialActionClassifier"]
                },
                "RESOURCE_CLEANUP": {
                    "question": "Were Astra-owned transient resources, handles, and processes cleaned?",
                    "mandatory": True,
                    "evidence_sources": ["ResourceLedger", "ProcessTreeInspection", "WindowZOrderAudit"]
                },
                "SECURITY_COMPLIANCE": {
                    "question": "Did all consequential operations pass authoritative security mediation?",
                    "mandatory": True,
                    "evidence_sources": ["SecurityActionGateAudit", "ExecutionBrokerProvenance"]
                },
                "PROVENANCE": {
                    "question": "Can the result be tied causally to the actual production execution without fabrication?",
                    "mandatory": True,
                    "evidence_sources": ["TaskExecutionAuditLog", "ResidentProcessTaskID", "ModelRequestResponseHash"]
                }
            },
            "predicate_templates": {
                "application_discovery_goal": [
                    {
                        "name": "intended_app_identity_matches_resolved",
                        "dimension": "ENTITY_CORRECTNESS",
                        "evaluator": "SemanticEntityIdentityEvaluator",
                        "evidence_source": "AppInfo.aliases + canonical_id",
                        "failure_reason": "Resolved application is semantically distinct from requested target"
                    },
                    {
                        "name": "unambiguous_or_clarified",
                        "dimension": "ENTITY_CORRECTNESS",
                        "evaluator": "AmbiguityThresholdEvaluator",
                        "evidence_source": "ResolvedEntity.is_ambiguous",
                        "failure_reason": "Selected candidate has ambiguous competitor without user clarification"
                    }
                ],
                "document_ui_goal": [
                    {
                        "name": "requested_app_open",
                        "dimension": "EXECUTION_REALITY",
                        "evaluator": "ProcessAndWindowActiveEvaluator",
                        "evidence_source": "psutil + win32gui",
                        "failure_reason": "Target application process or top-level window was not present"
                    },
                    {
                        "name": "editable_surface_observed",
                        "dimension": "EXECUTION_REALITY",
                        "evaluator": "UIAEditableControlEvaluator",
                        "evidence_source": "pywinauto UIA controls",
                        "failure_reason": "No focused editable document surface found in application"
                    },
                    {
                        "name": "requested_content_observed_in_surface",
                        "dimension": "STATE_TRANSITION_CORRECTNESS",
                        "evaluator": "UIAValuePatternEvaluator",
                        "evidence_source": "UIA TextPattern / Edit.get_value()",
                        "failure_reason": "Target text was not present in the application editor surface"
                    },
                    {
                        "name": "application_save_flow_observed",
                        "dimension": "MODALITY_CORRECTNESS",
                        "evaluator": "NativeSaveDialogEvaluator",
                        "evidence_source": "Save As Dialog HWND + filename entry + commit",
                        "failure_reason": "Direct filesystem bypass used instead of native application Save workflow"
                    },
                    {
                        "name": "requested_artifact_exists_and_matches",
                        "dimension": "OUTPUT_CORRECTNESS",
                        "evaluator": "PhysicalFileContentEvaluator",
                        "evidence_source": "Path.stat() + Path.read_text() + SHA256",
                        "failure_reason": "Artifact is missing, 0 bytes, or content does not match semantic contract"
                    }
                ],
                "browser_goal": [
                    {
                        "name": "browser_context_exists",
                        "dimension": "EXECUTION_REALITY",
                        "evaluator": "BrowserProcessEvaluator",
                        "evidence_source": "Running browser process + window handle",
                        "failure_reason": "No browser instance was active or controlled"
                    },
                    {
                        "name": "requested_navigation_observed",
                        "dimension": "STATE_TRANSITION_CORRECTNESS",
                        "evaluator": "BrowserNavigationEvaluator",
                        "evidence_source": "Browser address bar / DOM location / CDP URL",
                        "failure_reason": "Browser URL does not match requested destination"
                    },
                    {
                        "name": "requested_interaction_observed",
                        "dimension": "STATE_TRANSITION_CORRECTNESS",
                        "evaluator": "BrowserDOMInteractionEvaluator",
                        "evidence_source": "DOM state mutation / Accessibility tree",
                        "failure_reason": "Requested web interaction did not occur on page"
                    }
                ],
                "multi_application_goal": [
                    {
                        "name": "two_independent_apps_participate",
                        "dimension": "EXECUTION_REALITY",
                        "evaluator": "MultiAppParticipantEvaluator",
                        "evidence_source": "Distinct process PIDs and window HWNDs for App A and App B",
                        "failure_reason": "Fewer than two distinct application contexts participated in execution"
                    },
                    {
                        "name": "causal_information_transfer",
                        "dimension": "STATE_TRANSITION_CORRECTNESS",
                        "evaluator": "InformationFlowEvaluator",
                        "evidence_source": "App A extraction -> agent intermediate state -> App B entry",
                        "failure_reason": "Data entered into App B was not derived from App A observation"
                    }
                ],
                "side_effect_cleanliness": [
                    {
                        "name": "no_unrequested_consequential_actions",
                        "dimension": "SIDE_EFFECT_CLEANLINESS",
                        "evaluator": "SideEffectCleanlinessEvaluator",
                        "evidence_source": "SideEffectLedger comparison against GoalContract",
                        "failure_reason": "Consequential actions occurred that did not advance any goal predicate"
                    }
                ]
            }
        }
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)
    print(f"Wrote formal acceptance model specification to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
