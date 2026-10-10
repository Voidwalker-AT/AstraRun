"""Semantic Entity Resolution & Candidate Normalization Engine for AstraRun Brain."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

from astrarun.core.logging import get_logger
from astrarun.core.models import AppInfo
from astrarun.nlp.clause_decomposer import strip_politeness
from astrarun.search.index import SearchIndex
from astrarun.search.models import CandidateCategory, SearchResult

logger = get_logger("astrarun.brain.decision.entity_resolver")

# Maintenance, troubleshooter, and secondary variants that must NEVER be silently selected
MAINTENANCE_KEYWORDS = {
    "reset", "cache", "preferences", "troubleshoot", "troubleshooting",
    "diagnostic", "repair", "safe mode", "safemode", "crash reporter",
    "feedback", "report issue", "release notes", "changelog", "manual",
    "getting started", "whats new", "what's new", "eula", "donate",
    "register", "profile manager", "uninstall"
}


@dataclass
class ResolvedEntity:
    """Strongly-typed entity resolution output."""
    entity_id: str
    name: str
    target_path: str
    confidence: float
    is_ambiguous: bool = False
    ambiguous_candidates: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    is_installed: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


def resolve_lnk_target(lnk_path: str | Path) -> Optional[str]:
    """Extract physical .exe target path from a Windows .lnk shortcut without COM dependency."""
    try:
        p = Path(lnk_path)
        if not p.exists() or p.suffix.lower() != ".lnk":
            return str(p) if p.exists() else None

        with open(p, "rb") as f:
            content = f.read()

        # Parse Shell Link Header (minimum 76 bytes)
        if len(content) < 76 or content[:4] != b"\x4c\x00\x00\x00":
            return str(p)

        flags = int.from_bytes(content[0x14:0x18], byteorder="little")
        has_link_info = bool(flags & 0x02)

        if has_link_info:
            pos = 76
            has_id_list = bool(flags & 0x01)
            if has_id_list and len(content) >= pos + 2:
                id_list_len = int.from_bytes(content[pos:pos + 2], byteorder="little")
                pos += 2 + id_list_len

            if len(content) >= pos + 28:
                local_base_offset = int.from_bytes(content[pos + 0x10:pos + 0x14], byteorder="little")
                if local_base_offset > 0 and pos + local_base_offset < len(content):
                    raw_str = content[pos + local_base_offset:]
                    null_idx = raw_str.find(b"\x00")
                    if null_idx != -1:
                        raw_str = raw_str[:null_idx]
                    try:
                        resolved_target = raw_str.decode("mbcs", errors="ignore")
                        if resolved_target and os.path.isabs(resolved_target):
                            return resolved_target
                    except Exception:
                        pass
    except Exception as ex:
        logger.debug("Failed parsing LNK '%s': %s", lnk_path, ex)

    return str(lnk_path)


class SemanticEntityResolver:
    """
    Resolves natural-language references to canonical local desktop applications,
    documents, or system entities without hardcoding specific application titles.
    """

    _instance: Optional[SemanticEntityResolver] = None

    def __init__(self, app_cache: Optional[Any] = None, search_index: Optional[SearchIndex] = None) -> None:
        self.app_cache = app_cache
        self.search_index = search_index
        self._init_dependencies()
        SemanticEntityResolver._instance = self

    @classmethod
    def get_instance(cls, app_cache: Optional[Any] = None, search_index: Optional[SearchIndex] = None) -> SemanticEntityResolver:
        if cls._instance is None:
            cls._instance = cls(app_cache=app_cache, search_index=search_index)
        elif app_cache is not None or search_index is not None:
            if app_cache is not None:
                cls._instance.app_cache = app_cache
            if search_index is not None:
                cls._instance.search_index = search_index
        return cls._instance

    def _init_dependencies(self) -> None:
        if self.app_cache is None:
            try:
                from astrarun.discovery.apps import AppDiscoveryCache
                self.app_cache = AppDiscoveryCache()
            except Exception:
                pass

        if self.search_index is None and self.app_cache is not None:
            try:
                self.search_index = SearchIndex()
                self.search_index.build(
                    apps=list(self.app_cache.apps.values()),
                    workspace_files=[],
                    projects=[],
                    open_windows=[],
                )
            except Exception:
                pass

    def resolve_application(self, utterance_or_target: str) -> Optional[ResolvedEntity]:
        """
        Multi-stage resolution pipeline:
        1. Politeness and conversational stripping
        2. Exact key / alias lookup against dynamic AppDiscoveryCache
        3. SearchIndex multi-attribute ranking with maintenance filtering
        4. Canonical target deduplication
        5. Ambiguity thresholding
        """
        raw = utterance_or_target.strip()
        if not raw:
            return None

        # 1. Normalize and strip politeness / conversational prefixes
        query = strip_politeness(raw)
        action_match = re.match(
            r"^(?:open|launch|start|run|bring\s+up|switch\s+to|focus|execute)\s+(?:the\s+|an?\s+)?(.*)$",
            query,
            re.IGNORECASE,
        )
        if action_match:
            query = action_match.group(1).strip()

        # Remove trailing polite phrases
        query = re.sub(r"\b(?:please|for\s+me|quick|now|thanks)\b", "", query, flags=re.IGNORECASE).strip()
        query = re.sub(r"^(?:the\s+|an?\s+)", "", query, flags=re.IGNORECASE).strip()

        if not query:
            return None

        q_lower = query.lower()
        q_stem = re.sub(r"[^a-z0-9]", "", q_lower)

        # 2. Stage 1: Exact AppDiscoveryCache Key or Name Match
        if self.app_cache and self.app_cache.apps:
            # Direct key match
            if q_lower in self.app_cache.apps:
                app = self.app_cache.apps[q_lower]
                return self._create_resolved_entity(app, confidence=1.0, reason="exact_key_match")

            # Check exact name or alias match
            for key, app in self.app_cache.apps.items():
                app_name_l = app.name.lower()
                if app_name_l == q_lower:
                    return self._create_resolved_entity(app, confidence=1.0, reason="exact_name_match")
                if q_lower in [a.lower() for a in getattr(app, "aliases", [])]:
                    return self._create_resolved_entity(app, confidence=0.98, reason="exact_alias_match")
                # Stem match (e.g. "calc" -> "calculator")
                app_stem = re.sub(r"[^a-z0-9]", "", app_name_l)
                if q_stem and (q_stem == app_stem or app_stem == q_stem):
                    return self._create_resolved_entity(app, confidence=0.95, reason="exact_stem_match")
                # Acronym / abbreviation match (e.g. "vscode" -> "Visual Studio Code")
                words = [w for w in re.findall(r'[a-z0-9]+', app_name_l) if w]
                if len(words) > 1:
                    initials = "".join(w[0] for w in words)
                    hybrid = "".join(w[0] for w in words[:-1]) + words[-1]
                    if q_stem in (initials, hybrid):
                        return self._create_resolved_entity(app, confidence=0.96, reason="acronym_match")

        # 3. Stage 2: Unified SearchIndex Ranking
        candidates: List[SearchResult] = []
        if self.search_index:
            candidates = self.search_index.search(query, limit=10)

        # Filter strictly for APP candidates
        app_candidates = [c for c in candidates if c.category == CandidateCategory.APP]

        if not app_candidates and self.app_cache:
            # Fallback scan over cache
            q_tokens = set(re.findall(r'[a-z0-9]+', q_lower))
            for app in self.app_cache.apps.values():
                score = 0.0
                name_l = app.name.lower()
                name_tokens = set(re.findall(r'[a-z0-9]+', name_l))
                if q_lower in name_l:
                    score = 0.70 + (len(q_lower) / max(len(name_l), 1)) * 0.20
                elif any(q_lower in a.lower() for a in getattr(app, "aliases", [])):
                    score = 0.85
                elif q_tokens and name_tokens:
                    overlap = len(q_tokens & name_tokens) / len(q_tokens)
                    if overlap >= 0.50:
                        score = 0.50 + overlap * 0.35

                # Penalize candidates missing key query tokens when multi-word query provided
                if len(q_tokens) > 1 and name_tokens:
                    coverage = len(q_tokens & name_tokens) / len(q_tokens)
                    if coverage < 0.50:
                        score *= 0.40

                if score >= 0.50:
                    app_candidates.append(
                        SearchResult(
                            id=app.key,
                            name=app.name,
                            subtitle=getattr(app, "description", "") or app.path,
                            category=CandidateCategory.APP,
                            score=score,
                            matched_alias=app.key,
                            target=app.path,
                            command=app.path,
                        )
                    )
            app_candidates.sort(key=lambda x: x.score, reverse=True)

        if not app_candidates:
            return None

        # 4. Stage 3: Maintenance & Utility Sanitization Filter
        clean_candidates: List[SearchResult] = []
        for cand in app_candidates:
            cand_name_lower = cand.name.lower()
            is_maint = any(kw in cand_name_lower for kw in MAINTENANCE_KEYWORDS)
            # If user explicitly asked for maintenance utility, permit it
            if is_maint and not any(kw in q_lower for kw in ("reset", "troubleshoot", "repair", "safe")):
                continue
            clean_candidates.append(cand)

        # Fall back to unfiltered if all candidates were quarantined
        if not clean_candidates:
            clean_candidates = app_candidates

        # 5. Stage 4: Canonical Target Deduplication
        clustered: List[SearchResult] = []
        seen_targets: set[str] = set()
        seen_names: set[str] = set()

        for cand in clean_candidates:
            target_path = resolve_lnk_target(cand.target) if cand.target else cand.target
            norm_target = (target_path or cand.name).lower().strip()
            norm_name = cand.name.lower().strip()
            if norm_target in seen_targets or norm_name in seen_names:
                continue
            seen_targets.add(norm_target)
            seen_names.add(norm_name)
            cand.target = target_path or cand.target
            clustered.append(cand)

        if not clustered:
            return None

        top = clustered[0]

        # 6. Stage 5: Ambiguity Assessment
        # If top candidate is highly confident and clearly beats runner up
        if len(clustered) == 1 or top.score >= 0.85:
            if len(clustered) > 1:
                runner_up = clustered[1]
                if (top.score - runner_up.score) >= 0.15:
                    return self._create_from_search_result(top, is_ambiguous=False, reason="dominant_confidence")
            else:
                return self._create_from_search_result(top, is_ambiguous=False, reason="single_canonical_match")

        # Check for multiple competitive candidates within 0.10 score band
        competitive = [c for c in clustered if (top.score - c.score) <= 0.10 and c.score >= 0.60]
        if len(competitive) > 1:
            # Genuine ambiguity
            return ResolvedEntity(
                entity_id=top.id,
                name=top.name,
                target_path=top.target,
                confidence=top.score,
                is_ambiguous=True,
                ambiguous_candidates=[
                    {"id": c.id, "name": c.name, "target": c.target, "score": c.score}
                    for c in competitive
                ],
                reason="multiple_competitive_candidates",
                is_installed=True,
                metadata={"query": query},
            )

        return self._create_from_search_result(top, is_ambiguous=False, reason="best_ranked_candidate")

    def is_app_installed(self, query: str) -> Tuple[bool, Optional[ResolvedEntity]]:
        """Check if an application matching query is installed."""
        ent = self.resolve_application(query)
        if ent and ent.is_installed:
            return True, ent
        return False, None

    def is_app_running(self, query: str) -> Tuple[bool, List[int], Optional[ResolvedEntity]]:
        """Check if an application matching query has active running processes."""
        ent = self.resolve_application(query)
        pids: List[int] = []
        if not ent:
            return False, [], None

        target_stem = Path(ent.target_path).stem.lower() if ent.target_path else ent.name.lower()
        for p in psutil.process_iter(["pid", "name"]):
            try:
                p_stem = Path(p.info["name"] or "").stem.lower()
                if p_stem == target_stem or ent.name.lower() in p_stem:
                    pids.append(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return len(pids) > 0, pids, ent

    def _create_resolved_entity(self, app: AppInfo, confidence: float, reason: str) -> ResolvedEntity:
        resolved_path = resolve_lnk_target(app.path) if app.path else app.path
        return ResolvedEntity(
            entity_id=app.key,
            name=app.name,
            target_path=resolved_path or app.path,
            confidence=confidence,
            is_ambiguous=False,
            reason=reason,
            is_installed=True,
            metadata={"source": "app_cache", "app_key": app.key, "aliases": getattr(app, "aliases", [])},
        )

    def _create_from_search_result(self, res: SearchResult, is_ambiguous: bool, reason: str) -> ResolvedEntity:
        return ResolvedEntity(
            entity_id=res.id,
            name=res.name,
            target_path=res.target or "",
            confidence=res.score,
            is_ambiguous=is_ambiguous,
            reason=reason,
            is_installed=True,
            metadata={"source": "search_index", "matched_alias": res.matched_alias},
        )


class SemanticEntityIdentityEvaluator:
    """
    Evaluates whether a resolved entity matches the user's semantic intent,
    rejecting false positives, ambiguous unclarified selections, and semantic family mismatches.
    """

    @staticmethod
    def evaluate(expected_target: str, resolved: Optional[ResolvedEntity]) -> Tuple[bool, str]:
        if resolved is None:
            return False, f"Expected '{expected_target}' but no entity was resolved."

        if resolved.is_ambiguous and resolved.confidence < 0.85:
            cands = ", ".join(c.get("name", "") for c in resolved.ambiguous_candidates[:3])
            return False, f"Resolution for '{expected_target}' was ambiguous among: {cands}."

        exp_lower = expected_target.lower().strip()
        exp_stem = re.sub(r'[^a-z0-9]', '', exp_lower)
        exp_tokens = set(re.findall(r'[a-z0-9]+', exp_lower))

        res_name_l = resolved.name.lower()
        res_key_l = resolved.entity_id.lower()
        res_stem = re.sub(r'[^a-z0-9]', '', res_name_l)
        res_tokens = set(re.findall(r'[a-z0-9]+', res_name_l))
        res_aliases = [a.lower() for a in resolved.metadata.get("aliases", [])]

        # 1. Direct match on key, name, stem, or aliases
        if (
            exp_lower in (res_key_l, res_name_l)
            or exp_stem in (res_stem, res_key_l)
            or (len(exp_stem) >= 4 and (exp_stem in res_stem or res_stem in exp_stem))
            or exp_lower in res_aliases
        ):
            if "word" in exp_tokens and "wordpad" in res_tokens and "wordpad" not in exp_tokens:
                return False, f"Semantic mismatch: expected Word but resolved '{resolved.name}'."
            return True, f"Exact semantic match with {resolved.name}."

        # 2. Acronym match (e.g. 'vscode' -> 'Visual Studio Code')
        res_words = [w for w in re.findall(r'[a-z0-9]+', res_name_l) if w]
        if len(res_words) > 1:
            initials = "".join(w[0] for w in res_words)
            hybrid = "".join(w[0] for w in res_words[:-1]) + res_words[-1]
            if exp_stem in (initials, hybrid):
                return True, f"Acronym match '{exp_stem}' -> {resolved.name}."

        # 3. Known discriminating semantic families
        # If expected specifies 'code' (like 'vscode' or 'visual studio code'), reject 'Visual Profiler'
        if "code" in exp_tokens and "code" not in res_tokens:
            return False, f"Semantic mismatch: expected code editor but resolved '{resolved.name}'."
        if "profiler" in exp_tokens and "profiler" not in res_tokens:
            return False, f"Semantic mismatch: expected profiler but resolved '{resolved.name}'."
        if "wordpad" in exp_tokens and "wordpad" not in res_tokens:
            return False, f"Semantic mismatch: expected WordPad but resolved '{resolved.name}'."
        if "word" in exp_tokens and "wordpad" in res_tokens and "wordpad" not in exp_tokens:
            return False, f"Semantic mismatch: expected Word but resolved '{resolved.name}'."
        if ("terminal" in exp_tokens or "wt" in exp_tokens) and "terminal" not in res_tokens and "wt" not in res_key_l:
            return False, f"Semantic mismatch: expected Terminal but resolved '{resolved.name}'."
        if ("cmd" in exp_tokens or "command" in exp_tokens) and ("terminal" in res_tokens or "wt" in res_tokens):
            return False, f"Semantic mismatch: expected Command Prompt but resolved '{resolved.name}'."

        # 4. Token coverage check for multi-word queries
        if len(exp_tokens) > 1:
            overlap = len(exp_tokens & res_tokens) / len(exp_tokens)
            if overlap >= 0.60:
                return True, f"Semantic token overlap ({overlap:.0%}) with {resolved.name}."
            return False, f"Insufficient token overlap ({overlap:.0%}) between '{expected_target}' and '{resolved.name}'."

        # 5. Single token check: if expected query was a single word (e.g. 'visual') and resolved is 'Visual Profiler'
        if len(exp_tokens) == 1 and exp_lower in res_tokens:
            if len(res_tokens) > 1:
                return False, f"Ambiguous single-word match '{expected_target}' against compound entity '{resolved.name}'."
            return True, f"Single-token match with {resolved.name}."

        return False, f"Could not establish semantic identity between '{expected_target}' and '{resolved.name}'."

