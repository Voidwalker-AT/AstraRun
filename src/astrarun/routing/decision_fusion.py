"""Decision Fusion Engine for AstraRun v0.10.3.

Arbitrates between Tier 0 deterministic fast-path, Laya A pre-gate, Neural NLP IR,
and Laya B verifier to synthesize a verified, policy-safe execution plan.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from astrarun.core.logging import get_logger
from astrarun.core.models import Decision, RoutingContext
from astrarun.nlp.ir import ParsedClause, ParsedRequest
from astrarun.routing.laya_sandwich import LayaPreGateResult, LayaVerifierResult

logger = get_logger("astrarun.routing.decision_fusion")


@dataclass
class FusedExecutionPlan:
    """The synthesized, arbitrated execution plan produced by DecisionFusionEngine."""
    action_type: str            # "fast_path", "workflow", "clarify", "rejected", "single_intent"
    confidence: float
    decision: Optional[Decision] = None
    parsed_request: Optional[ParsedRequest] = None
    executable_clauses: list[ParsedClause] = field(default_factory=list)
    rejection_reason: Optional[str] = None
    clarification_prompt: Optional[str] = None
    source: str = "decision_fusion"
    entropy: float = 0.0


def compute_shannon_entropy(probabilities: dict[str, float]) -> float:
    """Compute Shannon entropy across a probability distribution."""
    if not probabilities:
        return 0.0
    total = sum(probabilities.values())
    if total <= 0:
        return 0.0
    entropy = 0.0
    for p in probabilities.values():
        if p > 0:
            norm_p = p / total
            entropy -= norm_p * math.log2(norm_p)
    return entropy


class DecisionFusionEngine:
    """
    Arbitrates multi-tier decision outputs.
    
    Ensures fast commands execute at < 15ms while complex, compound, or ambiguous
    commands receive full neural parsing, verification, and safety arbitration.
    """

    def __init__(self, entropy_threshold: float = 1.25) -> None:
        self.entropy_threshold = entropy_threshold

    def fuse(
        self,
        query: str,
        fast_path_decision: Optional[Decision],
        pre_gate: LayaPreGateResult,
        parsed_request: ParsedRequest,
        verifier: LayaVerifierResult,
    ) -> FusedExecutionPlan:
        """Arbitrate across all decision sources and synthesize final execution plan."""
        # 1. Check for explicit verifier rejection
        if not verifier.is_consistent or not verifier.negation_respected:
            logger.warning(
                "Laya B verifier rejected execution: reason='%s'",
                verifier.rejection_reason
            )
            return FusedExecutionPlan(
                action_type="rejected",
                confidence=verifier.confidence,
                rejection_reason=verifier.rejection_reason or "Plan failed semantic safety verification.",
                parsed_request=parsed_request,
                source="laya_b_verifier"
            )

        # 2. Check for Ambiguity / Clarification Required
        if pre_gate.ambiguity in ("ambiguous", "incomplete") or parsed_request.ambiguity_score > 0.45:
            logger.info("Decision fusion triggered clarification: ambiguity='%s'", pre_gate.ambiguity)
            return FusedExecutionPlan(
                action_type="clarify",
                confidence=0.5,
                clarification_prompt="Could you please clarify your request?",
                parsed_request=parsed_request,
                source="decision_fusion_ambiguity"
            )

        # 3. Tier 0 Fast-Path Preservation
        # If deterministic router produced a high-confidence single action and query is not compound:
        if (
            fast_path_decision is not None
            and fast_path_decision.is_resolved
            and not parsed_request.is_compound
            and not pre_gate.is_compound
            and not parsed_request.has_negation
        ):
            logger.debug("Decision fusion selected Tier 0 Fast-Path for '%s'", query)
            return FusedExecutionPlan(
                action_type="fast_path",
                confidence=fast_path_decision.confidence,
                decision=fast_path_decision,
                executable_clauses=parsed_request.executable_clauses,
                source="tier_0_fast_path"
            )

        # 4. Multi-Action / Compound Workflow Execution
        executable_clauses = parsed_request.executable_clauses
        if parsed_request.is_compound or len(executable_clauses) > 1:
            logger.info(
                "Decision fusion approved compound workflow: %d executable clause(s)",
                len(executable_clauses)
            )
            return FusedExecutionPlan(
                action_type="workflow",
                confidence=min(parsed_request.confidence, verifier.confidence),
                parsed_request=parsed_request,
                executable_clauses=executable_clauses,
                source="neural_nlp_workflow"
            )

        # 5. Single Affirmative Clause from Neural NLP
        if len(executable_clauses) == 1:
            first_clause = executable_clauses[0]
            logger.debug("Decision fusion resolved single affirmative clause: %s", first_clause.intent)
            return FusedExecutionPlan(
                action_type="single_intent",
                confidence=parsed_request.confidence,
                parsed_request=parsed_request,
                executable_clauses=[first_clause],
                source="neural_nlp_single"
            )

        # 6. Fallback / Unresolved
        return FusedExecutionPlan(
            action_type="clarify",
            confidence=0.0,
            clarification_prompt="I couldn't identify an executable action.",
            parsed_request=parsed_request,
            source="decision_fusion_fallback"
        )
