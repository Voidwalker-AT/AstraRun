"""Evidence extraction engine for AstraRun Learning Foundation.

Inspects TaskLedger tasks and runtime events to extract structured evidence references,
explicit teaching patterns, user corrections, and confirmation outcomes.
Enforces strict non-learnable security policies.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

from astrarun.core.logging import get_logger
from astrarun.learning.models import (
    Correction,
    EvidenceReference,
    EvidenceType,
    MemoryNamespace,
    MemoryStatus,
    SemanticMemory,
)
from astrarun.routing.entity_resolver import BLOCKED_PATTERNS, PROTECTED_PROCESSES
from astrarun.tasks.models import Task, TaskEvent, TaskEventType, TaskStatus

logger = get_logger("astrarun.learning.evidence")

# Regex patterns for explicit user teaching statements
TEACHING_PATTERNS = [
    # "alias calc to calculator", "alias myproject to C:\Projects\MyProject"
    re.compile(r"^(?:please\s+)?alias\s+([a-zA-Z0-9_\-\.]+)\s+(?:to|=|is)\s+([^\s]+)", re.IGNORECASE),
    # "my editor is vscode", "my default browser is vivaldi"
    re.compile(r"^(?:my\s+)?(?:default\s+)?(editor|browser|terminal|shell)\s+is\s+([^\s]+)", re.IGNORECASE),
    # "always use code for editing", "always use chrome for web"
    re.compile(r"^always\s+use\s+([^\s]+)\s+for\s+([^\s]+)", re.IGNORECASE),
    # "set alias foo = bar"
    re.compile(r"^set\s+alias\s+([a-zA-Z0-9_\-\.]+)\s*=\s*([^\s]+)", re.IGNORECASE),
    # "when I say foo run bar"
    re.compile(r"^when\s+I\s+say\s+([a-zA-Z0-9_\-\.\s]+?)\s*,\s*(?:run|launch|open)\s+([^\s]+)", re.IGNORECASE),
]

# Correction indicator phrases
CORRECTION_PATTERNS = [
    re.compile(r"^(?:no\s*,\s*)?(?:i\s+meant|actually|instead|rather)\s+([^\s]+)", re.IGNORECASE),
    re.compile(r"^not\s+([^\s]+)\s*,\s*([^\s]+)", re.IGNORECASE),
    re.compile(r"^no\s+([^\s]+)", re.IGNORECASE),
]


class EvidenceExtractor:
    """
    Extracts empirical evidence, explicit teaching, and user corrections from tasks.
    """

    def is_security_safe(self, text: str, target: Optional[str] = None) -> bool:
        """
        Verify that evidence does not reference protected system processes,
        destructive shell commands, or hard-blocked patterns.
        """
        clean_text = text.strip() if text else ""
        for pat in BLOCKED_PATTERNS:
            if pat.search(clean_text):
                logger.warning("Security filter rejected evidence matching blocked pattern: %s", pat.pattern)
                return False

        if target:
            target_clean = target.lower().strip()
            if target_clean in PROTECTED_PROCESSES:
                logger.warning("Security filter rejected evidence referencing protected process: %s", target)
                return False

        return True

    def extract_teaching(self, task: Task) -> Optional[SemanticMemory]:
        """
        Check if a task's request text contains an explicit teaching statement.
        """
        if not task.request_text:
            return None

        clean_text = task.request_text.strip()
        if not self.is_security_safe(clean_text):
            return None

        for pat in TEACHING_PATTERNS:
            match = pat.search(clean_text)
            if match:
                groups = match.groups()
                if len(groups) >= 2:
                    if clean_text.lower().startswith("always use"):
                        target = groups[0].strip()
                        key = groups[1].strip().lower()
                    else:
                        key = groups[0].strip().lower()
                        target = groups[1].strip()

                    # Check security on the target
                    if not self.is_security_safe(clean_text, target):
                        return None

                    # Determine namespace
                    namespace = MemoryNamespace.ALIAS
                    target_type = "application"
                    if not clean_text.lower().startswith(("alias ", "set alias ", "always use ")) and key in {"editor", "browser", "terminal", "shell"}:
                        namespace = MemoryNamespace.PREFERENCE
                        target_type = "preference"

                    ref = EvidenceReference(
                        task_id=task.id,
                        conversation_id=task.conversation_id,
                        evidence_type=EvidenceType.EXPLICIT_TEACHING,
                        timestamp=task.created_at,
                        weight=3.0,
                        details={"raw_query": clean_text},
                    )

                    import uuid
                    return SemanticMemory(
                        id=str(uuid.uuid4()),
                        namespace=namespace,
                        key=key,
                        value=target,
                        target_type=target_type,
                        status=MemoryStatus.ACTIVE,
                        confidence=1.0,
                        support_count=1,
                        contradiction_count=0,
                        evidence_refs=[ref],
                        created_at=task.created_at,
                        updated_at=task.created_at,
                        last_used_at=task.created_at,
                        user_confirmed=True,
                        pinned=True,
                        metadata={"teaching_query": clean_text},
                    )

        return None

    def extract_task_evidence(self, task: Task) -> list[tuple[str, str, EvidenceReference]]:
        """
        Extract candidate evidence tuples: (key, target, EvidenceReference) from a single task.
        """
        results: list[tuple[str, str, EvidenceReference]] = []
        if not task.events:
            return results

        # Scan events
        for event in task.events:
            if event.type == TaskEventType.CONFIRMATION_ACCEPTED:
                cap_id = event.capability_id or event.data.get("capability")
                target = event.data.get("target") or event.data.get("entity") or cap_id
                if target and self.is_security_safe(str(target), str(target)):
                    ref = EvidenceReference(
                        task_id=task.id,
                        conversation_id=task.conversation_id,
                        event_id=event.id,
                        evidence_type=EvidenceType.CONFIRMATION_ACCEPTED,
                        timestamp=event.timestamp,
                        weight=2.0,
                        details={"capability": cap_id, "data": event.data},
                    )
                    results.append((task.request_text or "", str(target), ref))

            elif event.type == TaskEventType.CONFIRMATION_REJECTED:
                cap_id = event.capability_id or event.data.get("capability")
                target = event.data.get("target") or event.data.get("entity") or cap_id
                if target and self.is_security_safe(str(target), str(target)):
                    ref = EvidenceReference(
                        task_id=task.id,
                        conversation_id=task.conversation_id,
                        event_id=event.id,
                        evidence_type=EvidenceType.CONFIRMATION_REJECTED,
                        timestamp=event.timestamp,
                        weight=2.5,
                        details={"capability": cap_id, "data": event.data},
                    )
                    results.append((task.request_text or "", str(target), ref))

            elif event.type == TaskEventType.CLARIFICATION_RESOLVED:
                chosen = event.data.get("chosen_candidate")
                rejected = event.data.get("rejected_candidates", [])
                query_text = task.request_text or ""
                if chosen and self.is_security_safe(query_text, str(chosen)):
                    ref_pos = EvidenceReference(
                        task_id=task.id,
                        conversation_id=task.conversation_id,
                        event_id=event.id,
                        evidence_type=EvidenceType.USER_QUERY_SELECTION,
                        timestamp=event.timestamp,
                        weight=1.5,
                        details={"chosen": chosen},
                    )
                    results.append((query_text, str(chosen), ref_pos))

                for rej in rejected:
                    if rej and self.is_security_safe(query_text, str(rej)):
                        ref_neg = EvidenceReference(
                            task_id=task.id,
                            conversation_id=task.conversation_id,
                            event_id=event.id,
                            evidence_type=EvidenceType.CONFIRMATION_REJECTED,
                            timestamp=event.timestamp,
                            weight=2.0,
                            details={"rejected_during_clarify": rej},
                        )
                        results.append((query_text, str(rej), ref_neg))

        # Check for successful completion without issues
        if task.status == TaskStatus.COMPLETED and task.final_result and task.final_result.success:
            req = task.request_text or ""
            caps = task.final_result.capabilities_used
            if req and caps and self.is_security_safe(req):
                ref_success = EvidenceReference(
                    task_id=task.id,
                    conversation_id=task.conversation_id,
                    evidence_type=EvidenceType.SUCCESSFUL_EXECUTION,
                    timestamp=task.completed_at or time.time(),
                    weight=1.0,
                    details={"capabilities": caps},
                )
                results.append((req, caps[0], ref_success))

        return results

    def detect_correction(self, prior_task: Task, current_task: Task) -> Optional[Correction]:
        """
        Detect if current_task represents an immediate user correction of prior_task.
        Criteria:
        - Same conversation_id
        - Time difference <= 120 seconds
        - Prior task was cancelled, rejected, or completed recently
        - Current task query matches correction pattern or clearly adjusts target
        """
        if prior_task.conversation_id != current_task.conversation_id:
            return None

        t_diff = (current_task.created_at - (prior_task.completed_at or prior_task.created_at))
        if t_diff < 0 or t_diff > 120.0:
            return None

        curr_query = current_task.request_text.strip() if current_task.request_text else ""
        if not curr_query or not self.is_security_safe(curr_query):
            return None

        for pat in CORRECTION_PATTERNS:
            match = pat.search(curr_query)
            if match:
                corrected_target = match.group(1).strip()
                if not self.is_security_safe(curr_query, corrected_target):
                    return None

                prior_target = None
                if prior_task.final_result and prior_task.final_result.capabilities_used:
                    prior_target = prior_task.final_result.capabilities_used[0]
                elif prior_task.events:
                    for ev in prior_task.events:
                        if ev.data.get("target"):
                            prior_target = str(ev.data["target"])
                            break

                import uuid
                return Correction(
                    id=str(uuid.uuid4()),
                    task_id=current_task.id,
                    conversation_id=current_task.conversation_id,
                    incorrect_mapping={"query": prior_task.request_text, "target": prior_target},
                    corrected_mapping={"query": curr_query, "target": corrected_target},
                    timestamp=current_task.created_at,
                    applied=False,
                )

        return None
