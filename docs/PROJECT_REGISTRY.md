# Project Registry Specification (AstraRun v0.6)

> **Status**: PRODUCTION READY  
> **Package**: `astrarun.projects.registry`  
> **Last Verified**: 2026-09-27  

---

## 1. Overview & Operating Invariants

The **Project Registry** serves as the canonical project abstraction layer for AstraRun across the entire `E:\Workspace\` engineering platform. It exposes typed metadata, fuzzy matching, and path resolution over all workstation projects.

### Mandatory Platform Invariants
1. **Strict Read-Only Access (Platform Rule 10 & 11)**: The Project Registry NEVER writes to, mutates, or reformats `E:\Workspace\workspace.json`. All operations are read-only.
2. **Canonical Project Identifiers**: Project IDs are preserved exactly as defined in `workspace.json` (e.g. `"astrarun"`, `"ai-bridge"`, `"vivaldi-ai"`, `"security-workbench"`, `"server-nexusnode"`).
3. **Dynamic Discovery Fallback**: If a project directory exists under `Active/`, `Tools/`, or `Shared/` that is not yet listed in `workspace.json`, the registry dynamically discovers it with valid default metadata while leaving the catalog file intact.
4. **Portability & Path Resolution**: Paths are stored as normalized relative paths (e.g. `"Active/AstraRun"`) and resolved dynamically against the host workspace root.

---

## 2. Component Architecture

```
                    ┌─────────────────────────────────┐
                    │    E:\Workspace\workspace.json  │
                    │        (28 Cataloged Projects)  │
                    └────────────────┬────────────────┘
                                     │ Read-Only
                                     ▼
     ┌──────────────────────────────────────────────────────────────┐
     │                       ProjectRegistry                        │
     │                                                              │
     │  ┌───────────────────────┐   ┌────────────────────────────┐  │
     │  │ Exact ID & Path Lookup│   │    Fuzzy & Alias Matcher   │  │
     │  │  - get_project(id)    │   │    - find_project(query)   │  │
     │  │  - project_path(id)   │   │    - Aliases, tags, names  │  │
     │  └───────────────────────┘   └────────────────────────────┘  │
     │                                                              │
     │  ┌────────────────────────────────────────────────────────┐  │
     │  │               Dynamic Filesystem Discovery             │  │
     │  │   Scans E:\Workspace\Active\* for unlisted projects    │  │
     │  └────────────────────────────────────────────────────────┘  │
     └───────────────────────────────┬──────────────────────────────┘
                                     │
                                     ▼
                    ┌─────────────────────────────────┐
                    │         ProjectMetadata         │
                    │  (id, name, path, quick, tags)  │
                    └─────────────────────────────────┘
```

---

## 3. Data Models (`astrarun.projects.registry`)

### `ProjectMetadata`
```python
@dataclass
class ProjectMetadata:
    id: str                            # Unique catalog ID (e.g. "astrarun")
    name: str                          # Human-readable title (e.g. "AstraRun")
    relative_path: str                 # Relative path from workspace root (e.g. "Active/AstraRun")
    absolute_path: Path                # Resolved host filesystem path
    category: str                      # Workspace category ("active", "tools", "shared")
    status: str                        # Lifecycle status ("production", "active", "prototype")
    languages: list[str]               # Primary languages (["python", "typescript"])
    frameworks: list[str]              # Frameworks (["pyside6", "torch", "laya"])
    commands: dict[str, str]           # Registered commands ({"test": "pytest", "run": "python -m astrarun"})
    tags: list[str]                    # Semantic categorization tags
    quick: bool = False                # Priority project for launcher quick-actions
    aliases: list[str]                 # Recognized natural language synonyms
```

---

## 4. Public API Methods

| Method | Parameters | Returns | Description |
| :--- | :--- | :--- | :--- |
| `get_project` | `project_id: str` | `Optional[ProjectMetadata]` | Exact lookup by project ID or canonical alias. Returns `None` if unknown. |
| `find_project` | `query: str, threshold: float = 0.60` | `list[tuple[ProjectMetadata, float]]` | Ranked fuzzy search over IDs, names, aliases, and tags. |
| `project_path` | `project_id: str` | `Optional[Path]` | Resolves the absolute filesystem path for the project directory. |
| `project_metadata` | `project_id: str` | `Optional[dict[str, Any]]` | Returns raw dictionary representation for logging or telemetry. |
| `list_projects` | `category: Optional[str] = None` | `list[ProjectMetadata]` | Returns all registered projects, optionally filtered by category. |

---

## 5. Alias & Fuzzy Resolution Hierarchy

When a user submits a natural language project request (e.g. `"open Vivaldi AI in code"`, `"vscode for AI Bridge"`, `"explore Security Workbench"`), `ProjectRegistry.find_project` ranks candidates through a tiered scoring function:
1. **Exact ID Match**: Score `1.0` (e.g. query `"astrarun"` matches id `"astrarun"`).
2. **Exact Alias / Name Match**: Score `1.0` (e.g. query `"server"` matches alias `"server"` for project `"server-nexusnode"`).
3. **Prefix / Suffix Match**: Score `0.90` (e.g. query `"security"` matches `"security-workbench"`).
4. **Token Overlap**: Score `0.80` (e.g. query `"nexus"` matches `"server-nexusnode"`).
5. **Subsequence / Fuzzy Match**: Score `0.60..0.79` (character ngram alignment).

---

## 6. Verification & Test Evidence

Verified in `tests/test_v06_actions.py`:
- `test_project_registry_loading`: Validates successful ingestion of `workspace.json` projects.
- `test_project_registry_exact_and_fuzzy_search`: Validates exact lookup, path resolution, and fuzzy matching for `astrarun` and `server`.
- `test_project_registry_unknown_returns_none`: Confirms unknown queries safely return `None` without exceptions.
