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


from astrarun.tasks.checkpoints import TaskCheckpoint


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
        from astrarun.core.paths import AstraPaths
        self.checkpoints_dir = Path(checkpoints_dir or (AstraPaths.data_dir() / "checkpoints")).resolve()
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self,
        task_id: Any,
        goal: str = "",
        status: str = "IN_PROGRESS",
        step_index: int = 0,
        artifacts: Optional[List[str]] = None,
        context_variables: Optional[Dict[str, Any]] = None,
        summary: str = "",
    ) -> TaskCheckpoint:
        """Save task state snapshot to disk."""
        if hasattr(task_id, "task_id"):
            cp_obj = task_id
            t_id = cp_obj.task_id
            g = getattr(cp_obj, "goal", goal)
            st = getattr(cp_obj, "status", status)
            si = getattr(cp_obj, "step_index", step_index)
            arts = getattr(cp_obj, "artifacts", artifacts or [])
            cv = getattr(cp_obj, "context_variables", getattr(cp_obj, "important_outputs", context_variables or {}))
            sm = getattr(cp_obj, "summary", summary)
            cp = TaskCheckpoint(
                task_id=t_id,
                goal=g,
                status=st,
                step_index=si,
                timestamp=getattr(cp_obj, "timestamp", time.time()),
                artifacts=arts,
                context_variables=cv,
                summary=sm,
            )
            file_path = self.checkpoints_dir / f"{t_id}.json"
            file_path.write_text(json.dumps(cp.to_dict(), indent=2), encoding="utf-8")
            logger.debug("Checkpoint saved: %s (status=%s)", t_id, st)
            return cp

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

    load_latest_checkpoint = load_checkpoint
    def check_machine_drift(
        self,
        checkpoint: TaskCheckpoint,
        mounted_volumes: Optional[List[str]] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Compare checkpoint machine assumptions with current machine reality.
        Returns: (has_drift, drift_reasons)
        """
        drift_reasons: List[str] = []
        if mounted_volumes is None:
            try:
                from astrarun.machine.model import MachineModel
                vols_fact = MachineModel.get_instance().get_fact("hardware.storage.volumes")
                mounted_volumes = vols_fact.value if vols_fact else ["C"]
            except Exception:
                mounted_volumes = ["C"]

        mounted_upper = {str(v).upper().replace(":", "").replace("\\", "") for v in mounted_volumes}

        for art in checkpoint.artifacts:
            if len(art) >= 2 and art[1] == ":":
                drive = art[0].upper()
                if drive not in mounted_upper:
                    drift_reasons.append(
                        f"Storage volume {drive}:\\ required for artifact '{art}' is currently missing or disconnected."
                    )

        return len(drift_reasons) > 0, drift_reasons

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
