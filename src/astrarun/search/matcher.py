"""Fuzzy matcher evaluating queries against candidates."""

from __future__ import annotations

from typing import Any

from astrarun.search.models import CandidateCategory, SearchCandidate, SearchResult
from astrarun.search.scorer import FuzzyScorer


class FuzzyMatcher:
    """Evaluates user queries against search candidates using weighted multi-signal scoring."""

    def __init__(self, min_score: float = 0.45):
        self.min_score = min_score

    def match_candidate(
        self,
        query: str,
        candidate: SearchCandidate,
        launch_count: int = 0,
        is_recent: bool = False,
    ) -> SearchResult | None:
        """Score a single candidate against the query across precomputed name and aliases."""
        clean_q = query.strip().lower()
        if not clean_q:
            return None

        best_score = 0.0
        best_term_text = candidate.name

        # Evaluate across precomputed terms (zero redundant regex/parsing)
        for term in candidate.terms:
            score = FuzzyScorer.score_precomputed(clean_q, term)
            if score > best_score:
                best_score = score
                best_term_text = term.text
                if best_score >= 1.0:
                    break

        # If base textual score is below threshold, reject early without usage boost
        if best_score < self.min_score:
            return None

        # Add bounded usage boost
        usage_boost = FuzzyScorer.compute_usage_boost(launch_count, is_recent)
        final_score = min(1.0, best_score + usage_boost)

        canonical_cmd = self._build_canonical_command(candidate)

        return SearchResult(
            id=candidate.id,
            name=candidate.name,
            subtitle=candidate.description or candidate.category.value.title(),
            category=candidate.category,
            score=round(final_score, 4),
            matched_alias=best_term_text,
            target=candidate.target,
            command=canonical_cmd,
            metadata=candidate.metadata,
        )

    def search(
        self,
        query: str,
        candidates: list[SearchCandidate],
        usage_provider: Any = None,
        limit: int = 5,
    ) -> list[SearchResult]:
        """Match query against all candidates and return ranked results."""
        clean_q = query.strip().lower()
        if not clean_q:
            return []

        results: list[SearchResult] = []

        for candidate in candidates:
            launch_count = 0
            is_recent = False
            if usage_provider:
                launch_count, is_recent = usage_provider.get_usage(candidate.id)

            res = self.match_candidate(
                query=clean_q,
                candidate=candidate,
                launch_count=launch_count,
                is_recent=is_recent,
            )
            if res:
                results.append(res)

        # Sort by score descending, then alphabetically by name
        results.sort(key=lambda r: (-r.score, r.name.lower()))

        # Strict deduplication: collapse candidates sharing display name or target
        deduped: list[SearchResult] = []
        seen_names: set[str] = set()
        seen_targets: set[str] = set()

        for r in results:
            n_clean = r.name.strip().lower()
            t_clean = r.target.strip().lower()
            if n_clean in seen_names or t_clean in seen_targets:
                continue
            seen_names.add(n_clean)
            seen_targets.add(t_clean)
            deduped.append(r)
            if len(deduped) >= limit:
                break

        return deduped

    def _build_canonical_command(self, candidate: SearchCandidate) -> str:
        """Derive the canonical command string to execute this candidate."""
        if candidate.category == CandidateCategory.APP:
            return f"open {candidate.name.lower()}"
        elif candidate.category == CandidateCategory.FOLDER:
            return f"open {candidate.name.lower()}"
        elif candidate.category == CandidateCategory.WEB:
            return f"open {candidate.name.lower()}"
        elif candidate.category == CandidateCategory.COMMAND:
            return candidate.target
        return f"open {candidate.name.lower()}"
