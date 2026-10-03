"""Durable Task Checkpoints, State Recovery & Plan Revision for AstraRun 1.0.

Core Principles:
1. Recover state, not action history: Never blindly replay previously completed actions.
   Inspect what survived, what was lost, and resume from durable filesystem / process state.
2. Checkpoint durability: Every meaningful step records outputs, artifact hashes, and invariant states.
3. Secret-free persistence: Scrubbed data only; tokens and sensitive credentials are never serialized.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger
from astrarun.security.secret_broker import SecretBroker

logger = get_logger("astrarun.tasks.checkpoints")


@dataclass
class TaskCheckpoint:
    """Durable milestone record allowing seamless recovery after crashes, reboots, or interruptions."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = ""
    goal: str = ""
    status: str = "IN_PROGRESS"
    checkpoint_id: str = field(default_factory=lambda: f"chk_{int(time.time())}_{str(uuid.uuid4())[:6]}")
    plan_id: str = ""
    plan_version: int = 1
    completed_step_ids: List[str] = field(default_factory=list)
    completed_steps: List[Dict[str, Any]] = field(default_factory=list)
    current_step_id: Optional[str] = None
    current_step: Optional[Dict[str, Any]] = None
    step_index: int = 0
    important_outputs: Dict[str, Any] = field(default_factory=dict)
    context_variables: Dict[str, Any] = field(default_factory=dict)
    artifact_hashes: Dict[str, str] = field(default_factory=dict)  # filepath -> sha256
    artifacts: List[str] = field(default_factory=list)
    relevant_files: List[str] = field(default_factory=list)
    relevant_processes: Dict[str, Any] = field(default_factory=dict)  # handle/name -> pid
    browser_identifiers: Dict[str, Any] = field(default_factory=dict)  # tab_id, url
    workspace: str = ""
    machine_assumptions: Dict[str, Any] = field(default_factory=dict)
    resource_requirements: Dict[str, Any] = field(default_factory=dict)
    pending_confirmations: List[Dict[str, Any]] = field(default_factory=list)
    active_execution_budget_sec: float = 0.0
    pause_timestamp: Optional[float] = None
    pause_reason: Optional[str] = None
    recovery_metadata: Dict[str, Any] = field(default_factory=dict)
    invariant_states: Dict[str, bool] = field(default_factory=dict)  # invariant_id -> valid
    recoverable_handles: Dict[str, Any] = field(default_factory=dict)  # pids, hwnds, urls, download_ids
    summary: str = ""
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if self.artifacts and not self.artifact_hashes:
            for a in self.artifacts:
                self.artifact_hashes[a] = "unhashed"
        elif self.artifact_hashes and not self.artifacts:
            self.artifacts = list(self.artifact_hashes.keys())
        if self.important_outputs and not self.context_variables:
            self.context_variables = dict(self.important_outputs)
        elif self.context_variables and not self.important_outputs:
            self.important_outputs = dict(self.context_variables)

    def record_artifact(self, file_path: Path | str) -> Optional[str]:
        """Compute and store the SHA-256 hash of a generated or modified file."""
        p = Path(file_path)
        if not p.exists():
            return None
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(1024 * 1024):
                h.update(chunk)
        digest = h.hexdigest().lower()
        self.artifact_hashes[str(p.resolve())] = digest
        if str(p.resolve()) not in self.artifacts:
            self.artifacts.append(str(p.resolve()))
        return digest

    def to_dict(self) -> Dict[str, Any]:
        """Serialize checkpoint while ensuring zero secret leakage."""
        broker = SecretBroker()
        raw = asdict(self)
        # Scrub string outputs and context variables
        clean_outputs = {}
        for k, v in self.important_outputs.items():
            if isinstance(v, str):
                clean_outputs[k] = broker.scrub_text(v)[0]
            else:
                clean_outputs[k] = v
        raw["important_outputs"] = clean_outputs
        raw["context_variables"] = clean_outputs
        if isinstance(raw.get("summary"), str):
            raw["summary"] = broker.scrub_text(raw["summary"])[0]
        return raw

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskCheckpoint:
        known_keys = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known_keys}
        return cls(**filtered)


@dataclass
class PlanRevision:
    """Provenance record capturing dynamic adjustments to a task execution DAG."""
    original_plan_id: str
    revision: int
    reason: str
    preserved_completed_steps: List[str] = field(default_factory=list)
    invalidated_steps: List[str] = field(default_factory=list)
    new_steps: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class RecoveryPlan:
    """Reconstructed execution path formulated after environmental disturbance."""
    task_id: str
    original_plan_id: str
    disturbance_id: str
    reason: str
    survived_state: Dict[str, Any] = field(default_factory=dict)
    preserved_completed_steps: List[str] = field(default_factory=list)
    recovery_actions: List[Dict[str, Any]] = field(default_factory=list)
    resume_from_step_id: Optional[str] = None
    needs_user_clarification: bool = False
    clarification_payload: Optional[Dict[str, Any]] = None
