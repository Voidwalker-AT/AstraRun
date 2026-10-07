"""SQLite persistence layer for AstraRun Learning Foundation.

Manages data/astra_learning.db with strict schema versioning, WAL mode,
atomic transactions, corruption recovery, and complete audit logging.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from astrarun.core.logging import get_logger
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

logger = get_logger("astrarun.learning.persistence")

CURRENT_SCHEMA_VERSION = 1

DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at REAL NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS semantic_memories (
        id TEXT PRIMARY KEY,
        namespace TEXT NOT NULL,
        key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        target_type TEXT NOT NULL,
        status TEXT NOT NULL,
        confidence REAL NOT NULL,
        support_count INTEGER NOT NULL,
        contradiction_count INTEGER NOT NULL,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        last_used_at REAL NOT NULL,
        user_confirmed INTEGER NOT NULL DEFAULT 0,
        pinned INTEGER NOT NULL DEFAULT 0,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_memories_ns_key ON semantic_memories(namespace, key);",
    "CREATE INDEX IF NOT EXISTS idx_memories_status ON semantic_memories(status);",
    """
    CREATE TABLE IF NOT EXISTS evidence_records (
        id TEXT PRIMARY KEY,
        memory_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        event_id TEXT,
        evidence_type TEXT NOT NULL,
        timestamp REAL NOT NULL,
        weight REAL NOT NULL,
        details_json TEXT NOT NULL DEFAULT '{}',
        FOREIGN KEY (memory_id) REFERENCES semantic_memories(id) ON DELETE CASCADE
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_evidence_mem_id ON evidence_records(memory_id);",
    "CREATE INDEX IF NOT EXISTS idx_evidence_task_id ON evidence_records(task_id);",
    """
    CREATE TABLE IF NOT EXISTS corrections (
        id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        conversation_id TEXT NOT NULL,
        incorrect_json TEXT NOT NULL,
        corrected_json TEXT NOT NULL,
        timestamp REAL NOT NULL,
        applied INTEGER NOT NULL DEFAULT 0
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS skill_candidates (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        trigger_phrases_json TEXT NOT NULL,
        parameters_json TEXT NOT NULL,
        steps_json TEXT NOT NULL,
        status TEXT NOT NULL,
        support_count INTEGER NOT NULL,
        confidence REAL NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        author TEXT NOT NULL,
        review_notes TEXT
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_skills_status ON skill_candidates(status);",
    "CREATE INDEX IF NOT EXISTS idx_skills_name ON skill_candidates(name);",
    """
    CREATE TABLE IF NOT EXISTS audit_events (
        id TEXT PRIMARY KEY,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT NOT NULL,
        timestamp REAL NOT NULL,
        details_json TEXT NOT NULL DEFAULT '{}'
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_events(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_id);",
]


class LearningPersistence:
    """
    Thread-safe SQLite storage for learned workstation memory, skills, and audits.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            from astrarun.core.paths import AstraPaths
            self.db_path = AstraPaths.data_dir() / "astra_learning.db"
        else:
            self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and configure a SQLite connection."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _initialize_database(self) -> None:
        """Initialize schema and check database integrity."""
        try:
            with self._get_connection() as conn:
                for stmt in DDL_STATEMENTS:
                    conn.execute(stmt)

                # Check version
                cur = conn.execute("PRAGMA user_version;")
                row = cur.fetchone()
                version = row[0] if row else 0

                if version == 0:
                    conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")
                    conn.execute(
                        "INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, ?);",
                        (CURRENT_SCHEMA_VERSION, time.time())
                    )
                conn.commit()
        except sqlite3.DatabaseError as err:
            logger.error("Corrupted learning database encountered at %s: %s. Backing up and recreating.", self.db_path, err)
            self._handle_corruption()

    def _handle_corruption(self) -> None:
        """Safely backup corrupt database and recreate blank file."""
        if self.db_path.exists():
            backup_path = self.db_path.with_suffix(f".corrupt.{int(time.time())}")
            try:
                shutil.move(str(self.db_path), str(backup_path))
                logger.warning("Corrupt database moved to %s", backup_path)
            except Exception as e:
                logger.error("Failed to move corrupt database: %s", e)
        self._initialize_database()

    def check_integrity(self) -> bool:
        """Run quick_check on database."""
        try:
            with self._get_connection() as conn:
                cur = conn.execute("PRAGMA quick_check;")
                res = cur.fetchone()
                return bool(res and res[0] == "ok")
        except Exception:
            return False

    # --- Memory Operations ---

    def save_memory(self, memory: SemanticMemory) -> None:
        """Insert or update a semantic memory along with evidence records."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO semantic_memories (
                    id, namespace, key, value_json, target_type, status, confidence,
                    support_count, contradiction_count, created_at, updated_at,
                    last_used_at, user_confirmed, pinned, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    namespace=excluded.namespace,
                    key=excluded.key,
                    value_json=excluded.value_json,
                    target_type=excluded.target_type,
                    status=excluded.status,
                    confidence=excluded.confidence,
                    support_count=excluded.support_count,
                    contradiction_count=excluded.contradiction_count,
                    updated_at=excluded.updated_at,
                    last_used_at=excluded.last_used_at,
                    user_confirmed=excluded.user_confirmed,
                    pinned=excluded.pinned,
                    metadata_json=excluded.metadata_json;
                """,
                (
                    memory.id,
                    memory.namespace.value,
                    memory.key,
                    json.dumps(memory.value),
                    memory.target_type,
                    memory.status.value,
                    memory.confidence,
                    memory.support_count,
                    memory.contradiction_count,
                    memory.created_at,
                    memory.updated_at,
                    memory.last_used_at,
                    1 if memory.user_confirmed else 0,
                    1 if memory.pinned else 0,
                    json.dumps(memory.metadata),
                ),
            )

            # Insert new evidence records
            for ref in memory.evidence_refs:
                ref_id = f"{memory.id}_{ref.task_id}_{ref.event_id or ''}_{ref.timestamp}"
                conn.execute(
                    """
                    INSERT OR IGNORE INTO evidence_records (
                        id, memory_id, task_id, conversation_id, event_id,
                        evidence_type, timestamp, weight, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        ref_id,
                        memory.id,
                        ref.task_id,
                        ref.conversation_id,
                        ref.event_id,
                        ref.evidence_type.value,
                        ref.timestamp,
                        ref.weight,
                        json.dumps(ref.details),
                    ),
                )
            conn.commit()

    def get_memory(self, memory_id: str) -> Optional[SemanticMemory]:
        """Retrieve a specific memory by its unique ID."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM semantic_memories WHERE id = ?;", (memory_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_memory(conn, row)

    def find_memories(
        self,
        namespace: Optional[MemoryNamespace] = None,
        key: Optional[str] = None,
        status: Optional[MemoryStatus] = None,
    ) -> list[SemanticMemory]:
        """Query memories matching filter criteria."""
        query = "SELECT * FROM semantic_memories WHERE 1=1"
        params: list[Any] = []

        if namespace:
            query += " AND namespace = ?"
            params.append(namespace.value)
        if key:
            query += " AND key = ?"
            params.append(key)
        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY confidence DESC, updated_at DESC;"

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            rows = cur.fetchall()
            return [self._row_to_memory(conn, r) for r in rows]

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a memory and cascade delete its evidence records."""
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM semantic_memories WHERE id = ?;", (memory_id,))
            conn.commit()
            return cur.rowcount > 0

    def _row_to_memory(self, conn: sqlite3.Connection, row: sqlite3.Row) -> SemanticMemory:
        """Construct SemanticMemory instance from a database row."""
        mem_id = row["id"]
        # Fetch evidence references
        cur = conn.execute(
            "SELECT * FROM evidence_records WHERE memory_id = ? ORDER BY timestamp DESC;",
            (mem_id,),
        )
        evidence_rows = cur.fetchall()
        refs: list[EvidenceReference] = []
        for er in evidence_rows:
            refs.append(
                EvidenceReference(
                    task_id=er["task_id"],
                    conversation_id=er["conversation_id"],
                    event_id=er["event_id"],
                    evidence_type=EvidenceType(er["evidence_type"]),
                    timestamp=float(er["timestamp"]),
                    weight=float(er["weight"]),
                    details=json.loads(er["details_json"]),
                )
            )

        return SemanticMemory(
            id=mem_id,
            namespace=MemoryNamespace(row["namespace"]),
            key=row["key"],
            value=json.loads(row["value_json"]),
            target_type=row["target_type"],
            status=MemoryStatus(row["status"]),
            confidence=float(row["confidence"]),
            support_count=int(row["support_count"]),
            contradiction_count=int(row["contradiction_count"]),
            evidence_refs=refs,
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            last_used_at=float(row["last_used_at"]),
            user_confirmed=bool(row["user_confirmed"]),
            pinned=bool(row["pinned"]),
            metadata=json.loads(row["metadata_json"]),
        )

    # --- Correction Operations ---

    def save_correction(self, correction: Correction) -> None:
        """Persist a user correction record."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO corrections (
                    id, task_id, conversation_id, incorrect_json, corrected_json, timestamp, applied
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    correction.id,
                    correction.task_id,
                    correction.conversation_id,
                    json.dumps(correction.incorrect_mapping),
                    json.dumps(correction.corrected_mapping),
                    correction.timestamp,
                    1 if correction.applied else 0,
                ),
            )
            conn.commit()

    def list_corrections(self, limit: int = 50) -> list[Correction]:
        """Fetch recent user correction records."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM corrections ORDER BY timestamp DESC LIMIT ?;",
                (limit,),
            )
            rows = cur.fetchall()
            return [
                Correction(
                    id=r["id"],
                    task_id=r["task_id"],
                    conversation_id=r["conversation_id"],
                    incorrect_mapping=json.loads(r["incorrect_json"]),
                    corrected_mapping=json.loads(r["corrected_json"]),
                    timestamp=float(r["timestamp"]),
                    applied=bool(r["applied"]),
                )
                for r in rows
            ]

    # --- Skill Operations ---

    def save_skill(self, skill: SkillCandidate) -> None:
        """Insert or update a skill candidate."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO skill_candidates (
                    id, name, description, trigger_phrases_json, parameters_json,
                    steps_json, status, support_count, confidence, version,
                    created_at, updated_at, author, review_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    description=excluded.description,
                    trigger_phrases_json=excluded.trigger_phrases_json,
                    parameters_json=excluded.parameters_json,
                    steps_json=excluded.steps_json,
                    status=excluded.status,
                    support_count=excluded.support_count,
                    confidence=excluded.confidence,
                    version=excluded.version,
                    updated_at=excluded.updated_at,
                    author=excluded.author,
                    review_notes=excluded.review_notes;
                """,
                (
                    skill.id,
                    skill.name,
                    skill.description,
                    json.dumps(skill.trigger_phrases),
                    json.dumps(skill.parameters),
                    json.dumps([s.to_dict() for s in skill.steps]),
                    skill.status.value,
                    skill.support_count,
                    skill.confidence,
                    skill.version,
                    skill.created_at,
                    skill.updated_at,
                    skill.author,
                    skill.review_notes,
                ),
            )
            conn.commit()

    def get_skill(self, skill_id: str) -> Optional[SkillCandidate]:
        """Retrieve a specific skill by its ID."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM skill_candidates WHERE id = ?;", (skill_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_skill(row)

    def list_skills(self, status: Optional[SkillStatus] = None) -> list[SkillCandidate]:
        """List skills, optionally filtered by status."""
        query = "SELECT * FROM skill_candidates"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status.value)
        query += " ORDER BY confidence DESC, updated_at DESC;"

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            rows = cur.fetchall()
            return [self._row_to_skill(r) for r in rows]

    def delete_skill(self, skill_id: str) -> bool:
        """Delete a skill candidate."""
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM skill_candidates WHERE id = ?;", (skill_id,))
            conn.commit()
            return cur.rowcount > 0

    def _row_to_skill(self, row: sqlite3.Row) -> SkillCandidate:
        """Construct SkillCandidate instance from database row."""
        steps_raw = json.loads(row["steps_json"])
        steps = [SkillStep.from_dict(s) for s in steps_raw]
        return SkillCandidate(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            trigger_phrases=json.loads(row["trigger_phrases_json"]),
            parameters=json.loads(row["parameters_json"]),
            steps=steps,
            status=SkillStatus(row["status"]),
            support_count=int(row["support_count"]),
            confidence=float(row["confidence"]),
            version=int(row["version"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            author=row["author"],
            review_notes=row["review_notes"],
        )

    # --- Audit Trail Operations ---

    def record_audit(self, audit: AuditEvent) -> None:
        """Append an audit record to the persistent log."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO audit_events (
                    id, action, entity_type, entity_id, timestamp, details_json
                ) VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    audit.id,
                    audit.action.value,
                    audit.entity_type,
                    audit.entity_id,
                    audit.timestamp,
                    json.dumps(audit.details),
                ),
            )
            conn.commit()

    def list_audit_events(self, limit: int = 100) -> list[AuditEvent]:
        """Fetch recent audit events."""
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM audit_events ORDER BY timestamp DESC LIMIT ?;",
                (limit,),
            )
            rows = cur.fetchall()
            return [
                AuditEvent(
                    id=r["id"],
                    action=AuditAction(r["action"]),
                    entity_type=r["entity_type"],
                    entity_id=r["entity_id"],
                    timestamp=float(r["timestamp"]),
                    details=json.loads(r["details_json"]),
                )
                for r in rows
            ]

    # --- Pruning & Maintenance ---

    def clear_all_learning(self) -> None:
        """Wipe all learned memories, skills, and corrections while recording audit log."""
        import uuid
        audit = AuditEvent(
            id=str(uuid.uuid4()),
            action=AuditAction.DATA_CLEARED,
            entity_type="system",
            entity_id="all",
            timestamp=time.time(),
            details={"reason": "User requested learning database wipe"},
        )
        with self._get_connection() as conn:
            conn.execute("DELETE FROM evidence_records;")
            conn.execute("DELETE FROM semantic_memories;")
            conn.execute("DELETE FROM corrections;")
            conn.execute("DELETE FROM skill_candidates;")
            conn.commit()
        self.record_audit(audit)

    def prune_deprecated(self, older_than_days: int = 60) -> int:
        """Remove deprecated or rejected memories not used in over N days."""
        cutoff = time.time() - (older_than_days * 86400.0)
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                DELETE FROM semantic_memories
                WHERE status IN ('DEPRECATED', 'REJECTED')
                  AND pinned = 0
                  AND user_confirmed = 0
                  AND last_used_at < ?;
                """,
                (cutoff,),
            )
            deleted = cur.rowcount
            conn.commit()
            return deleted
