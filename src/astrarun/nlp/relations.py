"""Relation extraction between entities and clauses.

Extracts typed directed relations such as:
- PROCESS - LISTENS_ON -> PORT
- PROJECT - OPEN_WITH -> APPLICATION
- FOLDER - CONTAINS -> FILE
"""

from __future__ import annotations

import re
from typing import Any
from astrarun.nlp.models import NLPEntity, NLPEntityType, Relation, RelationType


def extract_relations(
    text: str,
    entities: list[NLPEntity],
    clauses: list[Any] | None = None
) -> list[Relation]:
    """Extract semantic relationships between extracted entities."""
    relations: list[Relation] = []

    # Map entities by type
    ports = [e for e in entities if e.type == NLPEntityType.PORT]
    pids = [e for e in entities if e.type == NLPEntityType.PROCESS]
    projects = [e for e in entities if e.type == NLPEntityType.PROJECT]
    apps = [e for e in entities if e.type == NLPEntityType.APPLICATION]
    files = [e for e in entities if e.type == NLPEntityType.FILE]
    folders = [e for e in entities if e.type == NLPEntityType.FOLDER]

    # 1. Relation: PROCESS -> LISTENS_ON -> PORT
    # e.g. "process using port 3000", "what's on port 5173", "pid 123 on port 8080"
    for port in ports:
        if pids:
            for pid in pids:
                relations.append(Relation(
                    type=RelationType.LISTENS_ON,
                    source_entity=f"process:{pid.normalized}",
                    target_entity=f"port:{port.normalized}",
                    confidence=0.98,
                    source="relation_process_port",
                ))
        elif re.search(r'\b(?:process|service|app)\b', text, re.I):
            relations.append(Relation(
                type=RelationType.LISTENS_ON,
                source_entity="process:unknown",
                target_entity=f"port:{port.normalized}",
                confidence=0.92,
                source="relation_process_port_cue",
            ))

    # 2. Relation: PROJECT -> OPEN_WITH -> APPLICATION
    # e.g. "open AstraRun in vscode", "AstraRun in vs code"
    for proj in projects:
        for app in apps:
            # Check if there is an "in" or "with" preposition
            pattern = rf'{re.escape(proj.text)}\s+(?:in|with|using)\s+{re.escape(app.text)}'
            if re.search(pattern, text, re.I) or (proj.start < app.start):
                relations.append(Relation(
                    type=RelationType.OPEN_WITH,
                    source_entity=f"project:{proj.normalized}",
                    target_entity=f"application:{app.normalized}",
                    confidence=0.98,
                    source="relation_project_app",
                ))

    # 3. Relation: FOLDER -> CONTAINS -> FILE
    for folder in folders:
        for f in files:
            relations.append(Relation(
                type=RelationType.CONTAINS,
                source_entity=f"folder:{folder.normalized}",
                target_entity=f"file:{f.normalized}",
                confidence=0.90,
                source="relation_folder_file",
            ))

    return relations
