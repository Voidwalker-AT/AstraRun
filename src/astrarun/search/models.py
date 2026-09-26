"""Data models for unified search and ranked suggestions with precomputed metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CandidateCategory(str, Enum):
    """Category classification for search candidates."""
    APP = "APP"
    FOLDER = "FOLDER"
    WEB = "WEB"
    COMMAND = "COMMAND"


@dataclass
class PrecomputedTerm:
    """Precomputed normalized search term, tokens, and acronym for ultra-low latency matching."""
    text: str
    lower: str
    tokens: list[str]
    acronym: str
    is_alias: bool


@dataclass
class SearchCandidate:
    """An indexed candidate representing an application, folder, URL, or action."""
    id: str
    name: str
    category: CandidateCategory
    target: str
    aliases: list[str] = field(default_factory=list)
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    terms: list[PrecomputedTerm] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        """Precompute lowercase strings, tokens, and acronyms at index time."""
        if not self.terms:
            self._precompute_terms()

    def _precompute_terms(self) -> None:
        """Build PrecomputedTerm instances for display name and all aliases."""
        terms_list: list[PrecomputedTerm] = []

        # 1. Primary Name
        name_lower = self.name.strip().lower()
        tokens = [t for t in re.split(r"[\s\-_]+", name_lower) if t]
        acronym = "".join(t[0] for t in tokens if t)
        terms_list.append(
            PrecomputedTerm(
                text=self.name,
                lower=name_lower,
                tokens=tokens,
                acronym=acronym,
                is_alias=False,
            )
        )

        # 2. Aliases
        for alias in self.aliases:
            al_clean = alias.strip().lower()
            if not al_clean or al_clean == name_lower:
                continue
            al_tokens = [t for t in re.split(r"[\s\-_]+", al_clean) if t]
            al_acronym = "".join(t[0] for t in al_tokens if t)
            terms_list.append(
                PrecomputedTerm(
                    text=alias,
                    lower=al_clean,
                    tokens=al_tokens,
                    acronym=al_acronym,
                    is_alias=True,
                )
            )

        self.terms = terms_list

    def all_search_terms(self) -> list[str]:
        """Return all raw terms (name, aliases) against which search is performed."""
        return [t.text for t in self.terms]


@dataclass
class SearchResult:
    """A scored and ranked search result presented to the UI or router."""
    id: str
    name: str
    subtitle: str
    category: CandidateCategory
    score: float
    matched_alias: str
    target: str
    command: str
    metadata: dict[str, Any] = field(default_factory=dict)
