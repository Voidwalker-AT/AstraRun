"""Authoritative SQLite-backed Knowledge Graph Store for Hermes Experiential Memory.

Maintains relational graph of discovered Windows entities, action affordances,
empirically verified state transitions, and diagnostic experiments with FTS5 search
and Bayesian epistemic confidence updating.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.paths import AstraPaths
from astrarun.hermes.models import (
    AffordanceEdge,
    AffordanceRisk,
    ConfidenceBand,
    EntityNode,
    EntityType,
    EpistemicStatus,
    ExperimentRecord,
    ExperimentStatus,
    StateTransitionRecord,
)
from astrarun.hermes.provenance import HermesProvenance

logger = logging.getLogger("astrarun.hermes.store")

SCHEMA_DDL = [
    """
    CREATE TABLE IF NOT EXISTS hermes_entities (
        entity_id TEXT PRIMARY KEY,
        entity_type TEXT NOT NULL,
        parent_entity_id TEXT REFERENCES hermes_entities(entity_id),
        name TEXT NOT NULL,
        class_name TEXT,
        binary_hash TEXT,
        version TEXT,
        env_hash TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_hermes_entities_type ON hermes_entities(entity_type);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_hermes_entities_parent ON hermes_entities(parent_entity_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_hermes_entities_name ON hermes_entities(name);
    """,
    """
    CREATE TABLE IF NOT EXISTS hermes_affordances (
        affordance_id TEXT PRIMARY KEY,
        entity_id TEXT NOT NULL REFERENCES hermes_entities(entity_id) ON DELETE CASCADE,
        action_name TEXT NOT NULL,
        capability_id TEXT NOT NULL,
        parameter_schema_json TEXT NOT NULL DEFAULT '{}',
        risk_level TEXT NOT NULL DEFAULT 'BENIGN_MUTATION',
        is_reversible INTEGER NOT NULL DEFAULT 1,
        confidence REAL NOT NULL DEFAULT 0.20,
        status TEXT NOT NULL DEFAULT 'HYPOTHESIS',
        verification_count INTEGER NOT NULL DEFAULT 0,
        contradiction_count INTEGER NOT NULL DEFAULT 0,
        last_verified_at REAL,
        created_at REAL NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_hermes_affordances_entity ON hermes_affordances(entity_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_hermes_affordances_action ON hermes_affordances(action_name);
    """,
    """
    CREATE TABLE IF NOT EXISTS hermes_transitions (
        transition_id TEXT PRIMARY KEY,
        affordance_id TEXT NOT NULL REFERENCES hermes_affordances(affordance_id) ON DELETE CASCADE,
        pre_state_hash TEXT NOT NULL,
        action_payload_json TEXT NOT NULL DEFAULT '{}',
        post_state_hash TEXT NOT NULL,
        expected_delta_json TEXT NOT NULL DEFAULT '{}',
        observed_delta_json TEXT NOT NULL DEFAULT '{}',
        transition_verified INTEGER NOT NULL,
        latency_ms REAL NOT NULL DEFAULT 0.0,
        trace_id TEXT NOT NULL,
        pre_frame_id TEXT NOT NULL,
        post_frame_id TEXT NOT NULL,
        timestamp REAL NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_hermes_transitions_affordance ON hermes_transitions(affordance_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS hermes_experiments (
        experiment_id TEXT PRIMARY KEY,
        target_entity_id TEXT NOT NULL REFERENCES hermes_entities(entity_id) ON DELETE CASCADE,
        hypothesis TEXT NOT NULL,
        probe_action_name TEXT NOT NULL,
        probe_payload_json TEXT NOT NULL DEFAULT '{}',
        expected_outcome TEXT NOT NULL,
        actual_outcome TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING',
        task_id TEXT NOT NULL DEFAULT '',
        trace_id TEXT NOT NULL DEFAULT '',
        prompt_hash TEXT NOT NULL DEFAULT '',
        response_hash TEXT NOT NULL DEFAULT '',
        timestamp REAL NOT NULL
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_hermes_experiments_entity ON hermes_experiments(target_entity_id);
    """,
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS hermes_knowledge_fts USING fts5(
        entity_name,
        class_name,
        action_name,
        hypothesis,
        metadata
    );
    """,
]


class HermesKnowledgeStore:
    """Persistent SQLite-backed graph store for Hermes experiential knowledge."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or (AstraPaths.data_dir() / "hermes" / "knowledge.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            for statement in SCHEMA_DDL:
                conn.execute(statement)
            conn.commit()

    def clear(self) -> None:
        """Purge all stored Hermes knowledge (used for cold-start testing)."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM hermes_transitions;")
            conn.execute("DELETE FROM hermes_experiments;")
            conn.execute("DELETE FROM hermes_affordances;")
            conn.execute("DELETE FROM hermes_entities;")
            try:
                conn.execute("DELETE FROM hermes_knowledge_fts;")
            except Exception:
                pass
            conn.commit()
        logger.info("HermesKnowledgeStore cleared.")

    # -------------------------------------------------------------------------
    # Entity Operations
    # -------------------------------------------------------------------------

    def upsert_entity(self, entity: EntityNode) -> EntityNode:
        now = time.time()
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT entity_id FROM hermes_entities WHERE entity_id = ?",
                (entity.entity_id,)
            )
            exists = cur.fetchone() is not None
            if exists:
                conn.execute(
                    """
                    UPDATE hermes_entities
                    SET entity_type = ?, parent_entity_id = ?, name = ?, class_name = ?,
                        binary_hash = ?, version = ?, env_hash = ?, metadata_json = ?, updated_at = ?
                    WHERE entity_id = ?
                    """,
                    (
                        entity.entity_type.value,
                        entity.parent_entity_id,
                        entity.name,
                        entity.class_name,
                        entity.binary_hash,
                        entity.version,
                        entity.env_hash,
                        json.dumps(entity.metadata),
                        now,
                        entity.entity_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO hermes_entities (
                        entity_id, entity_type, parent_entity_id, name, class_name,
                        binary_hash, version, env_hash, metadata_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entity.entity_id,
                        entity.entity_type.value,
                        entity.parent_entity_id,
                        entity.name,
                        entity.class_name,
                        entity.binary_hash,
                        entity.version,
                        entity.env_hash,
                        json.dumps(entity.metadata),
                        entity.created_at,
                        now,
                    ),
                )
                # Index into FTS
                try:
                    conn.execute(
                        """
                        INSERT INTO hermes_knowledge_fts (entity_name, class_name, action_name, hypothesis, metadata)
                        VALUES (?, ?, '', '', ?)
                        """,
                        (entity.name, entity.class_name or "", json.dumps(entity.metadata)),
                    )
                except Exception:
                    pass
            conn.commit()
        return entity

    def get_entity(self, entity_id: str) -> Optional[EntityNode]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM hermes_entities WHERE entity_id = ?", (entity_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_entity(row)

    def find_entity_by_name(
        self,
        name: str,
        entity_type: Optional[EntityType] = None,
        parent_entity_id: Optional[str] = None,
    ) -> Optional[EntityNode]:
        query = "SELECT * FROM hermes_entities WHERE LOWER(name) = LOWER(?)"
        params: List[Any] = [name]
        if entity_type:
            query += " AND entity_type = ?"
            params.append(entity_type.value)
        if parent_entity_id:
            query += " AND parent_entity_id = ?"
            params.append(parent_entity_id)
        query += " ORDER BY updated_at DESC LIMIT 1"

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_entity(row)

    def list_entities(self, parent_id: Optional[str] = None) -> List[EntityNode]:
        query = "SELECT * FROM hermes_entities"
        params: List[Any] = []
        if parent_id is not None:
            query += " WHERE parent_entity_id = ?"
            params.append(parent_id)
        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            return [self._row_to_entity(r) for r in cur.fetchall()]

    # -------------------------------------------------------------------------
    # Affordance Operations
    # -------------------------------------------------------------------------

    def upsert_affordance(self, affordance: AffordanceEdge) -> AffordanceEdge:
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT affordance_id FROM hermes_affordances WHERE affordance_id = ?",
                (affordance.affordance_id,)
            )
            exists = cur.fetchone() is not None
            if exists:
                conn.execute(
                    """
                    UPDATE hermes_affordances
                    SET action_name = ?, capability_id = ?, parameter_schema_json = ?,
                        risk_level = ?, is_reversible = ?, confidence = ?, status = ?,
                        verification_count = ?, contradiction_count = ?, last_verified_at = ?
                    WHERE affordance_id = ?
                    """,
                    (
                        affordance.action_name,
                        affordance.capability_id,
                        json.dumps(affordance.parameter_schema),
                        affordance.risk_level.value,
                        1 if affordance.is_reversible else 0,
                        affordance.confidence,
                        affordance.status.value,
                        affordance.verification_count,
                        affordance.contradiction_count,
                        affordance.last_verified_at,
                        affordance.affordance_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO hermes_affordances (
                        affordance_id, entity_id, action_name, capability_id,
                        parameter_schema_json, risk_level, is_reversible, confidence,
                        status, verification_count, contradiction_count, last_verified_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        affordance.affordance_id,
                        affordance.entity_id,
                        affordance.action_name,
                        affordance.capability_id,
                        json.dumps(affordance.parameter_schema),
                        affordance.risk_level.value,
                        1 if affordance.is_reversible else 0,
                        affordance.confidence,
                        affordance.status.value,
                        affordance.verification_count,
                        affordance.contradiction_count,
                        affordance.last_verified_at,
                        affordance.created_at,
                    ),
                )
            conn.commit()
        return affordance

    def get_affordance(self, affordance_id: str) -> Optional[AffordanceEdge]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM hermes_affordances WHERE affordance_id = ?", (affordance_id,))
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_affordance(row)

    def find_affordance(self, entity_id: str, action_name: str) -> Optional[AffordanceEdge]:
        with self._get_connection() as conn:
            cur = conn.execute(
                "SELECT * FROM hermes_affordances WHERE entity_id = ? AND LOWER(action_name) = LOWER(?) LIMIT 1",
                (entity_id, action_name),
            )
            row = cur.fetchone()
            if not row:
                return None
            return self._row_to_affordance(row)

    def list_affordances(self, entity_id: str) -> List[AffordanceEdge]:
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM hermes_affordances WHERE entity_id = ?", (entity_id,))
            return [self._row_to_affordance(r) for r in cur.fetchall()]

    # -------------------------------------------------------------------------
    # Transition Recording & Bayesian Belief Update
    # -------------------------------------------------------------------------

    def record_transition(self, transition: StateTransitionRecord) -> None:
        """Record an observed state transition and update affordance confidence."""
        now = time.time()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO hermes_transitions (
                    transition_id, affordance_id, pre_state_hash, action_payload_json,
                    post_state_hash, expected_delta_json, observed_delta_json,
                    transition_verified, latency_ms, trace_id, pre_frame_id, post_frame_id, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transition.transition_id,
                    transition.affordance_id,
                    transition.pre_state_hash,
                    json.dumps(transition.action_payload),
                    transition.post_state_hash,
                    json.dumps(transition.expected_delta),
                    json.dumps(transition.observed_delta),
                    1 if transition.transition_verified else 0,
                    transition.latency_ms,
                    transition.trace_id,
                    transition.pre_frame_id,
                    transition.post_frame_id,
                    transition.timestamp,
                ),
            )

            # Fetch current affordance to apply Bayesian update
            cur = conn.execute(
                "SELECT * FROM hermes_affordances WHERE affordance_id = ?",
                (transition.affordance_id,)
            )
            aff_row = cur.fetchone()
            if aff_row:
                old_conf = float(aff_row["confidence"])
                v_count = int(aff_row["verification_count"])
                c_count = int(aff_row["contradiction_count"])

                if transition.transition_verified:
                    v_count += 1
                    # Bayesian positive reinforcement: C_new = min(1.0, C_old + 0.35 * (1 - C_old))
                    new_conf = min(1.0, old_conf + 0.35 * (1.0 - old_conf))
                    new_status = EpistemicStatus.VERIFIED if new_conf >= 0.85 else EpistemicStatus.OBSERVED
                else:
                    c_count += 1
                    # Severe contraction on contradiction: C_new = max(0.05, C_old * 0.20)
                    new_conf = max(0.05, old_conf * 0.20)
                    new_status = EpistemicStatus.CONTRADICTED

                conn.execute(
                    """
                    UPDATE hermes_affordances
                    SET confidence = ?, status = ?, verification_count = ?, contradiction_count = ?, last_verified_at = ?
                    WHERE affordance_id = ?
                    """,
                    (new_conf, new_status.value, v_count, c_count, now, transition.affordance_id),
                )
            conn.commit()

    def list_transitions(self, entity_id: Optional[str] = None) -> List[StateTransitionRecord]:
        if entity_id:
            query = """
                SELECT t.* FROM hermes_transitions t
                JOIN hermes_affordances a ON t.affordance_id = a.affordance_id
                WHERE a.entity_id = ?
                ORDER BY t.timestamp ASC
            """
            params = [entity_id]
        else:
            query = "SELECT * FROM hermes_transitions ORDER BY timestamp ASC"
            params = []

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            out = []
            for r in cur.fetchall():
                rec = StateTransitionRecord(
                    transition_id=r["transition_id"],
                    affordance_id=r["affordance_id"],
                    pre_state_hash=r["pre_state_hash"],
                    action_payload=json.loads(r["action_payload_json"]) if r["action_payload_json"] else {},
                    post_state_hash=r["post_state_hash"],
                    expected_delta=json.loads(r["expected_delta_json"]) if r["expected_delta_json"] else {},
                    observed_delta=json.loads(r["observed_delta_json"]) if r["observed_delta_json"] else {},
                    transition_verified=bool(r["transition_verified"]),
                    latency_ms=float(r["latency_ms"] or 0.0),
                    trace_id=r["trace_id"] or "",
                    pre_frame_id=r["pre_frame_id"] or "",
                    post_frame_id=r["post_frame_id"] or "",
                    timestamp=float(r["timestamp"]),
                )
                out.append(rec)
            return out

    # -------------------------------------------------------------------------
    # Diagnostic Experiment Logging
    # -------------------------------------------------------------------------

    def record_experiment(self, experiment: ExperimentRecord) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO hermes_experiments (
                    experiment_id, target_entity_id, hypothesis, probe_action_name,
                    probe_payload_json, expected_outcome, actual_outcome, status,
                    task_id, trace_id, prompt_hash, response_hash, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    experiment.experiment_id,
                    experiment.target_entity_id,
                    experiment.hypothesis,
                    experiment.probe_action_name,
                    json.dumps(experiment.probe_payload),
                    experiment.expected_outcome,
                    experiment.actual_outcome,
                    experiment.status.value,
                    experiment.task_id,
                    experiment.trace_id,
                    experiment.prompt_hash,
                    experiment.response_hash,
                    experiment.timestamp,
                ),
            )
            conn.commit()

    def update_experiment_status(
        self,
        experiment_id: str,
        status: ExperimentStatus,
        actual_outcome: str,
    ) -> None:
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE hermes_experiments
                SET status = ?, actual_outcome = ?
                WHERE experiment_id = ?
                """,
                (status.value, actual_outcome, experiment_id),
            )
            conn.commit()

    def list_experiments(self, target_entity_id: Optional[str] = None) -> List[ExperimentRecord]:
        if target_entity_id:
            query = "SELECT * FROM hermes_experiments WHERE target_entity_id = ? ORDER BY timestamp ASC"
            params = [target_entity_id]
        else:
            query = "SELECT * FROM hermes_experiments ORDER BY timestamp ASC"
            params = []

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            out = []
            for r in cur.fetchall():
                rec = ExperimentRecord(
                    experiment_id=r["experiment_id"],
                    target_entity_id=r["target_entity_id"],
                    hypothesis=r["hypothesis"],
                    probe_action_name=r["probe_action_name"],
                    probe_payload=json.loads(r["probe_payload_json"]) if r["probe_payload_json"] else {},
                    expected_outcome=r["expected_outcome"] or "",
                    actual_outcome=r["actual_outcome"],
                    status=ExperimentStatus(r["status"]),
                    task_id=r["task_id"] or "",
                    trace_id=r["trace_id"] or "",
                    prompt_hash=r["prompt_hash"] or "",
                    response_hash=r["response_hash"] or "",
                    timestamp=float(r["timestamp"]),
                )
                out.append(rec)
            return out

    # -------------------------------------------------------------------------
    # Epistemic Uncertainty Estimation & Experience Retrieval
    # -------------------------------------------------------------------------

    def get_uncertainty_score(
        self,
        entity_name: str,
        candidate_action: str,
    ) -> Tuple[float, ConfidenceBand, Optional[AffordanceEdge]]:
        """
        Calculates confidence score, band, and matching affordance for a target action.
        Returns: (confidence, ConfidenceBand, AffordanceEdge | None)
        """
        entity = self.find_entity_by_name(entity_name)
        if not entity:
            return 0.0, ConfidenceBand.UNKNOWN, None

        affordance = self.find_affordance(entity.entity_id, candidate_action)
        if not affordance:
            return 0.10, ConfidenceBand.UNKNOWN, None

        return affordance.confidence, affordance.confidence_band, affordance

    def query_experience(
        self,
        entity_name: str,
        action_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate experience for an entity into a prompt-friendly context payload."""
        entity = self.find_entity_by_name(entity_name)
        if not entity:
            return {
                "entity": None,
                "is_known": False,
                "confidence": 0.0,
                "affordances": [],
                "recent_transitions": [],
            }

        affordances = self.list_affordances(entity.entity_id)
        if action_name:
            affordances = [a for a in affordances if a.action_name.lower() == action_name.lower()]

        transitions = []
        with self._get_connection() as conn:
            cur = conn.execute(
                """
                SELECT t.*, a.action_name FROM hermes_transitions t
                JOIN hermes_affordances a ON t.affordance_id = a.affordance_id
                WHERE a.entity_id = ?
                ORDER BY t.timestamp DESC LIMIT 5
                """,
                (entity.entity_id,),
            )
            for r in cur.fetchall():
                transitions.append({
                    "action": r["action_name"],
                    "verified": bool(r["transition_verified"]),
                    "observed_delta": json.loads(r["observed_delta_json"]),
                    "latency_ms": r["latency_ms"],
                })

        max_conf = max((a.confidence for a in affordances), default=0.0)
        return {
            "entity": {
                "id": entity.entity_id,
                "name": entity.name,
                "class": entity.class_name,
                "type": entity.entity_type.value,
            },
            "is_known": len(affordances) > 0,
            "max_confidence": max_conf,
            "affordances": [
                {
                    "action": a.action_name,
                    "confidence": a.confidence,
                    "band": a.confidence_band.value,
                    "status": a.status.value,
                    "verifications": a.verification_count,
                    "contradictions": a.contradiction_count,
                }
                for a in affordances
            ],
            "recent_transitions": transitions,
        }

    # -------------------------------------------------------------------------
    # Helper Deserializers
    # -------------------------------------------------------------------------

    def _row_to_entity(self, row: sqlite3.Row) -> EntityNode:
        return EntityNode(
            entity_id=row["entity_id"],
            entity_type=EntityType(row["entity_type"]),
            parent_entity_id=row["parent_entity_id"],
            name=row["name"],
            class_name=row["class_name"],
            binary_hash=row["binary_hash"],
            version=row["version"],
            env_hash=row["env_hash"],
            metadata=json.loads(row["metadata_json"]) if row["metadata_json"] else {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_affordance(self, row: sqlite3.Row) -> AffordanceEdge:
        return AffordanceEdge(
            affordance_id=row["affordance_id"],
            entity_id=row["entity_id"],
            action_name=row["action_name"],
            capability_id=row["capability_id"],
            parameter_schema=json.loads(row["parameter_schema_json"]) if row["parameter_schema_json"] else {},
            risk_level=AffordanceRisk(row["risk_level"]),
            is_reversible=bool(row["is_reversible"]),
            confidence=row["confidence"],
            status=EpistemicStatus(row["status"]),
            verification_count=row["verification_count"],
            contradiction_count=row["contradiction_count"],
            last_verified_at=row["last_verified_at"],
            created_at=row["created_at"],
        )
