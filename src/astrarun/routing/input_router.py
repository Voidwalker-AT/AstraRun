"""Lightweight deterministic launcher input router for AstraRun 1.0.

Classifies command bar input into semantic categories BEFORE search index evaluation:
- NATURAL_LANGUAGE: Conversational greetings, politeness, assistance queries ("hi", "hello", "thanks")
- QUESTION: Machine intelligence or context questions ("what gpu do i have", "how much vram")
- GOAL: Multi-step plans, workflows, or instructions ("make me a...", "create a file")
- DIRECT_APP_INTENT: Explicit application launch verbs ("open calc", "launch vivaldi")
- DIRECT_FILE_INTENT: File paths, directory navigation ("C:\\...", "explorer ...")
- APP_SEARCH: Short keywords matching applications ("calc", "notepad", "code")
- AMBIGUOUS: Fallback for ambiguous or mixed queries
"""

from __future__ import annotations

import os
import re
from enum import Enum
from typing import Optional, Set

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.routing.input_router")


class InputIntent(str, Enum):
    NATURAL_LANGUAGE = "NATURAL_LANGUAGE"
    QUESTION = "QUESTION"
    GOAL = "GOAL"
    DIRECT_APP_INTENT = "DIRECT_APP_INTENT"
    DIRECT_FILE_INTENT = "DIRECT_FILE_INTENT"
    APP_SEARCH = "APP_SEARCH"
    AMBIGUOUS = "AMBIGUOUS"


# Exact conversational / greeting phrases
CONVERSATIONAL_EXACT: Set[str] = {
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
    "thanks",
    "thank you",
    "thx",
    "ty",
    "cheers",
    "appreciate it",
    "bye",
    "goodbye",
    "cya",
    "see ya",
    "later",
    "ok",
    "okay",
    "who are you",
    "what are you",
    "what can you do",
    "help",
    "?",
}

# Conversational responses returned immediately on Enter
CONVERSATIONAL_RESPONSES: dict[str, str] = {
    "hi": "✦ Hi. What do you need?",
    "hello": "✦ Hello. How can I help you today?",
    "hey": "✦ Hey there. What would you like to do?",
    "hiya": "✦ Hi. What do you need?",
    "yo": "✦ Ready. What's the task?",
    "sup": "✦ Ready. What do you need?",
    "howdy": "✦ Howdy! How can I assist you?",
    "greetings": "✦ Greetings. What can I do for you?",
    "good morning": "✦ Good morning. What are we working on?",
    "good afternoon": "✦ Good afternoon. How can I help?",
    "good evening": "✦ Good evening. What do you need?",
    "thanks": "✦ You're welcome!",
    "thank you": "✦ Glad to help!",
    "thx": "✦ Anytime!",
    "ty": "✦ You're welcome!",
    "cheers": "✦ Cheers! What's next?",
    "bye": "✦ Goodbye! Astra is standing by in your tray.",
    "goodbye": "✦ Goodbye! Press Alt+Space whenever you need me.",
    "who are you": "✦ I am Astra, your intelligent workstation copilot.",
    "what can you do": "✦ I launch apps, answer machine questions, automate desktop workflows, and run local models.",
    "help": "✦ Type an app name to launch it, ask a machine question, or describe a multi-step task.",
}

# Question prefixes
QUESTION_PREFIXES = (
    "what ",
    "what's ",
    "how ",
    "how's ",
    "why ",
    "where ",
    "where's ",
    "who ",
    "who's ",
    "when ",
    "which ",
    "can you ",
    "could you ",
    "would you ",
    "is it ",
    "is there ",
    "are there ",
    "do you ",
    "does it ",
    "tell me ",
    "show me ",
    "check if ",
    "check whether ",
    "how much ",
    "how many ",
)

# Explicit app launch verbs
APP_LAUNCH_VERBS = ("open ", "launch ", "start ", "run ")

# Goal / workflow prefixes
GOAL_PREFIXES = (
    "make ",
    "make me ",
    "create ",
    "create a ",
    "save ",
    "save file ",
    "generate ",
    "write ",
    "write a ",
    "summarize ",
    "organize ",
    "find and replace ",
    "build ",
    "deploy ",
    "test ",
    "extract ",
    "convert ",
    "transcribe ",
    "analyze ",
    "refactor ",
    "download ",
    "clone ",
    "backup ",
)

# Compound conjunctions indicating multi-clause instructions
COMPOUND_CONJUNCTIONS = (
    " and then ",
    " then ",
    " and open ",
    " and run ",
    " and save ",
    " with ",
    " & ",
    "; ",
)


def get_conversational_response(query: str) -> str:
    """Return an appropriate immediate inline response for conversational input."""
    clean = query.strip().lower()
    clean = re.sub(r"[!.,?]+$", "", clean).strip()
    return CONVERSATIONAL_RESPONSES.get(clean, "✦ Hi. What do you need?")


def classify_launcher_input(
    query: str,
    known_app_names: Optional[Set[str]] = None,
) -> InputIntent:
    """
    Classify user input to determine search behavior and execution routing.

    Gating Rules:
    1. NATURAL_LANGUAGE -> 0 app suggestions. Inline response on Enter.
    2. QUESTION -> 0 app suggestions. Route to context / machine intelligence.
    3. GOAL -> 0 app suggestions. Route to planner / HUD.
    4. DIRECT_APP_INTENT -> High confidence app suggestions.
    5. DIRECT_FILE_INTENT -> File / folder resolution.
    6. APP_SEARCH -> Short app search query.
    """
    clean = query.strip()
    if not clean:
        return InputIntent.AMBIGUOUS

    lower = clean.lower()
    lower_nopunct = re.sub(r"[!.,?]+$", "", lower).strip()

    # 1. Natural Language / Greetings / Politeness
    if lower_nopunct in CONVERSATIONAL_EXACT or lower in CONVERSATIONAL_EXACT:
        return InputIntent.NATURAL_LANGUAGE

    # 2. Questions (Ends with question mark or starts with interrogative prefix)
    if lower.endswith("?") or any(lower.startswith(p) for p in QUESTION_PREFIXES):
        # Exception: explicit app query like "open calculator?"
        if any(lower.startswith(v) for v in APP_LAUNCH_VERBS):
            return InputIntent.DIRECT_APP_INTENT
        return InputIntent.QUESTION

    # 3. Direct File or Path Navigation
    if (
        re.match(r"^[a-zA-Z]:[\\/]", clean)
        or clean.startswith("\\\\")
        or clean.startswith("file://")
        or clean.startswith("~/")
    ):
        return InputIntent.DIRECT_FILE_INTENT

    # 4. Direct App Launch Verbs
    if any(lower.startswith(v) for v in APP_LAUNCH_VERBS):
        # Extract target after verb
        target = re.sub(r"^(open|launch|start|run)\s+", "", lower, flags=re.IGNORECASE).strip()
        # If target looks like a path or URL
        if re.match(r"^[a-zA-Z]:[\\/]", target) or target.startswith("http://") or target.startswith("https://"):
            return InputIntent.DIRECT_FILE_INTENT
        return InputIntent.DIRECT_APP_INTENT

    # 5. Compound Workflows or Goals
    if any(conj in lower for conj in COMPOUND_CONJUNCTIONS):
        return InputIntent.GOAL

    if any(lower.startswith(g) for g in GOAL_PREFIXES):
        return InputIntent.GOAL

    # 6. Known App Token Match or Short Keyword Search
    words = lower.split()
    if len(words) <= 2:
        if known_app_names and lower in known_app_names:
            return InputIntent.APP_SEARCH
        # Short non-conversational token
        if len(lower) >= 2 and re.match(r"^[a-zA-Z0-9_\-]+$", lower):
            return InputIntent.APP_SEARCH

    # 7. Fallback: If 3 or more words and not matching above, classify as GOAL or AMBIGUOUS
    if len(words) >= 3:
        return InputIntent.GOAL

    return InputIntent.AMBIGUOUS
