"""RequestBoundaryRouter: First-stage ingress boundary classifier.

Classifies incoming RequestEnvelope into META_COMMAND vs OPERATIONAL_GOAL.
Adheres strictly to the Meta Invariant:
- Targets AstraRun itself or static product metadata only
- Never inspects dynamic external workstation/application state
- Never mutates filesystem, windows, processes, clipboard, network, etc.
- Never invokes external capabilities
- Cannot hide an operational clause (composites fail closed to OPERATIONAL_GOAL)
- Boundary uncertainty fails closed to OPERATIONAL_GOAL.
"""

from __future__ import annotations

import re
from typing import Optional

from astrarun.ingress.models import IngressDecision, IngressRoute, RequestEnvelope


# Exact normalized allowlists for static product meta commands
_EXACT_HELP_PHRASES = {
    "help",
    "?",
    "what can you do",
    "capabilities",
    "commands",
    "show capabilities",
    "show commands",
    "list capabilities",
    "list commands",
    "open help",
    "show help",
}

_EXACT_HISTORY_PHRASES = {
    "history",
    "open history",
    "show history",
    "view history",
}

_EXACT_MEMORY_PHRASES = {
    "memory",
    "open memory",
    "show memory",
    "view memory",
    "learned aliases",
    "what have you learned",
}

_EXACT_SKILLS_PHRASES = {
    "skills",
    "open skills",
    "show skills",
    "view skills",
    "learned skills",
}

_EXACT_SETTINGS_PHRASES = {
    "settings",
    "open settings",
    "show settings",
    "preferences",
    "open preferences",
    "show preferences",
    "config",
    "open config",
}

_EXACT_DIAGNOSTICS_PHRASES = {
    "diagnostics",
    "open diagnostics",
    "show diagnostics",
    "system diagnostics",
    "open system diagnostics",
}

_EXACT_HOTKEY_PHRASES = {
    "hotkey",
    "hotkey status",
    "hotkey diagnostics",
    "diagnostics hotkey",
    "check hotkey",
}

_EXACT_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hiya",
    "yo",
    "sup",
    "howdy",
    "greetings",
    "good morning",
    "good afternoon",
    "good evening",
    "who are you",
    "what are you",
    "hi there",
    "hello there",
    "hey there",
    "hello friend",
    "hi friend",
}

_EXACT_ACKNOWLEDGEMENTS = {
    "thanks",
    "thank you",
    "thx",
    "ty",
    "cheers",
    "appreciate it",
    "thank you very much",
    "thanks a lot",
    "thanks so much",
    "thank you so much",
    "bye",
    "goodbye",
    "cya",
    "see ya",
    "later",
    "ok",
    "okay",
}

_COMPOUND_INDICATOR_PATTERN = re.compile(
    r"\b(?:and|then|with|also|but|now|or)\b|[;&\n]|&&|,\s*(?:then|and|now)\b",
    re.IGNORECASE,
)

_OPERATIONAL_VERBS_PATTERN = re.compile(
    r"\b(?:open|launch|start|run|close|quit|exit|terminate|kill|delete|remove|format|"
    r"copy|paste|click|type|toggle|focus|select|move|snap|maximize|minimize|restore|"
    r"turn\s+off|disconnect|connect|inspect|list|calculate|compute|simulate)\b",
    re.IGNORECASE,
)


class RequestBoundaryRouter:
    """
    First-stage ingress boundary classifier.
    
    Answers only:
    'Can this request safely remain inside AstraRun's own UI/meta layer,
     or must it enter workstation goal handling?'
    """

    def __init__(self) -> None:
        pass

    def classify(self, request: str | RequestEnvelope) -> IngressDecision:
        """Alias for classify_ingress."""
        return self.classify_ingress(request)

    def classify_ingress(self, envelope: str | RequestEnvelope) -> IngressDecision:
        """
        Classify incoming request envelope into META_COMMAND or OPERATIONAL_GOAL.
        
        Boundary uncertainty and composites fail closed to OPERATIONAL_GOAL.
        """
        if isinstance(envelope, str):
            envelope = RequestEnvelope.create(envelope)

        raw = envelope.raw_query or ""
        norm = envelope.normalized_query or " ".join(raw.strip().split())

        # 1. Empty query
        if not norm:
            return IngressDecision(
                route=IngressRoute.META_COMMAND,
                reason_code="EMPTY_INPUT",
                normalized_query=norm,
                meta_family="EMPTY_INPUT",
            )

        lower_norm = norm.lower()

        # 2. Check for compound conjunctions and chained clauses
        # Any query with compound indicators or sequential clauses cannot be pure META.
        if _COMPOUND_INDICATOR_PATTERN.search(lower_norm):
            return IngressDecision(
                route=IngressRoute.OPERATIONAL_GOAL,
                reason_code="COMPOSITE_CONTAINS_OPERATIONAL_CLAUSE",
                normalized_query=norm,
            )

        # 3. Check for comma-separated operational clauses (e.g. "hello, open notepad")
        if "," in lower_norm:
            parts = [p.strip() for p in lower_norm.split(",") if p.strip()]
            if len(parts) > 1:
                # If any sub-part contains an operational verb, reject from META
                for p in parts[1:]:
                    if _OPERATIONAL_VERBS_PATTERN.search(p):
                        return IngressDecision(
                            route=IngressRoute.OPERATIONAL_GOAL,
                            reason_code="COMPOSITE_CONTAINS_OPERATIONAL_CLAUSE",
                            normalized_query=norm,
                        )

        # 4. Strip punctuation for exact meta matching
        clean_key = re.sub(r"[!.,?]+$", "", lower_norm).strip()
        # Clean leading polite prefixes (e.g. "please help") only if remaining query is purely meta
        if clean_key.startswith("please "):
            clean_key = clean_key[7:].strip()
        elif clean_key.endswith(" please"):
            clean_key = clean_key[:-7].strip()

        # Disallow operational verbs combined with meta words if not an exact match
        # (e.g. "say hello then open calculator" would have been caught, but "open notepad" will fail below)

        # 5. Exact match against authorized META families
        if clean_key in _EXACT_HELP_PHRASES:
            return IngressDecision(
                route=IngressRoute.META_COMMAND,
                reason_code="META_HELP",
                normalized_query=norm,
                meta_family="HELP",
            )

        if clean_key in _EXACT_HISTORY_PHRASES:
            return IngressDecision(
                route=IngressRoute.META_COMMAND,
                reason_code="META_HISTORY_PANEL",
                normalized_query=norm,
                meta_family="HISTORY_PANEL",
            )

        if clean_key in _EXACT_MEMORY_PHRASES:
            return IngressDecision(
                route=IngressRoute.META_COMMAND,
                reason_code="META_MEMORY_PANEL",
                normalized_query=norm,
                meta_family="MEMORY_PANEL",
            )

        if clean_key in _EXACT_SKILLS_PHRASES:
            return IngressDecision(
                route=IngressRoute.META_COMMAND,
                reason_code="META_SKILLS_PANEL",
                normalized_query=norm,
                meta_family="SKILLS_PANEL",
            )

        if clean_key in _EXACT_SETTINGS_PHRASES:
            return IngressDecision(
                route=IngressRoute.META_COMMAND,
                reason_code="META_SETTINGS_PANEL",
                normalized_query=norm,
                meta_family="SETTINGS_PANEL",
            )

        if clean_key in _EXACT_DIAGNOSTICS_PHRASES:
            return IngressDecision(
                route=IngressRoute.META_COMMAND,
                reason_code="META_DIAGNOSTICS_PANEL",
                normalized_query=norm,
                meta_family="DIAGNOSTICS_PANEL",
            )

        if clean_key in _EXACT_HOTKEY_PHRASES:
            return IngressDecision(
                route=IngressRoute.META_COMMAND,
                reason_code="META_HOTKEY_STATUS",
                normalized_query=norm,
                meta_family="HOTKEY_STATUS",
            )

        if clean_key in _EXACT_GREETINGS:
            return IngressDecision(
                route=IngressRoute.META_COMMAND,
                reason_code="META_GREETING",
                normalized_query=norm,
                meta_family="EXACT_GREETING",
            )

        if clean_key in _EXACT_ACKNOWLEDGEMENTS:
            return IngressDecision(
                route=IngressRoute.META_COMMAND,
                reason_code="META_ACKNOWLEDGEMENT",
                normalized_query=norm,
                meta_family="EXACT_ACKNOWLEDGEMENT",
            )

        # 6. Default / Fail-Closed to OPERATIONAL_GOAL
        return IngressDecision(
            route=IngressRoute.OPERATIONAL_GOAL,
            reason_code="OPERATIONAL_DEFAULT",
            normalized_query=norm,
        )
