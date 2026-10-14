"""Domain models and data contracts for AstraRun Hermes Experiential Memory.

Defines strongly-typed representations for:
- Experiential entities (applications, top-level windows, controls)
- Affordances (actions and capabilities associated with entities)
- State transitions (causally observed pre-state -> action -> post-state)
- Diagnostic experiments (hypotheses, bounded probes, outcomes)
- Epistemic status and uncertainty classifications
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class EntityType(str, Enum):
    """Categorical types of discoverable Windows interaction targets."""
    APPLICATION = "APPLICATION"
    WINDOW = "WINDOW"
    CONTROL = "CONTROL"


class EpistemicStatus(str, Enum):
    """Epistemic lifecycle states for learned affordances and beliefs."""
    HYPOTHESIS = "HYPOTHESIS"
    OBSERVED = "OBSERVED"
    VERIFIED = "VERIFIED"
    CONTRADICTED = "CONTRADICTED"


class ConfidenceBand(str, Enum):
    """Operational classification of knowledge certainty."""
    KNOWN = "KNOWN"              # C >= 0.85: Confidently dispatch ACT
    LIKELY = "LIKELY"            # 0.60 <= C < 0.85: Dispatch ACT with postcondition check
    UNCERTAIN = "UNCERTAIN"      # 0.30 <= C < 0.60: Enter EXPLORE mode
    UNKNOWN = "UNKNOWN"          # C < 0.30: Cold encounter; enter EXPLORE mode
    CONTRADICTED = "CONTRADICTED"# C <= 0.15: Invalidated belief; re-explore


class AffordanceRisk(str, Enum):
    """Risk tier for affordances and exploration probes."""
    READ_ONLY = "READ_ONLY"
    BENIGN_MUTATION = "BENIGN_MUTATION"
    HIGH_RISK = "HIGH_RISK"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            val_upper = value.upper()
            if val_upper in ("LOW", "READ_ONLY", "SAFE", "INFO"):
                return cls.READ_ONLY
            if val_upper in ("HIGH", "HIGH_RISK", "CRITICAL", "DESTRUCTIVE"):
                return cls.HIGH_RISK
            if val_upper in ("MEDIUM", "BENIGN_MUTATION", "MUTATING"):
                return cls.BENIGN_MUTATION
        return super()._missing_(value)


class ExperimentStatus(str, Enum):
    """Lifecycle status of a diagnostic experiment."""
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    INCONCLUSIVE = "INCONCLUSIVE"


class ExplorationDecisionMode(str, Enum):
    """High-level cognitive mode decided by the uncertainty model."""
    ACT = "ACT"
    EXPLORE = "EXPLORE"


@dataclass
class EntityNode:
    """Discovered Windows entity node in the Hermes knowledge graph."""
    entity_id: str
    entity_type: EntityType
    name: str
    parent_entity_id: Optional[str] = None
    class_name: Optional[str] = None
    binary_hash: Optional[str] = None
    version: Optional[str] = None
    env_hash: str = "default_env"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        entity_type: EntityType,
        name: str,
        parent_entity_id: Optional[str] = None,
        class_name: Optional[str] = None,
        binary_hash: Optional[str] = None,
        version: Optional[str] = None,
        env_hash: str = "default_env",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EntityNode:
        return cls(
            entity_id=f"ent_{uuid.uuid4().hex[:12]}",
            entity_type=entity_type,
            name=name,
            parent_entity_id=parent_entity_id,
            class_name=class_name,
            binary_hash=binary_hash,
            version=version,
            env_hash=env_hash,
            metadata=metadata or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "parent_entity_id": self.parent_entity_id,
            "class_name": self.class_name,
            "binary_hash": self.binary_hash,
            "version": self.version,
            "env_hash": self.env_hash,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class AffordanceEdge:
    """Action affordance associated with an entity."""
    affordance_id: str
    entity_id: str
    action_name: str
    capability_id: str
    parameter_schema: Dict[str, Any] = field(default_factory=dict)
    risk_level: AffordanceRisk = AffordanceRisk.BENIGN_MUTATION
    is_reversible: bool = True
    confidence: float = 0.20
    status: EpistemicStatus = EpistemicStatus.HYPOTHESIS
    verification_count: int = 0
    contradiction_count: int = 0
    last_verified_at: Optional[float] = None
    created_at: float = field(default_factory=time.time)

    @property
    def confidence_band(self) -> ConfidenceBand:
        if self.status == EpistemicStatus.CONTRADICTED or self.confidence <= 0.15:
            return ConfidenceBand.CONTRADICTED
        if self.confidence >= 0.85:
            return ConfidenceBand.KNOWN
        if self.confidence >= 0.60:
            return ConfidenceBand.LIKELY
        if self.confidence >= 0.30:
            return ConfidenceBand.UNCERTAIN
        return ConfidenceBand.UNKNOWN

    @classmethod
    def create(
        cls,
        entity_id: str,
        action_name: str,
        capability_id: str,
        parameter_schema: Optional[Dict[str, Any]] = None,
        risk_level: AffordanceRisk = AffordanceRisk.BENIGN_MUTATION,
        is_reversible: bool = True,
        confidence: float = 0.20,
        status: EpistemicStatus = EpistemicStatus.HYPOTHESIS,
    ) -> AffordanceEdge:
        return cls(
            affordance_id=f"aff_{uuid.uuid4().hex[:12]}",
            entity_id=entity_id,
            action_name=action_name,
            capability_id=capability_id,
            parameter_schema=parameter_schema or {},
            risk_level=risk_level,
            is_reversible=is_reversible,
            confidence=confidence,
            status=status,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "affordance_id": self.affordance_id,
            "entity_id": self.entity_id,
            "action_name": self.action_name,
            "capability_id": self.capability_id,
            "parameter_schema": self.parameter_schema,
            "risk_level": self.risk_level.value,
            "is_reversible": self.is_reversible,
            "confidence": self.confidence,
            "status": self.status.value,
            "verification_count": self.verification_count,
            "contradiction_count": self.contradiction_count,
            "last_verified_at": self.last_verified_at,
            "created_at": self.created_at,
        }


@dataclass
class StateTransitionRecord:
    """Empirically verified state transition edge in Hermes."""
    transition_id: str
    affordance_id: str
    pre_state_hash: str
    action_payload: Dict[str, Any]
    post_state_hash: str
    expected_delta: Dict[str, Any]
    observed_delta: Dict[str, Any]
    transition_verified: bool
    latency_ms: float
    trace_id: str
    pre_frame_id: str
    post_frame_id: str
    timestamp: float = field(default_factory=time.time)
    predicate_type: str = "GENERIC_STATE_DELTA"
    expected_value: Dict[str, Any] = field(default_factory=dict)
    observed_value: Dict[str, Any] = field(default_factory=dict)
    evaluation: Dict[str, Any] = field(default_factory=dict)
    raw_evidence_reference: str = ""

    @classmethod
    def create(
        cls,
        affordance_id: str,
        pre_state_hash: str,
        action_payload: Dict[str, Any],
        post_state_hash: str,
        expected_delta: Dict[str, Any],
        observed_delta: Dict[str, Any],
        transition_verified: bool,
        latency_ms: float,
        trace_id: str,
        pre_frame_id: str,
        post_frame_id: str,
        predicate_type: str = "GENERIC_STATE_DELTA",
        expected_value: Optional[Dict[str, Any]] = None,
        observed_value: Optional[Dict[str, Any]] = None,
        evaluation: Optional[Dict[str, Any]] = None,
        raw_evidence_reference: str = "",
    ) -> StateTransitionRecord:
        return cls(
            transition_id=f"tr_{uuid.uuid4().hex[:12]}",
            affordance_id=affordance_id,
            pre_state_hash=pre_state_hash,
            action_payload=action_payload,
            post_state_hash=post_state_hash,
            expected_delta=expected_delta,
            observed_delta=observed_delta,
            transition_verified=transition_verified,
            latency_ms=latency_ms,
            trace_id=trace_id,
            pre_frame_id=pre_frame_id,
            post_frame_id=post_frame_id,
            predicate_type=predicate_type,
            expected_value=expected_value or expected_delta,
            observed_value=observed_value or observed_delta,
            evaluation=evaluation or {"verified": transition_verified},
            raw_evidence_reference=raw_evidence_reference,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "transition_id": self.transition_id,
            "affordance_id": self.affordance_id,
            "pre_state_hash": self.pre_state_hash,
            "action_payload": self.action_payload,
            "post_state_hash": self.post_state_hash,
            "expected_delta": self.expected_delta,
            "observed_delta": self.observed_delta,
            "transition_verified": self.transition_verified,
            "latency_ms": self.latency_ms,
            "trace_id": self.trace_id,
            "pre_frame_id": self.pre_frame_id,
            "post_frame_id": self.post_frame_id,
            "timestamp": self.timestamp,
            "predicate_type": self.predicate_type,
            "expected_value": self.expected_value,
            "observed_value": self.observed_value,
            "evaluation": self.evaluation,
            "raw_evidence_reference": self.raw_evidence_reference,
        }



@dataclass
class ExperimentRecord:
    """Diagnostic exploration experiment formulated to test an epistemic hypothesis."""
    experiment_id: str
    target_entity_id: str
    hypothesis: str
    probe_action_name: str
    probe_payload: Dict[str, Any]
    expected_outcome: str
    actual_outcome: Optional[str] = None
    status: ExperimentStatus = ExperimentStatus.PENDING
    task_id: str = ""
    trace_id: str = ""
    prompt_hash: str = ""
    response_hash: str = ""
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        target_entity_id: str,
        hypothesis: str,
        probe_action_name: str,
        probe_payload: Dict[str, Any],
        expected_outcome: str,
        task_id: str = "",
        trace_id: str = "",
        prompt_hash: str = "",
        response_hash: str = "",
    ) -> ExperimentRecord:
        return cls(
            experiment_id=f"exp_{uuid.uuid4().hex[:12]}",
            target_entity_id=target_entity_id,
            hypothesis=hypothesis,
            probe_action_name=probe_action_name,
            probe_payload=probe_payload,
            expected_outcome=expected_outcome,
            task_id=task_id,
            trace_id=trace_id,
            prompt_hash=prompt_hash,
            response_hash=response_hash,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "target_entity_id": self.target_entity_id,
            "hypothesis": self.hypothesis,
            "probe_action_name": self.probe_action_name,
            "probe_payload": self.probe_payload,
            "expected_outcome": self.expected_outcome,
            "actual_outcome": self.actual_outcome,
            "status": self.status.value,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "prompt_hash": self.prompt_hash,
            "response_hash": self.response_hash,
            "timestamp": self.timestamp,
        }
