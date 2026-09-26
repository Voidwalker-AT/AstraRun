"""Deterministic and fuzzy-assisted router for AstraRun v0.2."""

from __future__ import annotations

import re
import time
from urllib.parse import urlparse

from astrarun.core.logging import get_logger
from astrarun.core.models import Decision, RoutingContext
from astrarun.routing.base import BaseRouter
from astrarun.search.models import CandidateCategory

logger = get_logger("astrarun.routing.deterministic")

# Verbs recognized at the start of a command
ACTION_VERBS = [
    "open ",
    "launch ",
    "start ",
    "run ",
    "show ",
    "go to ",
    "goto ",
]

# Strict execution threshold: fuzzy matches below this score will NOT auto-execute on raw Enter
AUTO_EXECUTE_MIN_SCORE = 0.75


def normalize_request(request: str) -> tuple[str, str]:
    """
    Clean and separate leading action verb from the query target.
    
    Returns:
        tuple of (verb, cleaned_target)
    """
    cleaned = request.strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)

    for verb in ACTION_VERBS:
        if cleaned.startswith(verb):
            target = cleaned[len(verb):].strip()
            return verb.strip(), target

    return "", cleaned


class DeterministicRouter(BaseRouter):
    """
    Fast deterministic router augmented with strict fuzzy discovery.
    
    Order of precedence:
    1. Direct internal actions (e.g. 'refresh apps')
    2. Direct URLs or configured URL aliases
    3. Known system and workspace folders
    4. Discovered applications and application aliases
    5. High-confidence fuzzy search fallback (score >= 0.75)
    6. Refusal / Unknown (preventing false execution)
    """

    def route(self, request: str, context: RoutingContext) -> Decision:
        t_start = time.perf_counter()
        raw_text = request.strip()
        if not raw_text:
            return Decision.unknown("", "Empty input")

        verb, target = normalize_request(raw_text)
        decision: Decision | None = None
        target_id: str | None = None

        # 1. Check for internal management commands
        if target in ("refresh apps", "refresh", "reload apps", "reload index"):
            decision = Decision(
                tool="refresh_apps",
                args={},
                confidence=1.0,
                source="deterministic",
                explanation="Internal command match: refresh apps"
            )
            target_id = "cmd:refresh_apps"

        # 2. Check for raw URL (http:// or https://)
        elif target.startswith("http://") or target.startswith("https://"):
            decision = Decision(
                tool="open_url",
                args={"url": target},
                confidence=1.0,
                source="deterministic",
                explanation=f"Direct web URL match: {target}"
            )
            target_id = f"url:{target}"

        # 3. Check for configured URL aliases (e.g. 'github', 'youtube')
        elif target in context.urls:
            url = context.urls[target]
            decision = Decision(
                tool="open_url",
                args={"url": url},
                confidence=0.98,
                source="deterministic",
                explanation=f"URL alias matched '{target}' -> {url}"
            )
            target_id = f"url:{target}"

        # 4. Check for Folder matches (e.g. 'downloads', 'documents', 'workspace', 'active projects')
        elif target in context.folders:
            folder_info = context.folders[target]
            decision = Decision(
                tool="open_folder",
                args={"folder": folder_info.path},
                confidence=1.0,
                source="deterministic",
                explanation=f"Known folder matched '{target}' -> {folder_info.path}"
            )
            target_id = f"folder:{target}"

        # 5. Check for Application matches
        elif target in context.aliases:
            resolved_app_key = context.aliases[target]
            if resolved_app_key in context.apps:
                app_info = context.apps[resolved_app_key]
                decision = Decision(
                    tool="open_app",
                    args={"app": resolved_app_key, "path": app_info.path},
                    confidence=0.98,
                    source="deterministic",
                    explanation=f"Application alias matched '{target}' -> {app_info.name}"
                )
                target_id = f"app:{resolved_app_key}"

        elif target in context.apps:
            app_info = context.apps[target]
            decision = Decision(
                tool="open_app",
                args={"app": target, "path": app_info.path},
                confidence=1.0,
                source="deterministic",
                explanation=f"Application matched '{target}' -> {app_info.name}"
            )
            target_id = f"app:{target}"

        # 6. Fallback to Fuzzy Search Index if available
        if decision is None and context.search_index is not None:
            results = context.search_index.search(target, limit=3)
            if results:
                top = results[0]
                # High-confidence fuzzy match meets execution threshold
                if top.score >= AUTO_EXECUTE_MIN_SCORE:
                    target_id = top.id
                    if top.category == CandidateCategory.APP:
                        decision = Decision(
                            tool="open_app",
                            args={"app": top.name.lower(), "path": top.target},
                            confidence=top.score,
                            source="deterministic_fuzzy",
                            explanation=f"Fuzzy match '{target}' -> {top.name} (score={top.score})"
                        )
                    elif top.category == CandidateCategory.FOLDER:
                        decision = Decision(
                            tool="open_folder",
                            args={"folder": top.target},
                            confidence=top.score,
                            source="deterministic_fuzzy",
                            explanation=f"Fuzzy folder match '{target}' -> {top.name} (score={top.score})"
                        )
                    elif top.category == CandidateCategory.WEB:
                        decision = Decision(
                            tool="open_url",
                            args={"url": top.target},
                            confidence=top.score,
                            source="deterministic_fuzzy",
                            explanation=f"Fuzzy web match '{target}' -> {top.name} (score={top.score})"
                        )
                    elif top.category == CandidateCategory.COMMAND:
                        decision = Decision(
                            tool="refresh_apps",
                            args={},
                            confidence=top.score,
                            source="deterministic_fuzzy",
                            explanation="Fuzzy match for refresh command"
                        )
                else:
                    logger.debug(
                        "Top fuzzy match '%s' (score=%.2f) below threshold %.2f; refusing auto-execution.",
                        top.name, top.score, AUTO_EXECUTE_MIN_SCORE
                    )

        # 7. Unresolved query fallback
        if decision is None:
            decision = Decision.unknown(request)

        # 8. Record telemetry event
        latency_ms = (time.perf_counter() - t_start) * 1000
        if context.telemetry:
            outcome = "resolved" if decision.is_resolved else "unresolved"
            context.telemetry.record_event(
                request=request,
                normalized_request=target,
                router=decision.source,
                outcome=outcome,
                tool=decision.tool if decision.is_resolved else None,
                target_id=target_id if decision.is_resolved else None,
                confidence=decision.confidence,
                latency_ms=latency_ms,
            )

        return decision
