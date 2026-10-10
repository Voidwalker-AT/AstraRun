"""Universal Computer-Use Subsystem for AstraRun.

Exposes generic mechanisms for observing and controlling Windows applications,
browsers, and user interfaces under strict security and lifecycle governance.
Does NOT decide semantic intent (which is strictly owned by the Brain domain).
"""

from __future__ import annotations

from astrarun.computer_use.controller import ComputerUseController
from astrarun.computer_use.facade import ComputerUse
from astrarun.computer_use.models import (
    ActionBackend,
    ComputerUseObservation,
    ControlType,
    RecoveryAction,
    UIAction,
    UIElement,
    VerificationCondition,
    VerificationResult,
)
from astrarun.computer_use.session import ApplicationSession, SessionState

__all__ = [
    "ComputerUse",
    "ComputerUseController",
    "ApplicationSession",
    "SessionState",
    "ActionBackend",
    "ControlType",
    "UIElement",
    "UIAction",
    "ComputerUseObservation",
    "VerificationCondition",
    "VerificationResult",
    "RecoveryAction",
]
