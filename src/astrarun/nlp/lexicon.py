"""Lexicon loader and accessors for AstraRun NLP engine."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

def _resolve_default_lexicon_path() -> Path:
    try:
        from astrarun.core.paths import get_install_root
        install_lex = get_install_root() / "config" / "nlp_lexicon.json"
        if install_lex.exists():
            return install_lex
    except Exception:
        pass
    if getattr(sys, "frozen", False):
        exe_parent = Path(sys.executable).resolve().parent
        exe_lex = exe_parent / "config" / "nlp_lexicon.json"
        if exe_lex.exists():
            return exe_lex
        internal_lex = exe_parent / "_internal" / "config" / "nlp_lexicon.json"
        if internal_lex.exists():
            return internal_lex
    repo_lex = Path(__file__).resolve().parent.parent.parent.parent / "config" / "nlp_lexicon.json"
    return repo_lex


_DEFAULT_LEXICON_PATH = _resolve_default_lexicon_path()

_CACHED_LEXICON: dict[str, Any] | None = None


def get_lexicon(path: Path | None = None) -> dict[str, Any]:
    """Retrieve the cached NLP lexicon or load from disk."""
    global _CACHED_LEXICON
    if _CACHED_LEXICON is not None and path is None:
        return _CACHED_LEXICON

    target = path or _resolve_default_lexicon_path()
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
            "politeness_prefixes": ["can you please", "could you please", "would you mind", "please", "can you", "could you", "kindly", "can u", "could u", "would u", "will you", "plz", "pls"],
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
