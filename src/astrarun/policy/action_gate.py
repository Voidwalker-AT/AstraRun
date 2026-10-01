"""ActionGate policy adapter maintaining backwards compatibility with v0.6-v0.11 callers."""

from __future__ import annotations

from astrarun.security.action_gate import (
    INITIAL_PRODUCTION_ALLOWLIST,
    ActionGate,
    ActionGateConfig,
    ConfirmationToken,
)

__all__ = [
    "ActionGate",
    "ActionGateConfig",
    "ConfirmationToken",
    "INITIAL_PRODUCTION_ALLOWLIST",
]
