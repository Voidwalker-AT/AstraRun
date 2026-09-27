"""AI Bridge interface boundary protocol for AstraRun v0.6.

Defines the clean abstraction layer connecting AstraRun workstation control
to future external reasoning providers (AI Bridge).
Zero direct cloud model API calls exist inside AstraRun.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class ReasoningRequest:
    """Request payload sent to a reasoning provider."""
    prompt: str
    system_instruction: str = ""
    context_data: dict[str, Any] = field(default_factory=dict)
    temperature: float = 0.2
    max_tokens: int = 512
    session_id: str = ""


@dataclass
class ReasoningResult:
    """Standardized response from a reasoning provider."""
    content: str
    model_name: str
    provider: str
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    raw_response: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ReasoningProvider(Protocol):
    """
    Protocol defining the reasoning gateway contract.
    Implemented by AI Bridge (or local mocked adapters) outside AstraRun.
    """

    def is_available(self) -> bool:
        """Check whether the reasoning service is online and ready."""
        ...

    def ask(self, request: ReasoningRequest) -> ReasoningResult:
        """Submit a reasoning request synchronously."""
        ...

    async def ask_async(self, request: ReasoningRequest) -> ReasoningResult:
        """Submit a reasoning request asynchronously."""
        ...
