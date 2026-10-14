"""Decision Fusion Engine for AstraRun v0.5.

Combines multiple complementary Laya decisions (Generic Laya, Fine-Tuned Laya,
and optionally external reference judges) into calibrated, gated ensemble decisions.

Includes disagreement metrics (agreement rate, Jensen-Shannon divergence, entropy),
ambiguity gating, and consequence risk gating.

ZERO PRODUCTION EXECUTION AUTHORITY: This engine operates strictly in shadow
and benchmarking modes. Production execution authority remains 100% deterministic/fuzzy.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.routing.laya import LayaDecision, LayaRouter, INTENT_CRITERIA

logger = get_logger("astrarun.routing.fusion")


@dataclass
class FusedDecision:
    """Rich semantic decision output produced by DecisionFusionEngine."""
    intent: str
    confidence: float
    probabilities: dict[str, float] = field(default_factory=dict)
    agreement: bool = True
    js_divergence: float = 0.0
    entropy: float = 0.0
    ambiguity_verdict: str = "safe_to_resolve"
    risk_verdict: str = "LOW"
    ensemble_mode: str = "E0"
    abstain: bool = False
    abstain_reason: str | None = None
    source_decisions: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0

    @property
    def is_executable_candidate(self) -> bool:
        """Indicates if the candidate would be safe to resolve if given authority."""
        return (
            not self.abstain
            and self.intent not in ("unknown", "")
            and self.ambiguity_verdict == "safe_to_resolve"
            and self.risk_verdict != "BLOCKED"
        )


def shannon_entropy(probs: dict[str, float]) -> float:
    """Compute Shannon entropy H(P) in bits for a discrete distribution."""
    h = 0.0
    for p in probs.values():
        if p > 1e-9:
            h -= p * math.log2(p)
    return max(0.0, round(h, 4))


def jensen_shannon_divergence(
    p_dist: dict[str, float],
    q_dist: dict[str, float],
    all_keys: Optional[list[str]] = None,
) -> float:
    """
    Compute Jensen-Shannon Divergence JSD(P || Q) in [0, 1] using base 2 log.
    
    JSD(P || Q) = 0.5 * KL(P || M) + 0.5 * KL(Q || M), where M = 0.5 * (P + Q).
    """
    if all_keys is None:
        keys = set(p_dist.keys()) | set(q_dist.keys())
    else:
        keys = set(all_keys)

    # Normalize vectors over the full union of keys
    sum_p = sum(p_dist.get(k, 0.0) for k in keys) or 1.0
    sum_q = sum(q_dist.get(k, 0.0) for k in keys) or 1.0

    kl_p_m = 0.0
    kl_q_m = 0.0

    for k in keys:
        p_val = max(1e-12, p_dist.get(k, 0.0) / sum_p)
        q_val = max(1e-12, q_dist.get(k, 0.0) / sum_q)
        m_val = 0.5 * (p_val + q_val)

        kl_p_m += p_val * math.log2(p_val / m_val)
        kl_q_m += q_val * math.log2(q_val / m_val)

    jsd = 0.5 * kl_p_m + 0.5 * kl_q_m
    return max(0.0, min(1.0, round(jsd, 4)))


class DecisionFusionEngine:
    """
    Orchestrates ensemble decision making and gating across Generic and Fine-Tuned Laya.
    
    Ensemble Configurations:
      - E0: Generic Laya Baseline (zero-shot)
      - E1: Fine-Tuned Laya Baseline (domain-adapted)
      - E2: Equal Weight Blend (50/50 probability mixture)
      - E3: Confidence-Weighted Blend (probabilities weighted by model confidence)
      - E4: Disagreement-Gated Fusion (abstain if top choice differs or JSD > threshold)
      - E5: Full Ambiguity + Risk Gated Fusion (multi-question validation with safety gating)
    """

    def __init__(
        self,
        generic_router: Optional[LayaRouter] = None,
        finetuned_router: Optional[LayaRouter] = None,
        default_mode: str = "E5",
        js_threshold: float = 0.25,
        confidence_threshold: float = 0.70,
    ) -> None:
        from astrarun.core.paths import resolve_model_path
        self.generic_router = generic_router or LayaRouter({"model": "convaiinnovations/laya"})
        self.finetuned_router = finetuned_router or LayaRouter({"model": str(resolve_model_path("AstraRun-Laya", dev_fallback=os.environ.get("ASTRARUN_LAYA_MODEL_PATH")))})
        self.default_mode = default_mode.upper()
        self.js_threshold = js_threshold
        self.confidence_threshold = confidence_threshold

    def fuse(
        self,
        request: str,
        mode: Optional[str] = None,
        generic_decision: Optional[LayaDecision] = None,
        ft_decision: Optional[LayaDecision] = None,
        aux_data: Optional[dict[str, Any]] = None,
    ) -> FusedDecision:
        """
        Produce a fused decision for the given user request.
        
        Optional precomputed decisions can be passed to avoid duplicate inference.
        """
        mode = (mode or self.default_mode).upper()
        t0 = time.perf_counter()

        # Gather model predictions if not precomputed
        gen_dec = generic_decision
        if gen_dec is None and mode in ("E0", "E2", "E3", "E4", "E5"):
            gen_dec = self.generic_router.predict_intent(request)

        ft_dec = ft_decision
        if ft_dec is None and mode in ("E1", "E2", "E3", "E4", "E5"):
            ft_dec = self.finetuned_router.predict_intent(request)

        # Mode E0: Generic Laya Baseline
        if mode == "E0":
            lat = (time.perf_counter() - t0) * 1000.0
            assert gen_dec is not None
            return FusedDecision(
                intent=gen_dec.intent,
                confidence=gen_dec.confidence,
                probabilities=gen_dec.probabilities,
                agreement=True,
                js_divergence=0.0,
                entropy=shannon_entropy(gen_dec.probabilities),
                ensemble_mode="E0",
                abstain=(gen_dec.intent == "unknown"),
                abstain_reason="Baseline unknown" if gen_dec.intent == "unknown" else None,
                source_decisions={"generic": gen_dec},
                latency_ms=lat,
            )

        # Mode E1: Fine-Tuned Laya Baseline
        if mode == "E1":
            lat = (time.perf_counter() - t0) * 1000.0
            assert ft_dec is not None
            return FusedDecision(
                intent=ft_dec.intent,
                confidence=ft_dec.confidence,
                probabilities=ft_dec.probabilities,
                agreement=True,
                js_divergence=0.0,
                entropy=shannon_entropy(ft_dec.probabilities),
                ensemble_mode="E1",
                abstain=(ft_dec.intent == "unknown"),
                abstain_reason="Baseline unknown" if ft_dec.intent == "unknown" else None,
                source_decisions={"finetuned": ft_dec},
                latency_ms=lat,
            )

        assert gen_dec is not None and ft_dec is not None

        # Calculate disagreement metrics
        all_keys = list(INTENT_CRITERIA.keys())
        p_gen = gen_dec.probabilities or {gen_dec.intent: gen_dec.confidence}
        p_ft = ft_dec.probabilities or {ft_dec.intent: ft_dec.confidence}

        agreement = (gen_dec.intent == ft_dec.intent)
        jsd = jensen_shannon_divergence(p_gen, p_ft, all_keys)

        # Mode E2: Equal Weight Blend
        if mode == "E2":
            fused_probs = {}
            for k in all_keys:
                fused_probs[k] = round(0.5 * p_gen.get(k, 0.0) + 0.5 * p_ft.get(k, 0.0), 4)
            top_intent = max(fused_probs.items(), key=lambda x: x[1])[0]
            conf = fused_probs[top_intent]
            lat = (time.perf_counter() - t0) * 1000.0

            return FusedDecision(
                intent=top_intent,
                confidence=conf,
                probabilities=fused_probs,
                agreement=agreement,
                js_divergence=jsd,
                entropy=shannon_entropy(fused_probs),
                ensemble_mode="E2",
                abstain=(top_intent == "unknown"),
                source_decisions={"generic": gen_dec, "finetuned": ft_dec},
                latency_ms=lat,
            )

        # Mode E3: Confidence-Weighted Blend
        if mode == "E3":
            c_gen = max(0.01, gen_dec.confidence)
            c_ft = max(0.01, ft_dec.confidence)
            w_gen = c_gen / (c_gen + c_ft)
            w_ft = c_ft / (c_gen + c_ft)

            fused_probs = {}
            for k in all_keys:
                fused_probs[k] = round(w_gen * p_gen.get(k, 0.0) + w_ft * p_ft.get(k, 0.0), 4)
            top_intent = max(fused_probs.items(), key=lambda x: x[1])[0]
            conf = fused_probs[top_intent]
            lat = (time.perf_counter() - t0) * 1000.0

            return FusedDecision(
                intent=top_intent,
                confidence=conf,
                probabilities=fused_probs,
                agreement=agreement,
                js_divergence=jsd,
                entropy=shannon_entropy(fused_probs),
                ensemble_mode="E3",
                abstain=(top_intent == "unknown"),
                source_decisions={"generic": gen_dec, "finetuned": ft_dec},
                latency_ms=lat,
            )

        # Mode E4: Disagreement-Gated Fusion
        if mode == "E4":
            # If models disagree on top intent or JS divergence exceeds threshold -> ABSTAIN
            disagree = not agreement or (jsd > self.js_threshold)
            c_gen = max(0.01, gen_dec.confidence)
            c_ft = max(0.01, ft_dec.confidence)
            w_gen = c_gen / (c_gen + c_ft)
            w_ft = c_ft / (c_gen + c_ft)

            fused_probs = {}
            for k in all_keys:
                fused_probs[k] = round(w_gen * p_gen.get(k, 0.0) + w_ft * p_ft.get(k, 0.0), 4)

            lat = (time.perf_counter() - t0) * 1000.0

            if disagree:
                return FusedDecision(
                    intent="unknown",
                    confidence=0.0,
                    probabilities=fused_probs,
                    agreement=agreement,
                    js_divergence=jsd,
                    entropy=shannon_entropy(fused_probs),
                    ensemble_mode="E4",
                    abstain=True,
                    abstain_reason=f"Model disagreement (agreement={agreement}, JSD={jsd:.3f} > {self.js_threshold})",
                    source_decisions={"generic": gen_dec, "finetuned": ft_dec},
                    latency_ms=lat,
                )

            top_intent = ft_dec.intent
            conf = fused_probs.get(top_intent, ft_dec.confidence)
            return FusedDecision(
                intent=top_intent,
                confidence=conf,
                probabilities=fused_probs,
                agreement=agreement,
                js_divergence=jsd,
                entropy=shannon_entropy(fused_probs),
                ensemble_mode="E4",
                abstain=(top_intent == "unknown"),
                source_decisions={"generic": gen_dec, "finetuned": ft_dec},
                latency_ms=lat,
            )

        # Mode E5: Full Ambiguity + Risk Gated Fusion
        # Extract ambiguity and risk from auxiliary data or fine-tuned raw result
        raw_res = ft_dec.raw_result.get("answers", {})
        ambiguity_verdict = (
            aux_data.get("ambiguity")
            if aux_data and "ambiguity" in aux_data
            else raw_res.get("ambiguity", {}).get("choice", "safe_to_resolve")
        )
        risk_verdict = (
            aux_data.get("risk")
            if aux_data and "risk" in aux_data
            else raw_res.get("risk", {}).get("choice", "LOW")
        )

        c_gen = max(0.01, gen_dec.confidence)
        c_ft = max(0.01, ft_dec.confidence)
        w_gen = c_gen / (c_gen + c_ft)
        w_ft = c_ft / (c_gen + c_ft)

        fused_probs = {}
        for k in all_keys:
            fused_probs[k] = round(w_gen * p_gen.get(k, 0.0) + w_ft * p_ft.get(k, 0.0), 4)

        lat = (time.perf_counter() - t0) * 1000.0

        # Safety Gate 1: Destructive / Blocked Risk
        if risk_verdict == "BLOCKED":
            return FusedDecision(
                intent="unknown",
                confidence=0.0,
                probabilities=fused_probs,
                agreement=agreement,
                js_divergence=jsd,
                entropy=shannon_entropy(fused_probs),
                ambiguity_verdict=ambiguity_verdict,
                risk_verdict="BLOCKED",
                ensemble_mode="E5",
                abstain=True,
                abstain_reason="Blocked by safety policy: risk level is BLOCKED",
                source_decisions={"generic": gen_dec, "finetuned": ft_dec},
                latency_ms=lat,
            )

        # Safety Gate 2: Ambiguity / Underspecified
        if ambiguity_verdict in ("ambiguous", "unknown"):
            return FusedDecision(
                intent="unknown",
                confidence=0.0,
                probabilities=fused_probs,
                agreement=agreement,
                js_divergence=jsd,
                entropy=shannon_entropy(fused_probs),
                ambiguity_verdict=ambiguity_verdict,
                risk_verdict=risk_verdict,
                ensemble_mode="E5",
                abstain=True,
                abstain_reason=f"Ambiguity gate tripped: {ambiguity_verdict}",
                source_decisions={"generic": gen_dec, "finetuned": ft_dec},
                latency_ms=lat,
            )

        # Safety Gate 3: Disagreement Gate
        if not agreement or (jsd > self.js_threshold):
            return FusedDecision(
                intent="unknown",
                confidence=0.0,
                probabilities=fused_probs,
                agreement=agreement,
                js_divergence=jsd,
                entropy=shannon_entropy(fused_probs),
                ambiguity_verdict=ambiguity_verdict,
                risk_verdict=risk_verdict,
                ensemble_mode="E5",
                abstain=True,
                abstain_reason=f"Model disagreement (agreement={agreement}, JSD={jsd:.3f} > {self.js_threshold})",
                source_decisions={"generic": gen_dec, "finetuned": ft_dec},
                latency_ms=lat,
            )

        # Passes all gates: Use fine-tuned intent with confidence-weighted probability
        top_intent = ft_dec.intent
        conf = fused_probs.get(top_intent, ft_dec.confidence)

        return FusedDecision(
            intent=top_intent,
            confidence=conf,
            probabilities=fused_probs,
            agreement=agreement,
            js_divergence=jsd,
            entropy=shannon_entropy(fused_probs),
            ambiguity_verdict=ambiguity_verdict,
            risk_verdict=risk_verdict,
            ensemble_mode="E5",
            abstain=(top_intent == "unknown"),
            abstain_reason="Resolved as unknown" if top_intent == "unknown" else None,
            source_decisions={"generic": gen_dec, "finetuned": ft_dec},
            latency_ms=lat,
        )
