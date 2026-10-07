"""Authoritative Evidence Classification Framework for AstraRun.

Complies with AstraRun Architecture Reality doctrine:
Evidence levels are strictly typed and cannot be self-promoted.
A source-tree unit test or mock provider must never claim real execution status.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


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


class EvidenceRecord(BaseModel):
    """Structured record of evidence with mandatory verification classification."""
    evidence_class: EvidenceClass
    claim: str
    target_component: str
    verified: bool
    details: Dict[str, Any] = Field(default_factory=dict)
    provenance_hash: Optional[str] = None
    timestamp: float = Field(default_factory=lambda: __import__("time").time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_class": self.evidence_class.value,
            "claim": self.claim,
            "target_component": self.target_component,
            "verified": self.verified,
            "details": self.details,
            "provenance_hash": self.provenance_hash,
            "timestamp": self.timestamp,
        }
