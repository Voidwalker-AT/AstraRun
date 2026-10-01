"""Hermes-style Progressive Skill Disclosure and Retrieval for AstraRun.

Implements 3-tier progressive skill disclosure:
  - Tier 1: Compact Name + 1-sentence description in system prompt (~15-20 tokens)
  - Tier 2: Detailed parameter schema injected upon skill selection
  - Tier 3: Isolated executable workflow loaded only upon execution
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.rag.embeddings import EmbeddingProvider
from astrarun.rag.models import SkillDefinition, SkillTier, TrustLevel

logger = get_logger("astrarun.rag.skills")


class SkillRegistry:
    """
    Houses validated and user-defined skills, managing progressive disclosure schemas.
    """

    def __init__(self):
        self._skills: Dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        """Register or update a skill in the catalog."""
        self._skills[skill.name.lower()] = skill
        logger.debug("Registered skill: %s", skill.name)

    def get(self, skill_name: str) -> Optional[SkillDefinition]:
        """Fetch a skill definition by name."""
        return self._skills.get(skill_name.lower())

    def list_all(self) -> List[SkillDefinition]:
        """Return all registered skills."""
        return list(self._skills.values())

    def export_tier_1_catalog(self) -> List[Dict[str, str]]:
        """
        Export lightweight Tier 1 catalog representation for system prompt injection.
        Each entry consumes only ~15-20 tokens.
        """
        return [s.to_tier_1_catalog() for s in self._skills.values()]

    def load_from_markdown(self, markdown_content: str, file_path: Optional[str] = None) -> Optional[SkillDefinition]:
        """
        Parse a SKILL.md document into a SkillDefinition.
        Supports standard SKILL.md format with YAML frontmatter or Markdown headers.
        """
        lines = markdown_content.splitlines()
        name = "Unknown Skill"
        desc = ""
        params: Dict[str, Any] = {}
        risk = "LOW"
        tags: List[str] = []
        code_lines: List[str] = []

        in_frontmatter = False
        in_code_block = False

        for line in lines:
            stripped = line.strip()
            if stripped == "---":
                in_frontmatter = not in_frontmatter
                continue

            if in_frontmatter:
                if ":" in stripped:
                    k, v = stripped.split(":", 1)
                    k, v = k.strip().lower(), v.strip()
                    if k == "name":
                        name = v
                    elif k in ("description", "desc"):
                        desc = v
                    elif k in ("risk", "risk_level"):
                        risk = v.upper()
                    elif k == "tags":
                        tags = [t.strip() for t in v.split(",") if t.strip()]
                continue

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue

            if in_code_block:
                code_lines.append(line)
            else:
                if stripped.startswith("# ") and name == "Unknown Skill":
                    name = stripped.lstrip("# ").strip()
                elif (stripped.startswith("## Description") or stripped.startswith(">")) and not desc:
                    desc = stripped.lstrip("#> Description:").strip()

        if not desc:
            desc = f"Executes the {name} skill."

        skill = SkillDefinition(
            id=re.sub(r"[^\w\-]", "_", name.lower()),
            name=name,
            one_sentence_description=desc,
            parameters_schema=params,
            executable_content="\n".join(code_lines),
            risk_level=risk,
            tags=tags,
            source_file=file_path,
        )
        self.register(skill)
        return skill

    def load_skills_directory(self, skills_dir: str | Path) -> int:
        """Scan a directory for SKILL.md files and load them."""
        p = Path(skills_dir)
        if not p.exists() or not p.is_dir():
            return 0

        count = 0
        for md_file in p.glob("**/*.md"):
            try:
                content = md_file.read_text(encoding="utf-8", errors="replace")
                if "SKILL" in md_file.name.upper() or "name:" in content.lower():
                    if self.load_from_markdown(content, file_path=str(md_file)):
                        count += 1
            except Exception as e:
                logger.debug("Failed to load skill file %s: %s", md_file, e)
        return count


class SkillRetriever:
    """
    Ranks and retrieves top-K skills matching a user's task or query.
    Prevents context blowup by selectively disclosing schemas.
    """

    def __init__(self, registry: SkillRegistry, embeddings: EmbeddingProvider):
        self.registry = registry
        self.embeddings = embeddings

    def find_relevant_skills(self, user_goal: str, top_k: int = 3) -> List[SkillDefinition]:
        """
        Find top-K skills matching the user goal using hybrid lexical + semantic matching.
        """
        all_skills = self.registry.list_all()
        if not all_skills:
            return []

        # If few skills, return all up to top_k
        if len(all_skills) <= top_k:
            return all_skills

        goal_lower = user_goal.lower()
        scored_skills = []

        # Embed user goal for semantic comparison
        goal_vec = self.embeddings.embed_text(user_goal)

        for skill in all_skills:
            # 1. Lexical Score (token overlap with name, desc, tags)
            lex_score = 0.0
            name_tokens = skill.name.lower().split()
            desc_tokens = skill.one_sentence_description.lower().split()
            for t in name_tokens:
                if t in goal_lower:
                    lex_score += 0.5
            for t in desc_tokens:
                if len(t) > 3 and t in goal_lower:
                    lex_score += 0.1
            for tag in skill.tags:
                if tag.lower() in goal_lower:
                    lex_score += 0.3

            # 2. Semantic Score
            skill_text = f"{skill.name}: {skill.one_sentence_description}"
            skill_vec = self.embeddings.embed_text(skill_text)
            import numpy as np
            sem_score = float(np.dot(goal_vec, skill_vec))

            # Fused score
            final_score = (0.4 * min(1.0, lex_score)) + (0.6 * sem_score)
            scored_skills.append((skill, final_score))

        scored_skills.sort(key=lambda x: x[1], reverse=True)
        return [skill for skill, score in scored_skills[:top_k]]
