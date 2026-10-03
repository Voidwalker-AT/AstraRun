"""Base machine provider interface for AstraRun 1.0."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from astrarun.core.logging import get_logger
from astrarun.machine.fact import MachineFact

logger = get_logger("astrarun.machine.providers.base")


class BaseMachineProvider(ABC):
    """Abstract base class for modular machine discovery providers."""

    name: str = "base_provider"

    @abstractmethod
    def discover(self) -> List[MachineFact]:
        """Perform initial discovery and return a list of MachineFacts."""
        pass

    def refresh(self, keys: Optional[List[str]] = None) -> List[MachineFact]:
        """
        Refresh dynamic/volatile facts. Defaults to calling discover().
        Subclasses can optimize to only refresh volatile keys.
        """
        return self.discover()
