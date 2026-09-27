"""Negation detection and scope attribution engine.

Identifies negation markers, determines clause-level and action-level scope,
and strictly prevents negated actions from leaking into executable proposals.
"""

from __future__ import annotations

import re
from typing import Any
from astrarun.nlp.models import Clause, Constraint, Negation
from astrarun.nlp.lexicon import get_lexicon

_RE_DIRECT_ACTION_NEGATION = re.compile(
    r'\b(?:don\'t|dont|do\s+not|never|avoid|stop)\s+(?:open|launch|start|run|kill|terminate|delete|execute|inspect|check)\b',
    re.I
)

_RE_GENERAL_NEGATION = re.compile(
    r'\b(?:don\'t|dont|do\s+not|never|avoid|not)\b',
    re.I
)

_RE_CONSTRAINT_NEGATION = re.compile(
    r'\b(?:without\s+starting|don\'t\s+start\s+anything|without\s+running|don\'t\s+run\s+anything)\b',
    re.I
)


def apply_negation_scope(clauses: list[Clause]) -> list[Negation]:
    """Analyze negation markers across clauses and attribute precise scope.
    
    Returns all detected Negation records and updates clause.negated in-place.
    """
    negations: list[Negation] = []

    for clause in clauses:
        clause_text = clause.text.strip()
        lowered = clause_text.lower()

        # 1. Check for startup constraint negations e.g. "without starting the server"
        if _RE_CONSTRAINT_NEGATION.search(clause_text):
            clause.constraints.append(Constraint(
                type="NO_STARTUP_ACTIONS",
                value=True,
                raw_text=clause_text,
            ))
            # If the entire clause is just the constraint (e.g. "don't start anything")
            if re.match(r'^(?:and\s+)?(?:don\'t|dont|do\s+not)\s+start\s+anything\b', lowered):
                clause.negated = True
                neg = Negation(
                    text="don't start anything",
                    target_clause_idx=clause.idx,
                    target_action="startup_actions",
                    scope_text=clause_text,
                )
                clause.negation_details = neg
                negations.append(neg)
                continue

        # 2. Check for direct action negation: "don't kill node", "never open AstraRun"
        match_direct = _RE_DIRECT_ACTION_NEGATION.search(clause_text)
        if match_direct:
            clause.negated = True
            neg = Negation(
                text=match_direct.group(0),
                target_clause_idx=clause.idx,
                target_action=clause.action,
                scope_text=clause_text,
            )
            clause.negation_details = neg
            negations.append(neg)
            continue

        # 3. Check for leading negation word in clause: "don't ...", "not ..."
        match_general = _RE_GENERAL_NEGATION.search(clause_text)
        if match_general:
            # Check if this is a negative imperative: starts with don't/never
            first_words = lowered.split()[:2]
            if any(w in ("don't", "dont", "never", "not") for w in first_words) or lowered.startswith("do not"):
                clause.negated = True
                neg = Negation(
                    text=match_general.group(0),
                    target_clause_idx=clause.idx,
                    target_action=clause.action,
                    scope_text=clause_text,
                )
                clause.negation_details = neg
                negations.append(neg)
            else:
                # Embedded negation e.g. "open AstraRun without..." -> constraint, not clause negation
                pass

    return negations


def verify_negation_safety(clauses: list[Clause], proposed_actions: list[Any]) -> None:
    """Strict security invariant: Negated actions MUST NEVER be proposed.
    
    Raises:
        RuntimeError: If a proposed action matches or originated from a negated clause.
    """
    clause_map = {c.idx: c for c in clauses}
    for prop in proposed_actions:
        src_idx = getattr(prop, "source_clause_idx", None)
        tool_name = getattr(prop, "tool_name", "") or getattr(prop, "tool", "")
        if src_idx is not None and src_idx in clause_map:
            src_clause = clause_map[src_idx]
            if src_clause.negated:
                raise RuntimeError(
                    f"CRITICAL SAFETY VIOLATION: Negated clause {src_clause.idx} ('{src_clause.text}') "
                    f"leaked into proposed action '{tool_name}'!"
                )
        # Also check direct clause negation matches
        for c in clauses:
            if c.negated and c.action and c.action == tool_name:
                raise RuntimeError(
                    f"CRITICAL SAFETY VIOLATION: Negated clause {c.idx} ('{c.text}') "
                    f"directly leaked into proposed action '{tool_name}'!"
                )

