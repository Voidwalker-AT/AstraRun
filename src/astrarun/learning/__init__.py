"""AstraRun Learning, Memory & Skill Foundation Subsystem (v0.8.5).

Exports domain models, evidence extractors, confidence calculators,
semantic memory stores, alias managers, pattern miners, and learning engine.
"""

from __future__ import annotations

from astrarun.learning.aliases import AliasManager
from astrarun.learning.confidence import ConfidenceCalculator
from astrarun.learning.dataset_builder import DatasetBuilder
from astrarun.learning.engine import LearningEngine
from astrarun.learning.evidence import EvidenceExtractor
from astrarun.learning.memory import MemoryStore
from astrarun.learning.models import (
    AuditAction,
    AuditEvent,
    Correction,
    EvidenceReference,
    EvidenceType,
    MemoryNamespace,
    MemoryStatus,
    SemanticMemory,
    SkillCandidate,
    SkillStatus,
    SkillStep,
)
from astrarun.learning.patterns import PatternMiner
from astrarun.learning.persistence import LearningPersistence
from astrarun.learning.skills import SkillManager

__all__ = [
    "AliasManager",
    "AuditAction",
    "AuditEvent",
    "ConfidenceCalculator",
    "Correction",
    "DatasetBuilder",
    "EvidenceExtractor",
    "EvidenceReference",
    "EvidenceType",
    "LearningEngine",
    "LearningPersistence",
    "MemoryNamespace",
    "MemoryStatus",
    "MemoryStore",
    "PatternMiner",
    "SemanticMemory",
    "SkillCandidate",
    "SkillManager",
    "SkillStatus",
    "SkillStep",
]
