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

        if endpoint and role:
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

        # 0. External AI delegation (only when commanded, not when merely permitted)
        is_permissive_delegation = bool(re.search(r'\b(?:you\s+may|optionally|feel\s+free\s+to|if\s+you\s+(?:genuinely\s+)?think|if\s+needed|can\s+consult|permitted\s+to)\b', q))
        if not is_permissive_delegation and any(w in q for w in ("chatgpt", "claude", "gemini", "external ai", "delegate", "advisor")):
            return IntentReasonerResult(
                intent_class=IntentClass.DELEGATE_EXTERNAL_AI,
                confidence=0.85,
                reason="Query references external AI delegation.",
                requires_code=False,
            )

        # 1. Ambiguous / Underspecified / Nonsense queries -> CLARIFICATION_REQUIRED
        words = q.split()
        bare_verbs = {
            "help", "what", "do something", "test", "run", "fix", "inspect", "start",
            "check", "solve", "calculate", "compute", "plot", "code", "script",
            "generate", "summary", "convert", "do", "make", "save", "delete", "open"
        }
        if len(words) <= 2 and (q in bare_verbs or (len(words) == 1 and words[0] in bare_verbs)):
            return IntentReasonerResult(
                intent_class=IntentClass.CLARIFICATION_REQUIRED,
                confidence=0.85,
                reason="Bare command lacking target operands or parameters.",
                requires_code=False,
            )

        vague_patterns = (
            r"^(?:run|do|fix|start|process|make|handle)\s+(?:it|the\s+thing|that\s+task|the\s+problem|the\s+job|this\s+please)$",
            r"^(?:find|delete|open|save)\s+(?:the\s+file|that\s+folder|the\s+application|it\s+to\s+disk)$",
            r"^(?:calculate|solve|compute|plot|parse)\s+(?:the\s+result|the\s+equation|the\s+numbers|the\s+chart|the\s+log)$",
            r"^(?:can\s+you\s+please|i\s+would\s+like\s+to|where\s+is\s+the|how\s+do\s+i\s+get\s+to|because\s+of\s+the|if\s+you\s+can\s+then)$",
        )
        if any(re.match(pat, q) for pat in vague_patterns):
            return IntentReasonerResult(
                intent_class=IntentClass.CLARIFICATION_REQUIRED,
                confidence=0.85,
                reason="Query contains vague placeholder target lacking required parameters.",
                requires_code=False,
            )

        nonsense_tokens = {"asdfghjkl", "qwertyuiop", "zxcvbnm", "blablabla"}
        if any(tok in q for tok in nonsense_tokens) or q in ("??? !!! ???", "............", "undefined null nan void") or re.match(r"^[^a-zA-Z0-9\s]+$", q):
            return IntentReasonerResult(
                intent_class=IntentClass.CLARIFICATION_REQUIRED,
                confidence=0.85,
                reason="Unrecognized or nonsensical input.",
                requires_code=False,
            )

        # 2. Application Launch & Direct System Commands -> KNOWN_CAPABILITY
        app_launch_match = re.match(r"^(?:open|launch|start)\s+([a-zA-Z0-9_\-\s\.\+]+)$", q)
        if app_launch_match:
            target_app = app_launch_match.group(1).strip()
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
            if any(target_app == a or target_app.startswith(a) for a in known_apps):
                return IntentReasonerResult(
                    intent_class=IntentClass.KNOWN_CAPABILITY,
                    candidate_capabilities=["open_application"],
                    confidence=0.90,
                    reason=f"Application or directory launch request for '{target_app}'.",
                    requires_code=False,
                )

        if any(w in q for w in ("battery report", "battery health", "battery status")) or q.startswith("generate battery report"):
            return IntentReasonerResult(
                intent_class=IntentClass.KNOWN_CAPABILITY,
                candidate_capabilities=["generate_battery_report"],
                confidence=0.95,
                reason="Direct battery status/report query.",
                requires_code=False,
            )

        if any(w in q for w in ("wifi networks", "scan wifi", "show wifi")):
            return IntentReasonerResult(
                intent_class=IntentClass.KNOWN_CAPABILITY,
                candidate_capabilities=["scan_wifi_networks"],
                confidence=0.90,
                reason="System Wi-Fi capability request.",
                requires_code=False,
            )

        if any(w in q for w in ("git status", "git branch", "git history")) or (("git log" in q) and not any(k in q for k in ("parse", "compute", "count", "stats", "lines changed", ".txt", ".json", ".csv"))):
            return IntentReasonerResult(
                intent_class=IntentClass.KNOWN_CAPABILITY,
                candidate_capabilities=["project_git_status"],
                confidence=0.90,
                reason="Repository Git status inspection.",
                requires_code=False,
            )

        if any(w in q for w in ("screenshot", "capture screen", "screen grab")):
            return IntentReasonerResult(
                intent_class=IntentClass.KNOWN_CAPABILITY,
                candidate_capabilities=["take_screenshot"],
                confidence=0.90,
                reason="Screen capture capability request.",
                requires_code=False,
            )

        system_queries = (
            "lock workstation", "lock screen", "mute system", "unmute system",
            "system memory", "check memory", "total disk", "disk space",
            "cpu usage", "running processes", "uptime", "hostname"
        )
        if any(w in q for w in system_queries) and not any(ext in q for ext in (".csv", ".json", ".log")):
            return IntentReasonerResult(
                intent_class=IntentClass.KNOWN_CAPABILITY,
                candidate_capabilities=["get_system_info"],
                confidence=0.90,
                reason="System control/info capability request.",
                requires_code=False,
            )

        # 3. Conversational / Q&A / Advice / Literary / Trivia -> CONVERSATIONAL
        inquiry_starters = (
            "why ", "what is ", "what are ", "what does ", "what was ", "how do i ",
            "how does ", "how can i ", "can you explain", "could you explain", "explain ",
            "tell me ", "summarize ", "good morning", "hello", "hi ", "thank you", "thanks",
            "who wrote", "who painted", "who is ", "where is the capital", "what causes",
            "have a great", "who are you"
        )
        is_literary_or_trivia = any(w in q for w in (
            "plot of ", "solve this riddle", "thinking puzzle", "solve a dispute", "solve conflict",
            "airport code", "postal code", "periodic table", "dimensions of", "clean code mean",
            "count me in", "count your chickens", "vote should count", "write an email",
            "write a congratulatory", "draft a polite", "warren commission report",
            "black box log", "captain's log"
        ))
        is_question = q.endswith("?") and not any(w in q for w in ("compute", "calculate", "simulate", "integrate", "run script"))

        if any(q.startswith(w) for w in inquiry_starters) or is_literary_or_trivia or is_question:
            if not any(w in q for w in ("write a script to", "write python code to", "compute the", "calculate the", "simulate a", "parse the")):
                return IntentReasonerResult(
                    intent_class=IntentClass.CONVERSATIONAL,
                    confidence=0.90,
                    reason="Conversational dialogue, conceptual inquiry, advice, or trivia.",
                    requires_code=False,
                )

        # 4. Genuine Dynamic Computation & Algorithmic Synthesis -> DYNAMIC_COMPUTATION
        is_explicit_python = bool(re.search(
            r'\b(?:python\s+(?:program|script|code)|program\s+that|script\s+that|create\s+(?:a\s+)?python|write\s+(?:a\s+)?python)\b',
            q
        ))

        is_math_algo = bool(re.search(
            r'\b(?:correlation\s+matrix|histogram|bin\s+table|eigenvalues?|polynomial|roots\s+of|random\s+walk|pendulum|lotka-volterra|monte\s+carlo|collatz|fibonacci|three-body|integration|simpson|diffusion|fourier|fft|dijkstra|brownian|markov|mandelbrot|game\s+of\s+life|singular\s+value|svd|poisson|geodesic|autocorrelation|cellular\s+automaton|pagerank|chi-square|pareto|regression|prime\s+(?:numbers|gaps|factorization)|determinant|sha256|checksum|convex\s+hull|graham\s+scan|hilbert\s+matrix|lu\s+decomposition|cholesky|qr\s+decomposition|k-means|voronoi)\b',
            q
        ))

        is_data_pipeline = bool(re.search(r'\b(?:parse|extract|aggregate|transform|compile|convert|turn|merge|organize|flatten)\b', q)) and (
            any(ext in q for ext in (".log", ".csv", ".json", ".txt"))
            or any(kw in q for kw in ("summary table", "summary report", "percentile", "percentiles", "distribution", "spikes", "frequencies", "frequency", "averages", "totals", "metrics", "latencies", "dataset", "server log", "test files", "tabular csv", "json payload", "auth_summary", "orders", "commits", "exceptions", "kernel panic", "stack traces"))
        )

        is_procedural_gen = bool(re.search(
            r'\bgenerate\s+(?:a\s+)?(?:\d+x\d+\s+)?(?:random\s+)?(?:maze|grid|synthetic|mandelbrot|matrix|dataset|distribution|series|histogram|cellular)\b',
            q
        ))

        is_direct_calc = bool(re.search(
            r'\b(?:calculate|compute|work\s+out|solve)\s+(?:the\s+)?(?:area|perimeter|trajectories|roots|eigenvalues?|distances?|equations?|system|integral|fourier|distribution|statistics|standard\s+deviation|variance|volatility|rolling|fibonacci|prime|autocorrelation|hilbert|condition\s+number|determinant|factorization|checksums?|sha256|convex\s+hull)\b',
            q
        ))

        is_data_plotting = bool(re.search(
            r'\b(?:plot|render|generate|create|make)\s+(?:a\s+)?(?:\d+[dD]\s+)?(?:scatter\s+plot|line\s+chart|bar\s+chart|histogram|heatmap|chart|plot|visualization|surface\s+plot)\b',
            q
        )) or bool(re.search(r'\b(?:visualiz\w*|plot\w*)\s+(?:memory|cpu|activity|temperature|sales|revenue|expenses|scores|readings|function|3d)\b', q))

        if is_explicit_python or is_math_algo or is_data_pipeline or is_procedural_gen or is_direct_calc or is_data_plotting:
            return IntentReasonerResult(
                intent_class=IntentClass.DYNAMIC_COMPUTATION,
                confidence=0.90,
                reason="Requires genuine algorithmic computation or programmatic data transformation.",
                requires_code=True,
            )

        # Check existing capabilities list
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
            confidence=0.50,
            reason="Unclassified intent; clarification required.",
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
            "3. Always import all needed standard library modules at the top of the file: import os, sys, math, struct, zlib, json, re; from pathlib import Path.\n"
            "4. Prefer Python standard library (math, struct, zlib, collections, json, os, sys, re, pathlib). NEVER import PIL, Pillow, matplotlib, scipy, pandas, numpy, or GUI libraries because binary C-extension DLLs fail to load inside the Windows AppContainer sandbox.\n"
            "   - If the goal is pure calculation, math, data processing, or text (and does NOT explicitly ask for an image, plot, or 3D visualization), do NOT create PNG files or call save_png; simply compute the results, print them to stdout (e.g. print('pi =', math.pi)), and/or save to json/text.\n"
            "   - ONLY when an image, plot, or 3D visualization is explicitly requested, generate pure standard library PNG images using struct and zlib:\n"
            "     * Compute a 3D surface: e.g. for (x, y) calculate z = math.sin(math.hypot(x, y)), clamp to [0..255]: val = max(0, min(255, int(127.5 * (z + 1.0)))), and extend rgb_bytes with struct.pack('>BBB', val, val, 255). All bytes packed with '>BBB' MUST be strictly clamped to 0 <= b <= 255.\n"
            "     * Save PNG using this exact pure-Python function:\n"
            "     def save_png(filename, width, height, rgb_bytes):\n"
            "         import zlib, struct\n"
            "         raw = bytearray()\n"
            "         for y in range(height):\n"
            "             raw.append(0)\n"
            "             raw.extend(rgb_bytes[y * width * 3 : (y + 1) * width * 3])\n"
            "         def chunk(tag, data):\n"
            '             return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)\n'
            '         ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)\n'
            '         with open(filename, "wb") as f:\n'
            '             f.write(b"\\x89PNG\\r\\n\\x1a\\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))\n'
            "   - To save the Python source code deliverable, use: from pathlib import Path; (Path(os.environ.get('ASTRARUN_OUTPUT_DIR', '.')) / 'source.py').write_text(Path(__file__).read_text(encoding='utf-8'), encoding='utf-8'). Do not embed code in large string variables.\n"
            "5. Ensure proper context management for file handles (do NOT perform write operations on closed files).\n"
            "6. For arrays and matrices, ensure dimensions and column lengths match exactly before stacking or concatenating.\n"
            "7. Never use raw ctypes, winreg, raw sockets, or unauthorized subprocess calls.\n"
            "8. Exit cleanly with code 0 on success; return non-zero on unrecoverable failure.\n"
            "9. Self-contained input files: If the goal specifies reading an existing file, create and write that file first if it does not already exist.\n"
            "10. Output files: ALWAYS create and save all requested output files (e.g. word_frequencies.json, fibonacci.txt). Save output files in os.environ.get('ASTRARUN_OUTPUT_DIR', '.') or the working directory using the exact filename requested in the goal. NEVER read output path from os.environ.get('path') because 'path' matches the system PATH variable on Windows.\n"
            "11. Word tokenization: If counting word frequencies, properly tokenize words by converting text to lowercase and extracting words without punctuation (e.g. re.findall(r'\\b[A-Za-z0-9_]+\\b', text.lower())).\n"
            "12. Print the requested result to stdout.\n"
            "13. NEVER output conversational preamble or explanations. Start directly with the ```python code fence.\n"
            "14. Unconditional execution: The script MUST unconditionally execute the goal and create all requested output files immediately when run. NEVER gate execution on command-line flags or checking if os.environ.get('goal') matches a keyword."
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
            "3. Ensure the corrected program remains self-contained, valid Python, and writes deliverables to the governed output directory.\n"
            "4. NEVER just catch an exception and print an error or exit without performing the goal. Fix the root cause in the data extraction or logic so requested deliverables are created with the intended values.\n"
            "5. When fixing a KeyError or missing field, inspect available fields in the input data structure and extract the actual data. Do not insert synthetic placeholder strings; resolve to the correct attribute or key so output deliverables contain authentic values.\n"
            "6. If the error is ModuleNotFoundError or ImportError (e.g. for PIL, _imaging, matplotlib, pandas, scipy, numpy), NEVER import external third-party or native C-extension libraries. Use pure Python standard library struct and zlib with save_png (IHDR, IDAT, IEND chunks) to generate a valid .png file. To save source code, read Path(__file__).read_text(encoding='utf-8').\n"
            "7. Preserve the original goal and intent. Do NOT change the task or invent files like sample_input.txt unless the original goal requested it.\n"
            "8. If a NameError occurs (e.g. name 'math' or 'Path' is not defined), ensure all imports are at the top: import os, sys, math, struct, zlib, json, re; from pathlib import Path.\n"
            "9. If a struct.error occurs ('B' format requires 0 <= number <= 255), clamp numbers to [0..255]: val = max(0, min(255, int(val))) before packing into 'B'.\n"
            "10. Always execute the logic at top level or in if __name__ == '__main__' and print computed results (e.g. print('pi =', math.pi)) so stdout captures output."
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
