"""Canonical Procedural Skill Service for AstraRun.

Preserves Hermes-style 3-Tier Progressive Skill Disclosure:
- Tier 1: Compact Name + 1-sentence description in system prompt (~15-20 tokens)
- Tier 2: Detailed parameter schema injected upon skill selection
- Tier 3: Isolated executable workflow loaded only upon execution
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("astrarun.memory.skills")


class SkillTier(int, Enum):
    """Progressive disclosure tiers."""
    CATALOG = 1     # Name + brief description
    SCHEMA = 2      # Parameters and input/output contracts
    EXECUTABLE = 3  # Full workflow / code implementation


@dataclass
class SkillDefinition:
    """Canonical representation of a procedural skill."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    executable_code: Optional[str] = None
    risk_level: str = "LOW"
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"

    def to_tier_1(self) -> Dict[str, str]:
        """Compact catalog entry for prompt injection (~15-20 tokens)."""
        return {"name": self.name, "description": self.description}

    def to_tier_2(self) -> Dict[str, Any]:
        """Schema disclosure."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "risk_level": self.risk_level,
        }

    def to_tier_3(self) -> Dict[str, Any]:
        """Full executable representation."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "executable_code": self.executable_code,
            "risk_level": self.risk_level,
            "version": self.version,
        }


class SkillService:
    """Authoritative procedural skill catalog and disclosure engine."""

    def __init__(self) -> None:
        self._skills: Dict[str, SkillDefinition] = {}

    def register_skill(self, skill: SkillDefinition) -> None:
        """Register a procedural skill."""
        self._skills[skill.name.lower()] = skill
        logger.debug("Registered procedural skill '%s'", skill.name)

    def get_skill(self, name: str) -> Optional[SkillDefinition]:
        """Retrieve skill definition by name."""
        return self._skills.get(name.lower())

    def list_skills(self) -> List[SkillDefinition]:
        """List all active skills."""
        return list(self._skills.values())

    def get_tier_1_catalog(self) -> List[Dict[str, str]]:
        """Lightweight prompt-friendly catalog of all skills."""
        return [s.to_tier_1() for s in self._skills.values()]

    def load_skill_markdown(self, content: str) -> Optional[SkillDefinition]:
        """Parse SKILL.md format into a canonical SkillDefinition."""
        lines = content.splitlines()
        name = "custom_skill"
        desc = ""
        params: Dict[str, Any] = {}
        for line in lines:
            if line.startswith("# ") and name == "custom_skill":
                name = line[2:].strip()
            elif line.startswith("Description:") or line.startswith("> Description:"):
                desc = line.split(":", 1)[1].strip()

        skill = SkillDefinition(name=name, description=desc or "Procedural skill", parameters=params)
        self.register_skill(skill)
        return skill
