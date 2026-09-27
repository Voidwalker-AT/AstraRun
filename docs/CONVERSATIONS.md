# AstraRun Conversation & Threading Subsystem

## 1. Overview
In AstraRun v0.8, user interactions are grouped into explicit **Conversation** sessions.
A conversation thread maintains chronological continuity across multi-turn queries, task executions, and user feedback, while preserving a clean separation from low-level execution mechanics.

---

## 2. Conversation Model (`src/astrarun/tasks/models.py`)

### `Conversation`
- `id: str` (UUIDv4)
- `title: str` (Auto-generated from the first user request)
- `created_at: float`
- `updated_at: float`
- `status: str` (`"ACTIVE"`, `"ARCHIVED"`)
- `task_ids: list[str]`
- `metadata: dict[str, Any]`

### `ConversationMessage`
- `id: str` (UUIDv4)
- `conversation_id: str`
- `task_id: Optional[str]`
- `sender: str` (`"USER"`, `"ASTRA_RESULT"`, `"SYSTEM"`)
- `text: str` (Sanitized human-readable text)
- `timestamp: float`
- `data: Optional[dict[str, Any]]`

---

## 3. Conversation Lifecycle in `TaskManager`
1. When a user issues a command via launcher or hotkey without an explicit `conversation_id`, `TaskManager` creates a new conversation or binds to the active session.
2. Upon task completion, `TaskManager` appends an `"ASTRA_RESULT"` message summarizing the outcome.
3. Users can inspect past conversation threads and review message chronologies in the History UI.
