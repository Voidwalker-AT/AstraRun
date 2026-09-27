"""Lexicon loader and accessors for AstraRun NLP engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_LEXICON_PATH = Path(__file__).resolve().parent.parent.parent.parent / "config" / "nlp_lexicon.json"

_CACHED_LEXICON: dict[str, Any] | None = None


def get_lexicon(path: Path | None = None) -> dict[str, Any]:
    """Retrieve the cached NLP lexicon or load from disk."""
    global _CACHED_LEXICON
    if _CACHED_LEXICON is not None and path is None:
        return _CACHED_LEXICON

    target = path or _DEFAULT_LEXICON_PATH
    if target.exists():
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        # Fallback minimal embedded lexicon
        data = {
            "action_synonyms": {
                "open_project": ["open project", "load project", "open my", "open repo"],
                "open_app": ["open", "launch", "start", "run"],
                "inspect_port": ["inspect port", "check port", "what's on port", "whats on port"],
                "inspect_process": ["inspect process", "check process", "inspect", "show process"],
                "terminate_process": ["kill", "stop", "terminate", "kill process"],
                "find_file": ["find", "search file", "look for", "open screenshot", "open pdf"],
                "search_web": ["search google for", "search web for", "google"],
                "ai_query": ["explain this", "summarize", "why is this failing", "why is port"],
            },
            "conjunctions": {
                "sequence": ["and then", "then", "after that", "afterwards"],
                "conjunction": ["and", "also", "as well as", "plus"],
                "contrast": ["but", "however", "except", "without"],
                "precedence_before": ["before"],
                "precedence_after": ["after"],
            },
            "negation_markers": ["don't", "dont", "do not", "never", "avoid", "stop", "not", "without", "except"],
            "politeness_prefixes": ["can you please", "could you please", "would you mind", "please", "can you", "could you", "kindly"],
            "temporal_synonyms": {
                "yesterday": ["yesterday"],
                "today": ["today"],
                "last_night": ["last night"],
                "recent": ["recent", "recently"],
                "most_recent": ["most recent", "latest", "newest", "last", "previous"],
                "just_now": ["just now"],
            },
            "contextual_pronouns": {
                "process": ["that process", "same process", "it", "that"],
                "project": ["that project", "same project", "the project", "this project"],
                "generic": ["it", "that", "the previous one", "the last one"],
            },
            "developer_abbreviations": {
                "repo": "repository",
                "proj": "project",
                "vsc": "vscode",
                "proc": "process",
                "pid": "process_id",
            },
            "constraint_markers": {
                "no_startup": ["don't start anything", "dont start anything", "without starting anything"],
                "read_only": ["just inspect", "only inspect", "read only"],
            },
        }

    if path is None:
        _CACHED_LEXICON = data
    return data
