# 22 — Workstation Memory & Procedural Skill Storage

> **Status**: PROVISIONAL SPECIFICATION  
> **Phase**: 11 — Memory Architecture, Context Management & Skill Persistence  
> **Focus**: Four-Tier Workstation Memory (Working, Episodic, Semantic, Procedural), Progressive Compaction, and SQLite FTS5  
> **Target System**: Local Windows 11 Workstation (`E:\Workspace\Active\AstraRun`)  

---

## 1. Executive Summary & The Four-Tier Memory Model

Autonomous workstation agents fail when they rely exclusively on unbounded LLM context windows or treat all memory as a flat vector blob. AstraRun establishes a rigorous **Four-Tier Workstation Memory Architecture**:

```mermaid
flowchart TD
    User[User Instruction / Goal] --> MemoryMgr[Astra Memory Manager]

    subgraph Tier 1: Working Memory (RAM - Ephemeral)
        WM[Active Task State\nLive Step DAG & Variable Bindings\nRing Buffer of Current Observations\nPurged on Task Completion]
    end

    subgraph Tier 2: Episodic Memory (Local Disk - Session History)
        EM[Local Task Trajectories & Observations\nStored in SQLite .astrarun/history.db\nProgressively Compacted Over Time\nZero User Friction to Retain]
    end

    subgraph Tier 3: Semantic Memory (Local Disk - Durable Facts)
        SM[Workstation Entities & Machine Profile\nUser Preferences & Tool Aliases\nProject Registry from workspace.json\nIndexed via SQLite FTS5]
    end

    subgraph Tier 4: Procedural Memory (Filesystem - Reusable Skills)
        PM[Validated Reusable Skills\nSKILL.md + run.py\nDeterministic Fast-Path Execution]
    end

    MemoryMgr <--> WM
    MemoryMgr <--> EM
    MemoryMgr <--> SM
    MemoryMgr <--> PM
```

---

## 2. Memory Tier Specifications

| Memory Tier | Storage Medium | Scope & Lifetime | Retention & Compaction Policy | Secret Policy | Evidence Tag |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1: Working Memory** | Process RAM (Ring Buffer) | Active task execution only; purged immediately when task completes. | Ephemeral; fixed head/tail observation windowing. | Secrets strictly masked via opaque handles. | `TARGET` |
| **Tier 2: Episodic Memory** | SQLite (`.astrarun/history.db`) | Recent multi-turn trajectories, actions, tool outputs, and verifications. | **Retained automatically** without per-task user confirmation. Progressively compacted over time (summaries after 7 days, raw logs pruned). | **Secrets 100% excluded** before write. | `TARGET` |
| **Tier 3: Semantic Memory** | SQLite (`.astrarun/memory.db`) | Durable workstation facts, user preferences, aliases, and project paths. | Long-term durable storage; indexed via SQLite FTS5; human-auditable and editable. | Secrets strictly prohibited; credentials live only in Windows Credential Manager. | `TARGET` |
| **Tier 4: Procedural Memory** | Filesystem (`.skills/`) | Validated, reusable parameterized skill bundles. | Promoted from successful trajectories after verification; stored as plain text markdown + Python scripts. | Never contains hardcoded secrets or environment variables. | `TARGET` |

---

## 3. Tier 1: Working Memory & Active Windowing

During active goal execution, working memory maintains the live execution state:
1. **DAG Graph State**: Node statuses (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`), dataflow edges, and variable bindings.
2. **Streaming Ring Buffer**: In-flight stdout/stderr buffers capped at 64 KB per step.
3. **Head/Tail Summarization**: Truncates massive compiler logs before feeding model context, guaranteeing input payloads stay within calculated token ceilings `[TARGET]`.

---

## 4. Tier 2: Episodic Memory & Progressive Compaction

Unlike prior drafts that mistakenly required user confirmation to retain basic task logs, **Episodic Memory is retained locally and automatically**:
1. **Automatic Ingestion**: Every completed or failed task run writes an episodic record:
   - User goal text.
   - Capability sequence executed.
   - Exit codes and observation summaries.
   - User feedback or corrections if provided.
2. **Progressive Compaction**:
   - **Days 1–7**: Full structured turn-by-turn trace retained for immediate recall and replay.
   - **Days 8–30**: Detailed stdout/stderr pruned; semantic summary and capability sequence retained.
   - **Day 30+**: High-level task outcome vector retained; stale execution artifacts purged.
3. **Zero Secret Leakage**: The real-time Aho-Corasick stream scrubber masks any registered secret pattern *before* episodic database writes occur.

---

## 5. Tier 3: Semantic Memory (SQLite FTS5)

Persistent workstation knowledge is stored in a clean SQLite database:

```sql
CREATE TABLE IF NOT EXISTS workstation_entities (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,         -- 'project', 'hardware', 'preference', 'alias'
    key TEXT NOT NULL,              -- 'E:/Workspace/Active/AstraRun'
    content TEXT NOT NULL,          -- JSON blob of entity attributes
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS workstation_entities_fts USING fts5(
    key,
    content,
    content='workstation_entities',
    content_rowid='rowid'
);
```

- **Retrieval**: Sub-millisecond exact keyword matching via SQLite FTS5 for file paths, project IDs, and CLI arguments `[TARGET]`.

---

## 6. Tier 4: Procedural Skill Memory

Procedural memory stores compiled skills ready for fast-path execution under `.skills/<skill_name>/`:
- `SKILL.md`: Frontmatter schema (name, description, inputs, outputs, safety tier) and execution instructions.
- `run.py`: Deterministic entrypoint script.
- `test_smoke.py`: Self-contained verification harness.

---

## 7. Memory Invariants

1. **Four-Way Separation**: Working, Episodic, Semantic, and Procedural tiers must remain architecturally distinct.
2. **Automatic Local Episodic History**: Normal episodic logging does not require per-task user approval.
3. **Zero-Secret Exclusion**: Plaintext secrets are strictly barred from all four memory tiers.
