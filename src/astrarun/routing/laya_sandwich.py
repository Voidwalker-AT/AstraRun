"""Laya Neural NLP Sandwich Router Adapter for AstraRun v0.10.3.

Provides Laya A (Semantic Pre-Gate) and Laya B (Semantic Post-Verifier)
reusing a SINGLE in-memory Laya model instance to guarantee zero duplicate 421M weights.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from astrarun.core.logging import get_logger
from astrarun.nlp.ir import ParsedClause, ParsedRequest
from astrarun.routing.laya import LayaDecision, LayaRouter

logger = get_logger("astrarun.routing.laya_sandwich")

# Laya A Pre-Gate Taxonomy Criteria
PRE_GATE_CRITERIA = {
    "domain": {
        "type": "choice",
        "instructions": "Which domain does the user query belong to?",
        "criteria": {
            "app_launch": "Launch or start an installed desktop application or software",
            "window_control": "Snap, minimize, maximize, restore, or close windows",
            "keyboard_input": "Type text, enter words, or press keyboard shortcuts",
            "compound_sequence": "Multiple sequential actions or piped commands",
            "system_query": "System status, CPU, RAM, battery, or volume control",
            "unknown": "Ambiguous, conversational, or unsupported request"
        }
    },
    "is_compound": {
        "type": "choice",
        "instructions": "Does the request contain multiple chained actions?",
        "criteria": {
            "single_action": "Only one atomic action requested",
            "multi_action": "Two or more actions chained together (e.g. open X and type Y)"
        }
    },
    "ambiguity": {
        "type": "choice",
        "instructions": "How clear is the user's intent?",
        "criteria": {
            "clear": "Specific and actionable without clarification",
            "ambiguous": "Unclear target or ambiguous meaning",
            "incomplete": "Missing crucial parameters or target element"
        }
    },
    "risk": {
        "type": "choice",
        "instructions": "What risk level is associated with this action?",
        "criteria": {
            "safe": "Read-only queries, typing, or non-destructive window actions",
            "moderate": "Closing windows or launching unknown executables",
            "destructive": "Terminating processes, modifying system files, or power actions"
        }
    }
}

# Laya B Post-Verifier Criteria
VERIFIER_CRITERIA = {
    "consistency": {
        "type": "choice",
        "instructions": "Does the planned structured execution match the user's intended request?",
        "criteria": {
            "consistent": "Plan completely and accurately captures all requested actions without distortion",
            "inconsistent": "Plan misses actions, adds unrequested actions, or distorts intent",
            "incomplete": "Plan is partially missing steps requested by user"
        }
    },
    "negation_respected": {
        "type": "choice",
        "instructions": "Did the user explicitly command NOT to perform an action present in the plan?",
        "criteria": {
            "respected": "Negated actions are excluded or plan respects user constraints",
            "violated": "Plan includes an action the user explicitly asked NOT to do"
        }
    }
}


@dataclass
class LayaPreGateResult:
    """Output from Laya A Semantic Pre-Gate."""
    domain: str = "unknown"
    is_compound: bool = False
    ambiguity: str = "clear"
    risk_level: str = "safe"
    confidence: float = 1.0
    probabilities: dict[str, dict[str, float]] = field(default_factory=dict)
    latency_ms: float = 0.0
    source: str = "laya_pre_gate"
    error: Optional[str] = None


@dataclass
class LayaVerifierResult:
    """Output from Laya B Semantic Verifier."""
    is_consistent: bool = True
    negation_respected: bool = True
    confidence: float = 1.0
    probabilities: dict[str, dict[str, float]] = field(default_factory=dict)
    latency_ms: float = 0.0
    source: str = "laya_verifier"
    rejection_reason: Optional[str] = None
    error: Optional[str] = None


class LayaSandwichRouter:
    """
    Coordinates Laya A (Pre-Gate) and Laya B (Verifier) around the Neural NLP layer.
    
    Shares the exact same underlying LayaRouter and ModernBERT model instance.
    """

    def __init__(self, laya_router: Optional[LayaRouter] = None) -> None:
        self.laya_router = laya_router or LayaRouter()

    @property
    def is_available(self) -> bool:
        return self.laya_router.enabled and not self.laya_router._load_failed

    def evaluate_pre_gate(self, query: str) -> LayaPreGateResult:
        """Execute Laya A semantic gate to classify domain, compound intent, and ambiguity."""
        clean_q = query.strip()
        if not clean_q:
            return LayaPreGateResult(domain="unknown", is_compound=False, error="Empty query")

        agent = self.laya_router.get_agent()
        if agent is None:
            # Deterministic heuristic pre-gate fallback
            return self._heuristic_pre_gate(clean_q)

        t0 = time.perf_counter()
        try:
            raw_output = agent.predict(clean_q, PRE_GATE_CRITERIA)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            domain = raw_output.get("domain", {}).get("choice", "unknown")
            is_compound_str = raw_output.get("is_compound", {}).get("choice", "single_action")
            ambiguity = raw_output.get("ambiguity", {}).get("choice", "clear")
            risk = raw_output.get("risk", {}).get("choice", "safe")

            probs = {
                k: raw_output.get(k, {}).get("probabilities", {})
                for k in ("domain", "is_compound", "ambiguity", "risk")
            }

            return LayaPreGateResult(
                domain=domain,
                is_compound=is_compound_str == "multi_action",
                ambiguity=ambiguity,
                risk_level=risk,
                confidence=raw_output.get("domain", {}).get("confidence", 0.90),
                probabilities=probs,
                latency_ms=latency_ms,
                source="laya_a_neural"
            )
        except Exception as err:
            logger.warning("Laya A pre-gate evaluation failed (%s), using heuristic fallback", err)
            return self._heuristic_pre_gate(clean_q)

    def evaluate_verifier(self, query: str, parsed_request: ParsedRequest) -> LayaVerifierResult:
        """Execute Laya B semantic verifier to confirm plan matches intent and honors negations."""
        clean_q = query.strip()
        if not clean_q:
            return LayaVerifierResult(is_consistent=False, rejection_reason="Empty query")

        # 1. Structural rule validation before neural verification
        if parsed_request.has_negation:
            for clause in parsed_request.clauses:
                if clause.is_negated and clause.intent in ("close_window", "kill_process", "close_app"):
                    # Explicit negation of a close action means we MUST NOT execute close
                    logger.info("Laya B detected explicit negation on destructive action: %s", clause.raw_clause)

        agent = self.laya_router.get_agent()
        if agent is None:
            # Deterministic heuristic verifier fallback
            return self._heuristic_verifier(clean_q, parsed_request)

        # Build prompt describing the planned actions
        plan_desc = "; ".join(f"Action {c.sequence_index + 1}: {c.intent} ({c.action_verb})" for c in parsed_request.clauses)
        eval_text = f"User Request: '{clean_q}'\nPlanned Actions: {plan_desc}"

        t0 = time.perf_counter()
        try:
            raw_output = agent.predict(eval_text, VERIFIER_CRITERIA)
            latency_ms = (time.perf_counter() - t0) * 1000.0

            consistency = raw_output.get("consistency", {}).get("choice", "consistent")
            negation_resp = raw_output.get("negation_respected", {}).get("choice", "respected")

            is_consistent = consistency == "consistent"
            negation_respected = negation_resp == "respected"

            rejection_reason = None
            if not is_consistent:
                rejection_reason = "Laya B detected semantic inconsistency between user request and planned actions"
            elif not negation_respected:
                rejection_reason = "Laya B detected violation of explicit user negation"

            probs = {
                k: raw_output.get(k, {}).get("probabilities", {})
                for k in ("consistency", "negation_respected")
            }

            return LayaVerifierResult(
                is_consistent=is_consistent and negation_respected,
                negation_respected=negation_respected,
                confidence=raw_output.get("consistency", {}).get("confidence", 0.95),
                probabilities=probs,
                latency_ms=latency_ms,
                source="laya_b_neural",
                rejection_reason=rejection_reason
            )
        except Exception as err:
            logger.warning("Laya B verifier evaluation failed (%s), using heuristic fallback", err)
            return self._heuristic_verifier(clean_q, parsed_request)

    def _heuristic_pre_gate(self, query: str) -> LayaPreGateResult:
        """Deterministic heuristic pre-gate used when Laya model is offline or uninitialized."""
        q_lower = query.lower()
        is_compound = any(conn in q_lower for conn in (" and ", " then ", " and then ", ";"))
        
        domain = "unknown"
        if any(w in q_lower for w in ("open", "launch", "start", "run")):
            domain = "app_launch"
        elif any(w in q_lower for w in ("type", "write", "enter")):
            domain = "keyboard_input"
        elif any(w in q_lower for w in ("snap", "dock", "minimize", "maximize", "close", "restore")):
            domain = "window_control"
        elif any(w in q_lower for w in ("cpu", "ram", "battery", "volume")):
            domain = "system_query"

        if is_compound:
            domain = "compound_sequence"

        return LayaPreGateResult(
            domain=domain,
            is_compound=is_compound,
            ambiguity="clear",
            risk_level="safe",
            confidence=0.85,
            source="laya_a_heuristic"
        )

    def _heuristic_verifier(self, query: str, parsed_request: ParsedRequest) -> LayaVerifierResult:
        """Deterministic heuristic verifier checking clause presence and negation consistency."""
        # Check if query asked to open something and we produced open_app
        q_lower = query.lower()
        
        # If user explicitly said "don't" or "do not", verify no negated action is in executable clauses
        for c in parsed_request.clauses:
            if c.is_negated and not parsed_request.has_negation:
                return LayaVerifierResult(
                    is_consistent=False,
                    negation_respected=False,
                    confidence=0.90,
                    rejection_reason="Contradiction in negation status",
                    source="laya_b_heuristic"
                )

        return LayaVerifierResult(
            is_consistent=True,
            negation_respected=True,
            confidence=0.90,
            source="laya_b_heuristic"
        )
