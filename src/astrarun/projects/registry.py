"""Project Registry for AstraRun v0.6.

Provides a clean, read-only abstraction over the workstation project catalog
defined in E:\\Workspace\\workspace.json and integrated with wsctl.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.projects.registry")


@dataclass
class ProjectMetadata:
    """Strongly-typed metadata for a cataloged workspace project."""
    id: str
    name: str
    relative_path: str
    absolute_path: Path
    category: str = "active"
    status: str = "active"
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    commands: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    quick: bool = False
    aliases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert project metadata to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "relative_path": self.relative_path,
            "absolute_path": str(self.absolute_path),
            "category": self.category,
            "status": self.status,
            "languages": self.languages,
            "frameworks": self.frameworks,
            "commands": self.commands,
            "tags": self.tags,
            "quick": self.quick,
            "aliases": self.aliases,
        }


class ProjectRegistry:
    """
    Read-only registry of all engineering projects across the workstation.
    Ground truth is loaded from workspace.json and supplemented by active directory discovery.
    """

    def __init__(
        self,
        workspace_root: Path | str = r"E:\Workspace",
        workspace_json_path: Path | str = r"E:\Workspace\workspace.json",
    ) -> None:
        p_root = Path(workspace_root)
        if not p_root.is_absolute() and (p_root.name.endswith(".json") or p_root.suffix == ".json"):
            canonical_json = Path(r"E:\Workspace\workspace.json")
            if canonical_json.exists():
                self.workspace_json_path = canonical_json
                self.workspace_root = Path(r"E:\Workspace")
            else:
                self.workspace_json_path = p_root.resolve()
                self.workspace_root = self.workspace_json_path.parent
        elif p_root.name.endswith(".json") or p_root.suffix == ".json":
            self.workspace_json_path = p_root.resolve()
            parent = p_root.resolve().parent
            self.workspace_root = parent if (parent / "Active").exists() or parent.name == "Workspace" else Path(r"E:\Workspace")
        else:
            self.workspace_root = Path(workspace_root).resolve()
            self.workspace_json_path = Path(workspace_json_path).resolve()
        self._projects: dict[str, ProjectMetadata] = {}
        self._alias_map: dict[str, str] = {}
        self._load()

    def _normalize_key(self, text: str) -> str:
        """Normalize identifier for lookup."""
        return re.sub(r"[^a-z0-9]", "", text.lower())

    def _load(self) -> None:
        """Load project definitions from workspace.json without mutating it."""
        self._projects.clear()
        self._alias_map.clear()

        if self.workspace_json_path.exists():
            try:
                with open(self.workspace_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                raw_projects = data.get("projects", [])
                for p in raw_projects:
                    pid = p.get("id")
                    if not pid:
                        continue
                    
                    rel_path = p.get("path", "")
                    abs_path = (self.workspace_root / rel_path).resolve()

                    name = p.get("name", pid)
                    aliases = [
                        pid,
                        name,
                        pid.replace("-", " "),
                        pid.replace("-", ""),
                        name.lower(),
                    ]
                    # Specific known project aliases
                    if "server" in pid:
                        aliases.extend(["server", "nexusnode", "nexus"])
                    if "security" in pid:
                        aliases.extend(["security workbench", "securityworkbench"])
                    if "vivaldi" in pid:
                        aliases.extend(["vivaldi", "vivaldi ai", "vivaldiai"])
                    if "bridge" in pid:
                        aliases.extend(["ai bridge", "aibridge", "bridge"])
                    if "nfc" in pid:
                        aliases.extend(["aegic nfc", "aegic", "nfc"])

                    meta = ProjectMetadata(
                        id=pid,
                        name=name,
                        relative_path=rel_path,
                        absolute_path=abs_path,
                        category=p.get("category", "active"),
                        status=p.get("status", "active"),
                        languages=p.get("languages", []),
                        frameworks=p.get("frameworks", []),
                        commands=p.get("commands", {}),
                        tags=p.get("tags", []),
                        quick=p.get("quick", False),
                        aliases=list(set(aliases)),
                    )
                    self._projects[pid] = meta
                    for a in meta.aliases:
                        self._alias_map[self._normalize_key(a)] = pid
                logger.info("Loaded %d cataloged projects from %s", len(self._projects), self.workspace_json_path)
            except Exception as err:
                logger.error("Failed to load %s: %s", self.workspace_json_path, err)

        # Supplement with AstraRun if not explicitly in workspace.json
        if "astrarun" not in self._projects:
            astrarun_rel = "Active/AstraRun"
            astrarun_abs = (self.workspace_root / astrarun_rel).resolve()
            if astrarun_abs.exists():
                meta = ProjectMetadata(
                    id="astrarun",
                    name="AstraRun",
                    relative_path=astrarun_rel,
                    absolute_path=astrarun_abs,
                    category="active",
                    status="active",
                    languages=["python"],
                    frameworks=["pyside6", "onnxruntime", "pytorch"],
                    commands={"test": ".venv\\Scripts\\pytest", "run": ".venv\\Scripts\\python src/astrarun/main.py"},
                    tags=["launcher", "desktop", "workstation", "router"],
                    quick=True,
                    aliases=["astrarun", "astra run", "astra", "launcher"],
                )
                self._projects["astrarun"] = meta
                for a in meta.aliases:
                    self._alias_map[self._normalize_key(a)] = "astrarun"

    def get_project(self, project_id: str) -> Optional[ProjectMetadata]:
        """Look up project by exact ID or alias."""
        if not project_id:
            return None
        
        # Direct key lookup
        clean_id = project_id.strip().lower()
        if clean_id in self._projects:
            return self._projects[clean_id]
        
        # Normalized alias lookup
        norm = self._normalize_key(clean_id)
        if norm in self._alias_map:
            target_id = self._alias_map[norm]
            return self._projects.get(target_id)
        
        # Hyphen/underscore replacement
        hyphenated = clean_id.replace("_", "-")
        if hyphenated in self._projects:
            return self._projects[hyphenated]

        return None

    def find_project(self, query: str) -> list[tuple[ProjectMetadata, float]]:
        """
        Search for matching projects using exact, alias, and fuzzy scoring.
        Returns a sorted list of (ProjectMetadata, score) descending.
        """
        clean = query.strip().lower()
        if not clean:
            return []

        # Strip common natural language noise
        clean = re.sub(r"^(?:open|launch|start|show|goto|go to|view)\s+", "", clean).strip()
        clean = re.sub(r"\s+(?:project|workspace|repo|code)$", "", clean).strip()
        clean = re.sub(r"^(?:my|the)\s+", "", clean).strip()

        # 1. Exact match
        direct = self.get_project(clean)
        if direct:
            return [(direct, 1.0)]

        results: list[tuple[ProjectMetadata, float]] = []
        clean_norm = self._normalize_key(clean)

        for pid, meta in self._projects.items():
            best_score = 0.0

            # Direct id / name comparisons
            if clean == pid.lower() or clean == meta.name.lower():
                best_score = max(best_score, 1.0)
            elif clean_norm and (clean_norm == self._normalize_key(pid) or clean_norm == self._normalize_key(meta.name)):
                best_score = max(best_score, 0.95)
            elif clean in pid.lower() or clean in meta.name.lower():
                best_score = max(best_score, 0.85)
            else:
                # Check aliases
                for alias in meta.aliases:
                    if clean == alias.lower():
                        best_score = max(best_score, 0.95)
                        break
                    elif clean in alias.lower() and len(clean) >= 3:
                        best_score = max(best_score, 0.80)

                # Check tags
                for tag in meta.tags:
                    if clean == tag.lower():
                        best_score = max(best_score, 0.70)
                    elif clean in tag.lower() and len(clean) >= 4:
                        best_score = max(best_score, 0.60)

            if best_score > 0.0:
                results.append((meta, round(best_score, 2)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def project_path(self, project_id: str) -> Optional[Path]:
        """Return the absolute filesystem path for a verified project."""
        meta = self.get_project(project_id)
        if meta and meta.absolute_path.exists():
            return meta.absolute_path
        return None

    def project_metadata(self, project_id: str) -> Optional[dict[str, Any]]:
        """Return raw dictionary metadata for a project."""
        meta = self.get_project(project_id)
        return meta.to_dict() if meta else None

    def list_projects(self) -> list[ProjectMetadata]:
        """Return all cataloged projects."""
        return list(self._projects.values())


_GLOBAL_PROJECT_REGISTRY: ProjectRegistry | None = None


def get_project_registry() -> ProjectRegistry:
    """Return the global cached ProjectRegistry singleton."""
    global _GLOBAL_PROJECT_REGISTRY
    if _GLOBAL_PROJECT_REGISTRY is None:
        _GLOBAL_PROJECT_REGISTRY = ProjectRegistry()
    return _GLOBAL_PROJECT_REGISTRY

