"""Knowledge Sufficiency Engine for AstraRun 1.0 (ACR-NEXT Phase 1.1).

Answers the fundamental question before execution or planning:
'Do we already know enough to satisfy this goal, or must we acquire information first?'

Invariants:
- High speed: Heuristic evaluation executes in < 15ms with zero network round trips.
- Decoupled from execution: Evaluator only assesses sufficiency and information needs; it does not execute tools.
- Multi-need compositional analysis: Discovers multiple concurrent needs (e.g. local + external).
- Hard-blocking vs Soft-enrichment: Distinguishes essential prerequisites from optional relevance context.
- Epistemic vs Capability separation: Live system state (e.g. battery, processes) is recognized as
  requiring observation rather than being labeled internal model knowledge.
- Two-axis privacy governance: Integrates LocalAccessScope and EgressDisclosurePolicy.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from astrarun.computer_use.world.summary import WorldStateSummary
from astrarun.core.logging import get_logger
from astrarun.security.models import EgressDisclosurePolicy, LocalAccessScope
from astrarun.session.models import ConversationSession

logger = get_logger("astrarun.cognition.sufficiency")


class SufficiencyReason(str, Enum):
    """Authoritative taxonomy for knowledge sufficiency determinations."""
    SUFFICIENT_INTERNAL_KNOWLEDGE = "SUFFICIENT_INTERNAL_KNOWLEDGE"
    SUFFICIENT_SESSION_CONTEXT = "SUFFICIENT_SESSION_CONTEXT"
    SUFFICIENT_VERIFIED_ARTIFACT = "SUFFICIENT_VERIFIED_ARTIFACT"
    SUFFICIENT_OBSERVABLE_STATE = "SUFFICIENT_OBSERVABLE_STATE"
    MISSING_CURRENT_INFORMATION = "MISSING_CURRENT_INFORMATION"
    MISSING_USER_SPECIFIC_CONTEXT = "MISSING_USER_SPECIFIC_CONTEXT"
    MISSING_LOCAL_CONTEXT = "MISSING_LOCAL_CONTEXT"
    MISSING_AUTHORITATIVE_SOURCE = "MISSING_AUTHORITATIVE_SOURCE"
    MISSING_EXTERNAL_VERIFICATION = "MISSING_EXTERNAL_VERIFICATION"
    AMBIGUOUS_GOAL = "AMBIGUOUS_GOAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass
class KnowledgeSufficiencyResult:
    """Strongly-typed determination of whether current knowledge suffices for a goal."""
    is_sufficient: bool
    reason: SufficiencyReason
    confidence: float = 1.0
    missing_aspects: List[str] = field(default_factory=list)
    explanation: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Phase 1.1 Compositional & Governance fields:
    information_needs: List[Any] = field(default_factory=list)
    reasons: List[SufficiencyReason] = field(default_factory=list)
    observable_capability_id: Optional[str] = None
    observation_required: bool = False
    has_hard_blocking_needs: bool = False
    has_soft_enrichment_needs: bool = False

    @property
    def hard_blocking_needs(self) -> List[Any]:
        from astrarun.cognition.acquisition import NeedBlockingType
        return [n for n in self.information_needs if getattr(n, "blocking_type", None) == NeedBlockingType.HARD_BLOCKING]

    @property
    def soft_enrichment_needs(self) -> List[Any]:
        from astrarun.cognition.acquisition import NeedBlockingType
        return [n for n in self.information_needs if getattr(n, "blocking_type", None) == NeedBlockingType.SOFT_ENRICHMENT]

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "is_sufficient": self.is_sufficient,
            "reason": self.reason.value,
            "confidence": self.confidence,
            "missing_aspects": list(self.missing_aspects),
            "explanation": self.explanation,
            "metadata": dict(self.metadata),
            "reasons": [r.value for r in self.reasons] if self.reasons else [self.reason.value],
            "observable_capability_id": self.observable_capability_id,
            "observation_required": self.observation_required,
            "has_hard_blocking_needs": self.has_hard_blocking_needs,
            "has_soft_enrichment_needs": self.has_soft_enrichment_needs,
            "information_needs": [
                n.to_dict() if hasattr(n, "to_dict") else str(n)
                for n in self.information_needs
            ],
        }
        return d


class KnowledgeSufficiencyEvaluator:
    """
    Evaluates whether AstraRun has sufficient knowledge to answer or act.
    
    Operates before TurnReasoner and Tool Planner.
    If knowledge is sufficient: passes through to normal reasoning/execution.
    If knowledge is insufficient: triggers InformationAcquisitionPlanner.
    """

    # User private data patterns
    _USER_SPECIFIC_PATTERNS = [
        re.compile(r"\b(?:my|our)\s+(?:[\w\-]+\s+)?(?:syllabus|notes|exam\s+notes|schedule|draft|homework|assignment|grades?|tax(?:es)?|tax\s+return|resume|cv|emails?|meetings?|calendar|agenda|todo|tasks?|project|codebase|repo|budget|finances?|report|health\s+records?|benefits|bank\s+statements?|client\s+list|private\s+key|sprint\s+plan|plan)\b", re.I),
        re.compile(r"\b(?:in|on|from)\s+my\s+(?:documents|desktop|downloads|computer|laptop|drive|account|folder|file|inbox|course\s+portal)\b", re.I),
        re.compile(r"\b(?:where\s+did\s+i\s+(?:put|save|leave|store)|what\s+did\s+i\s+write)\b", re.I),
        re.compile(r"\b(?:for\s+my|i\s+have\s+an?|to\s+help\s+with\s+my)(?:\s+[\w\-]+)*?\s+(?:class|exam|course|interview|meeting|doctor|presentation|quiz|test|homework|review|midterm)\b", re.I),
        re.compile(r"\b(?:did\s+the\s+(?:professor|lecturer|teacher|ta)\s+(?:say|post|change|announce))\b", re.I),
    ]

    # Local context patterns (reading/inspecting files or local environment)
    _LOCAL_CONTEXT_PATTERNS = [
        re.compile(r"\b(?:my\s+local\s+file|this\s+directory|in\s+this\s+folder|current\s+workspace|local\s+repo|local\s+runtime|on\s+my\s+machine|on\s+my\s+pc|installed\s+on\s+my\s+(?:pc|machine|computer|system))\b", re.I),
        re.compile(r"\b(?:read|inspect|analyze|parse|summarize|contents\s+of)\s+(?:the\s+)?(?:file\s+|document\s+|log\s+)?(?:[a-zA-Z]:\\[^\s]+|\.{1,2}[\\\/][^\s]+|[a-zA-Z0-9_\-]+\.(?:txt|py|json|csv|log|md|doc|docx|pdf|xml|yaml|yml|ini|cfg|toml|html|htm))\b", re.I),
        re.compile(r"\b(?:what\s+(?:is|does)\s+in|contents\s+of)\s+[a-zA-Z]:\\[^\s]+\b", re.I),
    ]

    # Real-time / live external information patterns
    _CURRENT_INFO_PATTERNS = [
        re.compile(r"\b(?:current(?:ly)?|latest|today(?:'s)?|tonight|right\s+now|real-?time|live)\s+(?:price|stock|weather|news|headlines|score|version|release|status|rate|valuation|driver|rate\s+decision|vulnerabilit(?:y|ies)|advisories|cves?|updates?|developments?)\b", re.I),
        re.compile(r"\b(?:stock\s+price\s+of|weather\s+(?:forecast\s+)?(?:in|for)|forecast\s+(?:in|for)|current\s+price\s+of|exchange\s+rate)\b", re.I),
        re.compile(r"\b(?:who\s+won\s+(?:the\s+)?(?:[\w\-]+\s+)*(?:match|game|election)\s+(?:today|yesterday|last\s+night))\b", re.I),
        re.compile(r"\b(?:what\s+is\s+happening\s+(?:in|with)|breaking\s+news)\b", re.I),
        re.compile(r"\b(?:latest\s+version\s+of|most\s+recent\s+release\s+of|newest\s+(?:cuda|driver|release|supported\s+version|python|model))\b", re.I),
        re.compile(r"\bwhat\s+(?:is\s+today's\s+date|day\s+is\s+it\s+today|time\s+is\s+it)\b", re.I),
        re.compile(r"\b(?:reported|released|announced)\s+(?:today|this\s+week|right\s+now)\b", re.I),
    ]

    # Authoritative standard / primary reference verification
    _AUTHORITATIVE_PATTERNS = [
        re.compile(r"\b(?:verify\s+against|check\s+(?:the\s+)?(?:rfc|nist|iso|ieee|fips|pep|official\s+spec|spec(?:ification)?))\b", re.I),
        re.compile(r"\b(?:according\s+to\s+(?:the\s+)?(?:rfc|official(?:\s+[\w\-]+)?\s+doc(?:umentation)?|nist|iso|fips|pep|w3c))\b", re.I),
        re.compile(r"\b(?:cite\s+(?:the\s+)?authoritative\s+(?:source|spec(?:ification)?|standard)|official\s+standard\s+for|official\s+(?:rfc|nist|w3c|pep|iso|ieee|fips))\b", re.I),
        re.compile(r"\b(?:rfc\s+\d+|pep\s+\d+|nist\s+(?:fips|sp)?\s*\d+|w3c\s+spec(?:ification)?)\b", re.I),
        re.compile(r"\b(?:official\s+(?:job\s+description|documentation|specification|standard))\b", re.I),
    ]

    # External intelligence / peer review consultation
    _EXTERNAL_AI_PATTERNS = [
        re.compile(r"\b(?:ask|consult)\s+(?:chatgpt|gemini|claude|(?:another|an\s+external)\s+ai)\b", re.I),
        re.compile(r"\b(?:send|upload|share|email|transmit|forward)\s+.*?\b(?:to|with)\s+(?:an?\s+)?(?:the\s+)?(?:chatgpt|gemini|claude|(?:external|another)\s+ai(?:\s+model)?|online\s+verifier)\b", re.I),
        re.compile(r"\b(?:verify\s+with\s+(?:gemini|chatgpt|claude)|peer\s+review\s+from\s+ai|get\s+(?:claude|gemini|chatgpt)'s\s+perspective|have\s+another\s+ai)\b", re.I),
    ]

    # Conversational pronouns requiring session lineage
    _CONVERSATIONAL_PRONOUNS = {
        "it", "that", "this", "them", "those", "these", "that example", "the explanation",
        "the previous answer", "the inverse", "that inverse", "shorter", "make it shorter",
    }

    # Deterministic greetings and etiquette
    _GREETINGS = {
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "thanks", "thank you", "help", "who are you",
    }

    # Trap phrases: static technical definitions that use temporal/privacy words without requiring acquisition
    _STATIC_CONCEPT_TRAPS = [
        re.compile(r"\b(?:explain|what\s+is|define|how\s+does)\s+(?:the\s+)?(?:latest\s+pointer|current\s+in\s+electrical|private\s+variable|private\s+key|private\s+method)\b", re.I),
        re.compile(r"\b(?:diffie-hellman|rsa|aes|hill\s+cipher|modular\s+inverse|fermat|dijkstra|recursion|b-tree|mutex|spinlock|tail\s+call|photoelectric|atp\s+synthase|mitosis|meiosis|separation\s+of\s+powers|deontology|utilitarianism|french\s+revolution)\b", re.I),
    ]

    def __init__(self) -> None:
        pass

    def evaluate(
        self,
        query: str,
        session: Optional[ConversationSession] = None,
        world_state: Optional[WorldStateSummary] = None,
    ) -> KnowledgeSufficiencyResult:
        """
        Evaluate whether existing knowledge and context suffice to satisfy the query.
        
        Guaranteed to complete within 15ms with zero network round trips.
        """
        from astrarun.cognition.acquisition import (
            AuthorityRequirement,
            FreshnessRequirement,
            InformationNeed,
            NeedBlockingType,
            NeedType,
        )

        t0 = time.perf_counter()
        q_raw = query.strip()
        q_lower = q_raw.lower()

        # 1. Empty or whitespace
        if not q_raw:
            return KnowledgeSufficiencyResult(
                is_sufficient=False,
                reason=SufficiencyReason.AMBIGUOUS_GOAL,
                confidence=1.0,
                missing_aspects=["Query is empty."],
                explanation="No query provided to evaluate.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
            )

        # 2. Greetings and simple etiquette
        clean_punct = re.sub(r"[^\w\s]", "", q_lower).strip()
        if clean_punct in self._GREETINGS:
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=1.0,
                explanation="Conversational greeting or politeness phrasing.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
            )

        # 3. Pure closed-form arithmetic: "2 + 2", "125 * 8", "100 mod 7"
        if re.match(r"^[-+]?\d+(\.\d+)?(\s*[\+\-\*\/%]\s*[-+]?\d+(\.\d+)?)+$", q_raw):
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=1.0,
                explanation="Closed-form arithmetic expression resolvable via internal deterministic computation.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
            )

        # 4. Live Workstation System & Observation Queries (Epistemic Separation)
        # e.g., "battery percentage", "check battery", "inspect running processes", "show system memory"
        is_battery = bool(re.search(r"\b(?:battery\s+(?:percentage|status|level)|check\s+battery)\b", q_lower))
        is_process_obs = bool(re.search(r"\b(?:inspect|check|show|get|view|list)\s+(?:running\s+)?(?:process(?:es)?|system|task(?:s)?|memory|cpu|disk|window(?:s)?)\b", q_lower))
        if is_battery or is_process_obs:
            cap_id = "battery_status" if is_battery else "inspect_process"
            desc = "Live workstation battery telemetry" if is_battery else "Live workstation process/system diagnostic"
            need = InformationNeed(
                need_id="need-sys-1",
                description=desc,
                need_type=NeedType.SYSTEM_STATE,
                freshness=FreshnessRequirement.REALTIME,
                authority=AuthorityRequirement.ANY_REASONABLE,
                priority=1,
                privacy_sensitive=False,
                blocking_type=NeedBlockingType.HARD_BLOCKING,
                access_scope=LocalAccessScope.ACTIVE_FOREGROUND_RESOURCE,
                disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
            )
            return KnowledgeSufficiencyResult(
                is_sufficient=True,  # Resolvable locally via authorized workstation capability
                reason=SufficiencyReason.SUFFICIENT_OBSERVABLE_STATE,
                confidence=1.0,
                explanation=f"Live system observation required and resolvable via authorized capability '{cap_id}'.",
                observable_capability_id=cap_id,
                observation_required=True,
                information_needs=[need],
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000, "observable_capability": cap_id},
            )

        # 5. Direct Operational Commands (window snapping, direct app launch without modifiers)
        if re.match(r"^(?:snap\s+(?:current\s+)?window\s+(?:left|right))\b", q_lower):
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=1.0,
                explanation="Deterministic window control command.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000, "fast_path": True},
            )
        if re.match(r"^(?:open|launch|start)\s+(?:notepad|calculator|calc|cmd|powershell|paint|terminal)$", q_lower):
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=1.0,
                explanation="Direct local operational command with fully specified target.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000, "fast_path": True},
            )

        # 6. Session Context & Conversational Pronouns
        if session is not None and (len(session.turns) > 0 or session.get_active_topic()):
            if re.search(r"\b(?:summarize|recap|review|shorten|bullets?|whole\s+thing|example|an\s+example|more\s+detail|elaborate)\b", q_lower):
                return KnowledgeSufficiencyResult(
                    is_sufficient=True,
                    reason=SufficiencyReason.SUFFICIENT_SESSION_CONTEXT,
                    confidence=0.95,
                    explanation=f"Session summarization / continuation against topic '{session.get_active_topic()}'.",
                    metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
                )

        q_no_temporal = re.sub(
            r"\bthis\s+(?:morning|afternoon|evening|night|week|month|year|weekend|quarter|summer|winter|spring|fall)\b",
            "",
            q_lower,
        )
        has_pronoun = any(
            re.search(rf"\b{re.escape(p)}\b", q_no_temporal)
            for p in self._CONVERSATIONAL_PRONOUNS
        )
        if has_pronoun:
            if session is not None and (len(session.turns) > 0 or session.pinned_artifacts or session.get_active_topic()):
                return KnowledgeSufficiencyResult(
                    is_sufficient=True,
                    reason=SufficiencyReason.SUFFICIENT_SESSION_CONTEXT,
                    confidence=0.95,
                    explanation=f"Conversational referents resolve against active session context (topic: {session.get_active_topic()}).",
                    metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
                )
            else:
                # Pronoun without session
                is_pure_pronoun = (
                    any(q_lower == p for p in ("it", "that", "this", "do it", "fix it", "check it", "run that", "make it shorter", "shorter", "open it", "open that"))
                    or bool(re.match(r"^(?:make\s+(?:it|that|this)\s+\w+|open\s+(?:it|that|this)|explain\s+(?:it|that|this)|summarize\s+(?:it|that|this))$", q_lower))
                )
                if is_pure_pronoun:
                    return KnowledgeSufficiencyResult(
                        is_sufficient=False,
                        reason=SufficiencyReason.AMBIGUOUS_GOAL,
                        confidence=0.90,
                        missing_aspects=["Pronoun referent has no antecedent in session history."],
                        explanation="Query uses conversational pronouns without any preceding session history.",
                        metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
                    )

        # 7. Check for Static Conceptual Trap Phrases
        is_concept_trap = any(p.search(q_raw) for p in self._STATIC_CONCEPT_TRAPS)

        # 8. Multi-Dimension Semantic Analysis (Compositional Evaluation)
        needs: List[InformationNeed] = []
        reasons: List[SufficiencyReason] = []
        missing_aspects: List[str] = []

        # Check write intent: writing to a file is an operational action, not a requirement to inspect the file
        is_write_intent = bool(re.search(r"\b(?:write|put|save|create|export|dump)\b", q_lower))

        # Check primary educational/conceptual intent
        is_educational_goal = bool(re.match(
            r"^(?:explain|how\s+does|why\s+does|what\s+is|what\s+are|describe|teach\s+me|help\s+me\s+study|walk\s+me\s+through|compare|give\s+me\s+an?\s+example\s+of|calculate|derive|show\s+how)\b",
            q_lower
        ))

        # Dimension A: Current / Real-Time Information Requirement
        if not is_concept_trap:
            for pat in self._CURRENT_INFO_PATTERNS:
                m = pat.search(q_raw)
                if m:
                    match_text = m.group(0)
                    missing_aspects.append(f"Real-time or current world state: '{match_text}'")
                    reasons.append(SufficiencyReason.MISSING_CURRENT_INFORMATION)
                    needs.append(
                        InformationNeed(
                            need_id=f"need-{len(needs) + 1}",
                            description=f"Current authoritative world state: {match_text}",
                            need_type=NeedType.CURRENT,
                            freshness=FreshnessRequirement.REALTIME if any(w in match_text.lower() for w in ("stock", "price", "score", "rate")) else FreshnessRequirement.CURRENT,
                            authority=AuthorityRequirement.CORROBORATED,
                            priority=1,
                            privacy_sensitive=False,
                            blocking_type=NeedBlockingType.HARD_BLOCKING,
                            access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                            disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                        )
                    )
                    break

        # Dimension B: Authoritative Standard / Primary Document
        for pat in self._AUTHORITATIVE_PATTERNS:
            m = pat.search(q_raw)
            if m:
                match_text = m.group(0)
                missing_aspects.append(f"Authoritative standard / primary document required: '{match_text}'")
                reasons.append(SufficiencyReason.MISSING_AUTHORITATIVE_SOURCE)
                needs.append(
                    InformationNeed(
                        need_id=f"need-{len(needs) + 1}",
                        description=f"Authoritative primary standard: {match_text}",
                        need_type=NeedType.AUTHORITATIVE_REFERENCE,
                        freshness=FreshnessRequirement.STATIC,
                        authority=AuthorityRequirement.PRIMARY_REQUIRED,
                        priority=1,
                        privacy_sensitive=False,
                        blocking_type=NeedBlockingType.HARD_BLOCKING,
                        access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                        disclosure_policy=EgressDisclosurePolicy.PUBLIC_SAFE,
                    )
                )
                break

        # Dimension C: User-Specific Context / Personal Records
        for pat in self._USER_SPECIFIC_PATTERNS:
            m = pat.search(q_raw)
            if m:
                match_text = m.group(0)
                is_enrichment = is_educational_goal and bool(re.search(r"\b(?:for\s+my|i\s+have\s+an?|to\s+help\s+with\s+my)(?:\s+[\w\-]+)*?\s+(?:exam|class|course|test|presentation|interview|quiz|homework|review|midterm)\b", q_lower))
                blocking = NeedBlockingType.SOFT_ENRICHMENT if is_enrichment else NeedBlockingType.HARD_BLOCKING

                missing_aspects.append(f"User private record or personal context: '{match_text}'")
                reasons.append(SufficiencyReason.MISSING_USER_SPECIFIC_CONTEXT)
                needs.append(
                    InformationNeed(
                        need_id=f"need-{len(needs) + 1}",
                        description=f"User private context: {match_text}",
                        need_type=NeedType.USER_SPECIFIC,
                        freshness=FreshnessRequirement.CURRENT,
                        authority=AuthorityRequirement.USER_SOURCE_REQUIRED,
                        priority=1 if blocking == NeedBlockingType.HARD_BLOCKING else 2,
                        privacy_sensitive=True,
                        blocking_type=blocking,
                        access_scope=LocalAccessScope.EXPLICITLY_AUTHORIZED_USER_DIRECTORIES,
                        disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
                    )
                )
                break

        # Dimension D: Local Workstation Filesystem / Local Document Inspection
        if not is_write_intent:
            for pat in self._LOCAL_CONTEXT_PATTERNS:
                m = pat.search(q_raw)
                if m:
                    match_text = m.group(0)
                    missing_aspects.append(f"Local filesystem resource or path: '{match_text}'")
                    reasons.append(SufficiencyReason.MISSING_LOCAL_CONTEXT)
                    needs.append(
                        InformationNeed(
                            need_id=f"need-{len(needs) + 1}",
                            description=f"Local document or machine state: {match_text}",
                            need_type=NeedType.LOCAL_DOCUMENT,
                            freshness=FreshnessRequirement.CURRENT,
                            authority=AuthorityRequirement.USER_SOURCE_REQUIRED,
                            priority=1,
                            privacy_sensitive=True,
                            blocking_type=NeedBlockingType.HARD_BLOCKING,
                            access_scope=LocalAccessScope.AUTHORIZED_WORKSPACE,
                            disclosure_policy=EgressDisclosurePolicy.LOCAL_ONLY,
                        )
                    )
                    break

        # Dimension E: External AI Consultation / Peer Review & Egress Disclosure
        for pat in self._EXTERNAL_AI_PATTERNS:
            m = pat.search(q_raw)
            if m:
                match_text = m.group(0)
                # Check if query attempts to transmit private content
                has_private_mention = (
                    SufficiencyReason.MISSING_USER_SPECIFIC_CONTEXT in reasons
                    or SufficiencyReason.MISSING_LOCAL_CONTEXT in reasons
                    or any(w in q_lower for w in ("file", "notes", "report", "draft", "homework", "tax", "resume", "private", "bank", "statement", "client", "financial", "confidential", "credential", "password", "key", "budget", "salary"))
                )
                disclosure = EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED if has_private_mention else EgressDisclosurePolicy.PUBLIC_SAFE
                scope = LocalAccessScope.SENSITIVE_PERSONAL_STORES if has_private_mention else LocalAccessScope.AUTHORIZED_WORKSPACE

                if has_private_mention:
                    for prev_n in needs:
                        if prev_n.privacy_sensitive:
                            prev_n.disclosure_policy = EgressDisclosurePolicy.EXPLICIT_CONFIRMATION_REQUIRED

                missing_aspects.append(f"External AI peer review consultation: '{match_text}'")
                reasons.append(SufficiencyReason.MISSING_EXTERNAL_VERIFICATION)
                needs.append(
                    InformationNeed(
                        need_id=f"need-{len(needs) + 1}",
                        description=f"External AI consultation: {match_text}",
                        need_type=NeedType.EXTERNAL_REVIEW,
                        freshness=FreshnessRequirement.CURRENT,
                        authority=AuthorityRequirement.CORROBORATED,
                        priority=1,
                        privacy_sensitive=has_private_mention,
                        blocking_type=NeedBlockingType.HARD_BLOCKING,
                        access_scope=scope,
                        disclosure_policy=disclosure,
                    )
                )
                break

        # 9. Evaluate Need Composition & Hard-Blocking vs Soft-Enrichment
        hard_blocking_needs = [n for n in needs if n.blocking_type == NeedBlockingType.HARD_BLOCKING]
        soft_enrichment_needs = [n for n in needs if n.blocking_type == NeedBlockingType.SOFT_ENRICHMENT]

        if hard_blocking_needs:
            # Query cannot proceed without these prerequisites
            primary_reason = reasons[0] if reasons else SufficiencyReason.INSUFFICIENT_EVIDENCE
            return KnowledgeSufficiencyResult(
                is_sufficient=False,
                reason=primary_reason,
                confidence=0.95,
                missing_aspects=missing_aspects,
                explanation=f"Query requires prerequisite evidence: {'; '.join(missing_aspects)}",
                information_needs=needs,
                reasons=reasons,
                has_hard_blocking_needs=True,
                has_soft_enrichment_needs=bool(soft_enrichment_needs),
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
            )

        if soft_enrichment_needs:
            # Query CAN proceed via internal knowledge; local context is optional enrichment
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=0.92,
                missing_aspects=missing_aspects,
                explanation="Core inquiry is resolvable via internal knowledge; personal context constitutes optional enrichment.",
                information_needs=needs,
                reasons=[SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE],
                has_hard_blocking_needs=False,
                has_soft_enrichment_needs=True,
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000, "enrichment_count": len(soft_enrichment_needs)},
            )

        # 10. General Analytical / Educational Inquiry (No missing needs detected)
        if is_educational_goal or is_concept_trap:
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=0.92,
                explanation="General conceptual, theoretical, or algorithmic inquiry resolvable via internal knowledge.",
                information_needs=[],
                reasons=[SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE],
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
            )

        # 11. Underspecified check: very short fragments without intent
        tokens = [t for t in re.findall(r"\b\w+\b", q_lower)]
        if len(tokens) <= 2 and clean_punct not in ("help", "status", "date"):
            return KnowledgeSufficiencyResult(
                is_sufficient=False,
                reason=SufficiencyReason.AMBIGUOUS_GOAL,
                confidence=0.85,
                missing_aspects=["Query is underspecified with insufficient grammatical intent."],
                explanation="Very short or fragmented query with ambiguous intent.",
                information_needs=[],
                reasons=[SufficiencyReason.AMBIGUOUS_GOAL],
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
            )

        # 12. Default: Sufficient internal knowledge for standard analytical processing
        return KnowledgeSufficiencyResult(
            is_sufficient=True,
            reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
            confidence=0.85,
            explanation="Query appears self-contained and suitable for direct synthesis or governed planning.",
            information_needs=[],
            reasons=[SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE],
            metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
        )
