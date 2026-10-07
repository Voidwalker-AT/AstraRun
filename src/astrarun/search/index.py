"""Unified discovery index aggregating applications, folders, web URLs, and commands."""

from __future__ import annotations

from typing import Any

from astrarun.core.logging import get_logger
from astrarun.core.models import AppInfo, FolderInfo
from astrarun.search.matcher import FuzzyMatcher
from astrarun.search.models import CandidateCategory, SearchCandidate, SearchResult

logger = get_logger("astrarun.search.index")


class SearchIndex:
    """Unified in-memory index of all launchable workstation entities."""

    def __init__(self, matcher: FuzzyMatcher | None = None, usage_store: Any = None):
        self._candidates: dict[str, SearchCandidate] = {}
        self._matcher = matcher or FuzzyMatcher()
        self._usage_store = usage_store

    def add(self, candidate: SearchCandidate) -> None:
        """Add or update a candidate in the index."""
        self._candidates[candidate.id] = candidate

    def get(self, candidate_id: str) -> SearchCandidate | None:
        """Retrieve candidate by stable ID."""
        return self._candidates.get(candidate_id)

    def all_candidates(self) -> list[SearchCandidate]:
        """Return list of all indexed candidates."""
        return list(self._candidates.values())

    def clear(self) -> None:
        """Clear all candidates from the index."""
        self._candidates.clear()

    def build_from_sources(
        self,
        apps: dict[str, AppInfo],
        folders: dict[str, FolderInfo],
        urls: dict[str, str],
        aliases: dict[str, str],
    ) -> None:
        """Index applications, folders, URLs, and aliases into a unified catalog."""
        self.clear()

        # Build alias lookup map: target_key -> list of aliases
        alias_map: dict[str, list[str]] = {}
        for alias, target_key in aliases.items():
            alias_map.setdefault(target_key.lower(), []).append(alias.lower())

        # 1. Index Applications with strict identity deduplication
        seen_targets: dict[str, str] = {}
        seen_names: dict[str, str] = {}

        for app_key, app in apps.items():
            cand_aliases = list(set([app_key] + alias_map.get(app_key, [])))
            stem = app.path.split("\\")[-1].rsplit(".", 1)[0].lower()
            if stem not in cand_aliases:
                cand_aliases.append(stem)

            try:
                from pathlib import Path
                canonical_target = Path(app.path).resolve().as_posix().lower()
            except Exception:
                canonical_target = app.path.strip().lower()
            import re
            norm_name = re.sub(r"[^a-zA-Z0-9]+", "", app.name.lower())

            existing_id = seen_targets.get(canonical_target) or seen_names.get(norm_name)
            if existing_id and existing_id in self._candidates:
                existing_cand = self._candidates[existing_id]
                for alias in cand_aliases:
                    if alias not in existing_cand.aliases:
                        existing_cand.aliases.append(alias)
                existing_cand._precompute_terms()
                continue

            cand_id = f"app:{app_key}"
            new_cand = SearchCandidate(
                id=cand_id,
                name=app.name,
                category=CandidateCategory.APP,
                target=app.path,
                aliases=cand_aliases,
                description=app.description or "Application",
                metadata={"key": app_key, "path": app.path},
            )
            self.add(new_cand)
            seen_targets[canonical_target] = cand_id
            seen_names[norm_name] = cand_id

        # 2. Index Folders
        for folder_key, folder in folders.items():
            cand_id = f"folder:{folder_key}"
            cand_aliases = list(set([folder_key] + alias_map.get(folder_key, [])))
            self.add(
                SearchCandidate(
                    id=cand_id,
                    name=folder.name or folder_key.title(),
                    category=CandidateCategory.FOLDER,
                    target=folder.path,
                    aliases=cand_aliases,
                    description=f"Folder: {folder.path}",
                    metadata={"key": folder_key, "path": folder.path},
                )
            )

        # 3. Index Web URLs
        for url_key, url_target in urls.items():
            cand_id = f"url:{url_key}"
            cand_aliases = [url_key]
            self.add(
                SearchCandidate(
                    id=cand_id,
                    name=url_key.title(),
                    category=CandidateCategory.WEB,
                    target=url_target,
                    aliases=cand_aliases,
                    description=url_target,
                    metadata={"key": url_key, "url": url_target},
                )
            )

        # 4. Index Internal Commands
        self.add(
            SearchCandidate(
                id="cmd:refresh_apps",
                name="Refresh Applications",
                category=CandidateCategory.COMMAND,
                target="refresh apps",
                aliases=["refresh", "reload apps", "reload index"],
                description="Rescan installed Windows applications and rebuild index",
                metadata={"action": "refresh_apps"},
            )
        )

        logger.info("SearchIndex built successfully: %d candidates indexed.", len(self._candidates))

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """Search across all indexed candidates."""
        return self._matcher.search(
            query=query,
            candidates=self.all_candidates(),
            usage_provider=self._usage_store,
            limit=limit,
        )
