"""Sequential Pattern Mining Engine for AstraRun Learning Foundation.

Discovers recurring multi-step workstation capability sequences from TaskLedger history,
abstracts concrete arguments into parameters, and assesses aggregate safety risks.
"""

from __future__ import annotations

import collections
import time
import uuid
from typing import Any, Sequence

from astrarun.core.logging import get_logger
from astrarun.learning.models import (
    SkillCandidate,
    SkillStatus,
    SkillStep,
)
from astrarun.tasks.models import Task, TaskEventType, TaskStatus

logger = get_logger("astrarun.learning.patterns")

DEFAULT_MIN_PATTERN_SUPPORT = 3
MAX_PATTERN_LENGTH = 5


class PatternMiner:
    """
    Offline sequential pattern miner extracting reusable workflow subgraphs from completed tasks.
    """

    def __init__(self, min_support: int = DEFAULT_MIN_PATTERN_SUPPORT) -> None:
        self.min_support = min_support

    def extract_capability_sequences(self, tasks: Sequence[Task]) -> list[tuple[str, list[dict[str, Any]]]]:
        """
        Extract ordered lists of capability invocations for each successfully completed task.
        Returns: list of (task_id, [(capability_id, arguments)])
        """
        sequences: list[tuple[str, list[dict[str, Any]]]] = []

        for t in tasks:
            if t.status != TaskStatus.COMPLETED:
                continue

            steps: list[dict[str, Any]] = []
            for ev in t.events:
                if ev.type == TaskEventType.CAPABILITY_COMPLETED and ev.capability_id:
                    steps.append({
                        "capability_id": ev.capability_id,
                        "data": dict(ev.data),
                    })

            if len(steps) >= 2:
                sequences.append((t.id, steps))

        return sequences

    def mine_patterns(self, tasks: Sequence[Task]) -> list[SkillCandidate]:
        """
        Mine repetitive contiguous capability n-grams across task histories.
        """
        sequences = self.extract_capability_sequences(tasks)
        if len(sequences) < self.min_support:
            return []

        # Count n-grams of length 2 to MAX_PATTERN_LENGTH
        ngram_occurrences: dict[tuple[str, ...], list[tuple[str, list[dict[str, Any]]]]] = collections.defaultdict(list)

        for task_id, steps in sequences:
            cap_ids = [s["capability_id"] for s in steps]
            n_steps = len(cap_ids)
            for length in range(2, min(n_steps + 1, MAX_PATTERN_LENGTH + 1)):
                for start in range(n_steps - length + 1):
                    sub_caps = tuple(cap_ids[start:start + length])
                    sub_steps = steps[start:start + length]
                    ngram_occurrences[sub_caps].append((task_id, sub_steps))

        candidates: list[SkillCandidate] = []
        now = time.time()

        for sub_caps, occs in ngram_occurrences.items():
            support = len(occs)
            if support >= self.min_support:
                # Deduplicate task IDs
                unique_task_ids = list({occ[0] for occ in occs})
                if len(unique_task_ids) < self.min_support:
                    continue

                # Formulate candidate name & description
                name = "-".join([c.replace("capability.", "").replace("_", "-") for c in sub_caps])
                desc = f"Automated workflow performing {' -> '.join(sub_caps)}."

                # Parameterize steps
                skill_steps: list[SkillStep] = []
                parameters: list[dict[str, Any]] = []

                # Sample the first occurrence to extract parameters
                sample_steps = occs[0][1]
                for idx, step_data in enumerate(sample_steps):
                    cap_id = step_data["capability_id"]
                    raw_args = step_data.get("data", {})

                    bindings: dict[str, str] = {}
                    # Identify common parameters (e.g. project_path, target_port, process_name)
                    for arg_key, arg_val in raw_args.items():
                        if arg_key in {"project", "path", "folder", "cwd", "target"}:
                            param_name = f"target_{arg_key}"
                            bindings[arg_key] = param_name
                            if not any(p["name"] == param_name for p in parameters):
                                parameters.append({
                                    "name": param_name,
                                    "type": "string",
                                    "default": str(arg_val),
                                    "description": f"Target {arg_key} parameter",
                                })

                    # Determine risk
                    requires_conf = "terminate" in cap_id or "delete" in cap_id
                    risk_level = "HIGH" if requires_conf else "LOW"

                    skill_steps.append(
                        SkillStep(
                            step_index=idx + 1,
                            capability_id=cap_id,
                            arguments=raw_args,
                            parameter_bindings=bindings,
                            requires_confirmation=requires_conf,
                            risk_level=risk_level,
                        )
                    )

                # Confidence calculation based on support
                confidence = min(0.95, round(0.50 + (0.10 * (support - self.min_support)), 2))

                candidate = SkillCandidate(
                    id=str(uuid.uuid4()),
                    name=name,
                    description=desc,
                    trigger_phrases=[f"run {name}", f"execute {name}"],
                    parameters=parameters,
                    steps=skill_steps,
                    status=SkillStatus.CANDIDATE,
                    support_count=support,
                    confidence=confidence,
                    version=1,
                    created_at=now,
                    updated_at=now,
                    evidence_task_ids=unique_task_ids,
                    author="pattern_miner",
                    review_notes=f"Discovered across {support} tasks with support count >= {self.min_support}.",
                )
                candidates.append(candidate)

        logger.info("PatternMiner discovered %d skill candidates", len(candidates))
        return candidates
