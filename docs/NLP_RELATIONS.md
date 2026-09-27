# AstraRun v0.6.5 — Semantic Relation Extraction

> **Status**: APPROVED  
> **Milestone**: AstraRun v0.6.5  
> **Source Module**: `src/astrarun/nlp/relations.py`  

---

## 1. Supported Relation Types

AstraRun's relation extractor connects entities and actions into a directed semantic graph:

```text
       ┌───────────┐         LISTENS_ON         ┌──────────┐
       │  PROCESS  │ ─────────────────────────> │   PORT   │
       └───────────┘                            └──────────┘
             │
             │ OPERATES_ON
             ▼
       ┌───────────┐          OPEN_WITH         ┌──────────┐
       │  PROJECT  │ ─────────────────────────> │   APP    │
       └───────────┘                            └──────────┘
```

| Relation Type | Source Entity | Target Entity | Trigger Syntax | Example |
| :--- | :--- | :--- | :--- | :--- |
| `LISTENS_ON` | `PROCESS` | `PORT` | `using port`, `on port`, `listen on` | `process using port 3000` |
| `OPEN_WITH` | `PROJECT` / `FILE` | `APPLICATION` | `in <app>`, `with <app>`, `using <app>` | `open AstraRun in vscode` |
| `CONTAINS` | `FOLDER` | `FILE` | `<file> in <folder>` | `newest pdf in downloads` |
| `OPERATES_ON`| `ACTION` | `ENTITY` | Transitive verbs (`open`, `kill`) | `terminate process 14236` |
| `FOLLOWS` | `CLAUSE` | `CLAUSE` | `then`, `after that`, `before` | `Clause 0 then Clause 1` |
| `REFERENCES` | `CONTEXT_REF` | `ENTITY` | Anaphoric resolution (`it`, `that`) | `it -> PID 14236` |

---

## 2. Extraction Mechanics

Relations are extracted after deterministic entities and clauses are resolved.
- For `OPEN_WITH`: Evaluates prepositions (`in`, `with`, `using`) connecting a project or file entity to an application entity.
- For `LISTENS_ON`: Associates listening sockets with explicit PIDs or general process cues.
- For `CONTAINS`: Binds file extensions or file names to parent folder paths.

All relations preserve source confidence scores and are stored in `StructuredUtterance.relations`.
