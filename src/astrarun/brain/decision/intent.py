"""Semantic Intent Classification Engine for AstraRun Brain."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from astrarun.brain.models import BrainDecision, BrainIntent
from astrarun.core.logging import get_logger
from astrarun.routing.laya import LayaRouter, LayaDecision

logger = get_logger("astrarun.brain.decision.intent")


class IntentClassifier:
    """
    Cognitive intent classification engine for AstraRun Brain.
    Determines whether user input is a direct action, composite multi-step goal,
    question, conversational greeting, or clarification request.
    """

    def __init__(self, laya_router: Optional[LayaRouter] = None) -> None:
        self.laya = laya_router

    def classify(self, text: str, context: Optional[Dict[str, Any]] = None) -> BrainDecision:
        clean = text.strip()
        lower = clean.lower()

        # 1. Conversational / greetings
        from astrarun.routing.input_router import classify_launcher_input, InputIntent, get_conversational_response
        input_intent = classify_launcher_input(clean)
        if input_intent == InputIntent.NATURAL_LANGUAGE:
            resp = get_conversational_response(clean)
            return BrainDecision(
                intent=BrainIntent.CONVERSATIONAL,
                confidence=1.0,
                reason="conversational_greeting",
                parameters={"response": resp, "raw_prompt": clean},
                routing_tier="DETERMINISTIC_GREETING",
            )

        # 2. Security Rejection Guard
        destructive_patterns = (
            "format c:", "format drive", "delete system32", "rm -rf /",
            "drop database", "download malware", "wipe disk", "wipe drive",
            "shred disk", "destroy system", "delete c:\\windows", "erase hard drive"
        )
        if any(w in lower for w in destructive_patterns):
            return BrainDecision(
                intent=BrainIntent.SECURITY_REJECTION,
                confidence=1.0,
                reason="Destructive system operation rejected by policy.",
                parameters={"raw_prompt": clean},
                routing_tier="SECURITY_REJECTION",
            )

        # 3. Questions / Inquiries
        if input_intent == InputIntent.QUESTION or lower.startswith(("what ", "how ", "why ", "where ", "who ", "which ", "tell me ")):
            return BrainDecision(
                intent=BrainIntent.QUESTION,
                confidence=0.90,
                reason="user_inquiry",
                parameters={"query": clean, "raw_prompt": clean},
                routing_tier="QUESTION_ROUTING",
            )

        # 4. Composite Goal Check
        has_compound = any(w in lower for w in (" and ", " then ", ";", ", then ", ", and "))
        if has_compound or input_intent == InputIntent.GOAL:
            return BrainDecision(
                intent=BrainIntent.COMPOSITE_GOAL,
                confidence=0.88,
                reason="compound_multi_step_goal",
                parameters={"raw_prompt": clean},
                routing_tier="AGENT_PLANNER",
            )

        # 5. Direct Action via Laya or deterministic resolution
        if self.laya:
            try:
                laya_res: LayaDecision = self.laya.decide(clean)
                if laya_res.is_resolved and laya_res.confidence >= 0.60:
                    return BrainDecision(
                        intent=BrainIntent.DIRECT_ACTION,
                        primary_capability=laya_res.intent,
                        confidence=laya_res.confidence,
                        reason="laya_semantic_intent",
                        parameters={"raw_prompt": clean, "laya_intent": laya_res.intent},
                        routing_tier="LAYA_SEMANTIC",
                    )
            except Exception as e:
                logger.debug("Laya decision failed: %s", e)

        return BrainDecision(
            intent=BrainIntent.DIRECT_ACTION,
            confidence=0.70,
            reason="default_direct_action",
            parameters={"raw_prompt": clean},
            routing_tier="HEURISTIC",
        )
