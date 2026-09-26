"""Abstract base router definition."""

from __future__ import annotations

from abc import ABC, abstractmethod

from astrarun.core.models import Decision, RoutingContext


class BaseRouter(ABC):
    """Abstract interface that all AstraRun routers must implement."""

    @abstractmethod
    def route(self, request: str, context: RoutingContext) -> Decision:
        """Parse natural-language request in context and return a structured Decision."""
        pass
