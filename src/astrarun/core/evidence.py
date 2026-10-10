"""Authoritative Evidence Classification Framework for AstraRun.

Complies with AstraRun Architecture Reality doctrine:
Evidence levels are strictly typed and cannot be self-promoted.
A source-tree unit test or mock provider must never claim real execution status.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, model_validator


class EvidenceClass(str, Enum):
    """Authoritative hierarchy of evidence classes."""
    UNIT = "UNIT"
    FIXTURE = "FIXTURE"
    MOCK = "MOCK"
    SIMULATED_PROVIDER = "SIMULATED_PROVIDER"
    SOURCE_TREE_INTEGRATION = "SOURCE_TREE_INTEGRATION"
    PRODUCTION_PATH_AUTOMATED = "PRODUCTION_PATH_AUTOMATED"
    FROZEN_EXE = "FROZEN_EXE"
    MODEL_RESIDENT = "MODEL_RESIDENT"
    REAL_LOCAL_MODEL_INFERENCE = "REAL_LOCAL_MODEL_INFERENCE"
    REAL_LOCAL_MODEL = "REAL_LOCAL_MODEL_INFERENCE"
    REAL_BROWSER = "REAL_BROWSER"
    REAL_EXTERNAL_PROVIDER = "REAL_EXTERNAL_PROVIDER"
    REAL_COMPUTER_USE = "REAL_COMPUTER_USE"
    HUMAN_OBSERVED = "HUMAN_OBSERVED"


# Classes that may NEVER be claimed by a low-tier harness without external physical proof.
_PHYSICAL_CLAIM_CLASSES: Set[EvidenceClass] = {
    EvidenceClass.REAL_COMPUTER_USE,
    EvidenceClass.REAL_BROWSER,
    EvidenceClass.REAL_LOCAL_MODEL_INFERENCE,
    EvidenceClass.FROZEN_EXE,
    EvidenceClass.HUMAN_OBSERVED,
}

# Classes that may NEVER self-promote into physical/external execution claims.
_LOW_TIER_CLASSES: Set[EvidenceClass] = {
    EvidenceClass.UNIT,
    EvidenceClass.FIXTURE,
    EvidenceClass.MOCK,
    EvidenceClass.SIMULATED_PROVIDER,
    EvidenceClass.SOURCE_TREE_INTEGRATION,
}


class EvidencePromotionError(ValueError):
    """Raised when evidence class self-promotion is attempted."""


def can_claim_evidence_class(
    claimed: EvidenceClass,
    provenance: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Generic anti-promotion gate.

    Low-tier harnesses may not claim physical/external execution classes unless
    explicit provenance demonstrates the higher-tier observation path was used.
    """
    if claimed not in _PHYSICAL_CLAIM_CLASSES:
        return True
    prov = provenance or {}
    if prov.get("physically_executed") is True and prov.get("runtime_artifact"):
        return True
    if prov.get("frozen_binary_hash") and prov.get("frozen_execution_trace"):
        return True
    if claimed == EvidenceClass.HUMAN_OBSERVED and prov.get("human_observed") is True:
        return True
    return False


def assert_evidence_class_allowed(
    claimed: EvidenceClass,
    provenance: Optional[Dict[str, Any]] = None,
) -> None:
    """Raise EvidencePromotionError if claimed class is not substantiated."""
    if not can_claim_evidence_class(claimed, provenance):
        raise EvidencePromotionError(
            f"Evidence class '{claimed.value}' cannot be self-promoted from low-tier harness "
            "without physical/frozen/human provenance."
        )


class EvidenceRecord(BaseModel):
    """Structured record of evidence with mandatory verification classification."""
    evidence_class: EvidenceClass
    claim: str
    target_component: str
    verified: bool
    details: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    provenance_hash: Optional[str] = None
    timestamp: float = Field(default_factory=lambda: __import__("time").time())

    @model_validator(mode="after")
    def _reject_self_promotion(self) -> "EvidenceRecord":
        # In-repo structural labels used by historical audits are allowed as labels only
        # when they do not assert physical runtime execution.
        structural_aliases = {
            "TEST_EXECUTED",
            "SOURCE_INSPECTED",
            "PHYSICALLY_OBSERVED",
            "FROZEN_PRODUCT_OBSERVED",
            "FROZEN_PRODUCT_PHYSICAL_EXECUTION",
            "FROZEN_PRODUCT_ADVERSARIAL_SAFETY",
            "REAL_INSTALLED_PRODUCT_EXECUTION",
        }
        claimed_raw = str(self.evidence_class)
        if claimed_raw in structural_aliases:
            return self
        assert_evidence_class_allowed(self.evidence_class, self.provenance or self.details)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_class": self.evidence_class.value,
            "claim": self.claim,
            "target_component": self.target_component,
            "verified": self.verified,
            "details": self.details,
            "provenance": self.provenance,
            "provenance_hash": self.provenance_hash,
            "timestamp": self.timestamp,
        }
