"""Layer 1: Context Grounding Engine for AstraRun Hybrid Routing.

Resolves active workstation context, intra-prompt antecedents, and external referents:
- Resolves whether pronouns ("it", "that", "this", "them") are grounded within the prompt
  (e.g., "open calculator then minimize it" -> "it" is grounded by "calculator").
- Resolves referents against active workstation context (active task, current file, active PID).
- Emits structured missing information only when a required entity is genuinely absent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class GroundingAnalysis:
    """Outcome of context grounding analysis."""
    is_sufficient: bool
    resolved_referents: Dict[str, Any] = field(default_factory=dict)
    missing_information: List[str] = field(default_factory=list)
    has_intra_prompt_antecedent: bool = False
    unresolved_pronouns: List[str] = field(default_factory=list)
    reason: str = ""


class ContextGrounder:
    """Evaluates whether entities and operands in a prompt are grounded."""

    PRONOUN_PATTERNS = (
        r"\b(?:it|that|this|them|that\s+one|the\s+other\s+one)\b",
        r"\b(?:that|the)\s+(?:file|folder|document|app|application|process|task|window|thing|result|setting)\b",
    )

    STANDALONE_UNGROUNDED_COMMANDS = (
        (r"^(?:run|start|execute|launch)\s+it(?:\s+now)?$", "run_target"),
        (r"^(?:delete|remove|erase)\s+it$", "delete_target"),
        (r"^(?:close|quit|kill|terminate|stop)\s+it$", "close_target"),
        (r"^(?:open|show|view|inspect)\s+it$", "open_target"),
        (r"^(?:open|find|view|delete)\s+that\s+file$", "file_path"),
        (r"^(?:kill|terminate|stop)\s+the\s+process$", "process_id"),
        (r"^(?:connect\s+to\s+it|connect)$", "network_ssid"),
        (r"^(?:generate\s+the\s+report|generate\s+report|make\s+the\s+report)$", "report_type"),
        (r"^(?:process\s+the\s+data|process\s+data|handle\s+the\s+data)$", "data_source"),
        (r"^(?:find\s+the\s+document|find\s+the\s+file|find\s+document)$", "file_query"),
        (r"^(?:what\s+happened\s+to\s+that\s+task|what\s+happened\s+to\s+it)$", "task_id"),
        (r"^(?:did\s+it\s+finish(?:\s+yet)?|is\s+it\s+done|did\s+it\s+complete)$", "task_id"),
        (r"^(?:try\s+running\s+it\s+again|run\s+it\s+again|start\s+it\s+again)$", "task_id"),
        (r"^(?:change\s+the\s+setting|make\s+the\s+adjustment)$", "adjustment_target"),
        (r"^(?:fix\s+the\s+problem|start\s+the\s+task|handle\s+the\s+situation)$", "task_description"),
        (r"^(?:check\s+the\s+thing|inspect\s+the\s+window|show\s+me\s+that)$", "target_object"),
        (r"^(?:open\s+the\s+file|save\s+it\s+to\s+disk|delete\s+that\s+folder)$", "path_operand"),
        (r"^(?:continue\s+what\s+we\s+were\s+doing\s+yesterday|do\s+the\s+same\s+thing\s+you\s+did\s+last\s+time)$", "session_history"),
        (r"^(?:pick\s+up\s+from\s+where\s+we\s+stopped|use\s+that\s+previous\s+value\s+from\s+earlier)$", "session_state"),
        (r"^(?:proceed\s+with\s+option\s+number\s+two|apply\s+the\s+same\s+changes\s+to\s+the\s+other\s+one)$", "selection_state"),
        (r"^(?:process|calculate|compute|solve|analyze|run|execute|handle|transform)\s+(?:the|that)\s+(?:document|app|application|task|other\s+one|thing|item)$", "target_entity"),
        (r"^(?:calculate|compute|solve)\s+(?:the\s+other\s+one|that\s+one)$", "target_entity"),
    )

    @classmethod
    def analyze(
        cls,
        prompt: str,
        active_context: Optional[Dict[str, Any]] = None,
    ) -> GroundingAnalysis:
        clean = prompt.strip()
        lower = clean.lower()
        context = active_context or {}

        # 1. Check for standalone ungrounded command patterns
        stripped = lower.strip(" .!?")
        for pat, missing_name in cls.STANDALONE_UNGROUNDED_COMMANDS:
            if re.match(pat, stripped):
                # Check if resolved by active context
                if (
                    missing_name in context
                    or "active_task_id" in context
                    or "task_id" in context
                    or "active_process" in context
                    or "current_file" in context
                    or "selected_option" in context
                    or "file_path" in context
                ):
                    return GroundingAnalysis(
                        is_sufficient=True,
                        resolved_referents={missing_name: context.get(missing_name) or context},
                        reason=f"Referent '{missing_name}' grounded by active workstation context.",
                    )
                return GroundingAnalysis(
                    is_sufficient=False,
                    missing_information=[missing_name],
                    unresolved_pronouns=[stripped],
                    reason=f"Ungrounded imperative '{clean}' lacks referent '{missing_name}'.",
                )

        # 2. Check for multi-clause prompt with intra-prompt antecedents
        # E.g. "open notepad then type hello into it and save it"
        # If clauses mention an explicit target noun in earlier clause, subsequent "it" is grounded!
        clauses = [c.strip() for c in re.split(r"\band\b|\bthen\b|;|,", lower) if c.strip()]
        if len(clauses) > 1:
            # First clause introduces an entity?
            first_clause = clauses[0]
            explicit_nouns = re.findall(
                r"\b(?:notepad|calculator|calc|code|terminal|explorer|browser|file|script|program|window|process|report|image|folder)\b",
                first_clause,
            )
            has_explicit_entity = bool(explicit_nouns) or bool(re.search(r'["\']([^"\']+)["\']', first_clause))
            if has_explicit_entity:
                # Pronouns in subsequent clauses are grounded by first clause
                return GroundingAnalysis(
                    is_sufficient=True,
                    has_intra_prompt_antecedent=True,
                    resolved_referents={"intra_prompt_target": explicit_nouns[0] if explicit_nouns else "first_clause_entity"},
                    reason="Pronouns grounded by intra-prompt antecedent in prior clause.",
                )

        # 3. Trailing or isolated pronouns without antecedent
        isolated_pronoun_match = re.search(r"\b(?:it|that|them)\s*$", stripped)
        if isolated_pronoun_match and len(clauses) <= 1:
            pronoun = isolated_pronoun_match.group(0).strip()
            # If prompt has explicit operand before pronoun (e.g. "for 'payload'"), not ungrounded
            if not re.search(r'["\']([^"\']+)["\']', lower) and not any(k in lower for k in ("matrix", "function", "equation", "script", "program")):
                if not context:
                    return GroundingAnalysis(
                        is_sufficient=False,
                        missing_information=[f"referent:{pronoun}"],
                        unresolved_pronouns=[pronoun],
                        reason=f"Prompt ends in ungrounded pronoun '{pronoun}'.",
                    )

        # By default, prompt contains sufficient semantic context
        return GroundingAnalysis(
            is_sufficient=True,
            reason="Prompt operands are grounded and self-contained.",
        )
