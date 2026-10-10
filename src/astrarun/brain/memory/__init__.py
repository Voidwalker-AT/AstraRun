"""Memory package for AstraRun Brain."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from astrarun.memory.service import MemoryService


class BrainMemory:
    """Unified memory facade for AstraRun Brain."""

    def __init__(self, memory_service: Optional[MemoryService] = None) -> None:
        self.service = memory_service

    def get_working_memory(self) -> Dict[str, Any]:
        if self.service and hasattr(self.service, "working"):
            return self.service.working.snapshot()
        return {}

    def get_facts(self) -> List[Dict[str, Any]]:
        if self.service and hasattr(self.service, "semantic"):
            return self.service.semantic.get_facts()
        return []


__all__ = ["BrainMemory"]
