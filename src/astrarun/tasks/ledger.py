"""Persistent SQLite-backed Task Ledger maintaining audit trails and conversation history."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from astrarun.core.logging import get_logger
from astrarun.tasks.models import (
    Conversation,
    ConversationMessage,
    Task,
    TaskError,
    TaskEvent,
    TaskEventType,
    TaskResult,
    TaskStatus,
)
from astrarun.tasks.serialization import (
    hash_request,
    sanitize_capability_payload,
    sanitize_request,
)

logger = get_logger("astrarun.tasks.ledger")

SCHEMA_VERSION = 1


class TaskLedger:
    """
    Persistent SQLite storage engine for Conversations, Tasks, and TaskEvents.
    
    Safety & Reliability Guarantees:
    - 100% Parameterized queries (Zero SQL injection vectors).
    - Database failure resilience: Failures log warnings and never break capability execution.
    - Automatic schema migration & corruption recovery with backup.
    - Crash recovery: Marks orphaned active tasks as INTERRUPTED upon startup.
    - Strict privacy controls: Secret redaction and optional raw request omission.
    """

    def __init__(
        self,
        db_path: Optional[str | Path] = None,
        store_raw_requests: bool = True,
        store_result_payloads: bool = False,
    ) -> None:
        if db_path is None:
            # Default to data/astra_history.db relative to workspace root
            root = Path(__file__).resolve().parent.parent.parent.parent
            self.db_path = root / "data" / "astra_history.db"
        else:
            self.db_path = Path(db_path)

        self.store_raw_requests = store_raw_requests
        self.store_result_payloads = store_result_payloads
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get or initialize the SQLite connection with WAL mode."""
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=10.0,
            )
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode and foreign keys for speed and integrity
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA foreign_keys = ON;")
        return self._conn

    def _init_database(self) -> None:
        """Initialize database tables, indices, and schema version."""
        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute("PRAGMA quick_check;")
                self._run_migrations(conn)
            except sqlite3.DatabaseError as err:
                logger.error("Database corruption detected on %s: %s. Attempting recovery.", self.db_path, err)
                self._handle_corruption()

    def _handle_corruption(self) -> None:
        """Handle database corruption by backing up corrupt DB and recreating a fresh one."""
        try:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

            if self.db_path.exists():
                backup_path = self.db_path.with_name(f"{self.db_path.name}.corrupt.{int(time.time())}")
                shutil.move(str(self.db_path), str(backup_path))
                logger.warning("Corrupt database backed up to: %s", backup_path)

            conn = self._get_connection()
            self._run_migrations(conn)
            logger.info("Fresh database initialized successfully after corruption recovery.")
        except Exception as recovery_err:
            logger.error("Critical failure recovering corrupt database: %s", recovery_err, exc_info=True)

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """Execute versioned schema setup."""
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        current_version = cursor.fetchone()[0]

        if current_version == 0:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    metadata TEXT
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    parent_task_id TEXT,
                    request_text TEXT,
                    request_hash TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'launcher',
                    created_at REAL NOT NULL,
                    started_at REAL,
                    completed_at REAL,
                    status TEXT NOT NULL,
                    summary TEXT,
                    capabilities_used TEXT,
                    duration_ms REAL DEFAULT 0.0,
                    error_code TEXT,
                    error_message TEXT,
                    metadata TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_events (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT,
                    capability_id TEXT,
                    entity_ids TEXT,
                    duration_ms REAL,
                    data TEXT,
                    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
                );
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    task_id TEXT,
                    sender TEXT NOT NULL,
                    text TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    data TEXT,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );
            """)

            # Indices for rapid querying and history searching
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_conv ON tasks(conversation_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id, timestamp ASC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_messages_conv ON conversation_messages(conversation_id, timestamp ASC);")

            cursor.execute(f"PRAGMA user_version = {SCHEMA_VERSION};")
            conn.commit()
            logger.info("Task Ledger database initialized to schema version %d.", SCHEMA_VERSION)

    # -------------------------------------------------------------------------
    # Crash Recovery
    # -------------------------------------------------------------------------

    def recover_interrupted_tasks(self) -> int:
        """
        Scan for tasks left in an active state when AstraRun was stopped or crashed,
        transitioning them to INTERRUPTED.
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.cursor()
                interrupted_states = (
                    TaskStatus.RUNNING.value,
                    TaskStatus.WAITING_CONFIRMATION.value,
                    TaskStatus.WAITING_CLARIFICATION.value,
                    TaskStatus.WAITING_USER.value,
                    TaskStatus.PARSING.value,
                    TaskStatus.RESOLVING.value,
                    TaskStatus.READY.value,
                )
                placeholders = ",".join("?" for _ in interrupted_states)
                cur.execute(f"SELECT id FROM tasks WHERE status IN ({placeholders})", interrupted_states)
                interrupted_ids = [r[0] for r in cur.fetchall()]
                cur.execute(
                    f"UPDATE tasks SET status = ?, error_code = 'INTERRUPTED', error_message = ? WHERE status IN ({placeholders})",
                    (TaskStatus.INTERRUPTED.value, "AstraRun closed before this task finished.", *interrupted_states)
                )
                affected = cur.rowcount
                now = time.time()
                for tid in interrupted_ids:
                    cur.execute(
                        """
                        INSERT INTO task_events (id, task_id, timestamp, event_type, status, title, summary, capability_id, entity_ids, duration_ms, data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, NULL, '[]', NULL, '{}')
                        """,
                        (str(uuid.uuid4()), tid, now, TaskEventType.TASK_INTERRUPTED.value, "FAILED", "Task Interrupted", "Process closed before task completion"),
                    )
                conn.commit()
                if affected > 0:
                    logger.info("Crash recovery: marked %d lingering tasks as INTERRUPTED.", affected)
                return affected
            except Exception as err:
                logger.error("Failed to execute crash recovery: %s", err)
                return 0

    # -------------------------------------------------------------------------
    # Conversation Management
    # -------------------------------------------------------------------------

    def create_conversation(self, title: Optional[str] = None, metadata: Optional[dict[str, Any]] = None) -> Conversation:
        """Create and persist a new Conversation thread."""
        conv_id = str(uuid.uuid4())
        now = time.time()
        conv = Conversation(
            id=conv_id,
            title=title or "New Conversation",
            created_at=now,
            updated_at=now,
            status="ACTIVE",
            task_ids=[],
            metadata=metadata or {},
        )
        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute(
                    "INSERT INTO conversations (id, title, created_at, updated_at, status, metadata) VALUES (?, ?, ?, ?, ?, ?)",
                    (conv.id, conv.title, conv.created_at, conv.updated_at, conv.status, json.dumps(conv.metadata)),
                )
                conn.commit()
            except Exception as err:
                logger.error("Failed to insert conversation %s: %s", conv_id, err)
        return conv

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Retrieve conversation by ID along with its associated task IDs."""
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,))
                row = cur.fetchone()
                if not row:
                    return None
                
                # Fetch task IDs
                cur_tasks = conn.execute("SELECT id FROM tasks WHERE conversation_id = ? ORDER BY created_at ASC", (conversation_id,))
                task_ids = [r["id"] for r in cur_tasks.fetchall()]
                
                return Conversation(
                    id=row["id"],
                    title=row["title"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    status=row["status"],
                    task_ids=task_ids,
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                )
            except Exception as err:
                logger.error("Failed to get conversation %s: %s", conversation_id, err)
                return None

    def list_conversations(self, limit: int = 50, offset: int = 0) -> list[Conversation]:
        """List recent conversations sorted by latest update."""
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.execute(
                    "SELECT * FROM conversations ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
                results = []
                for row in cur.fetchall():
                    results.append(Conversation(
                        id=row["id"],
                        title=row["title"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                        status=row["status"],
                        task_ids=[],
                        metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                    ))
                return results
            except Exception as err:
                logger.error("Failed to list conversations: %s", err)
                return []

    def rename_conversation(self, conversation_id: str, new_title: str) -> bool:
        """Rename an existing conversation thread."""
        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                    (new_title, time.time(), conversation_id),
                )
                conn.commit()
                return True
            except Exception as err:
                logger.error("Failed to rename conversation %s: %s", conversation_id, err)
                return False

    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete an entire conversation and all its tasks, events, and messages."""
        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
                conn.commit()
                return True
            except Exception as err:
                logger.error("Failed to delete conversation %s: %s", conversation_id, err)
                return False

    # -------------------------------------------------------------------------
    # Conversation Messages
    # -------------------------------------------------------------------------

    def record_message(self, message: ConversationMessage) -> None:
        """Persist a conversation message."""
        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute(
                    "INSERT INTO conversation_messages (id, conversation_id, task_id, sender, text, timestamp, data) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        message.id,
                        message.conversation_id,
                        message.task_id,
                        message.sender,
                        sanitize_request(message.text),
                        message.timestamp,
                        json.dumps(message.data) if message.data else None,
                    ),
                )
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (message.timestamp, message.conversation_id),
                )
                conn.commit()
            except Exception as err:
                logger.error("Failed to record conversation message %s: %s", message.id, err)

    def get_conversation_messages(self, conversation_id: str) -> list[ConversationMessage]:
        """Fetch all messages in a conversation in chronological order."""
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.execute(
                    "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY timestamp ASC",
                    (conversation_id,),
                )
                messages = []
                for row in cur.fetchall():
                    messages.append(ConversationMessage(
                        id=row["id"],
                        conversation_id=row["conversation_id"],
                        task_id=row["task_id"],
                        sender=row["sender"],
                        text=row["text"],
                        timestamp=row["timestamp"],
                        data=json.loads(row["data"]) if row["data"] else None,
                    ))
                return messages
            except Exception as err:
                logger.error("Failed to get messages for conversation %s: %s", conversation_id, err)
                return []

    # -------------------------------------------------------------------------
    # Task Persistence
    # -------------------------------------------------------------------------

    def save_task(self, task: Task) -> None:
        """Insert or update a Task record in the ledger."""
        # Privacy policy enforcement
        req_text = sanitize_request(task.request_text) if self.store_raw_requests else "[REDACTED_BY_PRIVACY_POLICY]"
        req_hash = task.request_hash or hash_request(task.request_text)

        summary = ""
        caps_used: list[str] = []
        err_code: Optional[str] = None
        err_msg: Optional[str] = None

        if task.final_result:
            summary = task.final_result.summary
            caps_used = task.final_result.capabilities_used
            if task.final_result.error:
                err_code = task.final_result.error.code
                err_msg = task.final_result.error.message

        with self._lock:
            try:
                conn = self._get_connection()
                # Ensure foreign key conversation exists
                conn.execute(
                    """
                    INSERT OR IGNORE INTO conversations (id, title, created_at, updated_at, status)
                    VALUES (?, ?, ?, ?, 'ACTIVE')
                    """,
                    (
                        task.conversation_id,
                        task.request_text or "Conversation",
                        task.created_at,
                        task.created_at,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO tasks (
                        id, conversation_id, parent_task_id, request_text, request_hash, source,
                        created_at, started_at, completed_at, status, summary, capabilities_used,
                        duration_ms, error_code, error_message, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        started_at = excluded.started_at,
                        completed_at = excluded.completed_at,
                        status = excluded.status,
                        summary = excluded.summary,
                        capabilities_used = excluded.capabilities_used,
                        duration_ms = excluded.duration_ms,
                        error_code = excluded.error_code,
                        error_message = excluded.error_message,
                        metadata = excluded.metadata
                    """,
                    (
                        task.id,
                        task.conversation_id,
                        task.parent_task_id,
                        req_text,
                        req_hash,
                        task.source,
                        task.created_at,
                        task.started_at,
                        task.completed_at,
                        task.status.value,
                        summary,
                        json.dumps(caps_used),
                        task.duration_ms(),
                        err_code,
                        err_msg,
                        json.dumps(task.metadata),
                    ),
                )
                conn.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (task.completed_at or task.created_at, task.conversation_id),
                )
                conn.commit()
            except Exception as err:
                logger.error("Failed to save task %s: %s", task.id, err)

    def append_event(self, event: TaskEvent) -> None:
        """Append an immutable TaskEvent to the ledger."""
        data_payload: dict[str, Any] = {}
        if self.store_result_payloads:
            data_payload = dict(event.data)
        elif event.capability_id:
            data_payload = sanitize_capability_payload(event.capability_id, event.data)
        else:
            # Keep primitive summary values
            for k, v in event.data.items():
                if isinstance(v, (int, float, bool, str)) and len(str(v)) < 100:
                    data_payload[k] = v

        with self._lock:
            try:
                conn = self._get_connection()
                conn.execute(
                    """
                    INSERT OR REPLACE INTO task_events (
                        id, task_id, timestamp, event_type, status, title, summary,
                        capability_id, entity_ids, duration_ms, data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.id,
                        event.task_id,
                        event.timestamp,
                        event.type.value,
                        event.status,
                        event.title,
                        event.summary,
                        event.capability_id,
                        json.dumps(event.entity_ids),
                        event.duration_ms,
                        json.dumps(data_payload),
                    ),
                )
                conn.commit()
            except Exception as err:
                logger.error("Failed to append event %s for task %s: %s", event.id, event.task_id, err)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        final_result: Optional[TaskResult] = None,
    ) -> None:
        """Update status and optionally record the final TaskResult for a task."""
        now = time.time()
        summary = final_result.summary if final_result else None
        caps_used = json.dumps(final_result.capabilities_used) if final_result else None
        err_code = final_result.error.code if (final_result and final_result.error) else None
        err_msg = final_result.error.message if (final_result and final_result.error) else None
        dur_ms = final_result.duration_ms if final_result else 0.0

        with self._lock:
            try:
                conn = self._get_connection()
                if final_result:
                    conn.execute(
                        """
                        UPDATE tasks SET
                            status = ?,
                            completed_at = ?,
                            summary = ?,
                            capabilities_used = ?,
                            duration_ms = ?,
                            error_code = ?,
                            error_message = ?
                        WHERE id = ?
                        """,
                        (status.value, now, summary, caps_used, dur_ms, err_code, err_msg, task_id),
                    )
                else:
                    conn.execute(
                        "UPDATE tasks SET status = ? WHERE id = ?",
                        (status.value, task_id),
                    )
                conn.commit()
            except Exception as err:
                logger.error("Failed to update status for task %s: %s", task_id, err)

    # -------------------------------------------------------------------------
    # Task Retrieval & Search
    # -------------------------------------------------------------------------

    def get_task(self, task_id: str, include_events: bool = True) -> Optional[Task]:
        """Retrieve a task by ID including its timeline events."""
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
                row = cur.fetchone()
                if not row:
                    return None

                events: list[TaskEvent] = []
                if include_events:
                    cur_ev = conn.execute("SELECT * FROM task_events WHERE task_id = ? ORDER BY timestamp ASC", (task_id,))
                    for ev_row in cur_ev.fetchall():
                        events.append(TaskEvent(
                            id=ev_row["id"],
                            task_id=ev_row["task_id"],
                            timestamp=ev_row["timestamp"],
                            type=TaskEventType(ev_row["event_type"]),
                            status=ev_row["status"],
                            title=ev_row["title"],
                            summary=ev_row["summary"],
                            capability_id=ev_row["capability_id"],
                            entity_ids=json.loads(ev_row["entity_ids"]) if ev_row["entity_ids"] else [],
                            data=json.loads(ev_row["data"]) if ev_row["data"] else {},
                            duration_ms=ev_row["duration_ms"],
                        ))

                res: Optional[TaskResult] = None
                if row["status"] in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.BLOCKED.value, TaskStatus.PARTIALLY_COMPLETED.value):
                    caps = json.loads(row["capabilities_used"]) if row["capabilities_used"] else []
                    err = TaskError(code=row["error_code"], message=row["error_message"] or "") if row["error_code"] else None
                    res = TaskResult(
                        task_id=row["id"],
                        success=(row["status"] == TaskStatus.COMPLETED.value),
                        status=TaskStatus(row["status"]),
                        message=row["summary"] or "",
                        summary=row["summary"] or "",
                        data={},
                        capabilities_used=caps,
                        duration_ms=row["duration_ms"] or 0.0,
                        error=err,
                    )

                return Task(
                    id=row["id"],
                    conversation_id=row["conversation_id"],
                    request_text=row["request_text"],
                    request_hash=row["request_hash"],
                    source=row["source"],
                    created_at=row["created_at"],
                    started_at=row["started_at"],
                    completed_at=row["completed_at"],
                    status=TaskStatus(row["status"]),
                    events=events,
                    final_result=res,
                    parent_task_id=row["parent_task_id"],
                    metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                )
            except Exception as err:
                logger.error("Failed to get task %s: %s", task_id, err)
                return None

    def get_recent_tasks(self, limit: int = 50, offset: int = 0) -> list[Task]:
        """Fetch recently created tasks ordered newest first."""
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.execute(
                    "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
                tasks: list[Task] = []
                for row in cur.fetchall():
                    tasks.append(self._row_to_shallow_task(row))
                return tasks
            except Exception as err:
                logger.error("Failed to get recent tasks: %s", err)
                return []

    def get_tasks_by_conversation(self, conversation_id: str) -> list[Task]:
        """Fetch all tasks belonging to a specific conversation thread."""
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.execute(
                    "SELECT * FROM tasks WHERE conversation_id = ? ORDER BY created_at ASC",
                    (conversation_id,),
                )
                tasks: list[Task] = []
                for row in cur.fetchall():
                    tasks.append(self._row_to_shallow_task(row))
                return tasks
            except Exception as err:
                logger.error("Failed to get tasks for conversation %s: %s", conversation_id, err)
                return []

    def get_tasks_by_status(self, status: TaskStatus, limit: int = 50) -> list[Task]:
        """Query tasks by their current status."""
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status.value, limit),
                )
                tasks: list[Task] = []
                for row in cur.fetchall():
                    tasks.append(self._row_to_shallow_task(row))
                return tasks
            except Exception as err:
                logger.error("Failed to get tasks by status %s: %s", status.value, err)
                return []

    def get_tasks_by_capability(self, capability_id: str, limit: int = 50) -> list[Task]:
        """Query tasks that utilized a specific capability."""
        with self._lock:
            try:
                conn = self._get_connection()
                pattern = f"%\"{capability_id}\"%"
                cur = conn.execute(
                    "SELECT * FROM tasks WHERE capabilities_used LIKE ? ORDER BY created_at DESC LIMIT ?",
                    (pattern, limit),
                )
                tasks: list[Task] = []
                for row in cur.fetchall():
                    tasks.append(self._row_to_shallow_task(row))
                return tasks
            except Exception as err:
                logger.error("Failed to get tasks by capability %s: %s", capability_id, err)
                return []

    def get_tasks_between(self, start_ts: float, end_ts: float, limit: int = 100) -> list[Task]:
        """Query tasks created within a specific timestamp interval."""
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.execute(
                    "SELECT * FROM tasks WHERE created_at >= ? AND created_at <= ? ORDER BY created_at DESC LIMIT ?",
                    (start_ts, end_ts, limit),
                )
                tasks: list[Task] = []
                for row in cur.fetchall():
                    tasks.append(self._row_to_shallow_task(row))
                return tasks
            except Exception as err:
                logger.error("Failed to get tasks between %f and %f: %s", start_ts, end_ts, err)
                return []

    def search_tasks(self, query: str, limit: int = 50) -> list[Task]:
        """
        Search task history using parameterized pattern matching across request text,
        summaries, and capabilities.
        """
        pattern = f"%{query.strip()}%"
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.execute(
                    """
                    SELECT * FROM tasks
                    WHERE request_text LIKE ? OR summary LIKE ? OR capabilities_used LIKE ?
                    ORDER BY created_at DESC LIMIT ?
                    """,
                    (pattern, pattern, pattern, limit),
                )
                tasks: list[Task] = []
                for row in cur.fetchall():
                    tasks.append(self._row_to_shallow_task(row))
                return tasks
            except Exception as err:
                logger.error("Failed to search tasks for '%s': %s", query, err)
                return []

    def _row_to_shallow_task(self, row: sqlite3.Row) -> Task:
        """Helper to convert a tasks DB row into a shallow Task instance."""
        caps = json.loads(row["capabilities_used"]) if row["capabilities_used"] else []
        err = TaskError(code=row["error_code"], message=row["error_message"] or "") if row["error_code"] else None
        res = None
        if row["status"] in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.BLOCKED.value, TaskStatus.PARTIALLY_COMPLETED.value):
            res = TaskResult(
                task_id=row["id"],
                success=(row["status"] == TaskStatus.COMPLETED.value),
                status=TaskStatus(row["status"]),
                message=row["summary"] or "",
                summary=row["summary"] or "",
                data={},
                capabilities_used=caps,
                duration_ms=row["duration_ms"] or 0.0,
                error=err,
            )
        return Task(
            id=row["id"],
            conversation_id=row["conversation_id"],
            request_text=row["request_text"],
            request_hash=row["request_hash"],
            source=row["source"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            status=TaskStatus(row["status"]),
            events=[],
            final_result=res,
            parent_task_id=row["parent_task_id"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    # -------------------------------------------------------------------------
    # Retention, Deletion, and Export
    # -------------------------------------------------------------------------

    def cleanup_retention(self, retention_days: int = 30, max_tasks: int = 5000) -> int:
        """
        Delete tasks and events older than retention_days or exceeding max_tasks.
        Returns the number of pruned tasks.
        """
        cutoff = time.time() - (retention_days * 86400.0)
        deleted_count = 0
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.cursor()
                
                # 1. Delete by age
                cur.execute("DELETE FROM tasks WHERE created_at < ?", (cutoff,))
                deleted_count += cur.rowcount

                # 2. Delete excess beyond max_tasks
                cur.execute("SELECT COUNT(*) FROM tasks;")
                total = cur.fetchone()[0]
                if total > max_tasks:
                    excess = total - max_tasks
                    cur.execute(
                        "DELETE FROM tasks WHERE id IN (SELECT id FROM tasks ORDER BY created_at ASC LIMIT ?)",
                        (excess,)
                    )
                    deleted_count += cur.rowcount

                # 3. Clean orphaned conversations
                cur.execute("""
                    DELETE FROM conversations
                    WHERE id NOT IN (SELECT DISTINCT conversation_id FROM tasks)
                    AND created_at < ?
                """, (cutoff,))

                conn.commit()
                if deleted_count > 0:
                    logger.info("Retention cleanup: removed %d old tasks.", deleted_count)
                return deleted_count
            except Exception as err:
                logger.error("Failed to run retention cleanup: %s", err)
                return 0

    def clear_history(self) -> int:
        """
        Purge all tasks, events, and conversation messages from the database.
        Returns total tasks deleted.
        """
        with self._lock:
            try:
                conn = self._get_connection()
                cur = conn.cursor()
                cur.execute("DELETE FROM task_events;")
                cur.execute("DELETE FROM conversation_messages;")
                cur.execute("DELETE FROM tasks;")
                deleted = cur.rowcount
                cur.execute("DELETE FROM conversations;")
                conn.commit()
                conn.execute("VACUUM;")
                logger.info("Task Ledger cleared by user request (%d tasks deleted).", deleted)
                return deleted
            except Exception as err:
                logger.error("Failed to clear history: %s", err)
                return 0

    def export_task(self, task_id: str, format: str = "json") -> str:
        """
        Export a task and its timeline as sanitized JSON or human-readable Markdown.
        """
        task = self.get_task(task_id, include_events=True)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        if format.lower() == "json":
            return json.dumps(task.to_dict(), indent=2)

        # Markdown Export
        lines = [
            f"# AstraRun Task Audit: {task.id}",
            f"- **Date**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(task.created_at))}",
            f"- **Status**: `{task.status.value}`",
            f"- **Request**: `{task.request_text}`",
            f"- **Duration**: {task.duration_ms():.2f} ms",
            "",
            "## Timeline Events",
        ]
        for ev in task.events:
            dur = f" ({ev.duration_ms:.1f} ms)" if ev.duration_ms else ""
            cap = f" [`{ev.capability_id}`]" if ev.capability_id else ""
            summary = f" — {ev.summary}" if ev.summary else ""
            lines.append(f"- **{ev.type.value}** [{ev.status}]{cap}: {ev.title}{summary}{dur}")

        if task.final_result:
            lines.extend([
                "",
                "## Final Result",
                f"- **Success**: `{task.final_result.success}`",
                f"- **Summary**: {task.final_result.summary}",
                f"- **Capabilities Used**: `{', '.join(task.final_result.capabilities_used)}`",
            ])
            if task.final_result.error:
                lines.append(f"- **Error**: `[{task.final_result.error.code}] {task.final_result.error.message}`")

        return "\n".join(lines)

    def close(self) -> None:
        """Safely close SQLite connection."""
        with self._lock:
            if self._conn:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
