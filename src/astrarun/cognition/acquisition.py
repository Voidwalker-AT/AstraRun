"""Information Acquisition Planning Engine for AstraRun 1.0.

Answers the second fundamental question when knowledge is insufficient:
'What information do we need, from where could it be acquired, and under what governance?'

Invariants:
- Phase 1 scope: Formulates structured acquisition plans; does NOT execute external fetching.
- Zero network I/O: All planning is local, deterministic, and fast.
- Privacy-aware: Explicitly flags user-specific data as privacy-sensitive and requiring user authorization.
- Structured taxonomy: Uses typed NeedType, FreshnessRequirement, AuthorityRequirement, and SourceType.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from astrarun.cognition.sufficiency import KnowledgeSufficiencyResult, SufficiencyReason
from astrarun.core.logging import get_logger
from astrarun.security.models import EgressDisclosurePolicy, LocalAccessScope
from astrarun.session.models import ConversationSession

logger = get_logger("astrarun.cognition.acquisition")


class NeedBlockingType(str, Enum):
    """Distinction between hard-blocking prerequisites and optional enrichment."""
    HARD_BLOCKING = "HARD_BLOCKING"      # Cannot proceed responsibly without this evidence
    SOFT_ENRICHMENT = "SOFT_ENRICHMENT"  # Can proceed with caveat/general answer; evidence enriches relevance


class NeedType(str, Enum):
    """Categorization of what class of information is missing."""
    FACTUAL = "FACTUAL"
    CURRENT = "CURRENT"
    USER_SPECIFIC = "USER_SPECIFIC"
    LOCAL_DOCUMENT = "LOCAL_DOCUMENT"
    AUTHORITATIVE_REFERENCE = "AUTHORITATIVE_REFERENCE"
    COMPARATIVE = "COMPARATIVE"
    EXTERNAL_REVIEW = "EXTERNAL_REVIEW"
    SYSTEM_STATE = "SYSTEM_STATE"


class FreshnessRequirement(str, Enum):
    """Temporal freshness constraints on candidate evidence."""
    STATIC = "STATIC"            # Invariant facts, historical data
    RECENT = "RECENT"            # Recent updates, e.g. within last few months
    CURRENT = "CURRENT"          # Today's state, current release
    REALTIME = "REALTIME"        # Live streams, current stock tick, live telemetry


class AuthorityRequirement(str, Enum):
    """Verification and authority standard for candidate evidence."""
    ANY_REASONABLE = "ANY_REASONABLE"
    CORROBORATED = "CORROBORATED"
    PRIMARY_PREFERRED = "PRIMARY_PREFERRED"
    PRIMARY_REQUIRED = "PRIMARY_REQUIRED"
    USER_SOURCE_REQUIRED = "USER_SOURCE_REQUIRED"


class SourceType(str, Enum):
    """Authoritative taxonomy of potential information sources."""
    SESSION_CONTEXT = "SESSION_CONTEXT"
    VERIFIED_ARTIFACT = "VERIFIED_ARTIFACT"
    LOCAL_KNOWLEDGE = "LOCAL_KNOWLEDGE"
    WEB_PRIMARY = "WEB_PRIMARY"
    WEB_SECONDARY = "WEB_SECONDARY"
    EXTERNAL_INTELLIGENCE = "EXTERNAL_INTELLIGENCE"
    CONNECTED_APPLICATION = "CONNECTED_APPLICATION"
    SYSTEM_OBSERVATION = "SYSTEM_OBSERVATION"


@dataclass
class InformationNeed:
    """Individual item of missing information identified by the planner."""
    need_id: str
    description: str
    need_type: NeedType
    freshness: FreshnessRequirement = FreshnessRequirement.STATIC
    authority: AuthorityRequirement = AuthorityRequirement.ANY_REASONABLE
    priority: int = 1  # 1 = highest, 5 = lowest
    privacy_sensitive: bool = False
    blocking_type: NeedBlockingType = NeedBlockingType.HARD_BLOCKING
    access_scope: LocalAccessScope = LocalAccessScope.ACTIVE_FOREGROUND_RESOURCE
    disclosure_policy: EgressDisclosurePolicy = EgressDisclosurePolicy.LOCAL_ONLY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "need_id": self.need_id,
            "description": self.description,
            "need_type": self.need_type.value,
            "freshness": self.freshness.value,
            "authority": self.authority.value,
            "priority": self.priority,
            "privacy_sensitive": self.privacy_sensitive,
            "blocking_type": self.blocking_type.value,
            "access_scope": self.access_scope.value,
            "disclosure_policy": self.disclosure_policy.value,
        }


@dataclass
class SourceCandidate:
    """Specific candidate source capable of satisfying an InformationNeed."""
    source_id: str
    source_type: SourceType
    identifier: str
    estimated_cost: float = 0.0
    estimated_latency_ms: int = 100
    confidence: float = 0.9
    requires_authorization: bool = False
    access_scope: LocalAccessScope = LocalAccessScope.ACTIVE_FOREGROUND_RESOURCE
    disclosure_policy: EgressDisclosurePolicy = EgressDisclosurePolicy.LOCAL_ONLY

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "identifier": self.identifier,
            "estimated_cost": self.estimated_cost,
            "estimated_latency_ms": self.estimated_latency_ms,
            "confidence": self.confidence,
            "requires_authorization": self.requires_authorization,
            "access_scope": self.access_scope.value,
            "disclosure_policy": self.disclosure_policy.value,
        }


@dataclass
class EvidenceRequest:
    """Concrete inquiry directed to one or more SourceCandidates."""
    request_id: str
    need_id: str
    target_sources: List[SourceCandidate] = field(default_factory=list)
    query_formulation: str = ""
    extraction_target: str = ""
    access_scope: LocalAccessScope = LocalAccessScope.ACTIVE_FOREGROUND_RESOURCE
    disclosure_policy: EgressDisclosurePolicy = EgressDisclosurePolicy.LOCAL_ONLY
    requires_confirmation: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "need_id": self.need_id,
            "target_sources": [s.to_dict() for s in self.target_sources],
            "query_formulation": self.query_formulation,
            "extraction_target": self.extraction_target,
            "access_scope": self.access_scope.value,
            "disclosure_policy": self.disclosure_policy.value,
            "requires_confirmation": self.requires_confirmation,
        }


@dataclass
class AcquisitionPlan:
    """Complete, structured information acquisition plan formulated before execution."""
    plan_id: str
    query: str
    sufficiency_result: KnowledgeSufficiencyResult
    needs: List[InformationNeed] = field(default_factory=list)
    evidence_requests: List[EvidenceRequest] = field(default_factory=list)
    user_summary: str = ""
    privacy_notice: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "query": self.query,
            "sufficiency_result": self.sufficiency_result.to_dict(),
            "needs": [n.to_dict() for n in self.needs],
            "evidence_requests": [r.to_dict() for r in self.evidence_requests],
            "user_summary": self.user_summary,
            "privacy_notice": self.privacy_notice,
            "created_at": self.created_at,
        }


class InformationAcquisitionPlanner:
    """
    Formulates structured Information Acquisition Plans when knowledge is insufficient.
    
    Translates KnowledgeSufficiencyResult into concrete InformationNeeds and ranked SourceCandidates.
    """

    def plan_acquisition(
        self,
        query: str,
        sufficiency: KnowledgeSufficiencyResult,
        session: Optional[ConversationSession] = None,
    ) -> AcquisitionPlan:
        """
        Formulate a structured acquisition plan for missing knowledge aspects.
        """
        plan_id = f"plan-acq-{uuid.uuid4().hex[:10]}"
        needs: List[InformationNeed] = []
        evidence_requests: List[EvidenceRequest] = []

        # If sufficiency already formulated concrete needs, use them directly
        if hasattr(sufficiency, "information_needs") and sufficiency.information_needs:
            for need in sufficiency.information_needs:
                needs.append(need)
                target_sources = self._resolve_sources_for_need(need, query)
                req = EvidenceRequest(
                    request_id=f"req-{len(evidence_requests) + 1}",
                    need_id=need.need_id,
                    target_sources=target_sources,
                    query_formulation=query,
                    extraction_target=need.description,
                    access_scope=need.access_scope,
                    disclosure_policy=need.disclosure_policy,
                    requires_confirmation=need.disclosure_policy.requires_confirmation,
                )
                evidence_requests.append(req)

            user_summary = self._synthesize_user_summary(sufficiency, needs, evidence_requests)
            has_disclosure_confirm = any(
                n.disclosure_policy == EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED
                for n in needs
            )
            privacy_notice = (
                "Security Invariant: Local files and personal records will NEVER be transmitted externally without explicit user confirmation."
                if has_disclosure_confirm
                else ""
            )
            return AcquisitionPlan(
                plan_id=plan_id,
                query=query,
                sufficiency_result=sufficiency,
                needs=needs,
                evidence_requests=evidence_requests,
                user_summary=user_summary,
                privacy_notice=privacy_notice,
            )

        reason = sufficiency.reason
        missing_aspects = sufficiency.missing_aspects or [sufficiency.explanation]

        if reason == SufficiencyReason.MISSING_CURRENT_INFORMATION:
            for idx, aspect in enumerate(missing_aspects, 1):
                need = InformationNeed(
                    need_id=f"need-{idx}",
                    description=f"Current or real-time state: {aspect}",
                    need_type=NeedType.CURRENT,
                    freshness=FreshnessRequirement.REALTIME if "stock" in query.lower() or "price" in query.lower() else FreshnessRequirement.CURRENT,
                    authority=AuthorityRequirement.CORROBORATED,
                    priority=1,
                    privacy_sensitive=False,
                    access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                    disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                )
                needs.append(need)

                req = EvidenceRequest(
                    request_id=f"req-{idx}",
                    need_id=need.need_id,
                    target_sources=[
                        SourceCandidate(
                            source_id="src-web-primary",
                            source_type=SourceType.WEB_PRIMARY,
                            identifier="Official / Real-time Web Feeds",
                            estimated_latency_ms=800,
                            confidence=0.95,
                            requires_authorization=False,
                            access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                            disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                        ),
                        SourceCandidate(
                            source_id="src-web-search",
                            source_type=SourceType.WEB_SECONDARY,
                            identifier="Web Search Index",
                            estimated_latency_ms=1200,
                            confidence=0.85,
                            requires_authorization=False,
                            access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                            disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                        ),
                    ],
                    query_formulation=query,
                    extraction_target=aspect,
                    access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                    disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                )
                evidence_requests.append(req)

        elif reason in (SufficiencyReason.MISSING_USER_SPECIFIC_CONTEXT, SufficiencyReason.MISSING_LOCAL_CONTEXT):
            is_local = (reason == SufficiencyReason.MISSING_LOCAL_CONTEXT)
            scope = LocalAccessScope.AUTHORIZED_WORKSPACE if is_local else LocalAccessScope.EXPLICITLY_AUTHORIZED_USER_DIRECTORIES
            for idx, aspect in enumerate(missing_aspects, 1):
                need = InformationNeed(
                    need_id=f"need-{idx}",
                    description=f"Private user / local resource: {aspect}",
                    need_type=NeedType.LOCAL_DOCUMENT if is_local else NeedType.USER_SPECIFIC,
                    freshness=FreshnessRequirement.CURRENT,
                    authority=AuthorityRequirement.USER_SOURCE_REQUIRED,
                    priority=1,
                    privacy_sensitive=True,
                    access_scope=scope,
                    disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
                )
                needs.append(need)

                sources = [
                    SourceCandidate(
                        source_id="src-local-files",
                        source_type=SourceType.LOCAL_KNOWLEDGE,
                        identifier="Local Workstation Filesystem / Indexed Documents",
                        estimated_latency_ms=150,
                        confidence=0.90,
                        requires_authorization=True,
                        access_scope=scope,
                        disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
                    ),
                    SourceCandidate(
                        source_id="src-connected-apps",
                        source_type=SourceType.CONNECTED_APPLICATION,
                        identifier="Connected Desktop Applications / Notes / Mail",
                        estimated_latency_ms=300,
                        confidence=0.85,
                        requires_authorization=True,
                        access_scope=scope,
                        disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
                    ),
                ]
                req = EvidenceRequest(
                    request_id=f"req-{idx}",
                    need_id=need.need_id,
                    target_sources=sources,
                    query_formulation=query,
                    extraction_target=aspect,
                    access_scope=scope,
                    disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
                )
                evidence_requests.append(req)

        elif reason in (SufficiencyReason.MISSING_AUTHORITATIVE_SOURCE, SufficiencyReason.MISSING_EXTERNAL_VERIFICATION):
            for idx, aspect in enumerate(missing_aspects, 1):
                need = InformationNeed(
                    need_id=f"need-{idx}",
                    description=f"Authoritative standard / primary document: {aspect}",
                    need_type=NeedType.AUTHORITATIVE_REFERENCE,
                    freshness=FreshnessRequirement.STATIC,
                    authority=AuthorityRequirement.PRIMARY_REQUIRED,
                    priority=1,
                    privacy_sensitive=False,
                    access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                    disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                )
                needs.append(need)

                req = EvidenceRequest(
                    request_id=f"req-{idx}",
                    need_id=need.need_id,
                    target_sources=[
                        SourceCandidate(
                            source_id="src-authoritative-docs",
                            source_type=SourceType.WEB_PRIMARY,
                            identifier="Official Standards Repository / Primary RFC / NIST",
                            estimated_latency_ms=900,
                            confidence=0.99,
                            requires_authorization=False,
                            access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                            disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                        ),
                        SourceCandidate(
                            source_id="src-external-intelligence",
                            source_type=SourceType.EXTERNAL_INTELLIGENCE,
                            identifier="Authoritative Model Peer Review",
                            estimated_latency_ms=2000,
                            confidence=0.92,
                            requires_authorization=False,
                            access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                            disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                        ),
                    ],
                    query_formulation=query,
                    extraction_target=aspect,
                    access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                    disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                )
                evidence_requests.append(req)

        elif reason == SufficiencyReason.AMBIGUOUS_GOAL:
            need = InformationNeed(
                need_id="need-1",
                description="Clarification of ambiguous goal or undefined pronoun referent",
                need_type=NeedType.USER_SPECIFIC,
                freshness=FreshnessRequirement.CURRENT,
                authority=AuthorityRequirement.USER_SOURCE_REQUIRED,
                priority=1,
                privacy_sensitive=False,
                access_scope=LocalAccessScope.ACTIVE_FOREGROUND_RESOURCE,
                disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
            )
            needs.append(need)

            req = EvidenceRequest(
                request_id="req-1",
                need_id=need.need_id,
                target_sources=[
                    SourceCandidate(
                        source_id="src-user-dialogue",
                        source_type=SourceType.SESSION_CONTEXT,
                        identifier="Direct Conversational Clarification with User",
                        estimated_latency_ms=0,
                        confidence=1.0,
                        requires_authorization=False,
                        access_scope=LocalAccessScope.ACTIVE_FOREGROUND_RESOURCE,
                        disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
                    ),
                ],
                query_formulation=query,
                extraction_target="User clarification",
                access_scope=LocalAccessScope.ACTIVE_FOREGROUND_RESOURCE,
                disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
            )
            evidence_requests.append(req)

        else:
            # Fallback for general insufficient evidence
            need = InformationNeed(
                need_id="need-1",
                description=f"Supplemental evidence: {sufficiency.explanation}",
                need_type=NeedType.FACTUAL,
                freshness=FreshnessRequirement.STATIC,
                authority=AuthorityRequirement.CORROBORATED,
                priority=2,
                privacy_sensitive=False,
                access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
            )
            needs.append(need)

            req = EvidenceRequest(
                request_id="req-1",
                need_id=need.need_id,
                target_sources=[
                    SourceCandidate(
                        source_id="src-web-search",
                        source_type=SourceType.WEB_SECONDARY,
                        identifier="Web Search Index",
                        estimated_latency_ms=1000,
                        confidence=0.85,
                        requires_authorization=False,
                        access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                        disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                    )
                ],
                query_formulation=query,
                extraction_target=sufficiency.explanation,
                access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
            )
            evidence_requests.append(req)

        user_summary = self._synthesize_user_summary(sufficiency, needs, evidence_requests)
        has_disclosure_confirm = any(
            n.disclosure_policy == EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED
            for n in needs
        )
        privacy_notice = (
            "Security Invariant: Local files and personal records will NEVER be transmitted externally without explicit user confirmation."
            if has_disclosure_confirm
            else ""
        )

        return AcquisitionPlan(
            plan_id=plan_id,
            query=query,
            sufficiency_result=sufficiency,
            needs=needs,
            evidence_requests=evidence_requests,
            user_summary=user_summary,
            privacy_notice=privacy_notice,
        )

    def _resolve_sources_for_need(self, need: InformationNeed, query: str) -> List[SourceCandidate]:
        """
        Resolve ranked, governance-compliant candidate sources for an InformationNeed.
        Enforces two-axis privacy: local read permission is never egress disclosure permission.
        """
        sources: List[SourceCandidate] = []
        if need.need_type == NeedType.CURRENT:
            sources.append(
                SourceCandidate(
                    source_id="src-web-primary",
                    source_type=SourceType.WEB_PRIMARY,
                    identifier="Official / Real-time Web Feeds",
                    estimated_latency_ms=800,
                    confidence=0.95,
                    requires_authorization=False,
                    access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                    disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                )
            )
            sources.append(
                SourceCandidate(
                    source_id="src-web-search",
                    source_type=SourceType.WEB_SECONDARY,
                    identifier="Web Search Index",
                    estimated_latency_ms=1200,
                    confidence=0.85,
                    requires_authorization=False,
                    access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                    disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                )
            )
        elif need.need_type in (NeedType.USER_SPECIFIC, NeedType.LOCAL_DOCUMENT):
            sources.append(
                SourceCandidate(
                    source_id="src-local-files",
                    source_type=SourceType.LOCAL_KNOWLEDGE,
                    identifier="Local Workstation Filesystem / Indexed Documents",
                    estimated_latency_ms=150,
                    confidence=0.90,
                    requires_authorization=True,
                    access_scope=need.access_scope,
                    disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
                )
            )
            sources.append(
                SourceCandidate(
                    source_id="src-connected-apps",
                    source_type=SourceType.CONNECTED_APPLICATION,
                    identifier="Connected Desktop Applications / Notes / Mail",
                    estimated_latency_ms=300,
                    confidence=0.85,
                    requires_authorization=True,
                    access_scope=need.access_scope,
                    disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
                )
            )
        elif need.need_type == NeedType.AUTHORITATIVE_REFERENCE:
            sources.append(
                SourceCandidate(
                    source_id="src-authoritative-docs",
                    source_type=SourceType.WEB_PRIMARY,
                    identifier="Official Standards Repository / Primary RFC / NIST",
                    estimated_latency_ms=900,
                    confidence=0.99,
                    requires_authorization=False,
                    access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                    disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                )
            )
            sources.append(
                SourceCandidate(
                    source_id="src-external-intelligence",
                    source_type=SourceType.EXTERNAL_INTELLIGENCE,
                    identifier="Authoritative Model Peer Review",
                    estimated_latency_ms=2000,
                    confidence=0.92,
                    requires_authorization=False,
                    access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                    disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                )
            )
        elif need.need_type == NeedType.SYSTEM_STATE:
            sources.append(
                SourceCandidate(
                    source_id="src-system-observation",
                    source_type=SourceType.SYSTEM_OBSERVATION,
                    identifier="Live Workstation System / OS Observation",
                    estimated_latency_ms=50,
                    confidence=0.99,
                    requires_authorization=False,
                    access_scope=LocalAccessScope.ACTIVE_FOREGROUND_RESOURCE,
                    disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
                )
            )
        elif need.need_type == NeedType.EXTERNAL_REVIEW:
            is_private = (
                need.privacy_sensitive
                or need.disclosure_policy == EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED
                or need.access_scope.is_restricted
            )
            sources.append(
                SourceCandidate(
                    source_id="src-external-intelligence",
                    source_type=SourceType.EXTERNAL_INTELLIGENCE,
                    identifier="External AI Consultation Service",
                    estimated_latency_ms=2000,
                    confidence=0.90,
                    requires_authorization=is_private,
                    access_scope=need.access_scope,
                    disclosure_policy=EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED if is_private else EgressDisclosurePolicy.PUBLIC_SAFE,
                )
            )
        else:
            sources.append(
                SourceCandidate(
                    source_id="src-web-search",
                    source_type=SourceType.WEB_SECONDARY,
                    identifier="Web Search Index",
                    estimated_latency_ms=1000,
                    confidence=0.85,
                    requires_authorization=False,
                    access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                    disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                )
            )
        return sources

    def _synthesize_user_summary(
        self,
        sufficiency: KnowledgeSufficiencyResult,
        needs: List[InformationNeed],
        requests: List[EvidenceRequest],
    ) -> str:
        """
        Formulate a transparent, helpful user explanation of required information and sources.
        """
        lines = []
        if sufficiency.reason == SufficiencyReason.AMBIGUOUS_GOAL:
            lines.append("I need a bit more context to proceed:")
            for n in needs:
                lines.append(f"• {n.description}")
            lines.append("\nPlease clarify your goal or specify the object you are referring to.")
            return "\n".join(lines)

        hard_needs = [n for n in needs if n.blocking_type == NeedBlockingType.HARD_BLOCKING]
        soft_needs = [n for n in needs if n.blocking_type == NeedBlockingType.SOFT_ENRICHMENT]

        if hard_needs:
            lines.append("To answer your request accurately, additional information is required:")
            for n in hard_needs:
                lines.append(f"• Required: {n.description} (Priority: P{n.priority})")
        if soft_needs:
            if not hard_needs:
                lines.append("I can provide a general answer, but the following context would improve accuracy:")
            else:
                lines.append("\nOptional enrichment context:")
            for n in soft_needs:
                lines.append(f"• Optional: {n.description} (Priority: P{n.priority})")

        # Collect unique target sources
        unique_sources: Dict[str, SourceCandidate] = {}
        for r in requests:
            for s in r.target_sources:
                if s.identifier not in unique_sources:
                    unique_sources[s.identifier] = s

        lines.append("\nProposed acquisition sources:")
        has_auth_req = False
        has_disclosure_confirm = False
        for s in unique_sources.values():
            auth_str = " [Requires User Authorization]" if s.requires_authorization else ""
            if s.requires_authorization:
                has_auth_req = True
            if s.disclosure_policy == EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED:
                has_disclosure_confirm = True
            lines.append(f"• {s.identifier} ({s.source_type.value}){auth_str}")

        if has_auth_req:
            lines.append("\nNote: Accessing local files or personal records requires explicit authorization.")
        if has_disclosure_confirm:
            lines.append("\nSecurity Invariant: Local files and personal records will NEVER be transmitted externally without explicit user confirmation.")

        return "\n".join(lines)
