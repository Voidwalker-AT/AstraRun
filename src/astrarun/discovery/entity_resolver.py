"""Backward-compatible bridge forwarding to astrarun.brain.decision.entity_resolver."""

from __future__ import annotations

from astrarun.brain.decision.entity_resolver import (
    MAINTENANCE_KEYWORDS,
    ResolvedEntity,
    SemanticEntityResolver,
    resolve_lnk_target,
)

__all__ = [
    "MAINTENANCE_KEYWORDS",
    "ResolvedEntity",
    "SemanticEntityResolver",
    "resolve_lnk_target",
]
