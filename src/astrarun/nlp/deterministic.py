"""Deterministic entity extractors for high-certainty workstation structures.

Extracts ports, PIDs, URLs, Windows paths, file extensions, percentages,
known project IDs from ProjectRegistry, and application aliases from the index.
All extractions preserve character start/end spans and return typed NLPEntity objects.
"""

from __future__ import annotations

import re
from typing import Any
from astrarun.nlp.models import NLPEntity, NLPEntityType

# Pre-compiled high-certainty regular expressions
_RE_URL = re.compile(
    r'(?i)\b(?:https?://|www\.)[a-z0-9\.\-_~:/?#\[\]@!$&\'()*+,;=%]+',
    re.UNICODE
)

_RE_WIN_PATH = re.compile(
    r'(?i)\b[a-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*',
    re.UNICODE
)

_RE_PORT = re.compile(
    r'(?i)(?:\bport(?:\s+number)?\s*[:#]?\s*|(?<=localhost:)|(?<=127\.0\.0\.1:)|(?<=\s:))(\d{2,5})\b',
    re.UNICODE
)

_RE_STANDALONE_COLON_PORT = re.compile(
    r'(?<![a-zA-Z0-9]):(\d{2,5})\b',
    re.UNICODE
)

_RE_PID = re.compile(
    r'(?i)\b(?:pid|process(?:\s+id)?)\s*[:#]?\s*(\d{1,6})\b',
    re.UNICODE
)

_RE_PERCENTAGE = re.compile(
    r'\b(\d+(?:\.\d+)?)\s*%',
    re.UNICODE
)

_RE_FILE_EXT = re.compile(
    r'(?i)\b\.([a-z0-9]{1,5})\b|\b([a-z0-9_-]+\.(?:pdf|py|cpp|c|h|java|ts|js|jsx|tsx|json|md|txt|docx|xlsx|png|jpg|exe|bat|ps1))\b',
    re.UNICODE
)

# Canonical Application Aliases Dictionary
DEFAULT_APP_ALIASES: dict[str, str] = {
    "vscode": "vscode",
    "vs code": "vscode",
    "code": "vscode",
    "visual studio code": "vscode",
    "terminal": "terminal",
    "wt": "terminal",
    "windows terminal": "terminal",
    "powershell": "powershell",
    "pwsh": "powershell",
    "cmd": "cmd",
    "prompt": "cmd",
    "command prompt": "cmd",
    "explorer": "explorer",
    "file explorer": "explorer",
    "files": "explorer",
    "chrome": "chrome",
    "google chrome": "chrome",
    "vivaldi": "vivaldi",
    "notepad": "notepad",
    "calc": "calculator",
    "calculator": "calculator",
    "taskmgr": "taskmanager",
    "task manager": "taskmanager",
    "git": "git",
    "edge": "edge",
    "msedge": "edge",
}


def extract_urls(text: str) -> list[NLPEntity]:
    """Extract HTTP/HTTPS URLs with exact spans."""
    entities: list[NLPEntity] = []
    for m in _RE_URL.finditer(text):
        entities.append(NLPEntity(
            type=NLPEntityType.URL,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            normalized=m.group(0),
            source="deterministic_url",
            confidence=1.0,
        ))
    return entities


def extract_windows_paths(text: str) -> list[NLPEntity]:
    """Extract absolute Windows filesystem paths."""
    entities: list[NLPEntity] = []
    for m in _RE_WIN_PATH.finditer(text):
        path_str = m.group(0).rstrip(".,;")
        entities.append(NLPEntity(
            type=NLPEntityType.FOLDER if not re.search(r'\.[a-zA-Z0-9]+$', path_str) else NLPEntityType.FILE,
            text=path_str,
            start=m.start(),
            end=m.start() + len(path_str),
            normalized=path_str,
            source="deterministic_path",
            confidence=1.0,
        ))
    return entities


def extract_ports(text: str, excluded_spans: list[tuple[int, int]] | None = None) -> list[NLPEntity]:
    """Extract TCP port numbers (e.g. 'port 3000', ':5173', 'port:8080')."""
    entities: list[NLPEntity] = []
    excluded = excluded_spans or []

    def _is_excluded(s: int, e: int) -> bool:
        return any(ex_s <= s and e <= ex_e for ex_s, ex_e in excluded)

    for m in _RE_PORT.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        try:
            port_val = int(m.group(1))
            if 1 <= port_val <= 65535:
                entities.append(NLPEntity(
                    type=NLPEntityType.PORT,
                    text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                    normalized=port_val,
                    source="deterministic_port",
                    confidence=1.0,
                ))
        except ValueError:
            pass

    for m in _RE_STANDALONE_COLON_PORT.finditer(text):
        if _is_excluded(m.start(), m.end()):
            continue
        # Avoid duplicate if already covered
        if any(e.start <= m.start() and m.end() <= e.end for e in entities):
            continue
        try:
            port_val = int(m.group(1))
            if 1 <= port_val <= 65535:
                entities.append(NLPEntity(
                    type=NLPEntityType.PORT,
                    text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                    normalized=port_val,
                    source="deterministic_port",
                    confidence=1.0,
                ))
        except ValueError:
            pass

    return entities


def extract_pids(text: str, excluded_spans: list[tuple[int, int]] | None = None) -> list[NLPEntity]:
    """Extract explicit process identifiers (PID 14236, process 14236)."""
    entities: list[NLPEntity] = []
    excluded = excluded_spans or []

    for m in _RE_PID.finditer(text):
        s, e = m.start(), m.end()
        if any(ex_s <= s and e <= ex_e for ex_s, ex_e in excluded):
            continue
        try:
            pid_val = int(m.group(1))
            entities.append(NLPEntity(
                type=NLPEntityType.PROCESS,
                text=m.group(0),
                start=s,
                end=e,
                normalized=pid_val,
                source="deterministic_pid",
                confidence=1.0,
            ))
        except ValueError:
            pass
    return entities


def extract_percentages(text: str) -> list[NLPEntity]:
    """Extract percentages (e.g. 50%, 100%)."""
    entities: list[NLPEntity] = []
    for m in _RE_PERCENTAGE.finditer(text):
        try:
            val = float(m.group(1))
            entities.append(NLPEntity(
                type=NLPEntityType.PERCENTAGE,
                text=m.group(0),
                start=m.start(),
                end=m.end(),
                normalized=val,
                source="deterministic_percentage",
                confidence=1.0,
            ))
        except ValueError:
            pass
    return entities


def extract_file_extensions(text: str) -> list[NLPEntity]:
    """Extract file extensions and file references."""
    entities: list[NLPEntity] = []
    for m in _RE_FILE_EXT.finditer(text):
        ext_group = m.group(1) or m.group(2)
        if not ext_group:
            continue
        normalized_ext = "." + ext_group if not ext_group.startswith(".") else ext_group
        if "." in ext_group and not ext_group.startswith("."):
            normalized_ext = "." + ext_group.split(".")[-1]
        entities.append(NLPEntity(
            type=NLPEntityType.FILE,
            text=m.group(0),
            start=m.start(),
            end=m.end(),
            normalized=normalized_ext.lower(),
            source="deterministic_file_ext",
            confidence=0.95,
        ))
    return entities


def extract_applications(text: str, app_aliases: dict[str, str] | None = None) -> list[NLPEntity]:
    """Extract known application entities using word boundary alias matching."""
    aliases = app_aliases or DEFAULT_APP_ALIASES
    entities: list[NLPEntity] = []
    # Sort aliases longest first for greedy matching
    sorted_aliases = sorted(aliases.items(), key=lambda kv: len(kv[0]), reverse=True)

    text_lower = text.lower()
    occupied_spans: list[tuple[int, int]] = []

    for alias, canonical in sorted_aliases:
        pattern = r'\b' + re.escape(alias) + r'\b'
        for m in re.finditer(pattern, text_lower):
            s, e = m.start(), m.end()
            if any(occ_s <= s and e <= occ_e for occ_s, occ_e in occupied_spans):
                continue
            entities.append(NLPEntity(
                type=NLPEntityType.APPLICATION,
                text=text[s:e],
                start=s,
                end=e,
                normalized=canonical,
                source="app_index_alias",
                confidence=1.0,
            ))
            occupied_spans.append((s, e))

    return entities


def extract_projects(
    text: str,
    project_registry: Any = None,
    excluded_spans: list[tuple[int, int]] | None = None
) -> list[NLPEntity]:
    """Extract known project references against ProjectRegistry."""
    entities: list[NLPEntity] = []
    if project_registry is None:
        try:
            from astrarun.projects import get_project_registry
            project_registry = get_project_registry()
        except Exception:
            return entities

    text_lower = text.lower()
    occupied = list(excluded_spans or [])

    # Check each project in registry
    all_projects = project_registry.list_projects()
    # Sort by display name / id length reverse for greedy match
    candidates: list[tuple[str, str]] = [] # (match_str, project_id)
    for p in all_projects:
        candidates.append((p.id.lower(), p.id))
        candidates.append((p.name.lower(), p.id))
        # Handle prefixes e.g. "tools-pdfcraft" -> "pdfcraft"
        if "-" in p.id:
            short_id = p.id.split("-", 1)[1].lower()
            candidates.append((short_id, p.id))

    # Deduplicate candidate strings
    candidates = sorted(list({c[0]: c[1] for c in candidates}.items()), key=lambda c: len(c[0]), reverse=True)

    for term, proj_id in candidates:
        if len(term) < 3:
            continue
        pattern = r'\b' + re.escape(term) + r'\b'
        for m in re.finditer(pattern, text_lower):
            s, e = m.start(), m.end()
            if any(occ_s <= s and e <= occ_e for occ_s, occ_e in occupied):
                continue
            entities.append(NLPEntity(
                type=NLPEntityType.PROJECT,
                text=text[s:e],
                start=s,
                end=e,
                normalized=proj_id,
                source="project_registry_exact",
                confidence=1.0,
            ))
            occupied.append((s, e))

    return entities


def extract_all_deterministic(
    text: str,
    project_registry: Any = None,
    app_aliases: dict[str, str] | None = None
) -> list[NLPEntity]:
    """Extract all deterministic entities with non-overlapping precedence.
    
    Precedence order:
    1. URLs
    2. Windows Paths
    3. Ports & PIDs
    4. Projects
    5. Applications
    6. File Extensions & Percentages
    """
    all_entities: list[NLPEntity] = []
    occupied_spans: list[tuple[int, int]] = []

    def _add_non_overlapping(ents: list[NLPEntity]):
        for ent in ents:
            if not any(occ_s <= ent.start and ent.end <= occ_e for occ_s, occ_e in occupied_spans):
                all_entities.append(ent)
                occupied_spans.append((ent.start, ent.end))

    # 1. URLs
    urls = extract_urls(text)
    _add_non_overlapping(urls)

    # 2. Windows paths
    paths = extract_windows_paths(text)
    _add_non_overlapping(paths)

    # 3. Ports & PIDs
    ports = extract_ports(text, occupied_spans)
    _add_non_overlapping(ports)

    pids = extract_pids(text, occupied_spans)
    _add_non_overlapping(pids)

    # 4. Projects (Higher priority than general apps e.g. "AstraRun" won't collide)
    projs = extract_projects(text, project_registry, occupied_spans)
    _add_non_overlapping(projs)

    # 5. Applications
    apps = extract_applications(text, app_aliases)
    _add_non_overlapping(apps)

    # 6. File extensions & percentages
    exts = extract_file_extensions(text)
    _add_non_overlapping(exts)

    pcts = extract_percentages(text)
    _add_non_overlapping(pcts)

    # Sort entities by start offset
    all_entities.sort(key=lambda e: e.start)
    return all_entities
