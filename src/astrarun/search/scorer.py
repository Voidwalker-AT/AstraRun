"""Multi-signal weighted fuzzy scoring algorithm with precomputed optimization."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrarun.search.models import PrecomputedTerm


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """
    Compute Damerau-Levenshtein distance between two strings,
    supporting insertions, deletions, substitutions, and transpositions.
    """
    len1, len2 = len(s1), len(s2)
    d: dict[tuple[int, int], int] = {}

    for i in range(-1, len1 + 1):
        d[(i, -1)] = i + 1
    for j in range(-1, len2 + 1):
        d[(-1, j)] = j + 1

    for i in range(len1):
        for j in range(len2):
            cost = 0 if s1[i] == s2[j] else 1
            d[(i, j)] = min(
                d[(i - 1, j)] + 1,        # deletion
                d[(i, j - 1)] + 1,        # insertion
                d[(i - 1, j - 1)] + cost  # substitution
            )
            if i > 0 and j > 0 and s1[i] == s2[j - 1] and s1[i - 1] == s2[j]:
                d[(i, j)] = min(d[(i, j)], d[(i - 2, j - 2)] + 1)  # transposition

    return d[(len1 - 1, len2 - 1)]


def extract_acronym(text: str) -> str:
    """Extract acronym from words separated by spaces, dashes, or underscores."""
    tokens = re.split(r"[\s\-_]+", text.strip())
    return "".join(t[0].lower() for t in tokens if t)


def is_subsequence(sub: str, string: str) -> bool:
    """Check if all characters in sub appear sequentially in string."""
    if not sub:
        return True
    idx = 0
    sub_len = len(sub)
    for ch in string:
        if ch == sub[idx]:
            idx += 1
            if idx == sub_len:
                return True
    return False


class FuzzyScorer:
    """Multi-signal weighted scorer balancing precision, prefixes, acronyms, and typos."""

    SCORE_EXACT = 1.00
    SCORE_ALIAS_EXACT = 0.98
    SCORE_PREFIX = 0.92
    SCORE_TOKEN_PREFIX = 0.88
    SCORE_SUBSTRING = 0.82
    SCORE_ACRONYM = 0.78
    SCORE_SUBSEQUENCE = 0.70

    @classmethod
    def score_precomputed(cls, q: str, term: PrecomputedTerm) -> float:
        """Score query against a precomputed search term with zero redundant regex/tokenization."""
        t = term.lower
        if not q or not t:
            return 0.0

        # 1. Exact match
        if q == t:
            return cls.SCORE_ALIAS_EXACT if term.is_alias else cls.SCORE_EXACT

        # 2. Prefix match
        if t.startswith(q):
            coverage = len(q) / len(t)
            return cls.SCORE_PREFIX + (0.04 * coverage)

        # 3. Token prefix match
        for token in term.tokens:
            if token.startswith(q):
                coverage = len(q) / len(token)
                return cls.SCORE_TOKEN_PREFIX + (0.03 * coverage)

        # 4. Substring match
        if q in t:
            return cls.SCORE_SUBSTRING

        # 5. Acronym match (precomputed)
        if len(q) >= 2 and q == term.acronym:
            return cls.SCORE_ACRONYM

        # 6. Subsequence match
        if len(q) >= 3 and is_subsequence(q, t):
            ratio = len(q) / len(t)
            if len(t) - len(q) <= 1 and len(q) >= 4:
                return 0.80 + 0.06 * ratio
            return cls.SCORE_SUBSEQUENCE * (0.8 + 0.2 * ratio)

        # 7. Typo / Edit Distance tolerance
        len_diff = abs(len(q) - len(t))
        if len_diff <= 2 and len(q) >= 4 and len(t) >= 4:
            dist = damerau_levenshtein_distance(q, t)
            if dist == 1:
                return 0.80 + 0.06 * (min(len(q), len(t)) / max(len(q), len(t)))
            elif dist == 2 and len(q) >= 6 and len(t) >= 6:
                return 0.65

        return 0.0

    @classmethod
    def score_single(cls, query: str, candidate_text: str, is_alias: bool = False) -> float:
        """Compute similarity score between query and arbitrary raw candidate string."""
        q = query.strip().lower()
        t = candidate_text.strip().lower()

        if not q or not t:
            return 0.0

        if q == t:
            return cls.SCORE_ALIAS_EXACT if is_alias else cls.SCORE_EXACT

        if t.startswith(q):
            coverage = len(q) / len(t)
            return cls.SCORE_PREFIX + (0.04 * coverage)

        tokens = [tok for tok in re.split(r"[\s\-_]+", t) if tok]
        for token in tokens:
            if token.startswith(q):
                coverage = len(q) / len(token)
                return cls.SCORE_TOKEN_PREFIX + (0.03 * coverage)

        if q in t:
            return cls.SCORE_SUBSTRING

        acronym = "".join(tok[0] for tok in tokens if tok)
        if len(q) >= 2 and q == acronym:
            return cls.SCORE_ACRONYM

        if len(q) >= 3 and is_subsequence(q, t):
            ratio = len(q) / len(t)
            if len(t) - len(q) <= 1 and len(q) >= 4:
                return 0.80 + 0.06 * ratio
            return cls.SCORE_SUBSEQUENCE * (0.8 + 0.2 * ratio)

        len_diff = abs(len(q) - len(t))
        if len_diff <= 2 and len(q) >= 4 and len(t) >= 4:
            dist = damerau_levenshtein_distance(q, t)
            if dist == 1:
                return 0.80 + 0.06 * (min(len(q), len(t)) / max(len(q), len(t)))
            elif dist == 2 and len(q) >= 6 and len(t) >= 6:
                return 0.65

        return 0.0

    @classmethod
    def compute_usage_boost(cls, launch_count: int, is_recent: bool = False) -> float:
        """Compute a modest usage bonus strictly capped at 0.03."""
        boost = min(0.02, launch_count * 0.001)
        if is_recent:
            boost += 0.01
        return boost
