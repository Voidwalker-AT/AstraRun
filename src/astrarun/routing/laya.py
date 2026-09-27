"""Laya shadow router adapter for AstraRun v0.3.

Provides isolated, non-autoregressive semantic decision-making without granting
production execution authority.
"""

from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from astrarun.core.logging import get_logger
from astrarun.core.models import Decision, RoutingContext
from astrarun.routing.base import BaseRouter

logger = get_logger("astrarun.routing.laya")

# Standard intent taxonomy defined in docs/INTENT_TAXONOMY.md
INTENT_CRITERIA = {
    "open_app": "Launch an installed desktop application",
    "open_folder": "Open a local folder in File Explorer",
    "open_url": "Navigate to a website URL",
    "open_project": "Open a software development workspace or project",
    "find_file": "Search for or open an individual document or file",
    "process_action": "Manage, restart, or kill running processes or ports",
    "system_action": "System, hardware, volume, or power actions",
    "ai_query": "Ask a conversational AI or coding question",
    "browser_action": "Search the web or perform in-browser actions",
    "unknown": "Ambiguous, unsupported, or unsafe request"
}

# Only these intents have live execution tools in AstraRun v0.3
EXECUTABLE_INTENTS = {"open_app", "open_folder", "open_url"}


@dataclass
class LayaDecision:
    """Rich semantic decision output produced by Laya."""
    intent: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    is_executable_now: bool = False
    requires_resolution: bool = False
    latency_ms: float = 0.0
    raw_result: dict[str, Any] = field(default_factory=dict)
    source: str = "laya"
    error: str | None = None

    @property
    def is_resolved(self) -> bool:
        return self.intent != "unknown" and self.error is None


class LayaRouter(BaseRouter):
    """
    Adapter integrating the Laya decision engine behind AstraRun's BaseRouter interface.
    
    Operates in shadow mode by default. Never executes tools directly.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.enabled = bool(self.config.get("enabled", True))
        self.mode = str(self.config.get("mode", "shadow")).lower()
        self.model_id = str(self.config.get("model", "convaiinnovations/laya"))
        self.device = str(self.config.get("device", "auto")).lower()
        self.confidence_threshold = float(self.config.get("confidence_threshold", 0.75))
        self.timeout_ms = float(self.config.get("timeout_ms", 3000.0))
        
        # Ensure canonical HF cache location per Platform Rule 9
        os.environ.setdefault("HF_HOME", "E:/AI_Models/HF_CACHE")
        
        self._agent = None
        self._load_lock = threading.Lock()
        self._load_failed = False
        self._load_error_msg = None

    def _resolve_device(self) -> str:
        if self.device in ("cpu", "cuda"):
            return self.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def get_agent(self) -> Any:
        """Thread-safe lazy loader for the underlying Laya agent."""
        if not self.enabled:
            return None
        if self._load_failed:
            return None
        if self._agent is not None:
            return self._agent

        with self._load_lock:
            if self._agent is not None:
                return self._agent
            if self._load_failed:
                return None

            try:
                import laya
                target_device = self._resolve_device()
                logger.info(
                    "Loading Laya model '%s' on device '%s'...",
                    self.model_id, target_device
                )
                t0 = time.perf_counter()
                self._agent = laya.load(
                    model_id_or_path=self.model_id,
                    device=target_device
                )
                load_sec = time.perf_counter() - t0
                logger.info("Laya model successfully loaded in %.2fs", load_sec)
                return self._agent
            except ImportError as err:
                self._load_failed = True
                self._load_error_msg = f"Laya package not installed: {err}"
                logger.warning(self._load_error_msg)
                return None
            except Exception as err:
                self._load_failed = True
                self._load_error_msg = f"Failed to load Laya model: {err}"
                logger.error(self._load_error_msg, exc_info=True)
                return None

    def predict_intent(self, request: str) -> LayaDecision:
        """
        Evaluate user request against the 10-class intent taxonomy.
        
        Returns structured LayaDecision preserving full calibrated probability distribution.
        """
        clean_req = request.strip()
        if not clean_req:
            return LayaDecision(
                intent="unknown",
                confidence=0.0,
                probabilities={},
                is_executable_now=False,
                requires_resolution=False,
                error="Empty request"
            )

        agent = self.get_agent()
        if agent is None:
            return LayaDecision(
                intent="unknown",
                confidence=0.0,
                probabilities={},
                is_executable_now=False,
                requires_resolution=False,
                error=self._load_error_msg or "Laya router disabled or unavailable"
            )

        questions = {
            "intent": {
                "type": "choice",
                "instructions": "Which action does the user intend?",
                "criteria": INTENT_CRITERIA
            }
        }

        t0 = time.perf_counter()
        try:
            raw_output = agent.predict(clean_req, questions)
            latency_ms = (time.perf_counter() - t0) * 1000.0
            
            answers = raw_output.get("answers", {})
            intent_answer = answers.get("intent", {})
            chosen_intent = intent_answer.get("choice", "unknown")
            probs = intent_answer.get("probabilities", {})
            confidence = float(intent_answer.get("confidence", probs.get(chosen_intent, 0.0)))

            is_exec = chosen_intent in EXECUTABLE_INTENTS and confidence >= self.confidence_threshold
            requires_res = chosen_intent in ("open_project", "find_file") or chosen_intent in EXECUTABLE_INTENTS

            return LayaDecision(
                intent=chosen_intent,
                confidence=confidence,
                probabilities={str(k): float(v) for k, v in probs.items()},
                is_executable_now=is_exec,
                requires_resolution=requires_res,
                latency_ms=latency_ms,
                raw_result=raw_output,
                source="laya"
            )
        except Exception as err:
            latency_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("Laya inference error on '%s': %s", clean_req, err, exc_info=True)
            return LayaDecision(
                intent="unknown",
                confidence=0.0,
                probabilities={},
                is_executable_now=False,
                requires_resolution=False,
                latency_ms=latency_ms,
                error=str(err),
                source="laya"
            )

    def predict_intent_batch(
        self,
        requests: list[str],
        batch_size: int = 16,
        questions: dict[str, Any] | None = None,
    ) -> list[LayaDecision]:
        """
        Evaluate batch of requests with high throughput vectorized inference.
        """
        clean_requests = [r.strip() for r in requests]
        agent = self.get_agent()
        if agent is None:
            err = self._load_error_msg or "Laya router disabled or unavailable"
            return [
                LayaDecision(
                    intent="unknown",
                    confidence=0.0,
                    error=err,
                )
                for _ in clean_requests
            ]

        q_spec = questions or {
            "intent": {
                "type": "choice",
                "instructions": "Which action does the user intend?",
                "criteria": INTENT_CRITERIA,
            }
        }

        t0 = time.perf_counter()
        try:
            results = agent.predict_batch(clean_requests, q_spec, batch_size=batch_size)
            total_lat = (time.perf_counter() - t0) * 1000.0
            per_query_lat = total_lat / max(1, len(clean_requests))

            decisions = []
            for clean_req, raw_output in zip(clean_requests, results):
                if not clean_req:
                    decisions.append(
                        LayaDecision(intent="unknown", confidence=0.0, error="Empty request", latency_ms=per_query_lat)
                    )
                    continue

                answers = raw_output.get("answers", {})
                intent_answer = answers.get("intent", {})
                chosen_intent = intent_answer.get("choice", "unknown")
                probs = intent_answer.get("probabilities", {})
                confidence = float(intent_answer.get("confidence", probs.get(chosen_intent, 0.0)))

                is_exec = chosen_intent in EXECUTABLE_INTENTS and confidence >= self.confidence_threshold
                requires_res = chosen_intent in ("open_project", "find_file") or chosen_intent in EXECUTABLE_INTENTS

                decisions.append(
                    LayaDecision(
                        intent=chosen_intent,
                        confidence=confidence,
                        probabilities={str(k): float(v) for k, v in probs.items()},
                        is_executable_now=is_exec,
                        requires_resolution=requires_res,
                        latency_ms=per_query_lat,
                        raw_result=raw_output,
                        source="laya",
                    )
                )
            return decisions
        except Exception as err:
            logger.error("Laya predict_batch error: %s", err, exc_info=True)
            return [
                LayaDecision(
                    intent="unknown",
                    confidence=0.0,
                    error=str(err),
                )
                for _ in clean_requests
            ]

    def route(self, request: str, context: RoutingContext) -> Decision:
        """
        Conform to the BaseRouter contract.
        
        Maps LayaDecision into AstraRun Decision.
        In shadow mode, this decision is logged but NOT executed.
        """
        laya_dec = self.predict_intent(request)
        
        if not laya_dec.is_resolved:
            return Decision(
                tool="unknown",
                args={},
                confidence=laya_dec.confidence,
                source="laya",
                explanation=f"Laya unresolved: {laya_dec.error or 'unknown intent'}"
            )

        intent = laya_dec.intent
        # Extract target argument if possible
        clean_target = re.sub(r"^(?:open|launch|start|run|show|go to|browse)\s+", "", request.strip(), flags=re.I).strip()
        
        if intent == "open_app":
            return Decision(
                tool="open_app",
                args={"app": clean_target},
                confidence=laya_dec.confidence,
                source="laya",
                explanation=f"Laya classified intent as open_app (confidence: {laya_dec.confidence:.2f})"
            )
        elif intent == "open_folder":
            return Decision(
                tool="open_folder",
                args={"folder": clean_target},
                confidence=laya_dec.confidence,
                source="laya",
                explanation=f"Laya classified intent as open_folder (confidence: {laya_dec.confidence:.2f})"
            )
        elif intent == "open_url":
            return Decision(
                tool="open_url",
                args={"url": clean_target},
                confidence=laya_dec.confidence,
                source="laya",
                explanation=f"Laya classified intent as open_url (confidence: {laya_dec.confidence:.2f})"
            )
        else:
            # Future / unexecutable intents
            return Decision(
                tool="unknown",
                args={"intent": intent, "target": clean_target},
                confidence=laya_dec.confidence,
                source="laya",
                explanation=f"Laya classified intent as future/non-executable '{intent}' (confidence: {laya_dec.confidence:.2f})"
            )
