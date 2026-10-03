"""Task, Session, and Semantic Continuity Engine for AstraRun 1.0.

Provides:
- Checkpoint persistence across task execution.
- Interrupted task discovery on application startup.
- Semantic resolution of ambiguous continuation queries ("continue what we were doing")
  with confidence thresholds and clarification branching.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tasks.continuity")


@dataclass
class TaskCheckpoint:
    """Snapshot of a task state for continuity and resumption."""
    task_id: str
    goal: str
    status: str  # IN_PROGRESS, COMPLETED, PAUSED, FAILED
    step_index: int = 0
    timestamp: float = field(default_factory=time.time)
    artifacts: List[str] = field(default_factory=list)
    context_variables: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskCheckpoint:
        return cls(**data)


@dataclass
class ContinuityResolution:
    """Outcome of resolving an ambiguous or semantic continuation query."""
    resolved: bool
    confidence: float
    target_task: Optional[TaskCheckpoint] = None
    explanation: str = ""
    needs_clarification: bool = False
    clarification_options: List[Dict[str, Any]] = field(default_factory=list)


class ContinuityEngine:
    """Authoritative continuity manager for Astra tasks and sessions."""

    def __init__(self, checkpoints_dir: Optional[Path] = None) -> None:
        self.checkpoints_dir = Path(checkpoints_dir or Path("data/checkpoints")).resolve()
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        task_id: str,
        goal: str,
        status: str = "IN_PROGRESS",
        step_index: int = 0,
        artifacts: Optional[List[str]] = None,
        context_variables: Optional[Dict[str, Any]] = None,
        summary: str = "",
    ) -> TaskCheckpoint:
        """Save task state snapshot to disk."""
        cp = TaskCheckpoint(
            task_id=task_id,
            goal=goal,
            status=status,
            step_index=step_index,
            timestamp=time.time(),
            artifacts=artifacts or [],
            context_variables=context_variables or {},
            summary=summary,
        )
        file_path = self.checkpoints_dir / f"{task_id}.json"
        file_path.write_text(json.dumps(cp.to_dict(), indent=2), encoding="utf-8")
        logger.debug("Checkpoint saved: %s (status=%s)", task_id, status)
        return cp

    def load_checkpoint(self, task_id: str) -> Optional[TaskCheckpoint]:
        """Load a specific task checkpoint by task_id."""
        file_path = self.checkpoints_dir / f"{task_id}.json"
        if not file_path.exists():
            return None
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
            return TaskCheckpoint.from_dict(data)
        except Exception as e:
            logger.warning("Error reading checkpoint %s: %s", file_path, e)
            return None

    def list_checkpoints(self, limit: int = 20) -> List[TaskCheckpoint]:
        """List all available checkpoints ordered by recency."""
        checkpoints: List[TaskCheckpoint] = []
        for p in self.checkpoints_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                checkpoints.append(TaskCheckpoint.from_dict(data))
            except Exception:
                continue
        checkpoints.sort(key=lambda cp: cp.timestamp, reverse=True)
        return checkpoints[:limit]

    def discover_interrupted_tasks(self) -> List[TaskCheckpoint]:
        """Identify tasks that were left IN_PROGRESS or PAUSED across session restarts."""
        interrupted = [
            cp for cp in self.list_checkpoints()
            if cp.status in {"IN_PROGRESS", "PAUSED"}
        ]
        logger.info("Session restart: discovered %d interrupted tasks.", len(interrupted))
        return interrupted

    def resolve_continuation_request(
        self,
        user_query: str,
        confidence_threshold: float = 0.80,
    ) -> ContinuityResolution:
        """
        Semantically resolve a continuation intent like:
        - 'continue the graph thing we were doing'
        - 'continue what we were doing'
        - 'keep going'
        """
        q_norm = user_query.lower().strip()
        tokens = set(re.findall(r"\w+", q_norm))

        recent_checkpoints = self.list_checkpoints(limit=10)
        if not recent_checkpoints:
            return ContinuityResolution(
                resolved=False,
                confidence=0.0,
                explanation="No previous task checkpoints found in session history.",
                needs_clarification=False,
            )

        scored: List[Tuple[float, TaskCheckpoint]] = []

        now = time.time()
        for i, cp in enumerate(recent_checkpoints):
            goal_tokens = set(re.findall(r"\w+", cp.goal.lower()))
            summary_tokens = set(re.findall(r"\w+", cp.summary.lower()))
            artifact_tokens = set(re.findall(r"\w+", " ".join(cp.artifacts).lower()))

            all_target_tokens = goal_tokens | summary_tokens | artifact_tokens

            # Stop words filter
            meaningful_query_tokens = tokens - {
                "continue", "resume", "the", "what", "we", "were", "doing",
                "thing", "please", "can", "you", "keep", "going", "with", "that"
            }

            if meaningful_query_tokens:
                overlap = meaningful_query_tokens & all_target_tokens
                token_score = len(overlap) / len(meaningful_query_tokens)
            else:
                # Completely generic "continue what we were doing" -> bias strongly toward most recent task
                token_score = 0.90 if i == 0 else 0.20

            # Recency factor: within last hour gets boost
            age_hours = (now - cp.timestamp) / 3600.0
            recency_boost = max(0.0, 0.10 * (1.0 - min(1.0, age_hours / 24.0)))

            total_score = min(1.0, token_score + (recency_boost if token_score > 0.3 else 0.0))
            scored.append((total_score, cp))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_score, top_cp = scored[0]

        if top_score >= confidence_threshold:
            return ContinuityResolution(
                resolved=True,
                confidence=round(top_score, 3),
                target_task=top_cp,
                explanation=f"Matched previous task '{top_cp.goal}' with high confidence ({round(top_score*100)}%).",
                needs_clarification=False,
            )

        # Ambiguous case: multiple candidates or low confidence
        candidates = [
            {"task_id": cp.task_id, "goal": cp.goal, "score": round(score, 3)}
            for score, cp in scored[:3] if score > 0.2
        ]
        return ContinuityResolution(
            resolved=False,
            confidence=round(top_score, 3),
            target_task=top_cp if top_score > 0.4 else None,
            explanation="Continuation query is ambiguous; multiple candidate tasks detected.",
            needs_clarification=True,
            clarification_options=candidates,
        )
