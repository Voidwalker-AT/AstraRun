"""Coreference identification and context-engine binding boundary.

The NLP layer identifies anaphoric reference tokens ('it', 'that', 'that process',
'that project', 'the previous one') and their spans. Final binding to verified machine
state is delegated to WorkstationContextEngine. Ambiguous candidates trigger CLARIFY.
"""

from __future__ import annotations

import re
from typing import Any
from astrarun.nlp.models import ContextualReference, NLPEntity, NLPEntityType

_PATTERNS: list[tuple[str, str]] = [
    # (regex, target_type)
    (r'(?i)\b(?:that|the|same|previous|last)\s+process\b', "process"),
    (r'(?i)\b(?:that|the|same|previous|last|this)\s+project\b', "project"),
    (r'(?i)\bthe\s+(?:previous|last)\s+one\b', "generic"),
    (r'(?i)\bthis\s+one\b', "generic"),
    (r'(?i)\b(?:it|that|this)\b', "generic"),
]


def extract_contextual_references(text: str) -> list[ContextualReference]:
    """Extract syntactic coreference tokens and their spans from raw text."""
    references: list[ContextualReference] = []
    occupied_spans: list[tuple[int, int]] = []

    for pattern_str, target_type in _PATTERNS:
        for m in re.finditer(pattern_str, text):
            s, e = m.start(), m.end()
            if any(occ_s <= s and e <= occ_e for occ_s, occ_e in occupied_spans):
                continue
            
            # Avoid matching "it" inside "exit", "git", etc.
            token = m.group(0)
            references.append(ContextualReference(
                text=token,
                target_type=target_type,
                start=s,
                end=e,
            ))
            occupied_spans.append((s, e))

    references.sort(key=lambda r: r.start)
    return references


def resolve_coreference_with_context(
    ref: ContextualReference,
    context: Any = None,
    clause_intent: str = ""
) -> ContextualReference:
    """Delegate binding of an identified reference to local WorkstationContext.
    
    If multiple plausible entities exist, sets ambiguous=True and populates candidate_ids.
    """
    if context is None:
        return ref

    target_type = ref.target_type

    # Infer target type from intent if generic
    if target_type == "generic":
        if "process" in clause_intent or "port" in clause_intent:
            target_type = "process"
        elif "project" in clause_intent or "open" in clause_intent:
            target_type = "project"

    # 1. Resolve Project Reference
    if target_type == "project":
        recent_projs = getattr(context, "recent_projects", [])
        if recent_projs:
            ref.resolved_id = recent_projs[0].project_id
            ref.resolved_value = recent_projs[0].project_id
            ref.candidate_ids = [p.project_id for p in recent_projs[:3]]
            ref.ambiguous = len(recent_projs) > 1 and "previous" in ref.text.lower()
        return ref

    # 2. Resolve Process Reference
    if target_type == "process":
        # Check recent actions for process inspections
        recent_actions = getattr(context, "recent_actions", [])
        inspected_pids: list[int] = []
        for action in recent_actions:
            if action.action_type in ("inspect_process", "inspect_port"):
                params = getattr(action, "metadata", {}) or getattr(action, "parameters", {})
                pid_val = params.get("pid")
                if pid_val is None and getattr(action, "entity_id", "").isdigit():
                    pid_val = int(action.entity_id)
                if pid_val and pid_val not in inspected_pids:
                    inspected_pids.append(pid_val)


        # Also check dev ports
        dev_ports = getattr(context, "dev_ports", [])
        for dp in dev_ports:
            if dp.pid and dp.pid not in inspected_pids:
                inspected_pids.append(dp.pid)

        if len(inspected_pids) == 1:
            ref.resolved_id = str(inspected_pids[0])
            ref.resolved_value = inspected_pids[0]
            ref.ambiguous = False
            ref.candidate_ids = [str(inspected_pids[0])]
        elif len(inspected_pids) > 1:
            # Ambiguous: multiple recent processes could be 'it'
            ref.resolved_id = None
            ref.resolved_value = None
            ref.ambiguous = True
            ref.candidate_ids = [str(p) for p in inspected_pids[:4]]
        return ref

    return ref
