"""SingleStepFastTrack optimization for genuinely unambiguous single-step turns.

Invariant:
- FastTrack produces standard TurnDecision objects.
- Does NOT bypass AgentCoordinator or ExecutionBroker.
- Strictly rejects pronouns, multi-turn references, ambiguous targets, or composite queries.
- Any conversational dependency falls through to TurnReasoner.
"""

from __future__ import annotations

import re
from typing import Optional

from astrarun.cognition.turn_models import PlanStep, TurnDecision, TurnMode
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.agent.fast_track")

# Pronouns and conversational references that MUST disqualify fast-track
CONVERSATIONAL_DISQUALIFIERS = {
    "it", "that", "this", "them", "those", "these", "earlier", "previous",
    "again", "shorter", "summarize", "explain", "why", "what", "more",
    "first", "second", "third", "said", "mentioned", "above", "below",
}

# Conjunctions and sequencing tokens indicating composite multi-step intent
COMPOSITE_DISQUALIFIERS = {
    "and", "then", "after", "while", "also", "plus", "with", "but",
}

# Delegation, retrieval, privacy, temporal qualifiers, and research keywords that strictly disqualify fast-track
DELEGATION_AND_GOVERNANCE_DISQUALIFIERS = {
    "to", "via", "using", "from", "into", "through",
    "chatgpt", "gemini", "claude", "ai", "model",
    "my", "our", "private", "confidential", "secret",
    "latest", "recent", "newest", "updated",
    "documentation", "docs", "notes", "report", "paper", "file", "folder",
    "show", "send", "transmit", "upload", "export",
}


class SingleStepFastTrack:
    """
    High-confidence, single-step deterministic fast track.
    
    Produces standard TurnDecision objects for clear-cut operations:
    - Pure arithmetic expressions (e.g. '2 + 2', '100 / 4')
    - Direct application launch without conditions (e.g. 'open calculator')
    - System diagnostics queries (e.g. 'battery percentage', 'battery status')
    - Window management without pronouns (e.g. 'snap current window left')
    """

    @classmethod
    def match(cls, query: str) -> Optional[TurnDecision]:
        """
        Evaluate query against strict fast-track invariants.
        Returns TurnDecision if unambiguously matched, otherwise None (fall through to TurnReasoner).
        """
        if not query or not query.strip():
            return None

        q_clean = query.strip()

        # Strip leading conversational greetings or polite prefixes if followed by an operation
        clean_stripped = re.sub(
            r"^(?:hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening|thanks|thank\s+you|please|can\s+you|could\s+you)[,\s]+(?:please\s+)?(?:now\s+)?",
            "",
            q_clean,
            flags=re.IGNORECASE,
        ).strip()
        if clean_stripped:
            q_clean = clean_stripped

        tokens = [t.lower() for t in re.findall(r"\b[a-zA-Z0-9_]+\b", q_clean)]

        # Check for conversational disqualifiers
        for t in tokens:
            if t in CONVERSATIONAL_DISQUALIFIERS:
                return None

        # Check for arithmetic expressions: e.g. "2 + 2", "15 * 3", "calculate 2 + 2"
        math_decision = cls._match_arithmetic(q_clean)
        if math_decision is not None:
            return math_decision

        # Check for composite disqualifiers (only after math check)
        for t in tokens:
            if t in COMPOSITE_DISQUALIFIERS:
                return None

        # Check for delegation, privacy, external models, and retrieval disqualifiers
        for t in tokens:
            if t in DELEGATION_AND_GOVERNANCE_DISQUALIFIERS:
                return None

        q_lower = " ".join(tokens)

        # 1. Calculator launch: "open calculator", "launch calculator", "start calculator"
        if q_lower in ("open calculator", "launch calculator", "start calculator"):
            return TurnDecision(
                mode=TurnMode.TOOL_PLAN,
                assistant_reply="Opening Calculator.",
                goal_summary="Launch Calculator application",
                plan_steps=[
                    PlanStep(
                        step_id="fast-step-1",
                        capability_id="open_application",
                        arguments={"app": "calculator"},
                    )
                ],
                confidence=1.0,
                model_role="FAST_TRACK",
                metadata={"fast_track": True, "template": "open_calculator", "app": "calculator"},
            )

        # 2. Battery status: "battery percentage", "battery status", "check battery"
        if q_lower in ("battery percentage", "battery status", "check battery", "battery level", "get battery"):
            return TurnDecision(
                mode=TurnMode.TOOL_PLAN,
                assistant_reply="Checking battery status.",
                goal_summary="Check system battery status",
                plan_steps=[
                    PlanStep(
                        step_id="fast-step-1",
                        capability_id="battery_status",
                        arguments={},
                    )
                ],
                confidence=1.0,
                model_role="FAST_TRACK",
                metadata={"fast_track": True, "template": "battery_status"},
            )

        # 3. Window snapping left
        if q_lower in ("snap current window left", "snap window left", "snap to left", "snap left"):
            return TurnDecision(
                mode=TurnMode.TOOL_PLAN,
                assistant_reply="Snapping window to the left.",
                goal_summary="Snap foreground window left",
                plan_steps=[
                    PlanStep(
                        step_id="fast-step-1",
                        capability_id="snap_window_left",
                        arguments={},
                    )
                ],
                confidence=1.0,
                model_role="FAST_TRACK",
                metadata={"fast_track": True, "template": "snap_window_left"},
            )

        # 4. Window snapping right
        if q_lower in ("snap current window right", "snap window right", "snap to right", "snap right"):
            return TurnDecision(
                mode=TurnMode.TOOL_PLAN,
                assistant_reply="Snapping window to the right.",
                goal_summary="Snap foreground window right",
                plan_steps=[
                    PlanStep(
                        step_id="fast-step-1",
                        capability_id="snap_window_right",
                        arguments={},
                    )
                ],
                confidence=1.0,
                model_role="FAST_TRACK",
                metadata={"fast_track": True, "template": "snap_window_right"},
            )

        return None

    @classmethod
    def _match_arithmetic(cls, query: str) -> Optional[TurnDecision]:
        """Safely evaluate simple arithmetic expressions like '2 + 2' or '100 / 4'."""
        expr = query.strip()
        # If query has explicit 'calculate' or 'compute', let downstream PURE_QUERY pipeline handle it
        if expr.lower().startswith(("calculate ", "compute ")):
            return None

        # Match only clean arithmetic: digits, spaces, and operators + - * / %
        if not re.match(r"^[-+]?\d+(\.\d+)?(\s*[\+\-\*\/%]\s*[-+]?\d+(\.\d+)?)+$", expr):
            return None

        # Safely evaluate with ast
        try:
            import ast
            parsed = ast.parse(expr, mode="eval")
            for node in ast.walk(parsed):
                if not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
                                          ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.USub, ast.UAdd)):
                    return None
            code = compile(parsed, "<math>", "eval")
            result = eval(code, {"__builtins__": None}, {})
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            return TurnDecision(
                mode=TurnMode.DIRECT_ANSWER,
                assistant_reply=f"{expr} = {result}",
                goal_summary="Compute arithmetic expression",
                confidence=1.0,
                model_role="FAST_TRACK",
                metadata={"fast_track": True, "expression": expr, "result": result},
            )
        except Exception:
            return None
