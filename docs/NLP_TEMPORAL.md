# AstraRun v0.6.5 — Workstation Temporal Engine

> **Status**: APPROVED  
> **Milestone**: AstraRun v0.6.5  
> **Source Module**: `src/astrarun/nlp/temporal.py`  

---

## 1. Principles & Local Timezone Contract

Workstation requests frequently reference temporal activities (`"open the project I worked on yesterday"`, `"what was I doing this morning"`).

### Core Rule: Workstation Local Time
All temporal intervals must be calculated relative to the host machine's current local timezone (`datetime.now().astimezone()`). Never assume UTC or machine-independent dates for day boundaries.

---

## 2. Supported Workstation Temporal Anchors

| Temporal Phrase | Canonical Value | Relation Type | Resolved Range ($[start\_ts, end\_ts]$) |
| :--- | :--- | :--- | :--- |
| **yesterday** | `yesterday` | `during` | Local 00:00:00 to 23:59:59 of day $(D - 1)$ |
| **today** | `today` | `during` | Local 00:00:00 to 23:59:59 of day $D$ |
| **last night** | `last_night` | `during` | Day $(D - 1)$ 18:00:00 to Day $D$ 06:00:00 |
| **just now** | `just_now` | `during` | $[T - 15\text{ minutes}, T]$ |
| **recent / recently** | `recent` | `during` | $[T - 4\text{ hours}, T]$ |
| **most recent / latest**| `most_recent`| `exact` | Immediate predecessor point-in-time |
| **previous project** | `previous` | `exact` | Immediate predecessor in `RecentProjectsManager` |

---

## 3. Integration with Context Engine

1. **NLP Layer**: Identifies the presence of the temporal phrase (e.g. `"yesterday"`) and calculates the exact UTC/local Unix epoch timestamp bounds `(start_ts, end_ts)`.
2. **Context Engine**: Uses `(start_ts, end_ts)` to filter historical `RecentProjectRecord.last_interacted` or `RecentAction.timestamp` in `data/context_state.json`.
3. **Deterministic Binding**: The matched project ID is returned and verified against `ProjectRegistry`.
