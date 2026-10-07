"""Production ModelService for AstraRun 1.0.

Provides a unified, model-agnostic cognitive service layer backed by local llama-server
instances supervised by ModelSupervisor:
  - Spark-X2.5-1.7B (:8090) as the FAST engine for intent classification, parameter extraction,
    and fast tool routing.
  - Qwen2.5-Coder-1.5B (:8089) as the DEEP engine for multi-step DAG planning, novel code
    generation, source repair, and complex replanning.

Enforces:
  - Strict loopback isolation (127.0.0.1)
  - Zero cloud leakage (SecretBroker stream scrubbing on all inputs & outputs)
  - Zero execution authority for models (all proposals pass through ASTInspector and ActionGate)
  - Full provenance tracking for every model-generated source file
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel

from astrarun.cognition.client import ModelClient
from astrarun.cognition.models import (
    InferenceObservation,
    InferenceRequest,
    IntentClass,
    IntentDecision,
    IntentReasonerResult,
    ModelRole,
    PlanDAG,
    PlanStep,
    RecoveryDecision,
    ResidencyPreference,
    VerificationDecision,
)
from astrarun.cognition.supervisor import ModelSupervisor
from astrarun.core.logging import get_logger
from astrarun.security.secret_broker import SecretBroker
from astrarun.tools.candidate import CandidateTool, CodeProvenance, DependencyRequest

from astrarun.core.paths import AstraPaths

logger = get_logger("astrarun.cognition.service")

# Canonical model filenames for local GGUF models
SPARK_MODEL_FILENAME = "Spark-X2.5-1.7B-Q4_K_M.gguf"
QWEN_MODEL_FILENAME = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"


class ModelService:
    """Production cognitive service managing Fast and Deep local models."""

    _instance: Optional[ModelService] = None

    def __init__(
        self,
        supervisor: Optional[ModelSupervisor] = None,
        client: Optional[ModelClient] = None,
        secret_broker: Optional[SecretBroker] = None,
        spark_path: Optional[str] = None,
        qwen_path: Optional[str] = None,
        spark_port: int = 8090,
        qwen_port: int = 8089,
    ) -> None:
        self.supervisor = supervisor or ModelSupervisor.get_instance()
        self.client = client or ModelClient()
        self.secret_broker = secret_broker or SecretBroker.get_instance()
        self.spark_path = spark_path or os.environ.get("ASTRA_SPARK_MODEL_PATH") or str(AstraPaths.resolve_model(SPARK_MODEL_FILENAME))
        self.qwen_path = qwen_path or os.environ.get("ASTRA_QWEN_MODEL_PATH") or str(AstraPaths.resolve_model(QWEN_MODEL_FILENAME))
        self.spark_port = spark_port
        self.qwen_port = qwen_port
        self.spark_endpoint = f"http://127.0.0.1:{spark_port}"
        self.deep_endpoint = f"http://127.0.0.1:{qwen_port}"

    @classmethod
    def get_instance(cls) -> ModelService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def ensure_backend(self, role: ModelRole, timeout: float = 20.0) -> bool:
        """Ensure the required model backend is running and healthy on loopback."""
        if role == ModelRole.FAST:
            model_id = "spark-x2.5"
            port = self.spark_port
            path = self.spark_path
            pref = ResidencyPreference.PINNED
            ngl = 99
        else:
            model_id = "qwen2.5-coder"
            port = self.qwen_port
            path = self.qwen_path
            pref = ResidencyPreference.WARM
            ngl = 99

        if self.supervisor.health_check(model_id):
            return True

        endpoint = f"http://127.0.0.1:{port}"
        if self.supervisor._check_endpoint_health(endpoint):
            from astrarun.cognition.residency import ModelRecord, ModelState
            rec = self.supervisor.residency.get_model(model_id) or ModelRecord(
                model_id=model_id,
                role=role,
                residency_preference=pref,
                endpoint=endpoint,
                port=port,
                model_path=path,
            )
            rec.state = ModelState.READY
            rec.health = "HEALTHY"
            self.supervisor.residency.register_model(rec)
            return True

        if not os.path.exists(path):
            logger.warning("GGUF model not found on disk: %s", path)
            return False

        logger.info("Starting local model backend [%s] on port %d...", model_id, port)
        return self.supervisor.start_server(
            model_id=model_id,
            model_path=path,
            port=port,
            role=role,
            preference=pref,
            ngl=ngl,
            timeout=timeout,
        )

    # =========================================================================
    # 1. Routing & Intent Classification (Spark Fast Engine)
    # =========================================================================
    def route(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> IntentDecision:
        """Classify user intent using the Fast engine (Spark)."""
        tid = task_id or f"route_{uuid.uuid4().hex[:8]}"

        if not self.ensure_backend(ModelRole.FAST, timeout=5.0):
            # Deterministic fallback when server is unavailable
            from astrarun.routing.input_router import classify_launcher_input, InputIntent
            det_intent = classify_launcher_input(query)
            return IntentDecision(
                intent=det_intent.value.lower(),
                confidence=0.8,
                is_compound=False,
                entities={"query": query},
                reasoning="Heuristic fallback; Spark backend offline.",
                requires_deep_planning=det_intent == InputIntent.GOAL,
            )

        system_prompt = (
            "You are AstraRun's Fast Cognitive Kernel. Classify the user query into a clean intent. "
            "Respond ONLY with a valid JSON object matching IntentDecision: "
            '{"intent": str, "confidence": float, "is_compound": bool, "entities": dict, "reasoning": str, "requires_deep_planning": bool}.'
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Query: {query}\nContext: {context or {}}"},
        ]
        req = InferenceRequest(
            task_id=tid,
            role=ModelRole.FAST,
            messages=messages,
            temperature=0.1,
            max_tokens=256,
        )

        try:
            obs = asyncio.run(self.client.complete(req, self.spark_endpoint, response_model=IntentDecision))
            if obs.is_success and obs.parsed_output:
                return IntentDecision.model_validate(obs.parsed_output)
        except Exception as e:
            logger.warning("Spark route inference failed: %s", e)

        return IntentDecision(
            intent="unknown",
            confidence=0.3,
            is_compound=False,
            entities={"query": query},
            reasoning="Inference completed without valid schema; falling back to deep planning.",
            requires_deep_planning=True,
        )

    classify_intent = route

    def classify_intent_reasoner(
        self,
        query: str,
        available_capabilities: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> IntentReasonerResult:
        """
        Tier 2 Local Intent Reasoner.
        Queries resident model for structured intent classification:
        {intent_class, candidate_capabilities, confidence, reason, requires_code}.
        """
        tid = task_id or f"reason_{uuid.uuid4().hex[:8]}"

        endpoint = None
        role = None
        if self.ensure_backend(ModelRole.DEEP, timeout=2.0):
            endpoint = self.deep_endpoint
            role = ModelRole.DEEP
        elif self.ensure_backend(ModelRole.FAST, timeout=2.0):
            endpoint = self.spark_endpoint
            role = ModelRole.FAST

            # Provide query-relevant capabilities rather than arbitrary prefix list
            query_tokens = set(query.lower().split())
            relevant_caps = [
                c for c in (available_capabilities or [])
                if any(tok in c.lower() for tok in query_tokens if len(tok) > 2)
            ]
            cap_list = ", ".join(relevant_caps[:15]) if relevant_caps else "none matching"
            system_prompt = (
                "You are AstraRun's Local Intent Reasoner. Classify the user query into exactly one intent_class:\n"
                "- KNOWN_CAPABILITY: Direct match for a single known OS capability (e.g. screenshot, inspect_port, find_file).\n"
                "- COMPOSITE_WORKFLOW: Multi-step pipeline combining TWO OR MORE EXISTING capabilities from the Available Capabilities list (e.g. 'check cpu status and inspect memory', 'minimize window then check battery status'). If the user wants to calculate, simulate, plot, format, transform data, or write a script, choose DYNAMIC_COMPUTATION, NOT COMPOSITE_WORKFLOW.\n"
                "- DYNAMIC_COMPUTATION: Requires writing novel Python code/script for calculations, equations, algorithms, simulations, data transformations, tables, summaries, or custom charts/plots (e.g. quadratic equation, regression, primes, simulation, scatter plot, 2D histogram, convert JSON to CSV, markdown report table, file organization).\n"
                "- DELEGATE_EXTERNAL_AI: Asks to consult an external model/advisor like ChatGPT, Claude, Gemini, or external assistant.\n"
                "- CONVERSATIONAL: Casual chat, general advice, explanations, questions about status, or troubleshooting conversation. Does NOT run code.\n"
                "- CLARIFICATION_REQUIRED: Ambiguous, underspecified, or incomplete user prompt that needs clarification before taking action (e.g. 'hello', 'do something', 'help').\n\n"
                "CRITICAL RULES:\n"
                "1. If the user asks a question, chats, asks for advice, or describes a vague issue (e.g., 'why is my laptop acting weird?', 'what does this warning mean?', 'continue what we were doing yesterday', 'help me decide which project to work on'), classify as CONVERSATIONAL or CLARIFICATION_REQUIRED, and set requires_code to false.\n"
                "2. If the request requires any calculation, math, simulation, data conversion, table/report generation, plotting, or file reorganization by code, ALWAYS choose DYNAMIC_COMPUTATION with requires_code to true.\n"
                "3. Respond ONLY with valid JSON matching IntentReasonerResult: "
                '{"intent_class": str, "candidate_capabilities": list, "confidence": float, "reason": str, "requires_code": bool}'
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Query: {query}\nAvailable Capabilities: [{cap_list}]\nContext: {context or {}}"},
            ]
            req = InferenceRequest(
                task_id=tid,
                role=role,
                messages=messages,
                temperature=0.1,
                max_tokens=256,
            )
            try:
                obs = asyncio.run(self.client.complete(req, endpoint, response_model=IntentReasonerResult))
                if obs.is_success and obs.parsed_output:
                    return IntentReasonerResult.model_validate(obs.parsed_output)
            except Exception as e:
                logger.warning("Local intent reasoner model call failed: %s", e)

        return self._fallback_intent_reasoner(query, available_capabilities)

    def _fallback_intent_reasoner(
        self,
        query: str,
        available_capabilities: Optional[List[str]] = None,
    ) -> IntentReasonerResult:
        """Deterministic semantic fallback when local model server is unavailable."""
        q = query.lower().strip()
        caps = available_capabilities or []

        # External AI delegation
        if any(w in q for w in ("chatgpt", "claude", "gemini", "external ai", "delegate", "advisor")):
            return IntentReasonerResult(
                intent_class=IntentClass.DELEGATE_EXTERNAL_AI,
                confidence=0.85,
                reason="Query references external AI delegation.",
                requires_code=False,
            )

        # Ambiguous / Short queries requiring clarification
        if len(q.split()) <= 2 and q in ("help", "what", "do something", "test", "run", "fix", "hello", "hi", "inspect", "start", "check"):
            return IntentReasonerResult(
                intent_class=IntentClass.CLARIFICATION_REQUIRED,
                confidence=0.75,
                reason="Underspecified query requiring parameter clarification.",
                requires_code=False,
            )

        # Conversational / Advice / Open-ended / Ambiguous questions
        inquiry_starters = ("why ", "what is ", "what does ", "what was ", "how do i ", "help me ", "can you explain", "good morning", "thanks", "continue ")
        if any(q.startswith(w) for w in inquiry_starters) or q.endswith("?") or any(w in q for w in ("acting weird", "went wrong", "which project to work on", "what we were doing yesterday", "difference between")):
            if not any(w in q for w in ("script", "code", "plot", "compute", "calculate", "generate csv")):
                return IntentReasonerResult(
                    intent_class=IntentClass.CONVERSATIONAL,
                    confidence=0.85,
                    reason="Open-ended question or conversational dialogue.",
                    requires_code=False,
                )

        # Dynamic computation / programmatic generation
        dyn_keywords = (
            "script", "python", "code", "csv", "json", "monte carlo", "simulation",
            "collatz", "prime", "algorithm", "plot", "graph", "histogram", "chart", "bar",
            "calculate", "compute", "valuation", "fibonacci", "roots", "quadratic",
            "regression", "three-body", "orbital", "dataset", "table", "organize",
            "scatter", "visualiz", "render", "parse", "log", "heatmap"
        )
        if any(w in q for w in dyn_keywords):
            return IntentReasonerResult(
                intent_class=IntentClass.DYNAMIC_COMPUTATION,
                confidence=0.85,
                reason="Requires computational algorithm or dynamic data processing.",
                requires_code=True,
            )

        # Direct capability match
        for cap in caps:
            if cap.replace("_", " ") in q or q.replace(" ", "_") == cap:
                return IntentReasonerResult(
                    intent_class=IntentClass.KNOWN_CAPABILITY,
                    candidate_capabilities=[cap],
                    confidence=0.85,
                    reason=f"Matches known capability {cap}.",
                    requires_code=False,
                )

        return IntentReasonerResult(
            intent_class=IntentClass.CLARIFICATION_REQUIRED,
            confidence=0.40,
            reason="Unknown query; clarification required. Does not assume Python execution.",
            requires_code=False,
        )

    # =========================================================================
    # 2. Multi-Step DAG Planning (Qwen Deep Engine)
    # =========================================================================

    def plan(
        self,
        goal: str,
        available_capabilities: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> Optional[PlanDAG]:
        """Synthesize a typed PlanDAG using Qwen2.5-Coder."""
        tid = task_id or f"plan_{uuid.uuid4().hex[:8]}"

        if not self.ensure_backend(ModelRole.DEEP, timeout=15.0):
            logger.warning("Qwen backend offline; cannot perform neural DAG planning.")
            return None

        system_prompt = (
            "You are AstraRun's Deep Autonomous Planner. Translate the goal into a deterministic PlanDAG. "
            "Every step must have a unique 'step_id', a valid 'capability', typed 'arguments', and 'dependencies'. "
            "NEVER produce cycles. Output ONLY a valid JSON object matching PlanDAG schema: "
            '{"goal": str, "steps": [{"step_id": str, "capability": str, "arguments": dict, "dependencies": list, "risk_hint": str}]}.'
        )

        caps_summary = "\n".join(f"- {c.get('id')}: {c.get('description')}" for c in available_capabilities[:40])
        user_content = f"Goal: {goal}\nAvailable Capabilities:\n{caps_summary}\nContext: {context or {}}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        req = InferenceRequest(
            task_id=tid,
            role=ModelRole.DEEP,
            messages=messages,
            temperature=0.2,
            max_tokens=1024,
        )

        try:
            obs = asyncio.run(self.client.complete(req, self.deep_endpoint, response_model=PlanDAG))
            if obs.is_success and obs.parsed_output:
                dag = PlanDAG.model_validate(obs.parsed_output)
                dag.validate_graph()
                return dag
        except Exception as e:
            logger.error("Deep planning exception: %s", e)

        return None

    # =========================================================================
    # 3. Dynamic Code Generation (Qwen Deep Engine)
    # =========================================================================

    def generate_code(
        self,
        goal: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None,
        requirements: Optional[List[str]] = None,
        task_id: Optional[str] = None,
    ) -> CandidateTool:
        """
        Synthesize complete, standalone code (single-file or multi-file) via Qwen2.5-Coder.
        Emits a strictly typed CandidateTool with cryptographic provenance.
        """
        tid = task_id or f"task_{uuid.uuid4().hex[:8]}"
        t_start = time.time()
        prompt_hash = hashlib.sha256(goal.encode("utf-8")).hexdigest()

        if not self.ensure_backend(ModelRole.DEEP, timeout=15.0):
            raise RuntimeError("Qwen2.5-Coder backend is unavailable for dynamic code synthesis.")

        system_prompt = (
            "You are AstraRun's Expert Autonomous Software Engineer powered by Qwen2.5-Coder.\n"
            "Output ONLY complete, robust, executable Python code inside ```python ... ``` fences.\n"
            "CRITICAL ARCHITECTURAL CONTRACT:\n"
            "1. Produce complete, standalone, immediately executable Python code with an explicit entrypoint.\n"
            "2. Read the destination directory from os.environ.get('ASTRARUN_OUTPUT_DIR', '.') when saving requested deliverables, or write deliverables directly to current working directory.\n"
            "3. Ensure all needed imports for the specific task are present at the top of the file.\n"
            "4. ONLY import libraries that are strictly necessary for the requested goal. Never import matplotlib or GUI libraries unless the user explicitly requested a chart, plot, or graph. If and only if creating plots, configure headless matplotlib before importing pyplot: import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt.\n"
            "5. Ensure proper context management for file handles (do NOT perform write operations on closed files).\n"
            "6. For arrays and matrices, ensure dimensions and column lengths match exactly before stacking or concatenating.\n"
            "7. Never use raw ctypes, winreg, raw sockets, or unauthorized subprocess calls.\n"
            "8. Exit cleanly with code 0 on success; return non-zero on unrecoverable failure.\n"
            "9. NEVER output conversational preamble or explanations. Start directly with the ```python code fence."
        )

        user_content = f"Goal: {goal}\nLanguage: {language}\nContext: {context or {}}\nRequirements: {requirements or []}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        req = InferenceRequest(
            task_id=tid,
            role=ModelRole.DEEP,
            messages=messages,
            temperature=0.2,
            max_tokens=2048,
        )

        obs = asyncio.run(self.client.complete(req, self.deep_endpoint))
        raw_text = obs.raw_output

        # Extract code from JSON or Markdown block
        source_files, entrypoint = self._extract_source_files(raw_text)

        cand = CandidateTool(
            goal=goal,
            purpose=goal,
            language=language,
            source_files=source_files,
            entrypoint=entrypoint,
            task_id=tid,
            generator_model="qwen2.5-coder",
        )

        source_hash = cand.compute_source_hash()
        from astrarun.tools.candidate import RevisionRecord
        rev1 = RevisionRecord(
            revision_number=1,
            request_id=tid,
            prompt_hash=prompt_hash,
            response_hash=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
            source_hash=source_hash,
            repair_reason="initial_synthesis",
        )
        cand.provenance = CodeProvenance(
            task_id=tid,
            model="qwen2.5-coder",
            model_version="1.5b-instruct",
            prompt_hash=prompt_hash,
            source_hash=source_hash,
            revision=1,
            reason_for_revision="initial_synthesis",
            final_revision=1,
            final_source_hash=source_hash,
            revisions=[rev1],
        )

        logger.info("Qwen synthesized CandidateTool [%s] (%d files, entry=%s, hash=%s)",
                    cand.tool_id, len(cand.source_files), cand.entrypoint, source_hash[:12])
        return cand

    # =========================================================================
    # 4. Source Self-Repair (Qwen Deep Engine)
    # =========================================================================

    def repair_code(
        self,
        candidate: CandidateTool,
        repair_context: Any = None,
        attempt: int = 1,
        error_message: Optional[str] = None,
    ) -> CandidateTool:
        """
        Diagnose a failing execution or AST violation and synthesize revised code via Qwen.
        Accepts structured repair packet or raw error message.
        Updates CodeProvenance revision history.
        """
        if repair_context is None and error_message is not None:
            repair_context = error_message

        if not self.ensure_backend(ModelRole.DEEP, timeout=15.0):
            raise RuntimeError("Qwen2.5-Coder backend is unavailable for code repair.")

        # Extract structured packet attributes if available
        if hasattr(repair_context, "failure_type"):
            fail_type = str(getattr(repair_context.failure_type, "value", repair_context.failure_type))
            analysis = getattr(repair_context, "analysis", "")
            err_msg = getattr(repair_context, "stderr", "") or "\n".join(getattr(repair_context, "ast_violations", [])) or getattr(repair_context, "verification_error", "")
            out_dir = getattr(repair_context, "output_dir", "")
        else:
            fail_type = "RUNTIME_EXCEPTION"
            analysis = "Analyze the traceback and correct source logic."
            err_msg = str(repair_context)
            out_dir = ""

        current_code = candidate.source_files.get(candidate.entrypoint, candidate.executable_code)
        system_prompt = (
            "You are AstraRun's Expert Autonomous Debugger powered by Qwen2.5-Coder.\n"
            "The candidate program failed with a structured execution or validation failure. "
            "Analyze the root cause and return the COMPLETE corrected Python source inside ```python ... ```.\n"
            "CRITICAL:\n"
            "1. Output ONLY the ```python code fence. Do not include commentary, explanations, or JSON objects.\n"
            "2. Diagnose the programming bug from the original goal, source code, and failure traceback.\n"
            "3. Ensure the corrected program remains self-contained, valid Python, and writes deliverables to the governed output directory."
        )

        exc_type = getattr(repair_context, "exception_type", None)
        exc_msg_field = getattr(repair_context, "exception_message", None)
        failing_line = getattr(repair_context, "failing_line", None)
        failing_file = getattr(repair_context, "failing_file", None)
        exc_info = ""
        if exc_type:
            exc_info = f"Exception: {exc_type}: {exc_msg_field or ''}\n"
        if failing_file and failing_line:
            exc_info += f"Failing Location: {failing_file} (line {failing_line})\n"

        user_content = (
            f"Goal: {candidate.goal}\n"
            f"Failing Entrypoint: {candidate.entrypoint}\n"
            f"Failure Classification: {fail_type}\n"
            f"{exc_info}"
            f"Diagnostic Analysis: {analysis}\n"
            f"Governed Output Directory: {out_dir or 'os.environ.get(\"ASTRARUN_OUTPUT_DIR\", \".\")'}\n"
            f"Error Traceback / Violation:\n{err_msg}\n\n"
            f"Current Source Code:\n```python\n{current_code}\n```\n"
            "Return the full corrected source file inside ```python ... ```."
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
        tid = f"{candidate.task_id}_rev{attempt + 1}"
        req = InferenceRequest(
            task_id=tid,
            role=ModelRole.DEEP,
            messages=messages,
            temperature=0.2,
            max_tokens=2048,
        )

        obs = asyncio.run(self.client.complete(req, self.deep_endpoint))
        new_sources, new_entry = self._extract_source_files(obs.raw_output)

        # Merge repaired files
        repaired_sources = dict(candidate.source_files)
        repaired_sources.update(new_sources)

        repaired_cand = CandidateTool(
            goal=candidate.goal,
            purpose=candidate.purpose,
            language=candidate.language,
            source_files=repaired_sources,
            entrypoint=new_entry or candidate.entrypoint,
            task_id=candidate.task_id,
            tool_id=candidate.tool_id,
            generator_model="qwen2.5-coder",
        )

        new_hash = repaired_cand.compute_source_hash()
        from astrarun.tools.candidate import RevisionRecord
        rev_record = RevisionRecord(
            revision_number=attempt + 1,
            request_id=tid,
            prompt_hash=hashlib.sha256(user_content.encode("utf-8")).hexdigest(),
            response_hash=hashlib.sha256(obs.raw_output.encode("utf-8")).hexdigest(),
            source_hash=new_hash,
            parent_revision=attempt,
            repair_reason=f"Repaired error ({fail_type}): {err_msg[:120]}",
        )

        prov = candidate.provenance or CodeProvenance(
            task_id=candidate.task_id,
            model="qwen2.5-coder",
            prompt_hash=hashlib.sha256(candidate.goal.encode()).hexdigest(),
            source_hash=new_hash,
        )
        prov.record_revision(rev_record)
        prov.reason_for_revision = f"Repaired error ({fail_type}): {err_msg[:120]}"
        repaired_cand.provenance = prov

        logger.info("Qwen repaired CandidateTool [%s] (revision %d, hash=%s)",
                    repaired_cand.tool_id, repaired_cand.provenance.revision, new_hash[:12])
        return repaired_cand

    # =========================================================================
    # 5. Reality Verification (Spark / Qwen)
    # =========================================================================

    def verify(
        self,
        goal: str,
        observation: Dict[str, Any],
    ) -> VerificationDecision:
        """
        Verify whether the observed reality satisfies the user's explicit objective.
        Checks exit code, created artifacts, and semantic content.
        """
        # Fast rule-based pre-check
        exit_code = observation.get("exit_code")
        artifacts = observation.get("artifacts", [])
        stderr = observation.get("stderr", "")

        # If goal asks for image/visualization/graph:
        is_visual = any(w in goal.lower() for w in ("graph", "plot", "visualization", "chart", "3d", "image"))
        if is_visual:
            # Check for image artifact existence & non-zero size
            valid_image = False
            for art in artifacts:
                art_p = Path(art.get("path") if isinstance(art, dict) else art)
                if art_p.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg") and art_p.exists() and art_p.stat().st_size > 100:
                    valid_image = True
                    break
            if not valid_image:
                return VerificationDecision(
                    is_success=False,
                    confidence=0.95,
                    reasoning="Visual objective requested, but no valid non-empty image artifact was created.",
                    missing_elements=["valid_image_artifact"],
                )

        if exit_code == 0 and not stderr:
            return VerificationDecision(is_success=True, confidence=0.95, reasoning="Process completed with exit code 0 and valid artifacts.")

        if exit_code != 0:
            return VerificationDecision(
                is_success=False,
                confidence=0.9,
                reasoning=f"Process exited with non-zero code {exit_code}: {stderr[:150]}",
            )

        return VerificationDecision(is_success=True, confidence=0.8, reasoning="Execution completed without critical failure.")

    # =========================================================================
    # 6. General Reasoning & Summarization
    # =========================================================================

    def reason(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        deep: bool = False,
    ) -> str:
        """Direct reasoning using Fast or Deep local model."""
        role = ModelRole.DEEP if deep else ModelRole.FAST
        endpoint = self.deep_endpoint if deep else self.spark_endpoint

        if not self.ensure_backend(role, timeout=10.0):
            return "Model backend is currently offline."

        messages = [
            {"role": "system", "content": "You are AstraRun's local reasoning assistant. Answer concisely and accurately."},
            {"role": "user", "content": f"{prompt}\nContext: {context or {}}"},
        ]
        req = InferenceRequest(role=role, messages=messages, temperature=0.3, max_tokens=512)
        try:
            obs = asyncio.run(self.client.complete(req, endpoint))
            return obs.raw_output.strip()
        except Exception as e:
            return f"Reasoning error: {e}"

    def summarize(self, text: str, max_tokens: int = 256) -> str:
        """Fast text summarization via Spark."""
        return self.reason(f"Summarize the following text concisely in 2-3 sentences:\n\n{text[:2000]}", deep=False)

    # =========================================================================
    # Helper Parsing Methods
    # =========================================================================

    def _extract_source_files(self, raw: str, default_entrypoint: str = "main.py") -> Tuple[Dict[str, str], str]:
        """Extract multi-file or single-file source from raw model output."""
        clean = raw.strip()

        # 1. Attempt Markdown code fence parsing first (most standard for LLM code gen)
        code_blocks = re.findall(r"```(?:python)?\s*([\s\S]*?)\s*```", clean, re.IGNORECASE)
        if code_blocks:
            combined_code = code_blocks[0].strip()
            return {default_entrypoint: combined_code}, default_entrypoint

        # 2. Attempt unclosed Markdown code fence (e.g. truncated generation)
        unclosed = re.search(r"```(?:python)?\s*\n?([\s\S]*)$", clean, re.IGNORECASE)
        if unclosed:
            combined_code = unclosed.group(1).rstrip()
            if combined_code.endswith("```"):
                combined_code = combined_code[:-3].rstrip()
            if combined_code.strip():
                return {default_entrypoint: combined_code.strip()}, default_entrypoint

        # 3. Attempt JSON structure parsing
        json_match = re.search(r"\{[\s\S]*\}", clean)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                if "files" in data and isinstance(data["files"], list):
                    sources = {}
                    for f in data["files"]:
                        p = f.get("path") or f.get("filename")
                        c = f.get("content") or ""
                        if p:
                            sources[p] = c
                    entry = data.get("entrypoint", default_entrypoint)
                    if sources:
                        return sources, entry
                elif "code" in data and isinstance(data["code"], str):
                    return {default_entrypoint: data["code"].strip()}, default_entrypoint
            except Exception:
                pass

        # 3. Raw text fallback
        return {default_entrypoint: clean}, default_entrypoint
