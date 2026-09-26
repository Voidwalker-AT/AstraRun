"""Deterministic rule-based router for AstraRun v0.1."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from astrarun.core.logging import get_logger
from astrarun.core.models import Decision, RoutingContext
from astrarun.routing.base import BaseRouter

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


def normalize_request(request: str) -> tuple[str, str]:
    """
    Clean and separate leading action verb from the query target.
    
    Returns:
        tuple of (verb, cleaned_target)
    """
    cleaned = request.strip().lower()
    # Collapse multiple whitespace
    cleaned = re.sub(r"\s+", " ", cleaned)

    for verb in ACTION_VERBS:
        if cleaned.startswith(verb):
            target = cleaned[len(verb):].strip()
            return verb.strip(), target

    return "", cleaned


class DeterministicRouter(BaseRouter):
    """
    Fast, rule-based deterministic router.
    
    Matches commands against:
    1. Direct URLs or configured URL aliases
    2. Known system and workspace folders
    3. Discovered applications and application aliases
    """

    def route(self, request: str, context: RoutingContext) -> Decision:
        raw_text = request.strip()
        if not raw_text:
            return Decision.unknown("", "Empty input")

        verb, target = normalize_request(raw_text)

        # 1. Check for raw URL (http:// or https://)
        if target.startswith("http://") or target.startswith("https://"):
            return Decision(
                tool="open_url",
                args={"url": target},
                confidence=1.0,
                source="deterministic",
                explanation=f"Direct web URL match: {target}"
            )

        # 2. Check for configured URL aliases (e.g. 'github', 'youtube')
        if target in context.urls:
            url = context.urls[target]
            return Decision(
                tool="open_url",
                args={"url": url},
                confidence=1.0,
                source="deterministic",
                explanation=f"URL alias matched '{target}' -> {url}"
            )

        # 3. Check for Folder matches (e.g. 'downloads', 'documents', 'workspace', 'active projects')
        # Check direct target or alias
        if target in context.folders:
            folder_info = context.folders[target]
            return Decision(
                tool="open_folder",
                args={"folder": folder_info.path},
                confidence=1.0,
                source="deterministic",
                explanation=f"Known folder matched '{target}' -> {folder_info.path}"
            )

        # 4. Check for Application matches
        # Resolve via alias if present (e.g. 'vscode' -> 'code', 'calculator' -> 'calc')
        resolved_app_key = context.aliases.get(target, target)

        if resolved_app_key in context.apps:
            app_info = context.apps[resolved_app_key]
            return Decision(
                tool="open_app",
                args={"app": resolved_app_key, "path": app_info.path},
                confidence=1.0,
                source="deterministic",
                explanation=f"Application matched '{target}' -> {app_info.name} ({app_info.path})"
            )

        # Also check if any discovered app name matches directly
        for key, app_info in context.apps.items():
            if app_info.name.lower() == target:
                return Decision(
                    tool="open_app",
                    args={"app": key, "path": app_info.path},
                    confidence=0.95,
                    source="deterministic",
                    explanation=f"Application name matched '{target}' -> {app_info.name} ({app_info.path})"
                )

        logger.debug("Deterministic router could not resolve request: '%s'", request)
        return Decision.unknown(request)
