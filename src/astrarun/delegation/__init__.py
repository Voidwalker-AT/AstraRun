"""AstraRun Delegated Agent Orchestration Subsystem.

Provides provider-neutral delegated AI orchestration, session tracking,
context packaging, advisory proposal parsing, and closed-loop empirical verification.
"""

from astrarun.delegation.models import (
    DelegateSession,
    DelegateProposal,
    DelegateResponse,
    DelegateTurn,
    ReviewStatus,
)
from astrarun.delegation.provider import DelegateProvider, DelegateRegistry
from astrarun.delegation.packager import ContextPackager
from astrarun.delegation.proposal import parse_delegate_proposal
from astrarun.delegation.mock import MockDelegateProvider

__all__ = [
    "DelegateSession",
    "DelegateProposal",
    "DelegateResponse",
    "DelegateTurn",
    "ReviewStatus",
    "DelegateProvider",
    "DelegateRegistry",
    "ContextPackager",
    "parse_delegate_proposal",
    "MockDelegateProvider",
]
