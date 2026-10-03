"""Dynamic Tool to Skill Lifecycle Promotion for AstraRun 1.0.

Tracks execution trajectories of ephemeral dynamic tools, identifies recurring
patterns, validates them, and promotes eligible tools to permanent procedural
skills in Hermes SKILL.md format.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.tools.candidate import CandidateTool

logger = get_logger("astrarun.tools.lifecycle")


@dataclass
class ToolTrajectoryRecord:
    """Record tracking usage patterns of dynamic tools."""
    tool_id: str
    goal: str
    execution_count: int = 1
    success_count: int = 1
    first_executed: float = field(default_factory=time.time)
    last_executed: float = field(default_factory=time.time)
    artifacts_produced: List[str] = field(default_factory=list)
    promoted_to_skill: bool = False
    skill_name: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ToolTrajectoryRecord:
        return cls(**data)


class ToolLifecycleManager:
    """Manages trajectory tracking and skill promotion."""

    def __init__(
        self,
        storage_path: Optional[Path] = None,
        skills_dir: Optional[Path] = None,
        promotion_threshold: int = 2,
    ) -> None:
        self.storage_path = Path(storage_path or Path("data/tool_trajectories.json")).resolve()
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self.skills_dir = Path(skills_dir or Path("skills")).resolve()
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.promotion_threshold = promotion_threshold
        self._records: Dict[str, ToolTrajectoryRecord] = {}
        self._load()

    def _load(self) -> None:
        if self.storage_path.exists():
            try:
                data = json.loads(self.storage_path.read_text(encoding="utf-8"))
                for k, v in data.items():
                    self._records[k] = ToolTrajectoryRecord.from_dict(v)
            except Exception as e:
                logger.warning("Failed to load tool trajectories: %s", e)

    def _save(self) -> None:
        try:
            d = {k: v.to_dict() for k, v in self._records.items()}
            self.storage_path.write_text(json.dumps(d, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error("Failed to save tool trajectories: %s", e)

    def record_execution(
        self,
        candidate: CandidateTool,
        success: bool,
        artifacts: Optional[List[Path]] = None,
    ) -> ToolTrajectoryRecord:
        """Record an execution instance of a dynamic tool."""
        # Normalize goal as key
        key = re.sub(r"[^a-zA-Z0-9_]+", "_", candidate.goal.lower().strip())[:48]
        art_names = [p.name for p in (artifacts or [])]

        if key in self._records:
            rec = self._records[key]
            rec.execution_count += 1
            if success:
                rec.success_count += 1
            rec.last_executed = time.time()
            for a in art_names:
                if a not in rec.artifacts_produced:
                    rec.artifacts_produced.append(a)
        else:
            rec = ToolTrajectoryRecord(
                tool_id=candidate.tool_id,
                goal=candidate.goal,
                execution_count=1,
                success_count=1 if success else 0,
                artifacts_produced=art_names,
            )
            self._records[key] = rec

        self._save()
        return rec

    def is_eligible_for_promotion(self, goal: str) -> bool:
        """Check if tool pattern has met recurrence and reliability thresholds."""
        key = re.sub(r"[^a-zA-Z0-9_]+", "_", goal.lower().strip())[:48]
        rec = self._records.get(key)
        if not rec:
            return False
        return (
            not rec.promoted_to_skill
            and rec.success_count >= self.promotion_threshold
            and (rec.success_count / rec.execution_count) >= 0.8
        )

    def promote_to_skill(self, candidate: CandidateTool, skill_name: Optional[str] = None) -> Path:
        """Promote a candidate tool into a permanent procedural skill."""
        sname = skill_name or re.sub(r"[^a-zA-Z0-9_]+", "_", candidate.goal.lower().strip())[:32]
        skill_dir = self.skills_dir / sname
        skill_dir.mkdir(parents=True, exist_ok=True)

        md_content = f"""---
name: {sname}
description: Governed procedural skill generated from recurring goal: {candidate.goal}
version: 1.0.0
risk_level: LOW
author: Astra Dynamic Tool Promotion
created_at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
---

# Skill: {sname}

## Goal
{candidate.goal}

## Inputs
{json.dumps(candidate.inputs, indent=2)}

## Implementation
```python
{candidate.executable_code.strip()}
```

## Verification Procedure
```python
{candidate.test_verification_block.strip() or '# Verification asserted during sandbox run'}
```

## Expected Side Effects
{chr(10).join(f"- {eff}" for eff in candidate.expected_side_effects) or "- Generates verified output artifact"}
"""

        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(md_content, encoding="utf-8")

        # Mark trajectory record as promoted
        key = re.sub(r"[^a-zA-Z0-9_]+", "_", candidate.goal.lower().strip())[:48]
        if key in self._records:
            self._records[key].promoted_to_skill = True
            self._records[key].skill_name = sname
            self._save()

        logger.info("Promoted candidate tool %s to skill: %s", candidate.tool_id, skill_file)
        return skill_file
