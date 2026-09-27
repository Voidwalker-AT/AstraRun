"""Mathematical confidence scoring, evidence weighting, and decay engine for AstraRun Learning.

Implements rigorous formulas for empirical support aggregation, time-decay attenuation,
promotion/deprecation thresholds, and conflict detection.
"""

from __future__ import annotations

import math
import time
from typing import Sequence

from astrarun.learning.models import (
    EvidenceReference,
    EvidenceType,
    MemoryNamespace,
    MemoryStatus,
    SemanticMemory,
)

# Standard Evidence Weights
EVIDENCE_WEIGHTS: dict[EvidenceType, float] = {
    EvidenceType.EXPLICIT_TEACHING: 3.0,
    EvidenceType.CONFIRMATION_ACCEPTED: 2.0,
    EvidenceType.USER_QUERY_SELECTION: 1.5,
    EvidenceType.SUCCESSFUL_EXECUTION: 1.0,
    EvidenceType.USER_CORRECTION: 3.0,
    EvidenceType.CONFIRMATION_REJECTED: 2.5,
    EvidenceType.EXECUTION_FAILED: 1.0,
}

# Positive vs Contradictory Categories
POSITIVE_EVIDENCE_TYPES: set[EvidenceType] = {
    EvidenceType.EXPLICIT_TEACHING,
    EvidenceType.CONFIRMATION_ACCEPTED,
    EvidenceType.USER_QUERY_SELECTION,
    EvidenceType.SUCCESSFUL_EXECUTION,
}

CONTRADICTORY_EVIDENCE_TYPES: set[EvidenceType] = {
    EvidenceType.USER_CORRECTION,
    EvidenceType.CONFIRMATION_REJECTED,
    EvidenceType.EXECUTION_FAILED,
}

# Lifecycle Thresholds
DEFAULT_PROMOTION_THRESHOLD = 0.85
DEFAULT_MIN_SUPPORT_COUNT = 3
DEFAULT_DEMOTION_THRESHOLD = 0.40
DEFAULT_CONFLICT_MARGIN = 0.20


class ConfidenceCalculator:
    """
    Computes mathematical confidence, recency decay, and state transitions for SemanticMemory.
    """

    def __init__(
        self,
        promotion_threshold: float = DEFAULT_PROMOTION_THRESHOLD,
        min_support_count: int = DEFAULT_MIN_SUPPORT_COUNT,
        demotion_threshold: float = DEFAULT_DEMOTION_THRESHOLD,
        decay_half_life_days: float = 70.0,
    ) -> None:
        self.promotion_threshold = promotion_threshold
        self.min_support_count = min_support_count
        self.demotion_threshold = demotion_threshold
        # Decay constant lambda where e^(-lambda * half_life) = 0.5
        self.decay_lambda = math.log(2.0) / max(1.0, decay_half_life_days)

    def calculate_confidence(
        self,
        evidence_refs: Sequence[EvidenceReference],
        last_used_at: float,
        pinned: bool = False,
        user_confirmed: bool = False,
        current_time: float | None = None,
    ) -> tuple[float, int, int]:
        """
        Calculate confidence score, support count, and contradiction count.

        Returns:
            (confidence, support_count, contradiction_count)
        """
        now = current_time if current_time is not None else time.time()

        pos_weight = 0.0
        neg_weight = 0.0
        support_count = 0
        contradiction_count = 0

        for ref in evidence_refs:
            weight = ref.weight * EVIDENCE_WEIGHTS.get(ref.evidence_type, 1.0)
            if ref.evidence_type in POSITIVE_EVIDENCE_TYPES:
                pos_weight += weight
                support_count += 1
            elif ref.evidence_type in CONTRADICTORY_EVIDENCE_TYPES:
                neg_weight += weight
                contradiction_count += 1

        if pos_weight <= 0.0:
            return 0.0, support_count, contradiction_count

        # Balance ratio penalizes contradictions double
        ratio = pos_weight / (pos_weight + (2.0 * neg_weight))

        # Saturation curve: requires multiple positive signals to approach 1.0
        saturation = 1.0 - math.exp(-pos_weight / 3.0)

        raw_score = ratio * saturation

        # Time decay
        delta_days = max(0.0, (now - last_used_at) / 86400.0)
        time_factor = math.exp(-self.decay_lambda * delta_days)

        if pinned or user_confirmed:
            # User confirmed or pinned facts do not decay below 0.95
            time_factor = max(0.95, time_factor)
        else:
            # Unpinned memories naturally decay over extended disuse
            time_factor = max(0.05, time_factor)

        final_score = round(max(0.0, min(1.0, raw_score * time_factor)), 4)
        return final_score, support_count, contradiction_count

    def evaluate_status(
        self,
        memory: SemanticMemory,
        current_time: float | None = None,
    ) -> MemoryStatus:
        """
        Determine target lifecycle status based on confidence, counts, and user confirmation.
        """
        if memory.status == MemoryStatus.REJECTED:
            return MemoryStatus.REJECTED

        if memory.status == MemoryStatus.CONFLICTED:
            return MemoryStatus.CONFLICTED

        conf, sup, cont = self.calculate_confidence(
            evidence_refs=memory.evidence_refs,
            last_used_at=memory.last_used_at,
            pinned=memory.pinned,
            user_confirmed=memory.user_confirmed,
            current_time=current_time,
        )

        # Explicit user confirmation elevates to ACTIVE as long as contradictions don't outweigh support
        if memory.user_confirmed or memory.pinned:
            if cont > sup and conf < self.demotion_threshold:
                return MemoryStatus.DEPRECATED
            return MemoryStatus.ACTIVE

        # Unconfirmed memories require high confidence and minimum support
        if conf >= self.promotion_threshold and sup >= self.min_support_count and cont == 0:
            return MemoryStatus.ACTIVE

        if conf < self.demotion_threshold and sup > 0:
            return MemoryStatus.DEPRECATED

        return MemoryStatus.CANDIDATE

    @staticmethod
    def detect_conflicts(
        memories: list[SemanticMemory],
        margin: float = DEFAULT_CONFLICT_MARGIN,
    ) -> list[SemanticMemory]:
        """
        Inspect a list of memories sharing identical (namespace, key) but pointing to different values.
        If confidence scores are close or no single memory dominates, marks them as CONFLICTED.
        """
        if len(memories) <= 1:
            return memories

        # Filter to active or high candidate memories
        viable = [m for m in memories if m.status in {MemoryStatus.ACTIVE, MemoryStatus.CANDIDATE} and m.confidence >= 0.40]
        if len(viable) <= 1:
            return memories

        # Sort descending by confidence
        viable.sort(key=lambda m: (m.user_confirmed, m.confidence), reverse=True)

        top1 = viable[0]
        top2 = viable[1]

        # If user explicitly confirmed one and not the other, confirmed takes precedence (no conflict)
        if top1.user_confirmed and not top2.user_confirmed:
            return memories

        # If confidence gap is within margin, trigger CONFLICTED
        diff = abs(top1.confidence - top2.confidence)
        if diff < margin:
            for m in viable:
                if m.status != MemoryStatus.REJECTED:
                    m.status = MemoryStatus.CONFLICTED

        return memories
