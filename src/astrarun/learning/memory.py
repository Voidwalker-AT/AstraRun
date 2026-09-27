"""Semantic Memory Store for AstraRun Learning Foundation.

Provides high-level CRUD, evidence accumulation, confidence recalculation,
conflict detection, and human confirmation workflows.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional

from astrarun.core.logging import get_logger
from astrarun.learning.confidence import (
    DEFAULT_CONFLICT_MARGIN,
    ConfidenceCalculator,
)
from astrarun.learning.models import (
    AuditAction,
    AuditEvent,
    Correction,
    EvidenceReference,
    EvidenceType,
    MemoryNamespace,
    MemoryStatus,
    SemanticMemory,
)
from astrarun.learning.persistence import LearningPersistence

logger = get_logger("astrarun.learning.memory")


class MemoryStore:
    """
    Manages semantic memories, evidence updates, conflict states, and audits.
    """

    def __init__(
        self,
        persistence: Optional[LearningPersistence] = None,
        calculator: Optional[ConfidenceCalculator] = None,
    ) -> None:
        self.persistence = persistence or LearningPersistence()
        self.calculator = calculator or ConfidenceCalculator()

    def add_or_update_memory(
        self,
        namespace: MemoryNamespace,
        key: str,
        value: str,
        target_type: str,
        evidence_ref: Optional[EvidenceReference] = None,
        pinned: bool = False,
        user_confirmed: bool = False,
        metadata: Optional[dict] = None,
    ) -> SemanticMemory:
        """
        Record a new observation or update an existing memory matching (namespace, key, value).
        """
        clean_key = key.strip().lower()
        clean_val = value.strip() if isinstance(value, str) else value

        # Search existing memories for exact match
        existing = self.persistence.find_memories(namespace=namespace, key=clean_key)
        target_mem: Optional[SemanticMemory] = None
        for m in existing:
            if m.value == clean_val:
                target_mem = m
                break

        now = time.time()
        if target_mem:
            # Update existing memory
            if evidence_ref:
                target_mem.evidence_refs.append(evidence_ref)
            target_mem.last_used_at = now
            target_mem.updated_at = now
            if pinned:
                target_mem.pinned = True
            if user_confirmed:
                target_mem.user_confirmed = True

            conf, sup, cont = self.calculator.calculate_confidence(
                evidence_refs=target_mem.evidence_refs,
                last_used_at=target_mem.last_used_at,
                pinned=target_mem.pinned,
                user_confirmed=target_mem.user_confirmed,
                current_time=now,
            )
            target_mem.confidence = conf
            target_mem.support_count = sup
            target_mem.contradiction_count = cont
            target_mem.status = self.calculator.evaluate_status(target_mem, current_time=now)
            self.persistence.save_memory(target_mem)

            self.persistence.record_audit(
                AuditEvent(
                    id=str(uuid.uuid4()),
                    action=AuditAction.MEMORY_UPDATED,
                    entity_type="memory",
                    entity_id=target_mem.id,
                    timestamp=now,
                    details={"key": clean_key, "confidence": conf, "status": target_mem.status.value},
                )
            )
            mem_to_return = target_mem
        else:
            # Create new memory
            refs = [evidence_ref] if evidence_ref else []
            new_id = str(uuid.uuid4())
            new_mem = SemanticMemory(
                id=new_id,
                namespace=namespace,
                key=clean_key,
                value=clean_val,
                target_type=target_type,
                status=MemoryStatus.CANDIDATE,
                confidence=0.0,
                support_count=1 if evidence_ref else 0,
                contradiction_count=0,
                evidence_refs=refs,
                created_at=now,
                updated_at=now,
                last_used_at=now,
                user_confirmed=user_confirmed,
                pinned=pinned,
                metadata=metadata or {},
            )
            conf, sup, cont = self.calculator.calculate_confidence(
                evidence_refs=refs,
                last_used_at=now,
                pinned=pinned,
                user_confirmed=user_confirmed,
                current_time=now,
            )
            if (user_confirmed or pinned) and cont == 0:
                conf = max(0.95, conf)
            new_mem.confidence = conf
            new_mem.support_count = sup
            new_mem.contradiction_count = cont
            new_mem.status = self.calculator.evaluate_status(new_mem, current_time=now)
            self.persistence.save_memory(new_mem)

            self.persistence.record_audit(
                AuditEvent(
                    id=str(uuid.uuid4()),
                    action=AuditAction.MEMORY_CREATED,
                    entity_type="memory",
                    entity_id=new_id,
                    timestamp=now,
                    details={"key": clean_key, "value": clean_val, "status": new_mem.status.value},
                )
            )
            mem_to_return = new_mem

        # Check for conflicts among memories sharing the same (namespace, key)
        all_for_key = self.persistence.find_memories(namespace=namespace, key=clean_key)
        if len(all_for_key) > 1:
            conflicted = self.calculator.detect_conflicts(all_for_key)
            for cm in conflicted:
                if cm.status == MemoryStatus.CONFLICTED:
                    self.persistence.save_memory(cm)
                    self.persistence.record_audit(
                        AuditEvent(
                            id=str(uuid.uuid4()),
                            action=AuditAction.CONFLICT_DETECTED,
                            entity_type="memory",
                            entity_id=cm.id,
                            timestamp=now,
                            details={"key": clean_key, "conflicting_value": cm.value},
                        )
                    )

        return mem_to_return

    def record_evidence(self, memory_id: str, evidence_ref: EvidenceReference) -> Optional[SemanticMemory]:
        """Add an evidence reference to an existing memory and re-evaluate status."""
        mem = self.persistence.get_memory(memory_id)
        if not mem:
            return None

        now = time.time()
        mem.evidence_refs.append(evidence_ref)
        mem.last_used_at = now
        mem.updated_at = now

        conf, sup, cont = self.calculator.calculate_confidence(
            evidence_refs=mem.evidence_refs,
            last_used_at=mem.last_used_at,
            pinned=mem.pinned,
            user_confirmed=mem.user_confirmed,
            current_time=now,
        )
        mem.confidence = conf
        mem.support_count = sup
        mem.contradiction_count = cont
        old_status = mem.status
        new_status = self.calculator.evaluate_status(mem, current_time=now)
        mem.status = new_status

        self.persistence.save_memory(mem)

        if old_status != new_status and new_status == MemoryStatus.ACTIVE:
            self.persistence.record_audit(
                AuditEvent(
                    id=str(uuid.uuid4()),
                    action=AuditAction.MEMORY_PROMOTED,
                    entity_type="memory",
                    entity_id=mem.id,
                    timestamp=now,
                    details={"old_status": old_status.value, "new_status": new_status.value},
                )
            )

        return mem

    def get_memory(self, memory_id: str) -> Optional[SemanticMemory]:
        """Fetch memory by ID."""
        return self.persistence.get_memory(memory_id)

    def find_memory(self, namespace: MemoryNamespace, key: str) -> Optional[SemanticMemory]:
        """
        Find the most authoritative active or high-confidence memory for a key.
        Returns None if no active memory or if status is CONFLICTED or REJECTED.
        """
        clean_key = key.strip().lower()
        candidates = self.persistence.find_memories(namespace=namespace, key=clean_key)
        if not candidates:
            return None

        # If any is CONFLICTED, do not return a single authoritative answer
        if any(c.status == MemoryStatus.CONFLICTED for c in candidates):
            logger.debug("Memory lookup for '%s' returned CONFLICTED", clean_key)
            return None

        # Filter active memories
        active = [c for c in candidates if c.status == MemoryStatus.ACTIVE]
        if active:
            # Sort by user_confirmed, then confidence
            active.sort(key=lambda m: (m.user_confirmed, m.confidence), reverse=True)
            return active[0]

        return None

    def list_memories(
        self,
        namespace: Optional[MemoryNamespace] = None,
        status: Optional[MemoryStatus] = None,
    ) -> list[SemanticMemory]:
        """List memories with optional filters."""
        return self.persistence.find_memories(namespace=namespace, status=status)

    def confirm_memory(self, memory_id: str) -> Optional[SemanticMemory]:
        """User explicitly confirms a candidate memory, promoting it to ACTIVE."""
        mem = self.persistence.get_memory(memory_id)
        if not mem:
            return None

        now = time.time()
        mem.user_confirmed = True
        mem.status = MemoryStatus.ACTIVE
        mem.confidence = max(0.95, mem.confidence)
        mem.updated_at = now
        self.persistence.save_memory(mem)

        self.persistence.record_audit(
            AuditEvent(
                id=str(uuid.uuid4()),
                action=AuditAction.MEMORY_PROMOTED,
                entity_type="memory",
                entity_id=mem.id,
                timestamp=now,
                details={"reason": "User confirmed candidate memory"},
            )
        )
        return mem

    def reject_memory(self, memory_id: str) -> Optional[SemanticMemory]:
        """User explicitly rejects a memory, marking it REJECTED."""
        mem = self.persistence.get_memory(memory_id)
        if not mem:
            return None

        now = time.time()
        mem.status = MemoryStatus.REJECTED
        mem.user_confirmed = False
        mem.confidence = 0.0
        mem.updated_at = now
        self.persistence.save_memory(mem)

        self.persistence.record_audit(
            AuditEvent(
                id=str(uuid.uuid4()),
                action=AuditAction.MEMORY_DEPRECATED,
                entity_type="memory",
                entity_id=mem.id,
                timestamp=now,
                details={"reason": "User rejected memory"},
            )
        )
        return mem

    def delete_memory(self, memory_id: str) -> bool:
        """Permanently delete a memory record."""
        mem = self.persistence.get_memory(memory_id)
        if not mem:
            return False

        now = time.time()
        deleted = self.persistence.delete_memory(memory_id)
        if deleted:
            self.persistence.record_audit(
                AuditEvent(
                    id=str(uuid.uuid4()),
                    action=AuditAction.MEMORY_DELETED,
                    entity_type="memory",
                    entity_id=memory_id,
                    timestamp=now,
                    details={"key": mem.key, "value": mem.value},
                )
            )
        return deleted

    def apply_correction(self, correction: Correction) -> None:
        """
        Process a user correction: penalizes incorrect mapping, rewards corrected mapping.
        """
        now = time.time()
        inc_target = str(correction.incorrect_mapping.get("target") or "")
        corr_target = str(correction.corrected_mapping.get("target") or "")
        key = str(correction.incorrect_mapping.get("key") or correction.incorrect_mapping.get("query") or "").strip().lower()

        if inc_target and key:
            # Find and penalize incorrect target
            memories = self.persistence.find_memories(key=key)
            for m in memories:
                if str(m.value).lower() == inc_target.lower():
                    ref_neg = EvidenceReference(
                        task_id=correction.task_id,
                        conversation_id=correction.conversation_id,
                        evidence_type=EvidenceType.USER_CORRECTION,
                        timestamp=now,
                        weight=3.0,
                        details={"correction_id": correction.id},
                    )
                    self.record_evidence(m.id, ref_neg)

        if corr_target and key:
            # Find or create corrected target
            ref_pos = EvidenceReference(
                task_id=correction.task_id,
                conversation_id=correction.conversation_id,
                evidence_type=EvidenceType.EXPLICIT_TEACHING,
                timestamp=now,
                weight=3.0,
                details={"correction_id": correction.id},
            )
            self.add_or_update_memory(
                namespace=MemoryNamespace.ALIAS,
                key=key,
                value=corr_target,
                target_type="application",
                evidence_ref=ref_pos,
                user_confirmed=True,
            )

        correction.applied = True
        self.persistence.save_correction(correction)

    def resolve_conflicts(
        self,
        namespace: MemoryNamespace,
        key: str,
        chosen_memory_id: str,
    ) -> list[SemanticMemory]:
        """
        Resolve a CONFLICTED key by accepting chosen_memory_id and rejecting or deprecating others.
        """
        now = time.time()
        memories = self.persistence.find_memories(namespace=namespace, key=key.strip().lower())
        updated: list[SemanticMemory] = []

        for m in memories:
            if m.id == chosen_memory_id:
                m.status = MemoryStatus.ACTIVE
                m.user_confirmed = True
                m.confidence = max(0.95, m.confidence)
                m.updated_at = now
                self.persistence.save_memory(m)
                updated.append(m)
            else:
                m.status = MemoryStatus.DEPRECATED
                m.updated_at = now
                self.persistence.save_memory(m)
                updated.append(m)

        self.persistence.record_audit(
            AuditEvent(
                id=str(uuid.uuid4()),
                action=AuditAction.CONFLICT_RESOLVED,
                entity_type="memory",
                entity_id=chosen_memory_id,
                timestamp=now,
                details={"key": key, "chosen_id": chosen_memory_id},
            )
        )
        return updated

    def decay_all(self, current_time: Optional[float] = None) -> list[SemanticMemory]:
        """
        Run recency decay across all active and candidate memories.
        """
        now = current_time if current_time is not None else time.time()
        all_memories = self.persistence.find_memories()
        modified: list[SemanticMemory] = []

        for mem in all_memories:
            if mem.status in {MemoryStatus.ACTIVE, MemoryStatus.CANDIDATE}:
                conf, sup, cont = self.calculator.calculate_confidence(
                    evidence_refs=mem.evidence_refs,
                    last_used_at=mem.last_used_at,
                    pinned=mem.pinned,
                    user_confirmed=mem.user_confirmed,
                    current_time=now,
                )
                if abs(conf - mem.confidence) > 0.001:
                    mem.confidence = conf
                    mem.support_count = sup
                    mem.contradiction_count = cont
                    mem.status = self.calculator.evaluate_status(mem, current_time=now)
                    mem.updated_at = now
                    self.persistence.save_memory(mem)
                    modified.append(mem)

        return modified
