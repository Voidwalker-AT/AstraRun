"""Semantic UI element resolver with strict precedence and ambiguity detection."""

from __future__ import annotations

import difflib
import re
from typing import Dict, List, Optional, Set

from astrarun.core.logging import get_logger
from astrarun.interaction.models import (
    ControlType,
    ResolutionCandidate,
    ResolutionResult,
    UIElementRef,
)

logger = get_logger("astrarun.interaction.resolver")

# Semantic synonyms mapping common colloquial user words to UI control concepts
SEMANTIC_SYNONYMS: Dict[str, Set[str]] = {
    "ok": {"save", "confirm", "submit", "apply", "accept", "ok", "yes", "done"},
    "confirm": {"save", "confirm", "submit", "apply", "ok", "yes"},
    "submit": {"save", "confirm", "submit", "apply", "send"},
    "cancel": {"cancel", "close", "dismiss", "abort", "no"},
    "close": {"cancel", "close", "dismiss", "exit"},
    "search": {"search", "find", "query", "filter", "lookup"},
    "delete": {"delete", "remove", "erase", "trash", "purge"},
    "next": {"next", "continue", "forward", "proceed"},
    "back": {"back", "previous", "return"},
}


INTERACTIVE_CONTROL_TYPES: Set[ControlType] = {
    ControlType.BUTTON,
    ControlType.EDIT,
    ControlType.CHECK_BOX,
    ControlType.COMBO_BOX,
    ControlType.TAB,
    ControlType.TAB_ITEM,
    ControlType.RADIO_BUTTON,
    ControlType.HYPERLINK,
    ControlType.LIST,
    ControlType.LIST_ITEM,
    ControlType.MENU_ITEM,
}


class UIElementResolver:
    """
    Resolves natural language queries to concrete UIElementRef handles.
    Enforces deterministic precedence:
      AutomationId exact > Name exact > ControlType + Name > Semantic Synonyms > Bounded Fuzzy
    """

    @classmethod
    def resolve(
        cls,
        target_query: str,
        elements: list[UIElementRef],
        expected_type: Optional[ControlType] = None,
    ) -> ResolutionResult:
        """Resolve a natural language query against discovered UI elements."""
        if not target_query or not elements:
            return ResolutionResult(
                element=None,
                confidence=0.0,
                match_reason="Empty query or no elements provided.",
            )

        clean_query = target_query.strip().lower()
        candidates: list[ResolutionCandidate] = []

        for el in elements:
            name_lower = (el.name or "").strip().lower()
            auto_id_lower = (el.automation_id or "").strip().lower()
            class_lower = (el.class_name or "").strip().lower()

            base_score = 0.0
            reason = ""

            # 1. Exact AutomationId match (Score: 1.0)
            if auto_id_lower and auto_id_lower == clean_query:
                base_score = 1.0
                reason = f"Exact AutomationId match '{el.automation_id}'"
            # 2. Exact Name match (Score: 0.95)
            elif name_lower and name_lower == clean_query:
                base_score = 0.98 if expected_type and el.control_type == expected_type else 0.95
                reason = f"Exact Name match '{el.name}'"
            # 3. ControlType + Word boundary Match (Score: 0.90)
            elif expected_type and el.control_type == expected_type and re.search(r"\b" + re.escape(clean_query) + r"\b", name_lower):
                base_score = 0.90
                reason = f"Type & Word match '{el.name}'"
            # 4. General Word boundary Match in Name (Score: 0.85)
            elif re.search(r"\b" + re.escape(clean_query) + r"\b", name_lower):
                base_score = 0.85
                reason = f"Word boundary match in Name '{el.name}'"
            # 5. AutomationId substring / word match (Score: 0.82)
            elif clean_query in auto_id_lower:
                base_score = 0.82
                reason = f"Substring match in AutomationId '{el.automation_id}'"
            # 6. Semantic Synonym Match (Score: 0.80)
            else:
                synonyms = SEMANTIC_SYNONYMS.get(clean_query, set())
                for syn in synonyms:
                    if syn in name_lower or syn in auto_id_lower:
                        base_score = 0.85 if expected_type and el.control_type == expected_type else 0.80
                        reason = f"Semantic synonym '{syn}' match for '{clean_query}'"
                        break

                # 7. Substring in Name (Score: 0.75)
                if not base_score and clean_query in name_lower:
                    base_score = 0.75
                    reason = f"Substring match in Name '{el.name}'"

                # 8. Bounded Fuzzy Similarity (Score: 0.60 - 0.72)
                if not base_score:
                    ratio = difflib.SequenceMatcher(None, clean_query, name_lower).ratio()
                    if ratio >= 0.75:
                        base_score = round(0.60 + ratio * 0.12, 3)
                        reason = f"Fuzzy match (ratio {ratio:.2f})"

            if base_score > 0.0:
                # Give interactive controls a slight precedence over static text labels
                if el.control_type in INTERACTIVE_CONTROL_TYPES:
                    base_score += 0.04
                candidates.append(ResolutionCandidate(el, base_score, reason))

        if not candidates:
            return ResolutionResult(
                element=None,
                confidence=0.0,
                match_reason=f"No matching UI element found for query '{target_query}'.",
            )

        # Sort candidates by score descending
        candidates.sort(key=lambda c: c.score, reverse=True)

        # Ambiguity check: if top 2 candidates have very close scores (< 0.05 difference)
        if len(candidates) >= 2:
            top = candidates[0]
            runner_up = candidates[1]

            # If top is interactive and runner-up is static/non-interactive, interactive wins unambiguously
            both_interactive = (top.element.control_type in INTERACTIVE_CONTROL_TYPES and
                                runner_up.element.control_type in INTERACTIVE_CONTROL_TYPES)

            if both_interactive and (top.score - runner_up.score) < 0.05 and top.element.automation_id != runner_up.element.automation_id:
                names = [f"'{c.element.name or c.element.automation_id}' ({c.element.control_type.value})" for c in candidates[:3]]
                prompt = f"Ambiguous UI target '{target_query}'. Did you mean: {', '.join(names)}?"
                logger.info("Ambiguity detected resolving '%s': %s", target_query, prompt)
                return ResolutionResult(
                    element=None,
                    confidence=top.score,
                    match_reason="Multiple ambiguous candidates detected.",
                    candidates=candidates,
                    ambiguous=True,
                    clarification_prompt=prompt,
                )

        winner = candidates[0]
        return ResolutionResult(
            element=winner.element,
            confidence=winner.score,
            match_reason=winner.match_reason,
            candidates=candidates,
            ambiguous=False,
        )
