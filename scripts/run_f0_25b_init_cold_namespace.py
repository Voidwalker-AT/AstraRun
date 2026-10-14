"""F0-25B Fresh Hermes Namespace Initializer & Auditor.

Creates a dedicated, clean Hermes namespace profile for F0-25B Notepad++ learning:
%LOCALAPPDATA%\\AstraRun\\data\\hermes\\f025b_notepadpp_learning.db

Verifies:
- Notepad++ procedural affordances = 0
- Notepad++ action transitions = 0
- Notepad++ shortcuts = 0
- Notepad++ experiment history = 0
- Populates generic ontology concepts (WINDOW, MENU, BUTTON, EDITABLE_SURFACE, TAB, DOCUMENT, etc.)
  without any application-specific procedural instructions.
Emits docs/audit/F0_25B_COLD_NAMESPACE.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from astrarun.core.paths import AstraPaths
from astrarun.hermes.models import (
    EntityNode,
    EntityType,
)
from astrarun.hermes.provenance import HermesProvenance
from astrarun.hermes.store import HermesKnowledgeStore

GENERIC_CONCEPTS = [
    "WINDOW",
    "MENU",
    "BUTTON",
    "EDITABLE_SURFACE",
    "TAB",
    "DOCUMENT",
    "DIALOG",
    "FILE",
    "TEXT",
    "FOCUS",
    "SAVE",
    "SEARCH",
    "SCROLL",
    "SELECTION",
]


def init_cold_namespace() -> dict:
    db_path = AstraPaths.data_dir() / "hermes" / "f025b_notepadpp_learning.db"
    # Ensure fresh state
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass

    store = HermesKnowledgeStore(db_path=db_path)
    env_hash = HermesProvenance.compute_env_hash()

    # Seed generic concepts
    for concept in GENERIC_CONCEPTS:
        ent = EntityNode.create(
            entity_type=EntityType.CONTROL if concept in ("BUTTON", "EDITABLE_SURFACE", "TAB", "MENU") else EntityType.WINDOW,
            name=concept,
            env_hash=env_hash,
            metadata={"ontology": "generic_gui_primitive", "domain": "cross_application"},
        )
        store.upsert_entity(ent)

    # Audit namespace for any Notepad++ knowledge
    npp_entity = store.find_entity_by_name("Notepad++")
    npp_affordances = []
    npp_transitions = []
    npp_experiments = []
    npp_shortcuts = []

    if npp_entity:
        npp_affordances = store.list_affordances(npp_entity.entity_id)
        npp_transitions = store.list_transitions(npp_entity.entity_id)

    # Search FTS or affordances for any shortcuts
    with store._get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM hermes_affordances WHERE action_name LIKE '%Ctrl+%' OR capability_id LIKE '%notepad%'")
        rows = cur.fetchall()
        for r in rows:
            npp_shortcuts.append(dict(r))

        cur.execute("SELECT COUNT(*) FROM hermes_experiments")
        total_experiments = cur.fetchone()[0]

    all_entities = store.list_entities()

    evidence = {
        "phase": "F0-25B",
        "title": "Fresh Hermes Namespace Initialization & Zero-Contamination Audit",
        "timestamp": time.time(),
        "namespace_profile": "f025b_notepadpp_learning",
        "db_path": str(db_path),
        "db_size_bytes": db_path.stat().st_size if db_path.exists() else 0,
        "generic_concepts_loaded": GENERIC_CONCEPTS,
        "generic_concepts_count": len(all_entities),
        "notepadpp_audit": {
            "target_entity_exists": npp_entity is not None,
            "notepadpp_procedural_affordances": len(npp_affordances),
            "notepadpp_action_transitions": len(npp_transitions),
            "notepadpp_shortcuts": len(npp_shortcuts),
            "notepadpp_experiment_history": total_experiments,
            "procedural_knowledge_is_zero": (
                len(npp_affordances) == 0
                and len(npp_transitions) == 0
                and len(npp_shortcuts) == 0
                and total_experiments == 0
            ),
        },
        "cold_namespace_status": "PASS" if (
            len(npp_affordances) == 0
            and len(npp_transitions) == 0
            and len(npp_shortcuts) == 0
            and total_experiments == 0
            and len(all_entities) == len(GENERIC_CONCEPTS)
        ) else "FAIL",
    }

    out_file = ROOT / "docs" / "audit" / "F0_25B_COLD_NAMESPACE.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)

    print(f"Cold namespace status: {evidence['cold_namespace_status']}")
    print(f"Generic concepts seeded: {len(all_entities)}")
    print(f"Notepad++ affordances: {len(npp_affordances)}, shortcuts: {len(npp_shortcuts)}, experiments: {total_experiments}")
    print(f"Wrote {out_file}")
    return evidence


if __name__ == "__main__":
    init_cold_namespace()
