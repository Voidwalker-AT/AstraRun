"""Clause decomposition and ordering analysis for multi-action utterances.

Decomposes compound sentences into ordered atomic Clauses, identifies
conjunction types (THEN, BEFORE, AFTER, CONJUNCTION), normalizes politeness,
and assigns entities and constraints to their respective clause scopes.
"""

from __future__ import annotations

import re
from typing import Any
from astrarun.nlp.models import (
    Clause,
    Constraint,
    NLPEntity,
    NLPEntityType,
    OrderingRelation,
)
from astrarun.nlp.lexicon import get_lexicon

# Conjunction regex patterns ordered by specificity
_CONJUNCTION_RULES: list[tuple[re.Pattern, OrderingRelation, str]] = [
    (re.compile(r'\b(?:and\s+then|after\s+that|then|afterwards|subsequently)\b', re.I), OrderingRelation.THEN, "sequence"),
    (re.compile(r'\bbefore\b', re.I), OrderingRelation.BEFORE, "precedence_before"),
    (re.compile(r'\bafter\b', re.I), OrderingRelation.AFTER, "precedence_after"),
    (re.compile(r'\b(?:but|however|except|without)\b', re.I), OrderingRelation.CONJUNCTION, "contrast"),
    (re.compile(r'\b(?:and|also|as\s+well\s+as|plus)\b', re.I), OrderingRelation.CONJUNCTION, "conjunction"),
    (re.compile(r'&&|&', re.I), OrderingRelation.THEN, "shell_chain"),
    (re.compile(r';', re.I), OrderingRelation.THEN, "semicolon"),
]


# Action classification rules mapping text cues to canonical actions
_ACTION_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # (regex, canonical_action, intent_group)
    (re.compile(r'\b(?:why\s+is\s+(?:port|it|this)|explain|diagnose|summarize|write\s+code\s+for|how\s+do\s+i|why\s+did\s+my\s+server\s+crash|figure\s+out\s+what\'s\s+wrong|fix\s+my\s+development\s+environment|decide\s+which\s+project)\b', re.I), "ai_query", "ai_query"),
    (re.compile(r'\b(?:kill|terminate|stop|end\s+process|abort)\b', re.I), "terminate_process", "process_action"),
    (re.compile(r'\b(?:show\s+running\s+applications|show\s+running\s+apps|list\s+running\s+applications|list\s+running\s+apps|running\s+applications|running\s+apps)\b', re.I), "list_running_applications", "application_action"),
    (re.compile(r'\b(?:system\s+status|system\s+summary|workstation\s+status|system\s+info)\b', re.I), "system_summary", "system_action"),
    (re.compile(r'\b(?:gpu\s+status|gpu\s+usage|show\s+gpu|vram\s+status)\b', re.I), "gpu_status", "system_action"),
    (re.compile(r'\b(?:memory\s+status|show\s+memory(?:\s+usage)?|ram\s+usage|how\s+much\s+ram|ram\s+status|free\s+ram)\b', re.I), "memory_status", "system_action"),
    (re.compile(r'\b(?:cpu\s+status|cpu\s+usage|show\s+cpu|cpu\s+utilization)\b', re.I), "cpu_status", "system_action"),
    (re.compile(r'\b(?:show\s+all\s+listening\s+ports|show\s+listening\s+ports|list\s+listening\s+ports|all\s+listening\s+ports)\b', re.I), "list_listening_ports", "network_action"),
    (re.compile(r'\b(?:show\s+(?:node|python|all)?\s*processes|list\s+processes|running\s+processes|highest\s+cpu\s+process|process\s+using\s+(?:the\s+)?most\s+memory)\b', re.I), "list_processes", "process_action"),
    (re.compile(r'\b(?:show\s+windows\s+for|windows\s+for)\b', re.I), "windows_for_application", "window_action"),
    (re.compile(r'\b(?:list\s+windows|show\s+windows|all\s+windows|desktop\s+windows)\b', re.I), "list_windows", "window_action"),
    (re.compile(r'\b(?:foreground\s+window|active\s+window|current\s+window)\b', re.I), "foreground_window", "window_action"),
    (re.compile(r'\b(?:snap\s+.*(?:left|half\s+left)|tile\s+left)\b', re.I), "snap_window_left", "window_action"),
    (re.compile(r'\b(?:snap\s+.*(?:right|half\s+right)|tile\s+right)\b', re.I), "snap_window_right", "window_action"),
    (re.compile(r'\b(?:minimize\s+(?:window|this)|minimize)\b', re.I), "minimize_window", "window_action"),
    (re.compile(r'\b(?:maximize\s+(?:window|this)|maximize)\b', re.I), "maximize_window", "window_action"),
    (re.compile(r'\b(?:restore\s+(?:window|this)|restore)\b', re.I), "restore_window", "window_action"),
    (re.compile(r'\b(?:move\s+.*to\s+monitor|move\s+to\s+monitor|send\s+to\s+monitor)\b', re.I), "move_window_to_monitor", "window_action"),
    (re.compile(r'\b(?:move\s+window|position\s+window)\b', re.I), "move_window", "window_action"),
    (re.compile(r'\b(?:resize\s+window)\b', re.I), "resize_window", "window_action"),
    (re.compile(r'\b(?:close\s+(?:this\s+)?window|close\s+this)\b', re.I), "close_window", "window_action"),
    (re.compile(r'\b(?:arrange\s+desktop|tile\s+windows|tile\s+all)\b', re.I), "arrange_desktop", "window_action"),
    (re.compile(r'\b(?:undo\s+window|undo\s+layout|undo\s+last\s+window)\b', re.I), "undo_last_window_move", "window_action"),
    (re.compile(r'\b(?:what(?:\'s|\s+is|\s+are)\s+(?:using|on|running\s+on)|who\s+is\s+using|which\s+process\s+has|inspect\s+port|check\s+port|show\s+port|status\s+of\s+port|port\s+\d+\s+status)\b', re.I), "inspect_port", "inspect_action"),
    (re.compile(r'\b(?:how\s+much\s+memory|inspect\s+process|check\s+process|process\s+info|process\s+details|process\s+status)\b', re.I), "inspect_process", "inspect_action"),
    (re.compile(r'\b(?:inspect|check|show)\b', re.I), "inspect_port", "inspect_action"), # Default to inspection if ambiguous
    (re.compile(r'\b(?:find|search|look\s+for|locate|newest\s+pdf|latest\s+screenshot|recent\s+files)\b', re.I), "find_file", "search_action"),
    (re.compile(r'\b(?:focus\s+(?:window|this)|switch\s+to\s+window|activate\s+window)\b', re.I), "focus_window", "window_action"),
    (re.compile(r'\b(?:copy(?:\s+this|\s+selection)?)\b', re.I), "press_keyboard_shortcut", "interaction_action"),
    (re.compile(r'\b(?:paste(?:\s+here|\s+text)?)\b', re.I), "press_keyboard_shortcut", "interaction_action"),
    (re.compile(r'\b(?:select\s+all(?:\s+text)?)\b', re.I), "press_keyboard_shortcut", "interaction_action"),
    (re.compile(r'^(?:type|enter text)$', re.I), "type_text", "interaction_action"),
    (re.compile(r'^(?:snap|tile)$', re.I), "snap_window_left", "window_action"),
    (re.compile(r'\b(?:type\s+|enter\s+text\s+)\b', re.I), "type_text", "interaction_action"),
    (re.compile(r'\b(?:press\s+|shortcut\s+)\b', re.I), "press_keyboard_shortcut", "interaction_action"),
    (re.compile(r'\b(?:click\s+)\b', re.I), "click_ui_element", "interaction_action"),
    (re.compile(r'\b(?:open\s+(?:project|repo|my\s+project)|bring\s+up\s+project|switch\s+to\s+project|load\s+project)\b', re.I), "open_project", "project_action"),
    (re.compile(r'\b(?:open|launch|start|run|bring\s+up)\b', re.I), "open_project", "launcher_action"),
]


def strip_politeness(text: str) -> str:
    """Strip polite framing words while preserving core content."""
    lexicon = get_lexicon()
    prefixes = lexicon.get("politeness_prefixes", [])
    result = text.strip()
    
    # Check leading prefixes
    lowered = result.lower()
    for prefix in sorted(prefixes, key=len, reverse=True):
        if lowered.startswith(prefix + " "):
            result = result[len(prefix) + 1:].strip()
            lowered = result.lower()
            break

    # Strip trailing please / thank you
    result = re.sub(r'(?i),\s*please\s*$', '', result)
    result = re.sub(r'(?i)\s+please\s*$', '', result)
    return result


def infer_action_and_intent(
    clause_text: str,
    clause_entities: list[NLPEntity]
) -> tuple[str, str, float]:
    """Determine the canonical action, intent category, and confidence for a clause."""
    text_clean = clause_text.strip()
    
    # 1. Check for AI query semantics (questions like "why is port 3000 busy")
    if re.search(r'\b(?:why\s+is|explain|diagnose|analyze|how\s+do\s+i|write\s+code|why\s+did\s+my\s+server|figure\s+out|fix\s+my|decide\s+which)\b', text_clean, re.I):
        return ("ai_query", "ai_query", 0.95)

    # 2. Check for process termination
    if re.search(r'\b(?:kill|terminate|stop|end\s+process)\b', text_clean, re.I):
        return ("terminate_process", "process_action", 0.98)

    # 3. Check for application management (focus / close / list running)
    has_app = any(e.type == NLPEntityType.APPLICATION for e in clause_entities)
    has_proj = any(e.type == NLPEntityType.PROJECT for e in clause_entities)
    has_port = any(e.type == NLPEntityType.PORT for e in clause_entities)
    has_pid = any(e.type == NLPEntityType.PROCESS for e in clause_entities)

    if re.search(r'\b(?:show\s+running\s+applications|show\s+running\s+apps|list\s+running\s+applications|list\s+running\s+apps|running\s+applications|running\s+apps)\b', text_clean, re.I):
        return ("list_running_applications", "application_action", 0.98)

    if has_app and re.search(r'\b(?:focus|switch\s+to)\b', text_clean, re.I):
        return ("focus_application", "application_action", 0.95)

    if has_app and re.search(r'\b(?:close|quit)\b', text_clean, re.I):
        return ("close_application", "application_action", 0.95)

    if has_app and re.search(r'\b(?:show\s+windows\s+for|windows\s+for)\b', text_clean, re.I):
        return ("windows_for_application", "window_action", 0.95)

    # 3b. Window Management Capabilities (v0.9)
    if re.search(r'\b(?:list\s+windows|show\s+windows|all\s+windows|desktop\s+windows|open\s+windows)\b', text_clean, re.I):
        return ("list_windows", "window_action", 0.98)

    if re.search(r'\b(?:foreground\s+window|active\s+window|current\s+window)\b', text_clean, re.I):
        return ("foreground_window", "window_action", 0.98)

    if re.search(r'\b(?:snap\s+.*(?:left|half\s+left)|tile\s+left)\b', text_clean, re.I):
        return ("snap_window_left", "window_action", 0.95)

    if re.search(r'\b(?:snap\s+.*(?:right|half\s+right)|tile\s+right)\b', text_clean, re.I):
        return ("snap_window_right", "window_action", 0.95)

    if re.search(r'\b(?:minimize\s+(?:window|this)|minimize)\b', text_clean, re.I):
        return ("minimize_window", "window_action", 0.95)

    if re.search(r'\b(?:maximize\s+(?:window|this)|maximize)\b', text_clean, re.I):
        return ("maximize_window", "window_action", 0.95)

    if re.search(r'\b(?:restore\s+(?:window|this)|restore)\b', text_clean, re.I):
        return ("restore_window", "window_action", 0.95)

    if re.search(r'\b(?:move\s+.*to\s+monitor|move\s+to\s+monitor|send\s+to\s+monitor)\b', text_clean, re.I):
        return ("move_window_to_monitor", "window_action", 0.95)

    if re.search(r'\b(?:move\s+window|position\s+window)\b', text_clean, re.I):
        return ("move_window", "window_action", 0.95)

    if re.search(r'\b(?:resize\s+window)\b', text_clean, re.I):
        return ("resize_window", "window_action", 0.95)

    if re.search(r'\b(?:close\s+(?:this\s+)?window|close\s+this)\b', text_clean, re.I):
        return ("close_window", "window_action", 0.95)

    if re.search(r'\b(?:arrange\s+desktop|tile\s+windows|tile\s+all)\b', text_clean, re.I):
        return ("arrange_desktop", "window_action", 0.95)

    if re.search(r'\b(?:undo\s+window|undo\s+layout|undo\s+last\s+window)\b', text_clean, re.I):
        return ("undo_last_window_move", "window_action", 0.98)

    if re.search(r'\b(?:focus\s+(?:window|this)|switch\s+to\s+window|activate\s+window)\b', text_clean, re.I):
        return ("focus_window", "window_action", 0.95)

    if re.search(r'\b(?:copy(?:\s+this|\s+selection)?)\b', text_clean, re.I):
        return ("press_keyboard_shortcut", "interaction_action", 0.95)

    if re.search(r'\b(?:paste(?:\s+here|\s+text)?)\b', text_clean, re.I):
        return ("press_keyboard_shortcut", "interaction_action", 0.95)

    if re.search(r'\b(?:select\s+all(?:\s+text)?)\b', text_clean, re.I):
        return ("press_keyboard_shortcut", "interaction_action", 0.95)

    if text_clean.lower() in ("type", "type text"):
        return ("type_text", "interaction_action", 0.90)

    if text_clean.lower() in ("snap", "snap window"):
        return ("snap_window_left", "window_action", 0.90)

    # 3c. UI Interaction Capabilities (v0.10)
    if re.search(r'\b(?:type\s+|enter\s+text\s+)\b', text_clean, re.I):
        return ("type_text", "interaction_action", 0.95)

    if re.search(r'\b(?:press\s+|shortcut\s+)\b', text_clean, re.I):
        return ("press_keyboard_shortcut", "interaction_action", 0.95)

    if re.search(r'\b(?:click\s+)\b', text_clean, re.I):
        return ("click_ui_element", "interaction_action", 0.95)

    # 4. Check for system health status queries
    if re.search(r'\b(?:system\s+status|system\s+summary|workstation\s+status|system\s+info)\b', text_clean, re.I):
        return ("system_summary", "system_action", 0.98)

    if re.search(r'\b(?:gpu\s+status|gpu\s+usage|show\s+gpu|vram\s+status)\b', text_clean, re.I):
        return ("gpu_status", "system_action", 0.98)

    if re.search(r'\b(?:memory\s+status|show\s+memory(?:\s+usage)?|ram\s+usage|how\s+much\s+ram|ram\s+status|free\s+ram)\b', text_clean, re.I):
        return ("memory_status", "system_action", 0.98)

    if re.search(r'\b(?:cpu\s+status|cpu\s+usage|show\s+cpu|cpu\s+utilization)\b', text_clean, re.I):
        return ("cpu_status", "system_action", 0.98)

    if re.search(r'\b(?:disk\s+status|disk\s+usage|show\s+disk|free\s+disk|storage\s+status)\b', text_clean, re.I):
        return ("disk_status", "system_action", 0.98)

    if re.search(r'\b(?:battery\s+status|battery\s+level|show\s+battery|battery\s+health)\b', text_clean, re.I):
        return ("battery_status", "system_action", 0.98)

    if re.search(r'\b(?:audio\s+status|volume\s+status|sound\s+status|show\s+audio)\b', text_clean, re.I):
        return ("audio_status", "system_action", 0.98)

    # 5. Check for network listing
    if re.search(r'\b(?:(?:show\s+all\s+|list\s+all\s+|show\s+|list\s+|all\s+)?(?:listening\s+ports|open\s+ports))\b', text_clean, re.I):
        return ("list_listening_ports", "network_action", 0.98)

    if re.search(r'\b(?:network\s+connections|list\s+network\s+connections|network\s+status|show\s+network\s+connections)\b', text_clean, re.I):
        return ("list_network_connections", "network_action", 0.98)

    # 6. Check for process listing
    if re.search(r'\b(?:show\s+(?:node|python|all)?\s*processes|list\s+processes|running\s+processes|highest\s+cpu\s+process|process\s+using\s+(?:the\s+)?most\s+memory)\b', text_clean, re.I):
        return ("list_processes", "process_action", 0.95)

    # 7. Check for project status / git
    if has_proj and re.search(r'\b(?:what\s+branch\s+is|is\s+.*dirty|branch\s+of|git\s+status)\b', text_clean, re.I):
        return ("project_git_status", "project_action", 0.95)

    if has_proj and re.search(r'\b(?:status\s+of)\b', text_clean, re.I):
        return ("project_status", "project_action", 0.95)

    # 8. Check for port inspection
    if has_port and re.search(r'\b(?:inspect|check|show|what|who|which|status|busy|occupied|listen)\b', text_clean, re.I):
        return ("inspect_port", "inspect_action", 0.98)

    # Bare port questions like "port 3000" or "what is on 3000" or "port 3000 status"
    if has_port and not has_proj and not re.search(r'\b(?:kill|terminate|stop)\b', text_clean, re.I):
        return ("inspect_port", "inspect_action", 0.92)

    # 9. Process inspection
    if has_pid or re.search(r'\b(?:how\s+much\s+memory|inspect\s+process|check\s+process|process\s+info|process\s+details)\b', text_clean, re.I):
        if not re.search(r'\b(?:kill|terminate|stop)\b', text_clean, re.I):
            return ("inspect_process", "inspect_action", 0.95)

    # 10. File search
    if re.search(r'\b(?:find|search\s+for|look\s+for|pdf|screenshot|downloaded|recent\s+files)\b', text_clean, re.I) and not has_proj:
        return ("find_file", "search_action", 0.90)

    # 11. Web search
    if re.search(r'\b(?:search\s+google|search\s+youtube|google|search\s+web)\b', text_clean, re.I):
        return ("search_web", "web_action", 0.95)

    # 12. Startup / server actions
    if re.search(r'\b(?:start\s+(?:the\s+)?server|start\s+anything|run\s+anything|startup)\b', text_clean, re.I):
        return ("startup_actions", "startup_action", 0.95)

    if re.search(r'\b(?:run\s+(?:the\s+)?(?:(?:approved|safe)\s+)*test(?:\s+command)?|run\s+tests?|run\s+test\s+command)\b', text_clean, re.I):
        return ("run_project_command", "project_action", 0.95)

    # 13. Project open / launcher
    if has_proj:
        return ("open_project", "project_action", 0.98)

    # 14. App launch
    if has_app:
        return ("open_app", "launcher_action", 0.95)

    # Check pattern matches
    for pat, act, intent in _ACTION_PATTERNS:
        if pat.search(text_clean):
            return (act, intent, 0.85)

    # Default fallback
    return ("open_project" if "project" in text_clean.lower() else "unsupported", "unknown", 0.5)


def decompose_clauses(
    raw_text: str,
    entities: list[NLPEntity]
) -> tuple[list[Clause], list[tuple[int, OrderingRelation, int]]]:
    """Split utterance into atomic Clauses with ordering relations.
    
    Preserves exact clause text and assigns entities that fall inside
    the clause character span.
    """
    cleaned_text = raw_text.strip()
    
    # Find all conjunction splitting points
    split_points: list[tuple[int, int, OrderingRelation, str]] = []

    # Special case: comma followed by "just" or "but" (e.g. "don't kill node, just inspect it")
    for m in re.finditer(r',\s*(?:but|just|then|after\s+that|also|and\s+then|and)\b', cleaned_text, re.I):
        split_points.append((m.start(), m.end(), OrderingRelation.THEN if "then" in m.group(0).lower() else OrderingRelation.CONJUNCTION, "comma_conjunction"))

    for pat, rel, name in _CONJUNCTION_RULES:
        for m in pat.finditer(cleaned_text):
            s, e = m.start(), m.end()
            inside_entity = any(
                ent.start <= s and e <= ent.end
                for ent in entities
                if ent.type in (NLPEntityType.URL, NLPEntityType.FOLDER, NLPEntityType.FILE)
            )
            if inside_entity:
                continue
            
            if not any(sp_s <= s and e <= sp_e for sp_s, sp_e, _, _ in split_points):
                split_points.append((s, e, rel, name))

    split_points.sort(key=lambda x: x[0])

    if not split_points:
        act, intent, conf = infer_action_and_intent(cleaned_text, entities)
        clause = Clause(
            idx=0,
            text=cleaned_text,
            action=act,
            intent=intent,
            entities=list(entities),
            confidence=conf,
            source="single_clause_parser",
        )
        return ([clause], [])

    segments: list[tuple[str, int, int]] = []
    ordering_relations: list[tuple[int, OrderingRelation, int]] = []

    last_idx = 0
    for i, (sp_s, sp_e, rel, _) in enumerate(split_points):
        seg_text = cleaned_text[last_idx:sp_s].strip()
        if seg_text:
            segments.append((seg_text, last_idx, sp_s))
        last_idx = sp_e

    final_seg = cleaned_text[last_idx:].strip()
    if final_seg:
        segments.append((final_seg, last_idx, len(cleaned_text)))

    for i in range(len(segments) - 1):
        rel = split_points[i][2] if i < len(split_points) else OrderingRelation.THEN
        ordering_relations.append((i, rel, i + 1))

    clauses: list[Clause] = []
    for idx, (seg_text, s_off, e_off) in enumerate(segments):
        clause_entities = [
            ent for ent in entities
            if s_off <= ent.start < e_off or s_off < ent.end <= e_off
        ]
        
        act, intent, conf = infer_action_and_intent(seg_text, clause_entities)
        
        constraints: list[Constraint] = []
        if re.search(r'\b(?:don\'t\s+start|without\s+starting|don\'t\s+run)\b', seg_text, re.I):
            constraints.append(Constraint(type="NO_STARTUP_ACTIONS", value=True, raw_text=seg_text))
        if re.search(r'\b(?:just\s+inspect|only\s+inspect|read\s+only)\b', seg_text, re.I):
            constraints.append(Constraint(type="READ_ONLY", value=True, raw_text=seg_text))

        clause = Clause(
            idx=idx,
            text=seg_text,
            action=act,
            intent=intent,
            entities=clause_entities,
            constraints=constraints,
            confidence=conf,
            source="multi_clause_decomposer",
        )
        clauses.append(clause)

    return (clauses, ordering_relations)
