# AstraRun SQLite Task Ledger

## 1. Storage Architecture
The persistent storage engine is implemented in `src/astrarun/tasks/ledger.py` using standard library `sqlite3` at `data/astra_history.db`.

Key performance and integrity settings:
- **Write-Ahead Logging (WAL)**: `PRAGMA journal_mode = WAL;` enables concurrent reads without blocking writes.
- **Foreign Keys**: `PRAGMA foreign_keys = ON;` guarantees referential integrity between conversations, tasks, and events.
- **Versioned Schema**: `PRAGMA user_version = 1;` ensures transparent forward migrations.

---

## 2. Relational Schema

```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    title TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    metadata TEXT
);

CREATE TABLE tasks (
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

CREATE TABLE task_events (
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

CREATE TABLE conversation_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    task_id TEXT,
    sender TEXT NOT NULL,
    text TEXT NOT NULL,
    timestamp REAL NOT NULL,
    data TEXT,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
```

---

## 3. High-Performance Indices
- `idx_tasks_created_at` ON `tasks(created_at DESC)`
- `idx_tasks_status` ON `tasks(status)`
- `idx_tasks_conversation_id` ON `tasks(conversation_id)`
- `idx_tasks_request_hash` ON `tasks(request_hash)`
- `idx_events_task_id` ON `task_events(task_id)`
- `idx_events_type` ON `task_events(event_type)`

---

## 4. Resilience & Crash Recovery
- **Automatic Corruption Recovery**: If header or page corruption is detected via `PRAGMA quick_check;`, the corrupted file is automatically backed up as `astra_history.db.corrupt.<timestamp>`, and a clean database is initialized seamlessly without crashing AstraRun.
- **Dangling Task Recovery**: On startup, `recover_interrupted_tasks()` detects any tasks left in active states (`RUNNING`, `WAITING_*`, `PARSING`, `RESOLVING`), marks them as `INTERRUPTED`, and appends an auditable `TASK_INTERRUPTED` event.
- **Fail-Safe Execution**: Invariant Rule #90: persistence errors log warnings and **never** break live launcher execution.
