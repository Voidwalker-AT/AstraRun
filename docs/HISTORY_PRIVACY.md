# AstraRun History Privacy, Redaction & Retention Controls

## 1. Zero-Secret Policy
In accordance with Platform Rule #7 and v0.8 requirements, AstraRun enforces comprehensive privacy controls before persisting any data to disk.

---

## 2. Privacy Protections

### 1. Regex-Based Redaction (`sanitize_request`)
Before storing any request text or conversation message in SQLite, sensitive credentials are automatically redacted:
- `sk-[A-Za-z0-9_-]{20,}` ➔ `[REDACTED_API_KEY]`
- `Bearer\s+[A-Za-z0-9\._-]{20,}` ➔ `Bearer [REDACTED_TOKEN]`
- `(?:password|passwd|pwd)\s*[=:]\s*([^\s;]+)` ➔ `password=[REDACTED_PASSWORD]`
- Generic high-entropy hex/base64 patterns (`(?i)(?:api_key|token|secret)\s*[=:]\s*([A-Za-z0-9_-]{16,})`) ➔ `[REDACTED_SECRET]`

### 2. SHA-256 Request Hashing (`hash_request`)
All tasks record a deterministic SHA-256 hash of the request text (`request_hash`). If the user configures `"store_raw_requests": false` in `config/settings.json`, AstraRun replaces the `request_text` column with `"[REDACTED_BY_PRIVACY_POLICY]"` while retaining search and indexing capability via the hash.

### 3. Capability Payload Bounding (`sanitize_capability_payload`)
Prevents storing large binary payloads, memory dumps, or sensitive process command-lines:
- `inspect_process`: Strips large environment blocks and truncates command line arguments to 100 characters after redacting secrets.
- `list_processes`: Bounded to at most 50 items.
- `find_file` / `list_recent_files`: Stores only count and top 3 summary metadata.
- Large binary output data is strictly omitted unless `store_result_payloads: true` is explicitly enabled.

---

## 3. Retention Policies & Purging
In `config/settings.json`:
```json
"history": {
  "retention_days": 30,
  "max_stored_tasks": 5000,
  "store_raw_requests": true,
  "store_result_payloads": false
}
```
- `cleanup_retention(retention_days, max_tasks)`: Periodically purges records older than `retention_days` and caps the database at `max_stored_tasks`.
- `clear_history()`: Completely flushes all past tasks, events, and conversation messages with a single user-confirmed command.
