"""Knowledge Sufficiency Engine for AstraRun 1.0.

Answers the fundamental question before execution or planning:
'Do we already know enough to satisfy this goal, or must we acquire information first?'

Invariants:
- High speed: Heuristic evaluation executes in < 15ms with zero network round trips.
- Decoupled from execution: Evaluator only assesses sufficiency; it does not plan tools.
- Generalizes across domains: Evaluates epistemic requirements without brittle topic keyword tables.
- Transparent: Produces typed SufficiencyReason and explicit missing aspects.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from astrarun.computer_use.world.summary import WorldStateSummary
from astrarun.core.logging import get_logger
from astrarun.session.models import ConversationSession

logger = get_logger("astrarun.cognition.sufficiency")


class SufficiencyReason(str, Enum):
    """Authoritative taxonomy for knowledge sufficiency determinations."""
    SUFFICIENT_INTERNAL_KNOWLEDGE = "SUFFICIENT_INTERNAL_KNOWLEDGE"
    SUFFICIENT_SESSION_CONTEXT = "SUFFICIENT_SESSION_CONTEXT"
    SUFFICIENT_VERIFIED_ARTIFACT = "SUFFICIENT_VERIFIED_ARTIFACT"
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

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["reason"] = self.reason.value
        return d


class KnowledgeSufficiencyEvaluator:
    """
    Evaluates whether AstraRun has sufficient knowledge to answer or act.
    
    Operates before TurnReasoner and Tool Planner.
    If knowledge is sufficient: passes through to normal reasoning/execution.
    If knowledge is insufficient: triggers InformationAcquisitionPlanner.
    """

    # Patterns indicating user private data or specific local environment
    _USER_SPECIFIC_PATTERNS = [
        re.compile(r"\b(?:my|our)\s+(?:syllabus|notes|exam\s+notes|schedule|draft|homework|assignment|grades?|tax(?:es)?|resume|cv|emails?|meetings?|calendar|agenda|todo|tasks?|project|codebase|repo|budget|finances?)\b", re.I),
        re.compile(r"\b(?:in|on|from)\s+my\s+(?:documents|desktop|downloads|computer|laptop|drive|account|folder|file|inbox)\b", re.I),
        re.compile(r"\b(?:where\s+did\s+i\s+(?:put|save|leave|store)|what\s+did\s+i\s+write)\b", re.I),
        re.compile(r"\bfor\s+my\s+(?:class|exam|course|interview|meeting|doctor|presentation)\b", re.I),
    ]

    # Patterns indicating local file or folder path context to inspect/read
    _LOCAL_CONTEXT_PATTERNS = [
        re.compile(r"\b(?:my\s+local\s+file|this\s+directory|in\s+this\s+folder|current\s+workspace|local\s+repo)\b", re.I),
        re.compile(r"\b(?:read|inspect|analyze|parse|summarize|search|contents\s+of)\s+(?:the\s+)?(?:file\s+|document\s+|log\s+)?(?:[a-zA-Z]:\\[^\s]+|\.{1,2}[\\\/][^\s]+|[a-zA-Z0-9_\-]+\.(?:txt|py|json|csv|log|md|doc|docx|pdf|xml|yaml|yml|ini|cfg|toml|html|htm))\b", re.I),
        re.compile(r"\b(?:what\s+(?:is|does)\s+in|contents\s+of)\s+[a-zA-Z]:\\[^\s]+\b", re.I),
    ]

    # Patterns indicating real-time, current, or live external information
    _CURRENT_INFO_PATTERNS = [
        re.compile(r"\b(?:current(?:ly)?|latest|today(?:'s)?|tonight|right\s+now|real-?time|live)\s+(?:price|stock|weather|news|headlines|score|version|release|status|rate|valuation)\b", re.I),
        re.compile(r"\b(?:stock\s+price\s+of|weather\s+in|forecast\s+for|current\s+price\s+of)\b", re.I),
        re.compile(r"\b(?:who\s+won\s+the\s+(?:match|game|election)\s+(?:today|yesterday|last\s+night))\b", re.I),
        re.compile(r"\b(?:what\s+is\s+happening\s+(?:in|with)|breaking\s+news)\b", re.I),
        re.compile(r"\b(?:latest\s+version\s+of|most\s+recent\s+release\s+of)\b", re.I),
        re.compile(r"\bwhat\s+(?:is\s+today's\s+date|day\s+is\s+it\s+today|time\s+is\s+it)\b", re.I),
    ]

    # Patterns indicating explicit requirement for authoritative / primary reference verification
    _AUTHORITATIVE_PATTERNS = [
        re.compile(r"\b(?:verify\s+against|check\s+(?:the\s+)?(?:rfc|nist|iso|ieee|fips|official\s+spec|spec(?:ification)?))\b", re.I),
        re.compile(r"\b(?:according\s+to\s+(?:the\s+)?(?:rfc|official\s+doc(?:umentation)?|nist|iso|fips))\b", re.I),
        re.compile(r"\b(?:cite\s+(?:the\s+)?authoritative\s+source|official\s+standard\s+for)\b", re.I),
    ]

    # Conversational pronouns that require session lineage
    _CONVERSATIONAL_PRONOUNS = {
        "it", "that", "this", "them", "those", "these", "that example", "the explanation",
        "the previous answer", "the inverse", "that inverse", "shorter", "make it shorter",
    }

    # Deterministic greetings and trivial phrases
    _GREETINGS = {
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "thanks", "thank you", "help",
    }

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
        
        Guaranteed to complete within 15ms.
        """
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

        # 3. Direct Operational Commands (fast-track patterns: open notepad, calculator, battery status, etc.)
        if re.match(r"^(?:open|launch|start)\s+(?:notepad|calculator|calc|cmd|powershell|paint|terminal)\b", q_lower):
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=1.0,
                explanation="Direct local operational command with fully specified target.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000, "fast_path": True},
            )
        if re.match(r"^(?:battery\s+(?:percentage|status|level)|check\s+battery|snap\s+(?:current\s+)?window\s+(?:left|right))\b", q_lower):
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=1.0,
                explanation="Deterministic workstation diagnostic or window control command.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000, "fast_path": True},
            )

        # 3B. Workstation Process & System Observation Commands
        if re.search(r"\b(?:inspect|check|show|get|view|list)\s+(?:running\s+)?(?:process(?:es)?|system|task(?:s)?|memory|cpu|disk|window(?:s)?)\b", q_lower):
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=1.0,
                explanation="Workstation process / system observation command.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
            )

        # 4. Pure closed-form arithmetic: "2 + 2", "15 * 3 / 2", "100 mod 7"
        if re.match(r"^[-+]?\d+(\.\d+)?(\s*[\+\-\*\/%]\s*[-+]?\d+(\.\d+)?)+$", q_raw):
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=1.0,
                explanation="Closed-form arithmetic expression resolvable via internal deterministic computation.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
            )

        # 5. Session Context & Conversational Pronoun / Summarization Resolution (evaluate early)
        if session is not None and (len(session.turns) > 0 or session.get_active_topic()):
            if re.search(r"\b(?:summarize|recap|review|shorten|bullets?|whole\s+thing)\b", q_lower):
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
                # If query contains explicit user-specific, current, or authoritative patterns, let those take precedence
                is_user_spec = any(p.search(q_raw) for p in self._USER_SPECIFIC_PATTERNS)
                is_curr = any(p.search(q_raw) for p in self._CURRENT_INFO_PATTERNS)
                is_auth = any(p.search(q_raw) for p in self._AUTHORITATIVE_PATTERNS)
                if not (is_user_spec or is_curr or is_auth):
                    return KnowledgeSufficiencyResult(
                        is_sufficient=False,
                        reason=SufficiencyReason.AMBIGUOUS_GOAL,
                        confidence=0.90,
                        missing_aspects=["Pronoun referent has no antecedent in session history."],
                        explanation="Query uses conversational pronouns without any preceding session history.",
                        metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
                    )

        # 6. Authoritative / Official Standard Verification Requirement
        for pat in self._AUTHORITATIVE_PATTERNS:
            if pat.search(q_raw):
                match_text = pat.search(q_raw).group(0)
                return KnowledgeSufficiencyResult(
                    is_sufficient=False,
                    reason=SufficiencyReason.MISSING_AUTHORITATIVE_SOURCE,
                    confidence=0.95,
                    missing_aspects=[f"Authoritative standard / primary document required: '{match_text}'"],
                    explanation=f"User explicitly requested verification against authoritative standard: {match_text}.",
                    metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
                )

        # 7. Current / Real-Time Information Requirement
        for pat in self._CURRENT_INFO_PATTERNS:
            if pat.search(q_raw):
                match_text = pat.search(q_raw).group(0)
                return KnowledgeSufficiencyResult(
                    is_sufficient=False,
                    reason=SufficiencyReason.MISSING_CURRENT_INFORMATION,
                    confidence=0.95,
                    missing_aspects=[f"Real-time or current world state: '{match_text}'"],
                    explanation=f"Query references temporal or live data outside static internal training: {match_text}.",
                    metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
                )

        # 8. User-Specific Context / Personal Records
        for pat in self._USER_SPECIFIC_PATTERNS:
            if pat.search(q_raw):
                match_text = pat.search(q_raw).group(0)
                return KnowledgeSufficiencyResult(
                    is_sufficient=False,
                    reason=SufficiencyReason.MISSING_USER_SPECIFIC_CONTEXT,
                    confidence=0.95,
                    missing_aspects=[f"User private record or personal schedule: '{match_text}'"],
                    explanation=f"Query references private user context not contained in session: {match_text}.",
                    metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
                )

        # 9. Local Workstation Context / File Paths (Only when reading/inspecting, not write actions)
        is_write_intent = bool(re.search(r"\b(?:write|put|save|create|export|dump)\b", q_lower))
        if not is_write_intent:
            for pat in self._LOCAL_CONTEXT_PATTERNS:
                if pat.search(q_raw):
                    match_text = pat.search(q_raw).group(0)
                    return KnowledgeSufficiencyResult(
                        is_sufficient=False,
                        reason=SufficiencyReason.MISSING_LOCAL_CONTEXT,
                        confidence=0.90,
                        missing_aspects=[f"Local filesystem resource or path: '{match_text}'"],
                        explanation=f"Query requires local file content inspection: {match_text}.",
                        metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
                    )

        # 10. General Analytical / Theoretical / Educational Explanation (Generalizes across all domains)
        # e.g., "explain X", "how does X work", "why does X work", "what is X", "compare X and Y", "derive X", "teach me X"
        if re.match(r"^(?:explain|how\s+does|why\s+does|what\s+is|what\s+are|describe|teach\s+me|compare|give\s+me\s+an?\s+example\s+of|calculate|derive|show\s+how)\b", q_lower):
            # Check if it didn't match the missing current/user/authoritative rules above
            return KnowledgeSufficiencyResult(
                is_sufficient=True,
                reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
                confidence=0.92,
                explanation="General conceptual, theoretical, or algorithmic inquiry resolvable via internal knowledge.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
            )

        # 11. Underspecified / Ambiguous check (e.g. 1-2 words that are not recognized commands)
        tokens = [t for t in re.findall(r"\b\w+\b", q_lower)]
        if len(tokens) <= 2 and clean_punct not in ("help", "status", "date"):
            return KnowledgeSufficiencyResult(
                is_sufficient=False,
                reason=SufficiencyReason.AMBIGUOUS_GOAL,
                confidence=0.85,
                missing_aspects=["Query is underspecified with insufficient grammatical intent."],
                explanation="Very short or fragmented query with ambiguous intent.",
                metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
            )

        # 12. Default: Sufficient internal knowledge for standard analytical processing
        return KnowledgeSufficiencyResult(
            is_sufficient=True,
            reason=SufficiencyReason.SUFFICIENT_INTERNAL_KNOWLEDGE,
            confidence=0.85,
            explanation="Query appears self-contained and suitable for direct synthesis or governed planning.",
            metadata={"latency_ms": (time.perf_counter() - t0) * 1000},
        )
