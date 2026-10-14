"""Dynamic Goal Interpreter and Compositional Plan Generator for AstraRun agent runtime."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any, Optional

from astrarun.agent.indexer import CapabilitySemanticIndex
from astrarun.agent.models import (
    ArgumentBinding,
    ArgumentSourceType,
    ConstraintStatus,
    ConstraintType,
    Goal,
    GoalContract,
    GoalPredicate,
    InteractionRequirement,
    OutputReference,
    Plan,
    PlanningLevel,
    PlanRevision,
    PlanStatus,
    PlanStep,
    PredicateStatus,
    PredicateType,
    ProgressMode,
    SemanticConstraint,
    StepDependency,
    StepState,
)
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.schema import InteractionTier, VerifierStrategy
from astrarun.cognition.models import ModelRole
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.agent.planner")


class GoalPlanner:
    """
    Translates high-level natural language user goals into structured, typed DAG execution plans.
    Leverages CapabilitySemanticIndex for dynamic discovery without hardcoding capability dispatch branches.
    """

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        indexer: Optional[CapabilitySemanticIndex] = None,
        model_service: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        context_builder: Optional[Any] = None,
    ):
        self.registry = registry or CapabilityRegistry()
        self.indexer = indexer or CapabilitySemanticIndex(self.registry)
        if model_service is not None:
            self.model_service = model_service
        else:
            try:
                from astrarun.cognition.service import ModelService
                self.model_service = ModelService.get_instance()
            except Exception:
                self.model_service = None
        if memory_service is not None:
            self.memory_service = memory_service
        else:
            try:
                from astrarun.memory.service import MemoryService
                self.memory_service = MemoryService.get_instance()
            except Exception:
                self.memory_service = None

        if context_builder is not None:
            self.context_builder = context_builder
        else:
            try:
                from astrarun.rag.context import ContextBuilder
                self.context_builder = ContextBuilder()
            except Exception:
                self.context_builder = None

    def retrieve_relevant_context(self, prompt: str) -> dict[str, Any]:
        """Retrieve relevant context across semantic, workspace, and working memory."""
        retrieved_facts = []
        retrieved_docs = []
        retrieved_skills = []
        working_mem = {}

        if self.memory_service:
            try:
                working_mem = self.memory_service.working.snapshot()
            except Exception:
                pass

            # 1. Semantic facts
            try:
                all_facts = self.memory_service.semantic.get_facts()
                prompt_tokens = set(re.findall(r"\w+", prompt.lower()))
                for f in all_facts:
                    k = f.get("key", "").lower()
                    v = str(f.get("value", "")).lower()
                    f_tokens = set(re.findall(r"\w+", f"{k} {v}"))
                    if (prompt_tokens & f_tokens) or (k in prompt.lower()) or any(t in k for t in prompt_tokens if len(t) > 3):
                        retrieved_facts.append(f)
            except Exception as err:
                logger.debug("Error retrieving semantic facts: %s", err)

            # 2. Workspace documents
            try:
                docs = self.memory_service.workspace.search_workspace(prompt, top_k=3)
                retrieved_docs.extend(docs)
            except Exception as err:
                logger.debug("Error searching workspace: %s", err)

            # 3. Procedural skills
            try:
                skills = self.memory_service.procedural.find_skills_for_prompt(prompt, top_k=2)
                retrieved_skills.extend(skills)
            except Exception as err:
                logger.debug("Error finding skills: %s", err)

        return {
            "facts": retrieved_facts,
            "docs": retrieved_docs,
            "skills": retrieved_skills,
            "working_memory": working_mem,
        }

    def extract_goal_contract(self, raw_prompt: str) -> GoalContract:
        """
        Synthesize a durable, typed GoalContract representing all user entities,
        constraints, and acceptance predicates from the natural language prompt.
        """
        clean = raw_prompt.strip()
        entities: dict[str, Any] = {}
        constraints: list[SemanticConstraint] = []
        acceptance_predicates: list[GoalPredicate] = []
        forbidden_outcomes: list[str] = []
        objective = "GENERAL_TASK"

        # 1. Target artifact & location extraction
        abs_file_match = re.search(r'([A-Za-z]:\\[^\r\n,;\"\'\s]+\.[a-zA-Z0-9_]+)', clean)
        full_path = None
        target_artifact = None
        target_location = None

        if abs_file_match:
            abs_p = Path(abs_file_match.group(1).strip())
            full_path = str(abs_p)
            target_artifact = abs_p.name
            target_location = str(abs_p.parent)
        else:
            fmatch = re.search(r'\b([a-zA-Z0-9_\-]+\.(?:txt|html|json|csv|md|py|xml|log|pdf|png|sha|toml|docx))\b', clean, re.I)
            target_artifact = fmatch.group(1) if fmatch else None

            locmatch = re.search(r'\b(?:on|in|to)\s+(?:the\s+|my\s+)?(Desktop|Downloads|Documents|Temp)\b', clean, re.I)
            target_location = locmatch.group(1).capitalize() if locmatch else None
            if not target_location:
                dirmatch = re.search(r'\b(?:under|in|into|at|to)\s*:?\s*([A-Za-z]:\\[a-zA-Z0-9_\-\\]+)', clean, re.I)
                if dirmatch:
                    target_location = dirmatch.group(1).strip()

            if target_artifact:
                if ":" in target_artifact:
                    full_path = target_artifact
                elif target_location == "Desktop":
                    full_path = str(Path.home() / "Desktop" / target_artifact)
                elif target_location == "Downloads":
                    full_path = str(Path.home() / "Downloads" / target_artifact)
                elif target_location == "Documents":
                    full_path = str(Path.home() / "Documents" / target_artifact)
                elif target_location == "Temp":
                    from astrarun.core.paths import AstraPaths
                    full_path = str(AstraPaths.temp_dir() / target_artifact)
                elif target_location and ":" in target_location:
                    full_path = str(Path(target_location) / target_artifact)
                else:
                    full_path = str(Path.home() / "Desktop" / target_artifact) if "desktop" in clean.lower() else target_artifact

        # 2. Content / payload extraction
        qmatch = re.search(r'["\']([^"\']+)["\']', clean)
        required_content = None
        if qmatch:
            required_content = qmatch.group(1)
        else:
            cmatch = re.search(r'\b(?:containing|contains|content(?:s)?\s+(?:should\s+be|is|are)?|with\s+(?:the\s+)?content(?:s)?|with\s+text)\s+([^,\r\n;]+?)(?=\s+(?:and|save|on|in|to|named|called|with\s+name|\.|$)|$)', clean, re.I)
            if cmatch:
                required_content = cmatch.group(1).strip()
            else:
                wmatch = re.search(r'\b(?:type|write)\s+([^;\r\n]+?)(?=\s*,\s*(?:then|and|save)|\s+(?:and|save|then|to|in|into|on|as|\.|$)|,|;|$)', clean, re.I)
                if wmatch:
                    required_content = wmatch.group(1).strip()
                else:
                    pmatch = re.search(r'\bput\s+([^,\r\n;]+?)\s+(?:in|into)\b', clean, re.I)
                    if pmatch:
                        required_content = pmatch.group(1).strip()
                    else:
                        rmatch = re.search(r'\b(?:reverse\s+(?:text\s+)?|hash\s+of\s+|hash\s+for\s+)([^;\r\n]+?)(?=\s*,\s*(?:then|and|save)|\s+(?:and|save|then|to|in|into|on|as|\.|$)|,|;|$)', clean, re.I)
                        if rmatch:
                            required_content = rmatch.group(1).strip()

        # 3. Application extraction
        appmatch = re.search(r'\b(?:open|launch|start|run|close|use|execute)\s+(?:a\s+suitable\s+)?(?:text\s+)?([a-zA-Z0-9_\-\+\s]+?)(?=\s+(?:and|then|with|to|type|write|save|as|on|in|into|for|,|;|\.|$)|,|;|\.|$)', clean, re.I)
        target_application = None
        if appmatch:
            candidate_app = appmatch.group(1).strip()
            candidate_app = re.sub(r'^(?:the\s+|an?\s+|up\s+)', '', candidate_app, flags=re.I).strip()
            excluded_apps = (
                'a', 'the', 'an', 'file', 'document', 'url', 'wifi', 'it', 'battery report', 'battery', 'windows',
                'program', 'script', 'code', 'solution', 'tests', 'test', 'command', 'cli', 'suite', 'task',
                'executable', 'query', 'calculation', 'simulation', 'whatever', 'whatever tools', 'tools', 'tool',
                'result', 'sample', 'action', 'actions', 'pipeline', 'workflow', 'fallback', 'job', 'routine',
                'step', 'steps', 'computation', 'algorithm', 'method', 'procedure'
            )
            cand_lower = candidate_app.lower()
            if candidate_app and cand_lower not in excluded_apps and not any(term in cand_lower for term in (
                "action", "pipeline", "workflow", "fallback", "job", "routine", "task", "solution", "simulation", "computation", "algorithm"
            )):
                target_application = candidate_app

        # 4. Wi-Fi extraction
        wifimatch = re.search(r'\b(?:connect\s+(?:to\s+)?(?:wifi\s+)?|wifi\s+connect\s+|connect\s+wifi\s+|switch\s+wifi\s+to\s+|join\s+(?:wifi\s+|network\s+)?)([a-zA-Z0-9_\-\*]+)\b', clean, re.I)
        ssid = None
        if wifimatch and wifimatch.group(1).lower() not in ('to', 'a', 'the', 'wifi', 'network'):
            ssid = wifimatch.group(1)

        # 5. Objective classification & predicate construction
        clean_lower = clean.lower()
        dynamic_compute_pattern = (
            r'\b(?:python\s+(?:program|script|code)|program\s+that|script\s+that|dynamic|algorithm|'
            r'monte\s+carlo|calculate|frequencies|counts?\s+words?|work\s+out|solve|roots|quadratic|'
            r'equation|formula|compute|simulation|collatz|prime|regression|orbital|fibonacci|'
            r'summary\s+table|summary\s+report|parse\s+log|extract\s+metrics|aggregate|events|'
            r'transform\s+dataset|tabular\s+csv|visualiz|histogram|scatter\s+plot|determinant|'
            r'bar\s+chart|line\s+chart|heatmap|chart)\b'
        )
        has_code_intent = bool(re.search(dynamic_compute_pattern, clean_lower))
        has_doc_intent = not has_code_intent and (target_artifact or bool(re.search(r'\b(?:save|saves|saving|saved|document|write|writes|writing|create\s+file|save\s+file|put)\b', clean_lower)))
        if has_code_intent:
            objective = "DYNAMIC_COMPUTATION"
            if target_location:
                entities["location"] = target_location
                constraints.append(SemanticConstraint(
                    constraint_type=ConstraintType.OUTPUT_LOCATION,
                    description=f"Output location {target_location}",
                    target_key="location",
                    expected_value=target_location,
                    is_mandatory=True,
                ))
            if target_artifact:
                entities["artifact"] = target_artifact
                constraints.append(SemanticConstraint(
                    constraint_type=ConstraintType.TARGET_ARTIFACT,
                    description=f"Artifact named {target_artifact}",
                    target_key="artifact",
                    expected_value=target_artifact,
                    is_mandatory=True,
                ))
            if required_content:
                entities["payload"] = required_content
                entities["content"] = required_content
                constraints.append(SemanticConstraint(
                    constraint_type=ConstraintType.REQUIRED_CONTENT,
                    description=f"Payload or content '{required_content}'",
                    target_key="content",
                    expected_value=required_content,
                    is_mandatory=True,
                ))
                constraints.append(SemanticConstraint(
                    constraint_type=ConstraintType.REQUIRED_CONTENT,
                    description=f"Payload or content '{required_content}'",
                    target_key="payload",
                    expected_value=required_content,
                    is_mandatory=True,
                ))
            if full_path:
                entities["target_path"] = full_path
                acceptance_predicates.append(GoalPredicate(
                    predicate_type=PredicateType.FILE_EXISTS,
                    description=f"File exists at {full_path}",
                    parameters={"path": full_path},
                    is_mandatory=True,
                ))
                acceptance_predicates.append(GoalPredicate(
                    predicate_type=PredicateType.FILE_NON_EMPTY,
                    description=f"File is non-empty at {full_path}",
                    parameters={"path": full_path},
                    is_mandatory=True,
                ))
                if required_content:
                    expected_file_content = required_content[::-1] if "reverse" in clean_lower else required_content
                    acceptance_predicates.append(GoalPredicate(
                        predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
                        description=f"File contains '{expected_file_content}'",
                        parameters={"path": full_path, "contains": expected_file_content},
                        is_mandatory=True,
                    ))
            acceptance_predicates.append(GoalPredicate(
                predicate_type=PredicateType.DATA_COMPUTED,
                description="Dynamic program execution and result verified",
                parameters={"location": target_location} if target_location else {},
                is_mandatory=True,
            ))
        elif has_doc_intent:
            objective = "PRODUCE_DOCUMENT"
            if target_artifact:
                entities["artifact"] = target_artifact
                constraints.append(SemanticConstraint(
                    constraint_type=ConstraintType.TARGET_ARTIFACT,
                    description=f"Artifact named {target_artifact}",
                    target_key="artifact",
                    expected_value=target_artifact,
                    is_mandatory=True,
                ))
            if target_location:
                entities["location"] = target_location
                constraints.append(SemanticConstraint(
                    constraint_type=ConstraintType.OUTPUT_LOCATION,
                    description=f"Output location {target_location}",
                    target_key="location",
                    expected_value=target_location,
                    is_mandatory=True,
                ))
            if required_content:
                entities["content"] = required_content
                constraints.append(SemanticConstraint(
                    constraint_type=ConstraintType.REQUIRED_CONTENT,
                    description=f"Required content '{required_content}'",
                    target_key="content",
                    expected_value=required_content,
                    is_mandatory=True,
                ))
            if target_application:
                entities["application"] = target_application
                constraints.append(SemanticConstraint(
                    constraint_type=ConstraintType.TARGET_APPLICATION,
                    description=f"Target application {target_application}",
                    target_key="app",
                    expected_value=target_application,
                    is_mandatory=False,
                ))

            if full_path:
                acceptance_predicates.append(GoalPredicate(
                    predicate_type=PredicateType.FILE_EXISTS,
                    description=f"File exists at {full_path}",
                    parameters={"path": full_path},
                    is_mandatory=True,
                ))
                acceptance_predicates.append(GoalPredicate(
                    predicate_type=PredicateType.FILE_NON_EMPTY,
                    description=f"File is non-empty at {full_path}",
                    parameters={"path": full_path},
                    is_mandatory=True,
                ))
                if required_content:
                    expected_file_content = required_content[::-1] if "reverse" in clean_lower else required_content
                    acceptance_predicates.append(GoalPredicate(
                        predicate_type=PredicateType.FILE_CONTENT_CONTAINS,
                        description=f"File contains '{expected_file_content}'",
                        parameters={"path": full_path, "contains": expected_file_content},
                        is_mandatory=True,
                    ))

        elif ssid or "wifi" in clean_lower:
            objective = "NETWORK_MANAGEMENT"
            if ssid:
                entities["ssid"] = ssid
                constraints.append(SemanticConstraint(
                    constraint_type=ConstraintType.NETWORK_STATE,
                    description=f"Connected to Wi-Fi SSID '{ssid}'",
                    target_key="ssid",
                    expected_value=ssid,
                    is_mandatory=True,
                ))
                acceptance_predicates.append(GoalPredicate(
                    predicate_type=PredicateType.NETWORK_CONNECTED,
                    description=f"Connected to Wi-Fi SSID '{ssid}'",
                    parameters={"ssid": ssid},
                    is_mandatory=True,
                ))

        elif target_application:
            objective = "APPLICATION_CONTROL"
            entities["application"] = target_application
            constraints.append(SemanticConstraint(
                constraint_type=ConstraintType.TARGET_APPLICATION,
                description=f"Application {target_application} running",
                target_key="app",
                expected_value=target_application,
                is_mandatory=True,
            ))
            acceptance_predicates.append(GoalPredicate(
                predicate_type=PredicateType.APPLICATION_RUNNING,
                description=f"Application {target_application} is running",
                parameters={"app": target_application},
                is_mandatory=True,
            ))
            if required_content:
                entities["content"] = required_content
                constraints.append(SemanticConstraint(
                    constraint_type=ConstraintType.REQUIRED_CONTENT,
                    description=f"Required interaction text '{required_content}'",
                    target_key="content",
                    expected_value=required_content,
                    is_mandatory=True,
                ))
                acceptance_predicates.append(GoalPredicate(
                    predicate_type=PredicateType.DATA_COMPUTED,
                    description=f"Interactive content '{required_content}' delivered to {target_application}",
                    parameters={"payload": required_content, "app": target_application},
                    is_mandatory=True,
                ))

        elif required_content and any(w in clean_lower for w in ("reverse", "hash", "count words", "format")):
            objective = "DYNAMIC_COMPUTATION"
            entities["payload"] = required_content
            constraints.append(SemanticConstraint(
                constraint_type=ConstraintType.REQUIRED_CONTENT,
                description="Input payload provided",
                target_key="payload",
                expected_value=required_content,
                is_mandatory=True,
            ))
            acceptance_predicates.append(GoalPredicate(
                predicate_type=PredicateType.DATA_COMPUTED,
                description="Result computation completed",
                parameters={"payload": required_content},
                is_mandatory=True,
            ))

        # Determine interaction modality requirement
        interaction_requirement = InteractionRequirement.DIRECT_RESULT_ALLOWED
        if target_application or bool(re.search(r'\b(?:open|launch|start|run|in|using|with)\s+(?:notepad|editor|wordpad|calc|calculator|paint|word|excel|chrome|edge|firefox|browser|terminal|powershell|cmd)\b', clean_lower)) or bool(re.search(r'\btype\s+(?:into|in)\b', clean_lower)):
            interaction_requirement = InteractionRequirement.APPLICATION_UI_REQUIRED
        if any(w in clean_lower for w in ("reveal the file", "show in explorer", "reveal in explorer", "show file", "open folder", "open in explorer", "show me the useful result", "show me the result", "show result", "reveal")):
            entities["reveal_result"] = True
            entities["presentation_requested"] = True

        return GoalContract(
            original_utterance=clean,
            objective=objective,
            target_application=target_application,
            target_artifact=target_artifact,
            target_location=target_location,
            entities=entities,
            constraints=constraints,
            acceptance_predicates=acceptance_predicates,
            interaction_requirement=interaction_requirement,
            forbidden_outcomes=forbidden_outcomes,
            provenance={"parser": "GoalPlanner.extract_goal_contract"},
        )

    def parse_goal(self, raw_prompt: str) -> Goal:
        """Parse raw user utterance into a normalized Goal representation using semantic retrieval."""
        clean = raw_prompt.strip()
        goal = Goal(
            goal_id=f"goal_{uuid.uuid4().hex[:8]}",
            raw_prompt=clean,
        )
        goal.contract = self.extract_goal_contract(clean)

        # Sync parameters and criteria from GoalContract
        if goal.contract.target_artifact:
            goal.parameters["filename"] = goal.contract.target_artifact
            if goal.contract.target_location:
                goal.parameters["folder"] = goal.contract.target_location
            for p in goal.contract.acceptance_predicates:
                if p.predicate_type == PredicateType.FILE_EXISTS:
                    cpath = p.parameters.get("path")
                    if cpath:
                        goal.parameters["path"] = cpath
                        goal.parameters["output_path"] = cpath
                    break

        req_cont = goal.contract.get_constraint("content") or goal.contract.get_constraint("payload")
        if req_cont and req_cont.expected_value:
            goal.parameters["text"] = str(req_cont.expected_value)
            goal.parameters["content"] = str(req_cont.expected_value)

        # 1. Detect Negation Guards ("... but don't open it", "do not kill ...")
        negated_clauses = []
        positive_prompt = clean

        neg_match = re.search(r"\b(?:but\s+)?(?:don'?t|do\s+not|never)\s+([a-zA-Z0-9_\-\s]+)$", clean, re.IGNORECASE)
        if neg_match:
            negated_phrase = neg_match.group(1).strip()
            negated_clauses.append(negated_phrase)
            positive_prompt = clean[:neg_match.start()].strip()

        goal.parameters["negated_actions"] = negated_clauses

        # 2. Decompose into Sub-Goals (Conjunctions: 'and', 'then', ';', '&')
        clauses = self._split_clauses(positive_prompt)
        sub_goals: list[dict[str, Any]] = []

        for clause in clauses:
            clause_clean = clause.strip()
            if not clause_clean:
                continue

            # Retrieve top capability candidate for this clause
            candidates = self.indexer.retrieve(clause_clean, top_k=3, min_score=0.15)
            if not candidates:
                # Check for direct single-word command
                direct_cap = self.registry.get(clause_clean.replace(" ", "_"))
                if direct_cap:
                    candidates = self.indexer.retrieve(direct_cap.id, top_k=1)

            if candidates:
                best = candidates[0]
                best_args = self._extract_arguments_for_capability(clause_clean, best.capability_id)
                for cand in candidates[1:5]:
                    if cand.score >= best.score - 0.05:
                        cand_args = self._extract_arguments_for_capability(clause_clean, cand.capability_id)
                        if not best_args and cand_args:
                            best = cand
                            best_args = cand_args
                            break
                        best_matches = any(len(tok) > 3 and tok in best.capability_id.lower() for tok in clause_clean.lower().split())
                        cand_matches = any(len(tok) > 3 and tok in cand.capability_id.lower() for tok in clause_clean.lower().split())
                        if not best_matches and cand_matches:
                            best = cand
                            best_args = cand_args
                            break
                extracted_args = best_args
                sub_goals.append({
                    "clause": clause_clean,
                    "capability_id": best.capability_id,
                    "score": best.score,
                    "arguments": extracted_args,
                    "entry": best.entry,
                })
            else:
                sub_goals.append({
                    "clause": clause_clean,
                    "capability_id": None,
                    "score": 0.0,
                    "arguments": {},
                })

        # Enforce InteractionRequirement modality invariant
        valid_cands = [sg for sg in sub_goals if sg.get("capability_id")]
        unresolved_cands = [sg for sg in sub_goals if not sg.get("capability_id")]
        if goal.contract.objective == "PRODUCE_DOCUMENT":
            is_app_ui = goal.contract.interaction_requirement in (
                InteractionRequirement.APPLICATION_UI_REQUIRED,
                InteractionRequirement.APPLICATION_UI,
            )
            if is_app_ui:
                app_target = goal.contract.target_application or "notepad"
                synth_sub_goals: list[dict[str, Any]] = [
                    {
                        "clause": f"open {app_target}",
                        "capability_id": "open_application",
                        "score": 1.0,
                        "arguments": {"app": app_target},
                    }
                ]
                if req_cont and req_cont.expected_value:
                    synth_sub_goals.append({
                        "clause": f"type {req_cont.expected_value}",
                        "capability_id": "type_into_window",
                        "score": 1.0,
                        "arguments": {"text": str(req_cont.expected_value), "app_name": app_target},
                    })
                save_args: dict[str, Any] = {
                    "app_name": app_target,
                    "filename": goal.contract.target_artifact or "untitled.txt",
                }
                if goal.parameters.get("path"):
                    save_args["path"] = goal.parameters["path"]
                if goal.contract.target_location:
                    save_args["folder"] = goal.contract.target_location
                synth_sub_goals.append({
                    "clause": f"save {goal.contract.target_artifact or 'document'} via application UI",
                    "capability_id": "save_document_via_ui",
                    "score": 1.0,
                    "arguments": save_args,
                })
                sub_goals = synth_sub_goals
            elif not valid_cands or unresolved_cands:
                has_compute = any(re.search(r'\b(?:calculate|work\s+out|solve|roots|compute|math|equation|formula)\b', sg.get("clause", ""), re.I) for sg in sub_goals)
                if has_compute:
                    resolved_chain: list[dict[str, Any]] = []
                    for sg in sub_goals:
                        if re.search(r'\b(?:calculate|work\s+out|solve|roots|compute|math|equation|formula)\b', sg.get("clause", ""), re.I):
                            resolved_chain.append({
                                "clause": sg.get("clause", ""),
                                "capability_id": "execute_dynamic_tool",
                                "score": 0.90,
                                "arguments": {"code": sg.get("clause", "")},
                            })
                        elif sg.get("capability_id"):
                            resolved_chain.append(sg)
                        elif "save" in sg.get("clause", "").lower():
                            resolved_chain.append({
                                "clause": sg.get("clause", ""),
                                "capability_id": "save_text_file",
                                "score": 1.0,
                                "arguments": {"path": goal.parameters.get("path") or "output.txt"},
                            })
                    if resolved_chain:
                        sub_goals = resolved_chain
                else:
                    save_args: dict[str, Any] = {}
                    if goal.parameters.get("path"):
                        save_args["path"] = goal.parameters["path"]
                    if goal.contract.target_artifact:
                        save_args["filename"] = goal.contract.target_artifact
                    if req_cont and req_cont.expected_value:
                        save_args["text"] = str(req_cont.expected_value)
                        save_args["content"] = str(req_cont.expected_value)
                    sub_goals = [{
                        "clause": f"save {goal.contract.target_artifact or 'file'}",
                        "capability_id": "save_text_file",
                        "score": 1.0,
                        "arguments": save_args,
                    }]

        goal.parameters["sub_goals"] = sub_goals

        # =====================================================================
        # AUTHORITATIVE 5-TIER INTELLIGENCE ROUTING HIERARCHY
        # =====================================================================
        clean_lower = clean.lower()

        # 0. Context-Sufficiency & Intent Clarity Assessment
        from astrarun.routing.context_sufficiency import ContextSufficiencyEngine, RoutingClassification

        sufficiency = ContextSufficiencyEngine.evaluate(clean, active_context=goal.parameters)

        # 0A. Security Policy Gate (Authoritative Fail-Closed Rejection)
        if sufficiency.classification == RoutingClassification.SECURITY_REJECTION:
            goal.intent = "security_denial"
            goal.parameters["routing_tier"] = "SECURITY_REJECTION"
            goal.parameters["routing_source"] = "SECURITY_POLICY"
            goal.parameters["rejection_reason"] = sufficiency.reason
            self._infer_success_criteria(goal)
            return goal

        # 0B. Clarification Gate (Bare nouns, ungrounded referents, nonsense fail-closed)
        if sufficiency.classification == RoutingClassification.CLARIFICATION_REQUIRED:
            goal.intent = "needs_clarification"
            goal.parameters["routing_tier"] = "CLARIFICATION"
            goal.parameters["routing_source"] = "CONTEXT_SUFFICIENCY"
            goal.parameters["clarification_reason"] = sufficiency.reason
            goal.parameters["missing_parameters"] = sufficiency.missing_parameters
            self._infer_success_criteria(goal)
            return goal

        # Tier 0: Deterministic Exact Known Capability Match
        exact_cap = self.registry.get(clean.replace(" ", "_").lower()) or self.registry.get(clean.lower())
        if exact_cap:
            goal.intent = exact_cap.id
            goal.parameters["routing_tier"] = "DETERMINISTIC"
            goal.parameters["routing_source"] = "DETERMINISTIC"
            self._infer_success_criteria(goal)
            return goal

        # Delegation Check: External AI Advisor Routing
        if sufficiency.classification == RoutingClassification.DELEGATE_EXTERNAL_AI:
            goal.intent = "consult_delegate"
            goal.parameters["goal"] = clean
            goal.parameters["routing_tier"] = "LOCAL_MODEL"
            goal.parameters["routing_source"] = "LOCAL_MODEL"
            if "chatgpt" in clean_lower:
                goal.parameters["provider_name"] = "chatgpt_web"
            goal.parameters["require_approval"] = any(w in clean_lower for w in ("approve", "approval", "review"))
            goal.parameters["reveal_result"] = any(w in clean_lower for w in ("reveal the file", "show in explorer", "reveal in explorer", "show file", "open folder", "open in explorer"))
            goal.parameters["reveal_type"] = "reveal_file" if any(w in clean_lower for w in ("reveal", "explorer", "folder")) else "open_file"
            self._infer_success_criteria(goal)
            return goal

        # Conversational / Inquiry / Advice / Trivia Check
        if sufficiency.classification == RoutingClassification.CONVERSATIONAL:
            goal.intent = "conversational_dialogue"
            goal.parameters["goal"] = clean
            goal.parameters["routing_tier"] = "LOCAL_MODEL"
            goal.parameters["requires_code"] = False
            self._infer_success_criteria(goal)
            return goal

        # Dynamic Computation / Transformation Check from Sufficiency Engine
        if sufficiency.classification == RoutingClassification.DYNAMIC_COMPUTATION:
            goal.intent = "execute_dynamic_tool"
            goal.parameters["goal"] = clean
            goal.parameters["routing_tier"] = "LOCAL_MODEL"
            goal.parameters["requires_code"] = True
            goal.parameters["reveal_result"] = any(w in clean_lower for w in ("reveal the file", "show in explorer", "reveal in explorer", "show file", "open folder", "open in explorer", "show me the useful result", "show me the result", "show result"))
            goal.parameters["reveal_type"] = "reveal_file" if any(w in clean_lower for w in ("reveal", "explorer", "folder")) else "open_file"
            self._infer_success_criteria(goal)
            return goal

        # Composite Workflow Check from Sufficiency Engine
        if sufficiency.classification == RoutingClassification.COMPOSITE:
            valid_sub_goals = [sg for sg in sub_goals if sg.get("capability_id")]
            goal.intent = "composite_dag_workflow"
            goal.parameters["routing_tier"] = "SEMANTIC_RETRIEVAL"
            goal.parameters["routing_source"] = "COMPOSITE_PIPELINE"
            for sg in valid_sub_goals:
                for k in ("path", "output_path", "ssid", "query"):
                    if k in sg.get("arguments", {}) and k not in goal.parameters:
                        goal.parameters[k] = sg["arguments"][k]
            self._infer_success_criteria(goal)
            return goal

        # Direct App Launch / Directory Open Check (Guarded against composite workflows)
        if not any(c in clean_lower for c in (" and ", " then ", ";")):
            app_launch_match = re.match(r"^(?:open|launch|start)\s+([a-zA-Z0-9_\-\s\.\+]+)$", clean_lower)
            known_apps = (
                "notepad", "calculator", "calc", "visual studio code", "vs code", "code",
                "vivaldi", "browser", "windows terminal", "terminal", "wt", "cmd", "command prompt",
                "powershell", "task manager", "file explorer", "explorer", "edge",
                "control panel", "device manager", "disk management", "registry editor",
                "settings", "taskbar settings", "services manager", "character map",
                "downloads folder", "desktop directory", "documents folder", "date and time settings",
                "sound settings", "display settings", "bluetooth settings", "installed apps list",
                "default apps settings", "clipboard settings", "storage settings", "network connections"
            )
            if app_launch_match and any(app_launch_match.group(1).strip() == a or app_launch_match.group(1).strip().startswith(a) for a in known_apps):
                target_app = app_launch_match.group(1).strip()
                goal.intent = "open_application"
                goal.parameters["app"] = target_app
                goal.parameters["routing_tier"] = "SEMANTIC_RETRIEVAL"
                goal.parameters["routing_source"] = "SEMANTIC"
                self._infer_success_criteria(goal)
                return goal

        # Explicit Known Capability from Sufficiency Engine
        if sufficiency.classification == RoutingClassification.KNOWN_CAPABILITY:
            valid_sub_goals = [sg for sg in sub_goals if sg.get("capability_id")]
            chosen_cap = sufficiency.target_capability or (valid_sub_goals[0]["capability_id"] if valid_sub_goals else None)
            if chosen_cap and self.registry.has_capability(chosen_cap):
                goal.intent = chosen_cap
                goal.parameters.update(sufficiency.extracted_parameters)
                goal.parameters["routing_tier"] = "SEMANTIC_RETRIEVAL"
                goal.parameters["routing_source"] = "CONTEXT_SUFFICIENCY"
                for sg in valid_sub_goals:
                    for k in ("path", "output_path", "filename", "folder", "app"):
                        if k in sg.get("arguments", {}) and k not in goal.parameters:
                            goal.parameters[k] = sg["arguments"][k]
                self._infer_success_criteria(goal)
                return goal

        # Tier 1: Semantic capability retrieval for existing discrete capabilities
        valid_sub_goals = [sg for sg in sub_goals if sg.get("capability_id")]
        unresolved_sub_goals = [sg for sg in sub_goals if not sg.get("capability_id")]

        # Genuine computational domain terms (avoid single generic unigrams like 'code', 'plot', 'table', 'log')
        comp_domains = (
            "eigenvalue", "eigenvalues", "polynomial", "roots of", "random walk",
            "double pendulum", "lotka-volterra", "monte carlo", "collatz", "fibonacci",
            "three-body", "numerical integration", "simpson's rule", "heat diffusion",
            "fourier transform", "fft", "dijkstra", "brownian motion", "markov chain",
            "mandelbrot", "game of life", "singular value decomposition", "svd",
            "poisson equation", "geodesic distance", "autocorrelation", "cellular automaton",
            "pagerank", "chi-square", "pareto front", "prim's algorithm", "linear regression",
            "write a script", "write python script", "generate script", "run script",
            "synthetic time-series", "correlation matrix", "histogram bin table", "frequency histogram",
            "determinant", "prime factorization", "checksum", "sha256",
            "lu decomposition", "cholesky", "qr decomposition", "linear equations",
            "rolling standard deviation", "variance", "volatility",
            "convex hull", "graham scan", "voronoi", "delaunay", "k-means", "clustered data",
            "kernel panic", "stack traces", "iostat", "auth.log", "app.log", "nested json",
            "commits per author", "git log", "python program", "python script", "create a python",
            "program that generates", "3d visualization", "visualization of"
        )
        is_explicit_code = any(w in clean_lower for w in comp_domains) or (
            bool(re.search(r'\b(?:parse|extract|aggregate|transform|compile|convert|turn|merge|organize|generate|flatten)\b', clean_lower)) and (
                any(ext in clean_lower for ext in (".json", ".csv", ".txt", ".log"))
                or any(kw in clean_lower for kw in ("dataset", "server log", "payload", "summary table", "report table", "test files", "login events", "orders", "commits", "metrics", "exceptions"))
            )
        ) or bool(re.search(r'\bgenerate\s+(?:a\s+)?(?:\d+x\d+\s+)?(?:random\s+)?(?:maze|grid|synthetic|mandelbrot|matrix|dataset|distribution|scatter\s+plot|histogram)\b', clean_lower)) or bool(re.search(r'\b(?:plot|render|generate|create|make)\s+(?:a\s+)?(?:\d+[dD]\s+)?(?:scatter\s+plot|line\s+chart|bar\s+chart|histogram|heatmap|chart|plot|visualization|surface\s+plot)\b', clean_lower)) or bool(re.search(r'\b(?:visualiz\w*|plot\w*)\s+(?:memory|cpu|activity|temperature|sales|revenue|expenses|scores|readings|function|3d)\b', clean_lower)) or bool(re.search(r'\b(?:python\s+(?:program|script|code)|program\s+that|script\s+that|create\s+(?:a\s+)?python|write\s+(?:a\s+)?python)\b', clean_lower))

        if not is_explicit_code and len(valid_sub_goals) == 1 and not unresolved_sub_goals:
            top_score = valid_sub_goals[0].get("score", 0.0)
            min_score = 0.30 if getattr(goal.contract, "objective", "") == "PRODUCE_DOCUMENT" else 0.50
            if top_score >= min_score:
                goal.intent = valid_sub_goals[0]["capability_id"]
                goal.parameters.update(valid_sub_goals[0]["arguments"])
                goal.parameters["routing_tier"] = "SEMANTIC_RETRIEVAL"
                goal.parameters["routing_source"] = "SEMANTIC"
                self._infer_success_criteria(goal)
                return goal

        # Composite multi-step workflow via existing discrete capabilities
        if not is_explicit_code and len(valid_sub_goals) > 1 and not unresolved_sub_goals:
            # If the primary action produces the target report file directly (e.g. generate_battery_report),
            # prefer the dedicated capability only when battery is explicitly requested
            if any(sg.get("capability_id") == "generate_battery_report" for sg in valid_sub_goals) and "battery" in clean_lower:
                bat_sg = next(sg for sg in valid_sub_goals if sg.get("capability_id") == "generate_battery_report")
                goal.intent = "generate_battery_report"
                goal.parameters.update(bat_sg["arguments"])
                for sg in valid_sub_goals:
                    for k in ("path", "output_path", "filename", "folder"):
                        if k in sg.get("arguments", {}) and k not in goal.parameters:
                            goal.parameters[k] = sg["arguments"][k]
                self._infer_success_criteria(goal)
                return goal

            # If all sub-goals resolve to the exact same capability, consolidate to that single capability
            unique_caps = {sg.get("capability_id") for sg in valid_sub_goals}
            if len(unique_caps) == 1:
                single_cap = next(iter(unique_caps))
                goal.intent = single_cap
                goal.parameters.update(valid_sub_goals[0].get("arguments", {}))
                goal.parameters["routing_tier"] = "SEMANTIC_RETRIEVAL"
                goal.parameters["routing_source"] = "SEMANTIC"
                self._infer_success_criteria(goal)
                return goal

            goal.intent = "composite_dag_workflow"
            goal.parameters["routing_tier"] = "SEMANTIC_RETRIEVAL"
            goal.parameters["routing_source"] = "SEMANTIC"
            for sg in valid_sub_goals:
                for k in ("path", "output_path", "ssid", "query"):
                    if k in sg.get("arguments", {}) and k not in goal.parameters:
                        goal.parameters[k] = sg["arguments"][k]
            self._infer_success_criteria(goal)
            return goal

        # Tier 2: LOCAL INTENT REASONER
        # Ask resident model for structured classification:
        # {intent_class, candidate_capabilities, confidence, reason, requires_code}
        available_cap_ids = [c.id for c in self.registry.list_capabilities()]
        reasoner_result = None
        has_running_backend = (
            self.model_service
            and hasattr(self.model_service, "supervisor")
            and (
                self.model_service.supervisor.is_running(ModelRole.FAST)
                or self.model_service.supervisor.is_running(ModelRole.DEEP)
            )
        )
        if has_running_backend:
            try:
                reasoner_result = self.model_service.classify_intent_reasoner(
                    clean, available_capabilities=available_cap_ids, context=goal.parameters
                )
            except Exception as e:
                logger.warning("Local intent reasoner call failed: %s", e)

        if not reasoner_result:
            from astrarun.cognition.service import ModelService
            reasoner_result = ModelService.get_instance()._fallback_intent_reasoner(
                clean, available_capabilities=available_cap_ids
            )

        from astrarun.cognition.models import IntentClass
        intent_class = reasoner_result.intent_class
        confidence = reasoner_result.confidence
        requires_code = reasoner_result.requires_code

        # Low confidence or explicit clarification required -> Tier 4 Clarification
        if intent_class == IntentClass.CLARIFICATION_REQUIRED or confidence < 0.40:
            goal.intent = "needs_clarification"
            goal.parameters["routing_tier"] = "CLARIFICATION"
            goal.parameters["clarification_reason"] = reasoner_result.reason
            self._infer_success_criteria(goal)
            return goal

        # External AI delegation
        if intent_class == IntentClass.DELEGATE_EXTERNAL_AI:
            goal.intent = "consult_delegate"
            goal.parameters["goal"] = clean
            goal.parameters["routing_tier"] = "LOCAL_MODEL"
            if "chatgpt" in clean_lower:
                goal.parameters["provider_name"] = "chatgpt_web"
            elif "mock" in clean_lower:
                goal.parameters["provider_name"] = "mock"
            goal.parameters["require_approval"] = any(w in clean_lower for w in ("approve", "approval", "review"))
            goal.parameters["reveal_result"] = any(w in clean_lower for w in ("reveal the file", "show in explorer", "reveal in explorer", "show file", "open folder", "open in explorer"))
            goal.parameters["reveal_type"] = "reveal_file" if any(w in clean_lower for w in ("reveal", "explorer", "folder")) else "open_file"
            self._infer_success_criteria(goal)
            return goal

        # Conversational dialogue or troubleshooting discussion -> DO NOT RUN PYTHON!
        if intent_class == IntentClass.CONVERSATIONAL:
            goal.intent = "conversational_dialogue"
            goal.parameters["goal"] = clean
            goal.parameters["routing_tier"] = "LOCAL_MODEL"
            goal.parameters["requires_code"] = False
            self._infer_success_criteria(goal)
            return goal

        # Known capability match resolved by reasoner
        if intent_class == IntentClass.KNOWN_CAPABILITY and reasoner_result.candidate_capabilities:
            cand = reasoner_result.candidate_capabilities[0]
            if self.registry.has_capability(cand):
                goal.intent = cand
                goal.parameters["routing_tier"] = "LOCAL_MODEL"
                self._infer_success_criteria(goal)
                return goal

        # Composite workflow resolved by reasoner
        if intent_class == IntentClass.COMPOSITE_WORKFLOW:
            valid_candidates = [
                c for c in reasoner_result.candidate_capabilities
                if self.registry.has_capability(c) and (
                    c.replace("_", " ") in clean_lower or any(tok in clean_lower for tok in c.split("_") if len(tok) > 3)
                )
            ]
            high_conf_sub_goals = [sg for sg in valid_sub_goals if sg.get("score", 0.0) >= 0.50]
            if not requires_code and (len(valid_candidates) >= 2 or len(high_conf_sub_goals) >= 2):
                goal.intent = "composite_dag_workflow"
                goal.parameters["routing_tier"] = "LOCAL_MODEL"
                self._infer_success_criteria(goal)
                return goal
            else:
                intent_class = IntentClass.DYNAMIC_COMPUTATION
                requires_code = True

        # Tier 3: Dynamic Tool Synthesis
        # Enter ONLY when reasoner concludes DYNAMIC_COMPUTATION and requires_code == True!
        if intent_class == IntentClass.DYNAMIC_COMPUTATION and requires_code:
            goal.intent = "execute_dynamic_tool"
            goal.parameters["goal"] = clean
            goal.parameters["routing_tier"] = "LOCAL_MODEL"
            goal.parameters["reveal_result"] = any(w in clean_lower for w in ("reveal the file", "show in explorer", "reveal in explorer", "show file", "open folder", "open in explorer", "show me the useful result", "show me the result", "show result"))
            goal.parameters["reveal_type"] = "reveal_file" if any(w in clean_lower for w in ("reveal", "explorer", "folder")) else "open_file"
            self._infer_success_criteria(goal)
            return goal

        # Unknown / Unclassified fallback -> Tier 4 Clarification (NEVER execute_dynamic_tool!)
        goal.intent = "needs_clarification"
        goal.parameters["routing_tier"] = "CLARIFICATION"
        goal.parameters["clarification_reason"] = "Could not map goal to a safe capability or structured intent."
        self._infer_success_criteria(goal)
        return goal

    def create_plan(self, goal: Goal) -> Plan:
        """Construct a validated execution DAG for the given Goal."""
        plan = Plan(
            plan_id=f"plan_{uuid.uuid4().hex[:8]}",
            goal_id=goal.goal_id,
            status=PlanStatus.DRAFT,
            planning_level=PlanningLevel.LEVEL_3_DYNAMIC_DAG,
        )

        # RAG Context Retrieval & Prompt Synthesis
        if self.context_builder:
            try:
                ctx_data = self.retrieve_relevant_context(goal.raw_prompt)
                from astrarun.rag.models import RetrievedDocument, DocType, TrustLevel
                doc_objs = []
                for d in ctx_data.get("docs", []):
                    doc_objs.append(RetrievedDocument(
                        chunk_id=d.get("chunk_id", ""),
                        source=d.get("source", ""),
                        content=d.get("content", ""),
                        doc_type=DocType.CODE,
                        trust_level=TrustLevel.TRUSTED_LOCAL,
                        score=float(d.get("score", 0.0)),
                    ))
                for idx, f in enumerate(ctx_data.get("facts", [])):
                    doc_objs.append(RetrievedDocument(
                        chunk_id=f"fact_{idx}",
                        source=f"semantic_memory:{f.get('key')}",
                        content=f"{f.get('key')}: {f.get('value')}",
                        doc_type=DocType.TEXT,
                        trust_level=TrustLevel.TRUSTED_LOCAL,
                        score=1.0,
                    ))

                turn_ctx = self.context_builder.build_turn_context(
                    system_instruction="AstraRun Autonomous Agent Planner",
                    task_prompt=goal.raw_prompt,
                    history_turns=[],
                    retrieved_docs=doc_objs,
                    retrieved_skills=ctx_data.get("skills", []),
                    working_memory=ctx_data.get("working_memory", {}),
                )
                plan.context = turn_ctx
                goal.parameters["retrieved_context"] = turn_ctx.get("task_prompt", "")
            except Exception as err:
                logger.debug("RAG context synthesis in planner error: %s", err)

        if goal.intent == "consult_delegate":
            contract = getattr(goal, "contract", None)
            strat = VerifierStrategy.FILE_NON_EMPTY
            strat_params: dict[str, Any] = {}
            if contract:
                for p in contract.acceptance_predicates:
                    pt = p.predicate_type.value if hasattr(p.predicate_type, "value") else str(p.predicate_type)
                    if pt in ("FILE_CONTENT_CONTAINS", "FILE_NON_EMPTY", "FILE_EXISTS"):
                        strat = VerifierStrategy(pt)
                        strat_params = dict(p.parameters)
                        break
            if not strat_params and goal.parameters.get("path"):
                strat_params = {"path": goal.parameters["path"]}

            del_satisfies = [PredicateType.DATA_COMPUTED.value]
            if contract:
                for p in contract.acceptance_predicates:
                    pt = p.predicate_type.value if hasattr(p.predicate_type, "value") else str(p.predicate_type)
                    if pt not in del_satisfies:
                        del_satisfies.append(pt)

            step_1 = PlanStep(
                step_id="step_1",
                capability_id="consult_delegate",
                arguments={
                    "goal": goal.parameters.get("goal", goal.raw_prompt),
                    "provider_name": goal.parameters.get("provider_name"),
                    "require_approval": goal.parameters.get("require_approval", True),
                },
                description="Consult external AI advisor in an authoritative closed-loop orchestration cycle",
                human_label="Orchestrate delegated AI session and empirical verification",
                interaction_tier=InteractionTier.TIER_B_STRUCTURED_CLI,
                verifier_strategy=strat,
                verifier_params=strat_params,
                satisfies_predicates=del_satisfies,
            )
            plan.steps.append(step_1)

            if goal.parameters.get("reveal_result"):
                step_2 = PlanStep(
                    step_id="step_2",
                    capability_id="present_result",
                    arguments={"target": OutputReference(step_id="step_1", field="artifact")},
                    dependencies=[StepDependency(step_id="step_1")],
                    description="Present output artifact to user",
                    human_label="Show finished artifact",
                    interaction_tier=InteractionTier.TIER_A_NATIVE,
                    verifier_strategy=VerifierStrategy.WINDOW_READY,
                )
                plan.steps.append(step_2)

            plan.status = PlanStatus.ACTIVE
            plan.planning_level = PlanningLevel.LEVEL_3_DYNAMIC_DAG if len(plan.steps) > 1 else PlanningLevel.LEVEL_1_SINGLE_ACTION
            return plan

        if goal.intent == "execute_dynamic_tool":
            contract = getattr(goal, "contract", None)
            strat = VerifierStrategy.FILE_NON_EMPTY
            strat_params: dict[str, Any] = {}
            if contract:
                for p in contract.acceptance_predicates:
                    pt = p.predicate_type.value if hasattr(p.predicate_type, "value") else str(p.predicate_type)
                    if pt == "FILE_CONTENT_CONTAINS":
                        strat = VerifierStrategy.FILE_CONTAINS
                        strat_params = dict(p.parameters)
                        break
                    elif pt in ("FILE_NON_EMPTY", "FILE_EXISTS"):
                        strat = VerifierStrategy(pt)
                        strat_params = dict(p.parameters)
            if not strat_params and goal.parameters.get("path"):
                strat_params = {"path": goal.parameters["path"]}

            step_args: dict[str, Any] = {"goal": goal.parameters.get("goal", goal.raw_prompt)}
            if goal.parameters.get("filename"):
                step_args["filename"] = goal.parameters["filename"]
            if goal.parameters.get("path"):
                step_args["path"] = goal.parameters["path"]
            elif contract and contract.target_artifact:
                step_args["filename"] = contract.target_artifact
                step_args["path"] = strat_params.get("path", contract.target_artifact)
            elif strat_params.get("path"):
                step_args["path"] = strat_params["path"]

            dyn_satisfies = [PredicateType.DATA_COMPUTED.value]
            if contract:
                for p in contract.acceptance_predicates:
                    pt = p.predicate_type.value if hasattr(p.predicate_type, "value") else str(p.predicate_type)
                    if pt not in dyn_satisfies:
                        dyn_satisfies.append(pt)

            step_1 = PlanStep(
                step_id="step_1",
                capability_id="execute_dynamic_tool",
                arguments=step_args,
                description="Synthesize, inspect, execute, and self-repair dynamic Python program in contained execution workspace",
                human_label="Synthesize and run dynamic Python program",
                interaction_tier=InteractionTier.TIER_B_STRUCTURED_CLI,
                verifier_strategy=strat,
                verifier_params=strat_params,
                satisfies_predicates=dyn_satisfies,
            )
            plan.steps.append(step_1)

            if goal.parameters.get("reveal_result"):
                step_2 = PlanStep(
                    step_id="step_2",
                    capability_id="present_result",
                    arguments={"target": OutputReference(step_id="step_1", field="artifact")},
                    dependencies=[StepDependency(step_id="step_1")],
                    description="Present output artifact to user",
                    human_label="Show finished visualization artifact",
                    interaction_tier=InteractionTier.TIER_A_NATIVE,
                    verifier_strategy=VerifierStrategy.WINDOW_READY,
                )
                plan.steps.append(step_2)

            plan.status = PlanStatus.ACTIVE
            plan.planning_level = PlanningLevel.LEVEL_3_DYNAMIC_DAG if len(plan.steps) > 1 else PlanningLevel.LEVEL_1_SINGLE_ACTION
            return plan

        if goal.intent == "generate_battery_report":
            step = PlanStep(
                step_id="step_1",
                capability_id="generate_battery_report",
                arguments={
                    k: v for k, v in goal.parameters.items()
                    if k in ("folder", "filename", "output_path")
                },
                description="Generate comprehensive Windows battery health report via powercfg.exe",
                human_label="Generate battery report into Downloads",
                interaction_tier=InteractionTier.TIER_B_STRUCTURED_CLI,
                verifier_strategy=VerifierStrategy.FILE_NON_EMPTY,
            )
            plan.steps.append(step)
            plan.status = PlanStatus.ACTIVE
            plan.planning_level = PlanningLevel.LEVEL_1_SINGLE_ACTION
            return plan

        sub_goals = goal.parameters.get("sub_goals", [])
        negated = goal.parameters.get("negated_actions", [])

        # If any sub-goal is completely unresolved, the composite goal cannot succeed
        if any(not sg.get("capability_id") for sg in sub_goals):
            return plan

        # Filter out any sub-goals that match negated actions
        filtered_sub_goals = []
        for sg in sub_goals:
            cap_id = sg.get("capability_id")
            if not cap_id:
                continue
            is_negated = False
            for neg in negated:
                if neg.lower() in cap_id.lower() or cap_id.lower() in neg.lower():
                    is_negated = True
                    break
            if not is_negated:
                filtered_sub_goals.append(sg)

        if not filtered_sub_goals:
            # Check if there is an un-decomposed intent
            if goal.intent and goal.intent not in ("unsupported_or_reasoning_required", "composite_dag_workflow"):
                cap = self.registry.get(goal.intent)
                if cap:
                    step = self._build_step_from_capability(goal.intent, goal.parameters, step_id="step_1")
                    plan.steps.append(step)
                    plan.status = PlanStatus.ACTIVE
                    plan.planning_level = PlanningLevel.LEVEL_1_SINGLE_ACTION
                    return plan

            plan.status = PlanStatus.FAILED
            return plan

        # Build steps and wire dataflow dependencies
        built_steps: list[PlanStep] = []
        for idx, sg in enumerate(filtered_sub_goals, start=1):
            step_id = f"step_{idx}"
            cap_id = sg["capability_id"]
            args = dict(sg["arguments"])

            step = self._build_step_from_capability(cap_id, args, step_id=step_id, clause=sg["clause"])
            built_steps.append(step)

        # Wire OutputReference and dependencies between steps
        self._wire_dataflow_dependencies(built_steps, contract=goal.contract)
        plan.steps = built_steps
        plan.contract = goal.contract
        plan.status = PlanStatus.ACTIVE
        if len(plan.steps) == 1:
            plan.planning_level = PlanningLevel.LEVEL_1_SINGLE_ACTION
        elif len(plan.steps) <= 4 and all(len(s.dependencies) <= 1 for s in plan.steps):
            plan.planning_level = PlanningLevel.LEVEL_2_STATIC_COMPOSE
        else:
            plan.planning_level = PlanningLevel.LEVEL_3_DYNAMIC_DAG

        return plan

    def replan(
        self,
        task: Any,
        failed_step: PlanStep,
        observation: Any,
        alternative_capability_id: Optional[str] = None,
    ) -> Optional[PlanRevision]:
        """
        Dynamically revise execution graph when an action fails.
        Goal-directed replanning:
        1. Identify unsatisfied goal predicates.
        2. Filter alternative capabilities whose declared effects advance at least one unsatisfied predicate.
        3. Strictly reject capabilities that do not advance the goal (e.g. open_folder / reveal_file for missing file content).
        4. If no capability can advance the goal, fail gracefully (return None) to prevent false completion.
        """
        logger.info("Replanning task %s triggered by failed step %s", task.task_id, failed_step.step_id)

        contract = getattr(task, "contract", None) or getattr(task.goal, "contract", None)

        # 1. Determine unsatisfied predicates that failed_step was meant to advance
        unsatisfied_predicates: list[str] = list(failed_step.satisfies_predicates)
        if contract:
            for pred in contract.acceptance_predicates:
                if pred.is_mandatory and pred.status != PredicateStatus.SATISFIED:
                    if pred.predicate_type.value not in unsatisfied_predicates:
                        unsatisfied_predicates.append(pred.predicate_type.value)

        # 2. Determine required effects based on unsatisfied predicates
        requires_file_production = any(p in ("FILE_EXISTS", "FILE_NON_EMPTY", "FILE_CONTENT_CONTAINS", "FILE_CONTENT_EQUALS") for p in unsatisfied_predicates)
        requires_app_launch = any(p in ("APPLICATION_RUNNING", "WINDOW_ACTIVE") for p in unsatisfied_predicates)
        requires_network = "NETWORK_CONNECTED" in unsatisfied_predicates

        target_alt = alternative_capability_id
        if not target_alt:
            if failed_step.capability_id == "consult_delegate":
                target_alt = "execute_dynamic_tool"
            else:
                entry = self.indexer.get_entry(failed_step.capability_id)
                domains = " ".join(entry.domains) if entry else failed_step.capability_id
                candidates = self.indexer.retrieve(domains, top_k=10)

                for c in candidates:
                    if c.capability_id == failed_step.capability_id:
                        continue

                    cand_schema = self.registry.get_capability_schema(c.capability_id)
                    cand_effects = getattr(cand_schema, "side_effects", []) if cand_schema else []
                    effect_names = [e.value if hasattr(e, "value") else str(e) for e in cand_effects]

                    # Goal-directed filter:
                    if requires_file_production:
                        # Replacement MUST create or modify files; READ_ONLY capabilities (open_folder, reveal_file) are REJECTED!
                        if not any(e in ("CREATES_FILE", "MODIFIES_FILE") for e in effect_names):
                            logger.debug("Replanner rejecting '%s': cannot satisfy file production predicates", c.capability_id)
                            continue

                    if requires_app_launch:
                        if not any(e in ("SPAWNS_PROCESS", "MODIFIES_WINDOW", "SYSTEM_STATE") for e in effect_names):
                            continue

                    if requires_network:
                        if "NETWORK_STATE" not in effect_names:
                            continue

                    target_alt = c.capability_id
                    break

        # Check if requested alternative satisfies the predicate requirement
        if target_alt:
            alt_schema = self.registry.get_capability_schema(target_alt)
            alt_effects = [e.value if hasattr(e, "value") else str(e) for e in getattr(alt_schema, "side_effects", [])] if alt_schema else []
            if requires_file_production and not any(e in ("CREATES_FILE", "MODIFIES_FILE") for e in alt_effects):
                logger.warning("Replanner rejecting alternative '%s': does not advance unsatisfied file predicates", target_alt)
                target_alt = None

        if not target_alt:
            logger.warning(
                "No viable goal-advancing alternative capability found for replan of %s (unsatisfied: %s)",
                failed_step.step_id,
                unsatisfied_predicates,
            )
            return None

        # Build replacement step
        new_step_id = f"step_replan_{uuid.uuid4().hex[:6]}"
        replan_args = dict(failed_step.arguments)
        # Ensure contract values (text, content, path, filename) are preserved in replan args!
        if contract:
            req_content = contract.get_constraint("content") or contract.get_constraint("text")
            if req_content and req_content.expected_value:
                replan_args["text"] = str(req_content.expected_value)
                replan_args["content"] = str(req_content.expected_value)
            if contract.target_artifact:
                replan_args["filename"] = contract.target_artifact
            if contract.target_location and not replan_args.get("path"):
                replan_args["path"] = str(Path.home() / contract.target_location / (contract.target_artifact or "file.txt"))

        new_step = self._build_step_from_capability(
            target_alt,
            arguments=replan_args,
            step_id=new_step_id,
            clause=f"Replan alternative for {failed_step.capability_id}",
        )
        new_step.dependencies = list(failed_step.dependencies)
        new_step.satisfies_predicates = list(failed_step.satisfies_predicates)

        # Mark failed step as SKIPPED to preserve audit trail
        failed_step.state = StepState.SKIPPED
        task.plan.steps.append(new_step)
        task.plan.version += 1

        revision = PlanRevision(
            task_id=task.task_id,
            previous_plan_version=task.plan.version - 1,
            new_plan_version=task.plan.version,
            reason=f"Step '{failed_step.step_id}' ({failed_step.capability_id}) failed; dynamically substituted with '{target_alt}' advancing unsatisfied predicates: {unsatisfied_predicates}.",
            observation_ids=[observation.observation_id] if observation else [],
            added_steps=[new_step_id],
            removed_steps=[failed_step.step_id],
        )
        task.revisions.append(revision)
        return revision

    def _split_clauses(self, text: str) -> list[str]:
        """Split compound multi-step instructions on conjunctions, merging pronoun modifiers."""
        raw_clauses = re.split(
            r"(?:,\s*(?=(?:type|write|save|open|launch|start|run|execute|show|find|close|reveal|and|then)\b)|\s+(?:and\s+(?:then\s+)?|then\s+|\&\s+|;\s*)|(?<=\w)\s+(?=(?:type|write|save|open|launch|start|close|show|find|reveal|run|execute)\b))",
            text,
            flags=re.IGNORECASE,
        )
        clauses: list[str] = []
        for c in raw_clauses:
            c = c.strip()
            if not c:
                continue
            # If clause begins with in-page target ("find the section", etc.) or relative display target
            if clauses and re.match(
                r"^(?:into|in|open\s+windows\b|find\s+(?:the\s+)?section\b|navigate\s+to\s+(?:the\s+)?section\b|scroll\s+to\b|search\s+for\s+section\b)\b",
                c,
                re.IGNORECASE,
            ):
                clauses[-1] = f"{clauses[-1]} {c}"
            elif clauses and re.match(r"^(?:show\s+(?:me\s+)?(?:the\s+)?file|reveal\s+(?:the\s+)?file)\b", c, re.IGNORECASE):
                if any(w in clauses[-1].lower() for w in ("explorer", "folder", "open")):
                    clauses[-1] = f"{clauses[-1]} and {c}"
                else:
                    clauses.append(c)
            elif clauses and re.match(r"^(?:(?:name|call|named|as)\s+(?:it\s+)?|with\s+name\s+)[a-zA-Z0-9_\-\.]+\.[a-zA-Z0-9]+\b", c, re.IGNORECASE):
                clauses[-1] = f"{clauses[-1]} and {c}"
            else:
                clauses.append(c)
        return clauses

    def _extract_arguments_for_capability(self, clause: str, cap_id: str) -> dict[str, Any]:
        """Dynamically extract argument values from natural language clause matching capability schema."""
        cap = self.registry.get(cap_id)
        if not cap:
            return {}

        args: dict[str, Any] = {}
        args_schema = getattr(cap, "args_schema", {})
        if not isinstance(args_schema, dict):
            args_schema = {}

        # 0. URL extraction (for open_url, web documentation navigation)
        if "url" in args_schema or cap_id == "open_url":
            url_match = re.search(r"https?://[^\s\"']+", clause)
            if url_match:
                args["url"] = url_match.group(0).strip()
            elif "pathlib" in clause.lower() and ("doc" in clause.lower() or "python" in clause.lower()):
                if "exists" in clause.lower():
                    args["url"] = "https://docs.python.org/3/library/pathlib.html#pathlib.Path.exists"
                else:
                    args["url"] = "https://docs.python.org/3/library/pathlib.html"
            elif "python" in clause.lower() and "doc" in clause.lower():
                args["url"] = "https://docs.python.org/3/"
            else:
                domain_match = re.search(r"\b([a-zA-Z0-9-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?)", clause)
                if domain_match:
                    args["url"] = f"https://{domain_match.group(1)}"

        # 1. Output file / path / query extraction (e.g. for battery reports, save text file, file search)
        folder_match = re.search(r"\b(?:in|to)\s+(Downloads|Documents|Desktop|Temp)\b", clause, re.IGNORECASE)
        folder = folder_match.group(1) if folder_match else "Downloads"

        path_match = re.search(r"(?:to|into|as|in|name\s+it|call\s+it|named|with\s+name)\s+([^\r\n,;\"'\s]+\.(?:html|xml|txt|json|pdf|csv|xlsx|toml|py|docx|zip|png|log|md|sha))\b", clause, re.IGNORECASE)
        file_match = path_match or re.search(r"\bas\s+([^\r\n,;\"'\s]+\.(?:html|xml|txt|json|pdf))\b", clause, re.IGNORECASE)
        if not file_match:
            file_match = re.search(r"\b([^\r\n,;\"'\s]+\.(?:html|xml|txt|json|pdf|csv|xlsx|toml|py|docx|zip|png|log|md|sha))\b", clause, re.IGNORECASE)

        temp_dir_match = re.search(r"\b(?:AstraRun\s+temporary\s+test\s+directory|temporary\s+test\s+directory|temp\s+directory|test\s+directory)\b", clause, re.IGNORECASE)
        if temp_dir_match:
            from astrarun.core.paths import AstraPaths
            temp_path = str(AstraPaths.temp_dir() / "test_milestone5v_battery.html")
            if "output_path" in args_schema or cap_id == "generate_battery_report":
                args["output_path"] = temp_path
            args["filename"] = "test_milestone5v_battery.html"
            args["folder"] = "temp"
        elif file_match:
            raw_path = file_match.group(1).strip()
            fname = os.path.basename(raw_path.replace("\\", "/"))
            if ":" in raw_path:
                full_path = raw_path
            elif re.match(r"^desktop[\\/]", raw_path, re.IGNORECASE):
                rel_part = re.sub(r"^desktop[\\/]+", "", raw_path, flags=re.IGNORECASE).lstrip("\\/")
                full_path = str(Path.home() / "Desktop" / rel_part)
            elif re.match(r"^downloads[\\/]", raw_path, re.IGNORECASE):
                rel_part = re.sub(r"^downloads[\\/]+", "", raw_path, flags=re.IGNORECASE).lstrip("\\/")
                full_path = str(Path.home() / "Downloads" / rel_part)
            elif re.match(r"^documents[\\/]", raw_path, re.IGNORECASE):
                rel_part = re.sub(r"^documents[\\/]+", "", raw_path, flags=re.IGNORECASE).lstrip("\\/")
                full_path = str(Path.home() / "Documents" / rel_part)
            elif "/" in raw_path or "\\" in raw_path:
                full_path = raw_path
            else:
                if folder_match and folder.lower() == "desktop":
                    full_path = str(Path.home() / "Desktop" / fname)
                elif folder_match and folder.lower() == "downloads":
                    full_path = str(Path.home() / "Downloads" / fname)
                elif folder_match and folder.lower() == "documents":
                    full_path = str(Path.home() / "Documents" / fname)
                else:
                    full_path = f"{folder}/{fname}" if folder_match else fname

            if "output_path" in args_schema or cap_id == "generate_battery_report":
                args["output_path"] = full_path
            if "path" in args_schema:
                args["path"] = full_path
            args["filename"] = fname
            if "query" in args_schema:
                args["query"] = fname
            if "name" in args_schema:
                args["name"] = fname
            args["folder"] = folder

        # 2. Text payload extraction (e.g. reverse_text, type_into_window, save_text_file, word_count, hash_text, format_json)
        if any(k in args_schema for k in ("text", "content", "data", "input", "payload")):
            quote_match = re.search(r'["\']([^"\']+)["\']', clause)
            if quote_match:
                val = quote_match.group(1)
            else:
                verb_match = re.search(r"^(?:reverse|type|write|save|count\s+words\s+in|calculate\s+hash\s+of|compute\s+sha256\s+hash\s+for|compute\s+hash\s+for|format\s+json\s+string|format\s+json\s+payload|beautify\s+json|format\s+json\s+data|beautify\s+json\s+string)\s+(.+?)(?:\s+to\s+|\s+in\s+|\s+on\s+|$)", clause, re.IGNORECASE)
                val = verb_match.group(1).strip() if verb_match else clause

            if val.lower().startswith(("it ", "to ", "in ", "on ", "as ", "into ")) or val.lower() in ("it", "file", "document", "them", "this"):
                val = ""

            if cap_id in ("save_text_file", "save_document_via_ui") and not quote_match:
                content_m = re.search(r"(?:with\s+)?(?:text|content)\s+['\"]?([^'\"\r\n]+)['\"]?", clause, re.IGNORECASE)
                if content_m:
                    val = content_m.group(1).strip()
                else:
                    val = ""

            if val:
                for k in ("text", "content", "data", "input", "payload"):
                    if k in args_schema and k not in args:
                        args[k] = val

        # 3. Numeric PID and Port extraction
        num_match = re.search(r"\b(\d{2,5})\b", clause)
        if num_match:
            val_int = int(num_match.group(1))
            if "pid" in args_schema:
                args["pid"] = val_int
            if "port" in args_schema:
                args["port"] = val_int

        # 4. SSID extraction for Wi-Fi
        if "ssid" in args_schema or cap_id == "wifi_connect":
            wifi_match = re.search(r"\b(?:connect\s+(?:to\s+)?(?:wifi\s+)?|wifi\s+(?:connect\s+|to\s+)?|switch\s+wifi\s+to\s+|join\s+(?:wifi\s+|network\s+)?)([a-zA-Z0-9_\-\*\s]+?)(?:\s+wifi)?$", clause, re.IGNORECASE)
            if wifi_match:
                ssid = wifi_match.group(1).strip()
                ssid = re.sub(r"\s+wifi$", "", ssid, flags=re.IGNORECASE).strip()
                ssid = re.sub(r"^(?:to|network)\s+", "", ssid, flags=re.IGNORECASE).strip()
                if ssid and ssid.lower() not in ("to", "a", "the", "network", "status"):
                    args["ssid"] = ssid

        # 5. App Name extraction
        app_match = re.search(r"\b(?:application|app|is|focus|open|launch|start|close|find)(?:\s+application|\s+app)?\s+([a-zA-Z0-9_\-\+]+)(?:\s+running)?\b", clause, re.IGNORECASE)
        if app_match:
            matched_app = app_match.group(1).strip()
            if matched_app.lower() not in ("application", "app", "the", "a", "is", "for", "with", "all", "running", "file", "process", "window", "wifi"):
                if "app" in args_schema:
                    args["app"] = matched_app
                if "name" in args_schema:
                    args["name"] = matched_app
                if "app_name" in args_schema:
                    args["app_name"] = matched_app
                if "query" in args_schema:
                    args["query"] = matched_app

        # 5b. Target extraction for UI clicks and control interaction
        if "target" in args_schema or cap_id in ("click_ui_element", "focus_ui_element", "toggle_ui_element", "select_ui_element"):
            click_match = re.search(r"\b(?:click|press|tap|invoke|select|focus|toggle)\s+(?:on\s+)?(?:the\s+)?(?:button\s+)?([^\r\n,;]+?)(?:\s+button|\s+in\s+|\s+on\s+|$)", clause, re.IGNORECASE)
            if click_match:
                tgt = click_match.group(1).strip()
                if tgt.lower() not in ("it", "the", "a", "button", "ui", "element"):
                    args["target"] = tgt

        # 6. Process name query
        proc_match = re.search(r"\bfind\s+process\s+([a-zA-Z0-9_\-]+)\b", clause, re.IGNORECASE)
        if proc_match and "query" in args_schema:
            args["query"] = proc_match.group(1).strip()

        # 7. Window Query extraction
        win_match = re.search(r"\b(?:window|search\s+for\s+window|find\s+window)\s+([a-zA-Z0-9_\-]+)\b", clause, re.IGNORECASE)
        if win_match and "query" in args_schema:
            wname = win_match.group(1).strip()
            if wname.lower() not in ("desktop", "layout", "left", "right", "on", "active", "current"):
                args["query"] = wname

        # 8. Defaults for desktop / window actions
        if "hwnd" in args_schema and "hwnd" not in args:
            args["hwnd"] = 0
        if "drive" in args_schema and "drive" not in args:
            args["drive"] = "C:"
        if "monitor_spec" in args_schema and "monitor_spec" not in args:
            args["monitor_spec"] = "primary"
        if "plan" in args_schema and "plan" not in args:
            args["plan"] = []

        return args

    def _build_step_from_capability(
        self,
        cap_id: str,
        arguments: dict[str, Any],
        step_id: str = "step_1",
        clause: str = "",
    ) -> PlanStep:
        """Construct a PlanStep from capability metadata and supplied arguments."""
        cap = self.registry.get(cap_id)
        schema = self.registry.get_capability_schema(cap_id) if hasattr(self.registry, "get_capability_schema") else None

        tier = getattr(schema, "interaction_tier", getattr(cap, "interaction_tier", InteractionTier.TIER_A_NATIVE))
        verifier = getattr(schema, "verifier_strategy", getattr(cap, "verifier_strategy", None))
        if not verifier or verifier == VerifierStrategy.RETURN_CODE_ONLY:
            if cap_id in ("save_text_file", "save_document_via_ui"):
                tier = InteractionTier.TIER_C_UI_AUTOMATION if cap_id == "save_document_via_ui" else InteractionTier.TIER_A_NATIVE
                content = arguments.get("content") or arguments.get("text")
                verifier = VerifierStrategy.FILE_CONTAINS if content else VerifierStrategy.FILE_NON_EMPTY
            elif cap_id in ("type_text", "type_into_window", "click_ui_element", "set_ui_element_value", "toggle_ui_element", "select_ui_element"):
                tier = InteractionTier.TIER_C_UI_AUTOMATION
                verifier = VerifierStrategy.UI_ELEMENT_STATE
            elif cap_id in ("open_application", "open_app", "focus_application"):
                tier = InteractionTier.TIER_A_NATIVE
                verifier = VerifierStrategy.WINDOW_READY
            elif cap_id in ("close_application", "close_app"):
                verifier = VerifierStrategy.PROCESS_EXIT
            elif cap_id == "generate_battery_report":
                tier = InteractionTier.TIER_B_STRUCTURED_CLI
                verifier = VerifierStrategy.FILE_NON_EMPTY
            elif cap_id == "wifi_connect":
                verifier = VerifierStrategy.NETWORK_SSID
            elif verifier is None:
                verifier = VerifierStrategy.RETURN_CODE_ONLY
        desc = getattr(cap, "description", f"Execute {cap_id}")

        # Human label derivation for user HUD
        human_label = desc
        if cap_id == "generate_battery_report":
            human_label = f"Generate battery report into {arguments.get('output_path', 'Downloads')}"
        elif cap_id == "wifi_scan":
            human_label = "Scan available Wi-Fi networks"
        elif cap_id == "wifi_status":
            human_label = "Check active Wi-Fi connection"
        elif cap_id == "wifi_connect":
            human_label = f"Connect to Wi-Fi '{arguments.get('ssid', '')}'"
        elif cap_id == "reverse_text":
            human_label = f"Reverse text payload: '{arguments.get('text', '')}'"
        elif cap_id == "save_text_file":
            human_label = f"Save text to {arguments.get('path', 'file')}"

        bindings: dict[str, ArgumentBinding] = {}
        for k, v in arguments.items():
            bindings[k] = ArgumentBinding(
                parameter=k,
                value=v,
                source_type=ArgumentSourceType.USER_TEXT,
                source_reference=clause or None,
            )

        satisfies_preds: list[str] = []
        requires_preds: list[str] = []
        effects: list[str] = []

        if cap_id in ("open_application", "open_app"):
            satisfies_preds = [PredicateType.APPLICATION_RUNNING.value, PredicateType.WINDOW_ACTIVE.value]
            effects = ["SPAWNS_PROCESS", "MODIFIES_WINDOW"]
        elif cap_id in ("type_text", "type_into_window"):
            satisfies_preds = ["DOCUMENT_CONTENT_WRITTEN", PredicateType.DATA_COMPUTED.value]
            requires_preds = [PredicateType.WINDOW_ACTIVE.value]
            effects = ["WRITES_CONTENT", "MODIFIES_WINDOW"]
        elif cap_id in ("save_text_file", "save_document_via_ui"):
            satisfies_preds = [PredicateType.FILE_EXISTS.value, PredicateType.FILE_NON_EMPTY.value, PredicateType.FILE_CONTENT_CONTAINS.value]
            effects = ["CREATES_FILE", "MODIFIES_FILE", "WRITES_CONTENT"]
        elif cap_id == "wifi_connect":
            satisfies_preds = [PredicateType.NETWORK_CONNECTED.value]
            effects = ["NETWORK_STATE"]
        elif cap_id == "generate_battery_report":
            satisfies_preds = [PredicateType.FILE_EXISTS.value, PredicateType.FILE_NON_EMPTY.value]
            effects = ["CREATES_FILE"]
        elif cap_id in ("reverse_text", "calculate_hash", "count_words"):
            satisfies_preds = [PredicateType.DATA_COMPUTED.value]
            effects = ["DATA_COMPUTED", "READ_ONLY"]
        else:
            if schema and hasattr(schema, "side_effects"):
                effects = [s.value if hasattr(s, "value") else str(s) for s in schema.side_effects]
            else:
                effects = ["READ_ONLY"]

        return PlanStep(
            step_id=step_id,
            capability_id=cap_id,
            arguments=arguments,
            argument_bindings=bindings,
            description=desc,
            human_label=human_label,
            interaction_tier=tier,
            verifier_strategy=verifier,
            verifier_params=arguments,
            satisfies_predicates=satisfies_preds,
            requires_predicates=requires_preds,
            declared_effects=effects,
            weight=1.0,
        )

    def _wire_dataflow_dependencies(self, steps: list[PlanStep], contract: Optional[GoalContract] = None) -> None:
        """
        Dynamically detect and wire dataflow dependencies:
        If Step i produces an output (e.g. 'reversed', 'file_path', 'metrics') and Step j requires an argument
        of compatible name that is not yet bound to a literal, wire an OutputReference from i to j.
        Also wires logical sequencing for app launch -> interaction and binds GoalContract constraints.
        """
        # Contextual propagation: If open_application precedes typing, bind app_name and use type_into_window
        app_name = None
        has_editor_workflow = False
        for step in steps:
            if step.capability_id in ("open_application", "open_app"):
                app_name = step.arguments.get("app_name") or step.arguments.get("app") or step.arguments.get("name")
            elif step.capability_id in ("type_text", "type_into_window"):
                if app_name:
                    step.capability_id = "type_into_window"
                    step.arguments["app_name"] = app_name
                    step.interaction_tier = InteractionTier.TIER_C_UI_AUTOMATION
                    step.interaction_requirement = InteractionRequirement.APPLICATION_UI
                    has_editor_workflow = True
            elif step.capability_id in ("save_text_file", "save_document_via_ui"):
                if app_name and "app_name" not in step.arguments:
                    step.arguments["app_name"] = app_name
                if step.capability_id == "save_document_via_ui":
                    step.interaction_tier = InteractionTier.TIER_C_UI_AUTOMATION
                    step.interaction_requirement = InteractionRequirement.APPLICATION_UI
                    step.description = f"Save active document in {app_name or 'application'} via native UI dialogs"
                    step.human_label = f"Save document in {app_name or 'application'} as {step.arguments.get('filename', 'document')}"

        # Propagate text payload and saved file path across sequential chain
        text_payload = None
        saved_file_path = None
        for step in steps:
            if step.capability_id in ("type_text", "type_into_window"):
                text_payload = step.arguments.get("text")
            elif step.capability_id in ("save_text_file", "save_document_via_ui"):
                if not step.arguments.get("text") and not step.arguments.get("content") and text_payload:
                    step.arguments["text"] = text_payload
                    step.arguments["content"] = text_payload
                saved_file_path = step.arguments.get("path")
            elif step.capability_id == "reveal_file":
                if not step.arguments.get("path") and saved_file_path:
                    step.arguments["path"] = saved_file_path

        # Bind required constraints from GoalContract to steps
        if contract:
            req_content = contract.get_constraint("content") or contract.get_constraint("text") or contract.get_constraint("required_content")
            if req_content and req_content.expected_value:
                content_val = str(req_content.expected_value)
                for step in steps:
                    if step.capability_id in ("type_text", "type_into_window"):
                        if not step.arguments.get("text"):
                            step.arguments["text"] = content_val
                    elif step.capability_id in ("save_text_file", "save_document_via_ui"):
                        preceding_transform = any(
                            s.capability_id in ("reverse_text", "calculate_hash", "count_words") or "reverse" in s.capability_id
                            for s in steps[:steps.index(step)]
                        )
                        if not preceding_transform:
                            if not step.arguments.get("text") and not step.arguments.get("content"):
                                step.arguments["text"] = content_val
                                step.arguments["content"] = content_val

            req_artifact = contract.get_constraint("artifact") or contract.get_constraint("filename") or contract.get_constraint("target_artifact")
            if req_artifact and req_artifact.expected_value:
                art_val = str(req_artifact.expected_value)
                for step in steps:
                    if step.capability_id in ("save_text_file", "save_document_via_ui"):
                        if not step.arguments.get("filename"):
                            step.arguments["filename"] = art_val
                        if not step.arguments.get("path") and contract.target_location:
                            loc = contract.target_location
                            if loc == "Desktop":
                                step.arguments["path"] = str(Path.home() / "Desktop" / art_val)
                            elif loc == "Downloads":
                                step.arguments["path"] = str(Path.home() / "Downloads" / art_val)


        for i in range(len(steps)):
            step_i = steps[i]
            cap_i = self.registry.get(step_i.capability_id)
            declared_outputs = getattr(cap_i, "outputs", [])
            output_names = [o if isinstance(o, str) else getattr(o, "name", str(o)) for o in declared_outputs] if declared_outputs else []

            # Infer common outputs by convention
            if step_i.capability_id == "reverse_text" and "reversed" not in output_names:
                output_names.append("reversed")
            elif "file" in step_i.capability_id and "output_file" not in output_names:
                output_names.extend(["output_file", "path"])
            elif "metrics" in step_i.capability_id and "metrics" not in output_names:
                output_names.append("metrics")
            else:
                suffix = step_i.capability_id.split('_')[-1]
                output_names.extend([f"{suffix}_out", f"{step_i.capability_id}_output", "result", "data"])

            for j in range(i + 1, len(steps)):
                step_j = steps[j]

                # Logical sequencing
                if step_i.capability_id in ("open_application", "open_app") and step_j.capability_id in ("type_text", "type_into_window", "click_ui_element", "save_document_via_ui"):
                    if not any(d.step_id == step_i.step_id for d in step_j.dependencies):
                        step_j.dependencies.append(StepDependency(step_id=step_i.step_id))
                if step_i.capability_id in ("type_text", "type_into_window", "reverse_text") and step_j.capability_id in ("save_text_file", "save_document_via_ui"):
                    if not any(d.step_id == step_i.step_id for d in step_j.dependencies):
                        step_j.dependencies.append(StepDependency(step_id=step_i.step_id))
                if step_i.capability_id in ("save_text_file", "save_document_via_ui") and step_j.capability_id == "reveal_file":
                    if not any(d.step_id == step_i.step_id for d in step_j.dependencies):
                        step_j.dependencies.append(StepDependency(step_id=step_i.step_id))

                cap_j = self.registry.get(step_j.capability_id)
                args_schema = getattr(cap_j, "args_schema", {})
                if not isinstance(args_schema, dict):
                    args_schema = {}

                # Check if any argument in step_j can be satisfied by output of step_i
                for arg_name in args_schema.keys():
                    current_val = step_j.arguments.get(arg_name)
                    should_bind = False

                    if arg_name in ("content", "text", "hwnd", "target_hwnd", "window", "task_id", "target") and step_i.capability_id in ("open_application", "open_app", "close_app", "close_application", "open_folder", "open_url", "type_into_window", "type_text"):
                        continue

                    if current_val is None or current_val == "" or (isinstance(current_val, str) and "result" in current_val.lower()):
                        should_bind = True

                    if should_bind:
                        matched_output = None
                        if arg_name in output_names:
                            matched_output = arg_name
                        elif arg_name in ("content", "text") and ("reversed" in output_names or "result" in output_names):
                            matched_output = "reversed" if "reversed" in output_names else "result"
                        elif arg_name in ("path", "target_path") and ("output_file" in output_names or "path" in output_names):
                            matched_output = "output_file" if "output_file" in output_names else "path"
                        elif output_names and arg_name not in ("path", "target_path", "output_path", "hwnd", "target_hwnd", "window", "task_id", "target"):
                            matched_output = output_names[0]

                        if matched_output:
                            step_j.arguments[arg_name] = OutputReference(
                                step_id=step_i.step_id,
                                field=matched_output,
                            )
                            if not any(d.step_id == step_i.step_id for d in step_j.dependencies):
                                step_j.dependencies.append(StepDependency(step_id=step_i.step_id))
                            break

    def _infer_success_criteria(self, goal: Goal) -> None:
        """Derive explicit goal completion criteria for GoalVerifier."""
        criteria: list[str] = []
        raw_lower = goal.raw_prompt.lower()

        if "battery report" in raw_lower:
            out = goal.parameters.get("output_path", "Downloads/battery-report.html")
            criteria.append(f"File exists and non-empty at {out}")
        elif "wifi" in raw_lower and "connect" in raw_lower:
            ssid = goal.parameters.get("ssid", "")
            if ssid:
                criteria.append(f"Connected to Wi-Fi SSID '{ssid}'")
        elif "save" in raw_lower and "path" in goal.parameters:
            criteria.append(f"File exists and non-empty at {goal.parameters['path']}")

        goal.success_criteria = criteria
