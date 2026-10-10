"""Neural Structure Engine for AstraRun v0.10.3.

Leverages spaCy en_core_web_sm for syntactic clause segmentation, dependency parsing,
explicit negation detection, and 100% exact literal payload span preservation.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Any, Optional

from astrarun.core.logging import get_logger
from astrarun.nlp.ir import LiteralPayload, ParsedClause, ParsedEntity, ParsedRequest, TextSpan

logger = get_logger("astrarun.nlp.structure_engine")

# Known action verbs and their target intent mappings
VERB_INTENT_MAP = {
    "open": "open_app",
    "launch": "open_app",
    "start": "open_app",
    "run": "open_app",
    "type": "type_text",
    "write": "type_text",
    "enter": "type_text",
    "snap": "snap_window",
    "dock": "snap_window",
    "minimize": "minimize_window",
    "maximize": "maximize_window",
    "restore": "restore_window",
    "close": "close_window",
    "kill": "close_window",
    "terminate": "close_window",
    "press": "press_key",
    "click": "ui_click",
    "focus": "focus_window",
    "switch": "focus_window",
}

SNAP_DIRECTIONS = {
    "left", "right", "top", "bottom",
    "top left", "top right", "bottom left", "bottom right",
    "top-left", "top-right", "bottom-left", "bottom-right",
    "left half", "right half"
}

NEGATION_TOKENS = {"not", "n't", "never", "no", "dont", "don't", "except", "without"}
PRONOUN_TOKENS = {"it", "this", "that", "that window", "this window", "the window"}


class NeuralStructureEngine:
    """Extracts typed linguistic structure, clause boundaries, and exact source spans."""

    def __init__(self, model_name: str = "en_core_web_sm") -> None:
        self.model_name = model_name
        self._nlp = None
        self._load_lock = threading.Lock()
        self._load_failed = False
        self._load_error_msg: Optional[str] = None

    def get_nlp(self) -> Any:
        """Thread-safe lazy loader for the spaCy language model."""
        if self._load_failed:
            return None
        if self._nlp is not None:
            return self._nlp

        with self._load_lock:
            if self._nlp is not None:
                return self._nlp
            if self._load_failed:
                return None
            try:
                import spacy
                logger.info("Loading spaCy model '%s' for NeuralStructureEngine...", self.model_name)
                t0 = time.perf_counter()
                try:
                    self._nlp = spacy.load(self.model_name)
                except Exception:
                    # In frozen environments, fallback to direct module load or bundled path
                    try:
                        import en_core_web_sm
                        self._nlp = en_core_web_sm.load()
                    except Exception:
                        from astrarun.core.paths import get_install_root
                        candidates = [
                            get_install_root() / "_internal" / self.model_name,
                            get_install_root() / self.model_name,
                        ]
                        for c in candidates:
                            if c.exists():
                                self._nlp = spacy.load(str(c))
                                break
                        else:
                            raise
                logger.info("spaCy model loaded in %.2fs", time.perf_counter() - t0)
                return self._nlp
            except Exception as err:
                self._load_failed = True
                self._load_error_msg = f"Failed to load spaCy model '{self.model_name}': {err}"
                logger.warning(self._load_error_msg)
                return None

    def parse(self, query: str) -> ParsedRequest:
        """Parse raw query into typed ParsedRequest IR."""
        clean_q = query.strip()
        if not clean_q:
            return ParsedRequest(raw_query="", clauses=[], confidence=0.0)

        nlp = self.get_nlp()
        if nlp is None:
            # Fallback to deterministic linguistic parser
            return self._parse_fallback(query)

        try:
            return self._parse_with_spacy(query, nlp)
        except Exception as err:
            logger.warning("spaCy parse error (%s), using fallback parser: %s", err, query)
            return self._parse_fallback(query)

    def _parse_with_spacy(self, raw_query: str, nlp: Any) -> ParsedRequest:
        """Syntactic parsing and clause extraction via spaCy."""
        doc = nlp(raw_query)

        # 1. Detect explicit coordination and clause segment splits
        split_indices: list[int] = [0]
        conj_pattern = re.compile(r'(?:,\s*then\b|,\s*and\b|\band\s+then\b|\bthen\b|\band\b|\bbut\b|&&|&|;)', re.I)
        for m in conj_pattern.finditer(raw_query):
            split_indices.append(m.start())
            split_indices.append(m.end())
        for token in doc:
            if token.pos_ in ("CCONJ", "SCONJ") and token.text.lower() in ("and", "then", "but", "while", ";"):
                split_indices.append(token.idx)
            elif token.text == ";":
                split_indices.append(token.idx + len(token.text))

        # Add end of query
        split_indices.append(len(raw_query))
        split_indices = sorted(list(set(split_indices)))

        # 2. Extract clause segments preserving original offsets
        raw_clauses: list[tuple[int, int, str]] = []
        for i in range(len(split_indices) - 1):
            s_idx = split_indices[i]
            e_idx = split_indices[i + 1]
            seg = raw_query[s_idx:e_idx].strip()
            # Strip leading conjunctions for clause content
            cleaned_seg = seg
            for prefix in (", then ", ", and ", "and then ", "then ", "and ", "but ", "; ", "& ", "&& ", ",", ";"):
                if cleaned_seg.lower().startswith(prefix):
                    cleaned_seg = cleaned_seg[len(prefix):].strip()
            if cleaned_seg.lower() in ("and", "then", "but", ";", "&", "&&", ","):
                continue
            if cleaned_seg:
                # Find start of cleaned_seg within raw_query
                actual_start = raw_query.find(cleaned_seg, s_idx)
                if actual_start != -1:
                    raw_clauses.append((actual_start, actual_start + len(cleaned_seg), cleaned_seg))

        if not raw_clauses:
            raw_clauses = [(0, len(raw_query), raw_query.strip())]

        # 3. Analyze each clause
        parsed_clauses: list[ParsedClause] = []
        has_any_negation = False

        from astrarun.nlp.clause_decomposer import infer_action_and_intent

        for seq_idx, (clause_start, clause_end, clause_text) in enumerate(raw_clauses):
            clause_doc = nlp(clause_text)
            
            # Check negation within clause
            is_negated = False
            for tok in clause_doc:
                if tok.dep_ == "neg" or tok.text.lower() in NEGATION_TOKENS:
                    is_negated = True
                    has_any_negation = True
                    break

            # Strip politeness/assistant prefixes from clause text
            from astrarun.nlp.clause_decomposer import strip_politeness
            cleaned_clause = strip_politeness(clause_text)

            clause_lower = cleaned_clause.lower()

            # Check for typing prefix pattern FIRST to ensure 100% verbatim payload preservation
            type_match = re.match(r"^(?:type|write|enter)\s+(.*)$", clause_text, re.IGNORECASE)
            if not type_match:
                type_match = re.match(r"^(?:type|write|enter)\s+(.*)$", cleaned_clause, re.IGNORECASE)

            if type_match:
                action_verb = "type"
                intent = "type_text"
                payload_raw = type_match.group(1).strip()
                if payload_raw:
                    p_start = clause_start + clause_text.find(payload_raw)
                    p_end = p_start + len(payload_raw)
                    payload_txt = raw_query[p_start:p_end]
                else:
                    p_start = clause_end
                    p_end = clause_end
                    payload_txt = ""

                payload = LiteralPayload(
                    text=payload_txt,
                    source_span=TextSpan(start=p_start, end=p_end, raw=payload_txt),
                    is_verbatim=True
                )
                clause_obj = ParsedClause(
                    clause_id=f"c{seq_idx}",
                    sequence_index=seq_idx,
                    intent=intent,
                    action_verb=action_verb,
                    is_negated=is_negated,
                    entities=[],
                    payload=payload,
                    dependency_clause_index=seq_idx - 1 if seq_idx > 0 else None,
                    source_span=TextSpan(start=clause_start, end=clause_end, raw=clause_text),
                    raw_clause=clause_text
                )
                parsed_clauses.append(clause_obj)
                continue

            # Conversational / chitchat queries (anchored to entire clause)
            if re.search(r'^(?:tell\s+me\s+a\s+joke.*|who\s+are\s+you|hello|hi|what\s+can\s+you\s+do)$', clause_lower.strip()):
                clause_obj = ParsedClause(
                    clause_id=f"c{seq_idx}",
                    sequence_index=seq_idx,
                    intent="unknown",
                    action_verb="unknown",
                    is_negated=is_negated,
                    entities=[],
                    payload=None,
                    dependency_clause_index=seq_idx - 1 if seq_idx > 0 else None,
                    source_span=TextSpan(start=clause_start, end=clause_end, raw=clause_text),
                    raw_clause=clause_text
                )
                parsed_clauses.append(clause_obj)
                continue

            # 0. Check for AI reasoning query (diagnostic / open-ended)
            if re.search(r'\b(?:why\s+is|explain|diagnose|analyze|how\s+do\s+i|write\s+code|why\s+did|figure\s+out|fix\s+my|decide\s+which)\b', clause_lower):
                clause_obj = ParsedClause(
                    clause_id=f"c{seq_idx}",
                    sequence_index=seq_idx,
                    intent="ai_query",
                    action_verb="ask",
                    is_negated=is_negated,
                    entities=[],
                    payload=None,
                    dependency_clause_index=seq_idx - 1 if seq_idx > 0 else None,
                    source_span=TextSpan(start=clause_start, end=clause_end, raw=clause_text),
                    raw_clause=clause_text
                )
                parsed_clauses.append(clause_obj)
                continue

            # Probe intent using domain decomposer, cleaning leading negation prefixes
            intent_probe_text = cleaned_clause
            for neg_prefix in ("do not ", "don't ", "never ", "not "):
                if intent_probe_text.lower().startswith(neg_prefix):
                    intent_probe_text = intent_probe_text[len(neg_prefix):].strip()
                    break

            inferred_action, _, _ = infer_action_and_intent(intent_probe_text, [])
            action_verb = "unknown"
            intent = "unknown"
            if inferred_action not in ("unknown", "unsupported"):
                intent = inferred_action
                action_verb = inferred_action.split("_")[0]

            # Check for process termination vs window closing
            if re.search(r'\b(?:kill|terminate|stop\s+process|end\s+process|abort)\b', clause_lower) or (
                re.search(r'\b(?:kill|terminate|stop)\b', clause_lower) and ("process" in clause_lower or re.search(r'\b\d{2,6}\b', clause_text))
            ):
                action_verb = "terminate"
                intent = "terminate_process"
                entities: list[ParsedEntity] = []
                pid_m = re.search(r'\b(\d{1,6})\b', clause_text)
                if pid_m:
                    pid_val = pid_m.group(1)
                    s = clause_start + pid_m.start(1)
                    e = clause_start + pid_m.end(1)
                    entities.append(ParsedEntity(
                        entity_type="process",
                        value=pid_val,
                        source_span=TextSpan(start=s, end=e, raw=raw_query[s:e]),
                        confidence=0.99
                    ))
                clause_obj = ParsedClause(
                    clause_id=f"c{seq_idx}",
                    sequence_index=seq_idx,
                    intent=intent,
                    action_verb=action_verb,
                    is_negated=is_negated,
                    entities=entities,
                    payload=None,
                    dependency_clause_index=seq_idx - 1 if seq_idx > 0 else None,
                    source_span=TextSpan(start=clause_start, end=clause_end, raw=clause_text),
                    raw_clause=clause_text
                )
                parsed_clauses.append(clause_obj)
                continue

            # Standard clause verb & entity extraction if not yet resolved
            if action_verb == "unknown":
                for tok in clause_doc:
                    w_lower = tok.text.lower()
                    if w_lower in VERB_INTENT_MAP:
                        action_verb = w_lower
                        intent = VERB_INTENT_MAP[w_lower]
                        break

            # If no direct verb mapped, check first token
            if action_verb == "unknown" and len(clause_doc) > 0:
                first_w = clause_doc[0].text.lower()
                if first_w in VERB_INTENT_MAP:
                    action_verb = first_w
                    intent = VERB_INTENT_MAP[first_w]

            # Extract entities
            entities: list[ParsedEntity] = []
            
            # Snap position check
            if any(k in clause_lower for k in ("snap", "tile", "dock", "window")) or intent.startswith("snap_window"):
                for snap_pos in SNAP_DIRECTIONS:
                    if snap_pos in clause_lower:
                        pos_idx = clause_lower.find(snap_pos)
                        s = clause_start + pos_idx
                        e = s + len(snap_pos)
                        entities.append(ParsedEntity(
                            entity_type="snap_position",
                            value=snap_pos,
                            source_span=TextSpan(start=s, end=e, raw=raw_query[s:e]),
                            confidence=0.98
                        ))
                        if "right" in snap_pos:
                            intent = "snap_window_right"
                        else:
                            intent = "snap_window_left"
                        action_verb = "snap"
                        break

            # Pronoun / coreference check
            for pron in PRONOUN_TOKENS:
                if f" {pron}" in f" {clause_lower}":
                    pron_idx = clause_lower.find(pron)
                    s = clause_start + pron_idx
                    e = s + len(pron)
                    entities.append(ParsedEntity(
                        entity_type="target_ref",
                        value=pron,
                        source_span=TextSpan(start=s, end=e, raw=raw_query[s:e]),
                        confidence=0.95,
                        referent_index=seq_idx - 1 if seq_idx > 0 else None
                    ))
                    break

            # Domain-specific refinements
            if re.search(r'^(?:open\s+(?:the\s+)?(?:project|document|file)|show\s+my\s+files|switch\s+window|switch)$', clause_lower.strip()):
                intent = "clarify"
                action_verb = "clarify"
            elif re.search(r'\b(?:take\s+me\s+to|open|show|explore)\s+(?:my\s+)?(?:active\s+projects|workspace|desktop|downloads|documents|pictures|videos|music)(?:\s+folder)?\b', clause_lower) or clause_lower in ("open workspace", "show me my workspace folder", "take me to desktop", "take me to downloads", "take me to active projects"):
                intent = "open_folder"
                action_verb = "open"
            elif any(u in clause_lower for u in ("http://", "https://", "www.", ".com", ".org", "youtube.com", "google.com", "github.com")) or (
                re.search(r'\b(?:search\s+google|search\s+youtube|search\s+web|open\s+url)\b', clause_lower)
            ):
                intent = "open_url"
                action_verb = "open"
            elif re.search(r'\b(?:minimize\s+(?:all|everything|windows)|show\s+desktop)\b', clause_lower):
                intent = "minimize_all"
                action_verb = "minimize"
            elif re.search(r'\bselect\s+(?:the\s+)?(?:first\s+|second\s+|last\s+)?(?:tab|option|item|checkbox|row|column)\b', clause_lower):
                intent = "ui_select"
                action_verb = "select"
            elif re.search(r'\b(?:focus\s+(?:field|input|box|search|editor|tab|address\s+bar|search\s+bar)|address\s+bar|search\s+bar)\b', clause_lower) and ("focus" in clause_lower or "bar" in clause_lower):
                intent = "ui_focus"
                action_verb = "focus"
            elif re.search(r'\b(?:switch\s+to|switch\s+window)\b', clause_lower):
                if clause_lower in ("switch window", "switch"):
                    intent = "clarify"
                    action_verb = "clarify"
                else:
                    intent = "focus_window"
                    action_verb = "focus"
            elif re.search(r'\b(?:is\s+(?:the\s+)?([a-zA-Z0-9_\-\.]+)\s+installed|check\s+if\s+(?:the\s+)?([a-zA-Z0-9_\-\.]+)\s+is\s+installed|do\s+i\s+have\s+([a-zA-Z0-9_\-\.]+)(?:\s+installed)?)\b', clause_lower):
                intent = "find_application"
                action_verb = "find"
            elif re.search(r'\b(?:is\s+(?:the\s+)?([a-zA-Z0-9_\-\.]+)\s+(?:currently\s+)?running|check\s+if\s+(?:the\s+)?([a-zA-Z0-9_\-\.]+)\s+is\s+(?:currently\s+)?running)\b', clause_lower):
                intent = "is_application_running"
                action_verb = "check"
            elif re.search(r'\b(?:count\s+to\s+\d+|calculate\s+|compute\s+)\b', clause_lower):
                intent = "computational_task"
                action_verb = "compute"
            elif re.search(r'\b(?:close|quit|exit)\s+(?:the\s+)?([a-zA-Z0-9_\-\.]+)\b', clause_lower) and not re.search(r'\b(?:window|this|that|tab)\b', clause_lower):
                intent = "close_application"
                action_verb = "close"
            elif re.search(r'\b(?:close\s+(?:that|this|the)?\s*window|then\s+close)\b', clause_lower) or clause_lower == "close window" or (clause_lower == "close" and seq_idx > 0):
                intent = "close_window"
                action_verb = "close"
            elif clause_lower in ("restart it", "close", "restart", "next", "undo it"):
                intent = "clarify"
                action_verb = "clarify"
            elif clause_lower.startswith("find ") and not clause_lower.startswith("find file"):
                intent = "open_app"
                action_verb = "open"
            elif re.search(r'\b(?:press|click)\s+(?:cancel|ok|submit|apply|save|yes|no|button)\b', clause_lower):
                intent = "ui_click"
                action_verb = "click"
            elif re.search(r'\b(?:press|ctrl\+|alt\+|shift\+|win\+|copy|paste|delete|enter|tab|escape|backspace)\b', clause_lower):
                intent = "press_key"
                action_verb = "press"
            elif re.search(r'\b(?:click|tap)\b', clause_lower):
                intent = "ui_click"
                action_verb = "click"
            elif re.search(r'\b(?:open|launch|start|bring\s+up|fire\s+up)\b', clause_lower) and re.search(r'\b(?:project|repo|workspace)\b', clause_lower):
                intent = "open_project"
                action_verb = "open"
            elif re.search(r'\b(?:run\s+(?:the\s+)?(?:(?:approved|safe)\s+)*test(?:\s+command)?|run\s+tests?|run\s+test\s+command)\b', clause_lower):
                intent = "run_project_command"
                action_verb = "run"
            elif re.search(r'\b(?:open|launch|start|run|bring\s+up|fire\s+up)\b', clause_lower) or re.search(r'\bget\s+([a-zA-Z0-9_\-]+)\s+running\b', clause_lower) or "i need to write some notes in" in clause_lower:
                if not re.search(r'\b(?:project|repo|workspace)\b', clause_lower):
                    if not any(k in clause_lower for k in ("folder", "downloads", "documents", "http", ".com", "system", "status")):
                        intent = "open_app"
                        action_verb = "open"

            # App / project / target entity extraction
            if intent in ("open_app", "open_project", "close_application", "close_window", "focus_window") and not any(e.entity_type == "snap_position" for e in entities):
                # Identify object noun / argument
                target_str = ""
                for tok in clause_doc:
                    if tok.text.lower() in VERB_INTENT_MAP or tok.text.lower() in ("the", "a", "an", "window", "app", "project", "repo", "workspace"):
                        continue
                    if tok.dep_ in ("dobj", "pobj", "compound", "nmod") or tok.pos_ in ("PROPN", "NOUN", "X"):
                        target_str += (" " if target_str else "") + tok.text

                if target_str:
                    t_idx = clause_text.find(target_str)
                    if t_idx != -1:
                        s = clause_start + t_idx
                        e = s + len(target_str)
                        e_type = "project" if intent == "open_project" else "app_name"
                        entities.append(ParsedEntity(
                            entity_type=e_type,
                            value=target_str,
                            source_span=TextSpan(start=s, end=e, raw=raw_query[s:e]),
                            confidence=0.95
                        ))

            if intent in ("open_app", "open_application") and not any(e.entity_type == "app_name" for e in entities):
                m = re.search(r'\b(?:open|launch|start|run|bring\s+up)\s+(?:the\s+|an?\s+)?([a-zA-Z0-9_\-\.]+)', clause_text, re.I)
                if m:
                    app_val = m.group(1).lower()
                    if app_val not in ("project", "repo", "workspace", "folder", "window", "url", "file", "tab", "the", "a", "an"):
                        t_idx = clause_text.lower().find(app_val)
                        if t_idx != -1:
                            s = clause_start + t_idx
                            e = s + len(app_val)
                            entities.append(ParsedEntity(
                                entity_type="app_name",
                                value=app_val,
                                source_span=TextSpan(start=s, end=e, raw=raw_query[s:e]),
                                confidence=0.9
                            ))

            # Specific subsystem queries take precedence over broad "system" keywords
            if re.search(r'\b(?:ram|memory)\b', clause_lower):
                intent = "memory_status"
                action_verb = "status"
            elif re.search(r'\b(?:cpu|processor)\b', clause_lower):
                intent = "cpu_status"
                action_verb = "status"
            elif re.search(r'\b(?:disk|storage|drive\s+space)\b', clause_lower):
                intent = "disk_status"
                action_verb = "status"
            elif re.search(r'\b(?:gpu|graphics|vram)\b', clause_lower):
                intent = "gpu_status"
                action_verb = "status"
            elif re.search(r'\b(?:battery|power)\b', clause_lower):
                intent = "battery_status"
                action_verb = "status"
            elif re.search(r'\b(?:volume|mute)\b', clause_lower):
                intent = "system_volume"
                action_verb = "mute" if "mute" in clause_lower else "volume"
            elif any(k in clause_lower for k in ("system", "health", "summary", "overview", "workstation status")):
                intent = "system_summary"
                action_verb = "status"

            clause_obj = ParsedClause(
                clause_id=f"c{seq_idx}",
                sequence_index=seq_idx,
                intent=intent,
                action_verb=action_verb,
                is_negated=is_negated,
                entities=entities,
                payload=None,
                dependency_clause_index=seq_idx - 1 if seq_idx > 0 else None,
                source_span=TextSpan(start=clause_start, end=clause_end, raw=clause_text),
                raw_clause=clause_text
            )
            parsed_clauses.append(clause_obj)

        is_compound = len(parsed_clauses) > 1
        return ParsedRequest(
            raw_query=raw_query,
            clauses=parsed_clauses,
            is_compound=is_compound,
            has_negation=has_any_negation,
            ambiguity_score=0.1 if is_compound else 0.02,
            confidence=0.95,
            source_engine="neural_spacy"
        )

    def _parse_fallback(self, query: str) -> ParsedRequest:
        """Deterministic regex and substring fallback parser."""
        from astrarun.nlp.clause_decomposer import decompose_clauses
        decomp_clauses, _ = decompose_clauses(query, [])

        parsed_clauses: list[ParsedClause] = []
        has_negation = False

        for seq_idx, raw_c in enumerate(decomp_clauses):
            c_text = raw_c.text
            s_idx = query.find(c_text)
            if s_idx == -1:
                s_idx = 0
            e_idx = s_idx + len(c_text)
            is_neg = raw_c.negated or any(neg in c_text.lower().split() for neg in NEGATION_TOKENS)
            if is_neg:
                has_negation = True

            payload: Optional[LiteralPayload] = None
            if raw_c.action == "type_text":
                type_m = re.match(r'^(?:type|enter text)\s*(.*)$', c_text, re.I)
                p_text = type_m.group(1).strip() if type_m else ""
                p_s = query.find(p_text, s_idx) if p_text else e_idx
                p_e = p_s + len(p_text) if p_text and p_s != -1 else e_idx
                raw_sp = query[p_s:p_e] if p_s != -1 else p_text
                payload = LiteralPayload(
                    text=raw_sp,
                    source_span=TextSpan(start=p_s if p_s != -1 else s_idx, end=p_e, raw=raw_sp),
                    is_verbatim=True
                )

            ents: list[ParsedEntity] = []
            for ent in raw_c.entities:
                ents.append(ParsedEntity(
                    entity_type="app_name" if ent.type.value == "APPLICATION" else ent.type.value.lower(),
                    value=str(ent.normalized),
                    source_span=TextSpan(start=ent.start, end=ent.end, raw=ent.text),
                    confidence=ent.confidence
                ))

            if (raw_c.action in ("open_app", "open_application") or raw_c.intent in ("open_app", "open_application")) and not any(e.entity_type == "app_name" for e in ents):
                m = re.search(r'\b(?:open|launch|start|run|bring\s+up)\s+(?:the\s+|an?\s+)?([a-zA-Z0-9_\-\.]+)', c_text, re.I)
                if m:
                    app_val = m.group(1).lower()
                    if app_val not in ("project", "repo", "workspace", "folder", "window", "url", "file", "tab", "the", "a", "an"):
                        app_s = query.lower().find(app_val, s_idx)
                        app_e = app_s + len(app_val) if app_s != -1 else e_idx
                        ents.append(ParsedEntity(
                            entity_type="app_name",
                            value=app_val,
                            source_span=TextSpan(start=app_s if app_s != -1 else s_idx, end=app_e, raw=query[app_s:app_e] if app_s != -1 else app_val),
                            confidence=0.9
                        ))

            parsed_clauses.append(ParsedClause(
                clause_id=f"c{seq_idx}",
                sequence_index=seq_idx,
                intent=raw_c.action or raw_c.intent or "unknown",
                action_verb=raw_c.action.split("_")[0] if raw_c.action else "unknown",
                is_negated=is_neg,
                entities=ents,
                payload=payload,
                dependency_clause_index=seq_idx - 1 if seq_idx > 0 else None,
                source_span=TextSpan(start=s_idx, end=e_idx, raw=c_text),
                raw_clause=c_text
            ))

        return ParsedRequest(
            raw_query=query,
            clauses=parsed_clauses,
            is_compound=len(parsed_clauses) > 1,
            has_negation=has_negation,
            ambiguity_score=0.15 if len(parsed_clauses) > 1 else 0.05,
            confidence=0.90,
            source_engine="deterministic_fallback"
        )
