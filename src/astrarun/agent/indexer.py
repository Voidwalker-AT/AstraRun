"""Searchable semantic index and retrieval engine for AstraRun workstation capabilities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from astrarun.capabilities.models import CapabilityCategory
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.capabilities.schema import InteractionTier
from astrarun.core.logging import get_logger
from astrarun.core.models import ToolRisk

logger = get_logger("astrarun.agent.indexer")


@dataclass
class SemanticCapabilityEntry:
    """Enriched semantic metadata for a workstation capability."""
    id: str
    description: str
    verbs: set[str] = field(default_factory=set)
    nouns: set[str] = field(default_factory=set)
    domains: set[str] = field(default_factory=set)
    aliases: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    interaction_tier: InteractionTier = InteractionTier.TIER_A_NATIVE
    risk: ToolRisk = ToolRisk.LOW
    category: str = "SYSTEM"

    def all_tokens(self) -> set[str]:
        """Collect all canonical lexical tokens for exact and fuzzy matching."""
        tokens = set(self.verbs) | set(self.nouns) | set(self.domains)
        tokens.add(self.id.lower().replace("_", " "))
        for alias in self.aliases:
            tokens.update(alias.lower().split())
        for eg in self.examples:
            tokens.update(eg.lower().split())
        return {t.strip().lower() for t in tokens if len(t.strip()) > 1}


@dataclass
class CapabilityRetrievalResult:
    """Ranked retrieval candidate with match score and provenance."""
    capability_id: str
    score: float
    matched_terms: list[str]
    entry: SemanticCapabilityEntry


STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
    "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here",
    "here's", "hers", "herself", "him", "himself", "his", "how", "how's", "i",
    "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it", "it's",
    "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself",
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought",
    "our", "ours", "ourselves", "out", "over", "own", "same", "shan't", "she",
    "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "using", "use", "across", "along", "around", "upon", "onto", "towards", "throughout",
}


class CapabilitySemanticIndex:
    """
    Searchable index mapping unstructured natural language goals to candidate capabilities.
    Allows new capabilities registered dynamically to be indexed and discovered without modifying planner code.
    """

    def __init__(self, registry: Optional[CapabilityRegistry] = None):
        self.registry = registry or CapabilityRegistry()
        self._entries: dict[str, SemanticCapabilityEntry] = {}
        self.rebuild_index()

    def rebuild_index(self) -> None:
        """Scan all registered capabilities and build semantic entries."""
        self._entries.clear()
        caps = self.registry.list_capabilities()
        for cap in caps:
            self.index_capability(cap)
        logger.debug("Indexed %d capabilities in semantic index", len(self._entries))

    def index_capability(self, cap: Any) -> None:
        """Extract and index semantic keywords, arguments, and metadata from a Capability."""
        cap_id = cap.id
        desc = cap.description or ""
        
        # Extract inputs/args
        inputs = []
        if hasattr(cap, "args_schema") and isinstance(cap.args_schema, dict):
            inputs = list(cap.args_schema.keys())
        elif hasattr(cap, "parameters"):
            inputs = [p.name for p in cap.parameters]

        # Extract outputs
        outputs = []
        if hasattr(cap, "outputs") and cap.outputs:
            outputs = [o if isinstance(o, str) else getattr(o, "name", str(o)) for o in cap.outputs]

        # Extract verbs and nouns from id and description
        verbs = set()
        nouns = set()
        domains = set()

        # Common action verbs
        common_verbs = {
            "open", "launch", "start", "run", "running", "close", "stop", "kill", "terminate",
            "get", "find", "locate", "search", "check", "inspect", "list", "show", "scan", "connect",
            "disconnect", "save", "write", "read", "reverse", "maximize", "minimize",
            "restore", "snap", "move", "type", "press", "click", "toggle", "select",
            "undo", "create", "delete", "remove", "arrange", "focus", "scroll", "tile", "cascade", "organize",
            "execute", "sample", "evaluate", "join", "fuse", "reconcile", "assemble", "compare", "audit",
        }

        # Id tokens
        id_parts = cap_id.lower().split("_")
        if id_parts:
            if id_parts[0] in common_verbs:
                verbs.add(id_parts[0])
                nouns.update(id_parts[1:])
            elif id_parts[0] in ("is", "are", "has"):
                verbs.add("is")
                verbs.add("check")
                nouns.update(id_parts[1:])
            else:
                nouns.update(id_parts)

        # Tokenize description safely (ignoring prompt-like adversarial strings)
        cleaned_desc = re.sub(r"[^a-zA-Z0-9\s_\-]", " ", desc.lower())
        words = cleaned_desc.split()
        for w in words:
            if w in common_verbs:
                verbs.add(w)
            elif len(w) > 2 and w not in STOPWORDS:
                nouns.add(w)

        # Verb expansions and synonyms
        if "open" in verbs or "launch" in verbs or "start" in verbs or "open_application" in cap_id:
            verbs.update(["open", "launch", "start", "run"])
        if "find" in verbs or "locate" in verbs or "search" in verbs:
            verbs.update(["find", "locate", "search"])
        if "arrange" in verbs or "ARRANGE" in cap_id.upper() or "DESKTOP" in cap_id.upper():
            verbs.update(["arrange", "tile", "cascade", "organize", "grid"])
            domains.update(["tile", "arrange", "grid", "cascade", "organize"])
        if "is_application_running" in cap_id or "is_running" in cap_id:
            verbs.update(["check", "is", "running"])

        # Domain inference
        cat_val = cap.category.value.upper() if hasattr(cap.category, "value") else str(cap.category).upper()
        if "WIFI" in cap_id or "NETWORK" in cat_val:
            domains.update(["wifi", "network", "wlan", "wireless", "ssid", "internet"])
        if "WINDOW" in cap_id or "WINDOW" in cat_val:
            domains.update(["window", "monitor", "screen", "display", "layout"])
        if "FILE" in cap_id or "FILE" in cat_val or "report" in cap_id:
            domains.update(["file", "folder", "directory", "report", "path", "downloads"])
        if "BATTERY" in cap_id or "POWER" in cat_val:
            domains.update(["battery", "power", "charge", "energy", "health"])
        if "PROCESS" in cap_id or "PORT" in cap_id:
            domains.update(["process", "port", "pid", "task", "service", "socket"])
        if "REVERSE" in cap_id:
            domains.update(["reverse", "text", "string", "invert"])
        if "CLIPBOARD" in cap_id.upper():
            domains.update(["clipboard", "clipboard_content", "pasteboard", "copy", "paste"])
        if "ARRANGE" in cap_id.upper() or "DESKTOP" in cap_id.upper():
            domains.update(["tile", "arrange", "grid", "cascade", "organize"])
        if "WORD" in cap_id.upper() or "COUNT" in cap_id.upper():
            domains.update(["word", "words", "count", "counter"])
        if "HASH" in cap_id.upper():
            domains.update(["hash", "checksum", "sha256", "digest"])
        if "FORMAT" in cap_id.upper() or "JSON" in cap_id.upper():
            domains.update(["format", "json", "beautify", "indent"])
        if "DYNAMIC" in cap_id.upper() or "DELEGATE" in cap_id.upper():
            domains.update(["code", "python", "program", "script", "tool", "computation", "dynamic", "generate", "execute", "synthesize", "file", "artifact"])

        tier = getattr(cap, "interaction_tier", InteractionTier.TIER_A_NATIVE)
        risk = getattr(cap, "risk", ToolRisk.LOW)

        entry = SemanticCapabilityEntry(
            id=cap_id,
            description=desc,
            verbs=verbs,
            nouns=nouns,
            domains=domains,
            aliases=[],
            examples=[],
            inputs=inputs,
            outputs=outputs,
            interaction_tier=tier,
            risk=risk,
            category=cat_val,
        )
        self._entries[cap_id] = entry

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.15,
        required_verbs: Optional[set[str]] = None,
    ) -> list[CapabilityRetrievalResult]:
        """
        Retrieve top-K matching capabilities for a natural language user query.
        Uses multi-factor scoring: exact token match, domain match, verb alignment, and argument overlap.
        """
        # Ensure index has latest registered capabilities
        if len(self._entries) < len(self.registry.list_capabilities()):
            self.rebuild_index()

        q_clean = query.strip().lower()
        all_tokens = set(re.findall(r"\b[a-z0-9_\-]+\b", q_clean))
        q_tokens = {t for t in all_tokens if t not in STOPWORDS}

        results: list[CapabilityRetrievalResult] = []

        for cap_id, entry in self._entries.items():
            matched_terms = []
            score = 0.0

            # 1. Exact ID match or substring
            clean_id = cap_id.lower().replace("_", " ")
            id_parts = cap_id.lower().split("_")
            generic_verbs = {"get", "check", "is", "show", "view", "display"}

            if clean_id in q_clean or cap_id.lower() in all_tokens:
                score += 1.0
                matched_terms.append(f"exact_id:{cap_id}")
            else:
                id_matches = [part for part in id_parts if part in q_tokens and len(part) > 2 and part not in generic_verbs]
                if id_matches:
                    score += 0.40 * len(id_matches)
                    matched_terms.extend([f"id_token:{p}" for p in id_matches])

            # Domain specific contextual boost
            if cap_id == "list_windows" and ("window" in all_tokens or "windows" in all_tokens) and any(w in all_tokens for w in ("list", "show", "open", "all")):
                score += 0.50
                matched_terms.append("context:list_windows")
            if "inspect_window_ui" in cap_id and any(w in all_tokens for w in ("controls", "ui", "components", "elements", "widgets")):
                score += 0.50
                matched_terms.append("context:inspect_ui")
            if "explorer" in all_tokens:
                if cap_id in ("open_folder", "reveal_file"):
                    score += 0.80
                    matched_terms.append("context:file_explorer")
                elif cap_id == "open_file":
                    score -= 1.20
            if "file" in all_tokens and any(w in all_tokens for w in ("show", "reveal", "highlight")):
                if cap_id == "reveal_file":
                    score += 1.50
                    matched_terms.append("context:reveal_file")
                elif cap_id == "open_folder":
                    score -= 0.80
            if any(w in all_tokens for w in ("save", "write")) and "file" in all_tokens:
                if cap_id == "save_text_file":
                    score += 1.80
                    matched_terms.append("context:save_file")
            if any(b in all_tokens for b in ("browser", "url", "website", "documentation", "docs", "web")):
                if cap_id == "open_url":
                    score += 1.0
                    matched_terms.append("context:browser_url")
                elif cap_id == "open_file":
                    score -= 1.20
            if any(k in all_tokens for k in ("open", "launch", "start", "run")):
                if any("app" in t or t in ("calc", "calculator", "notepad", "terminal", "browser", "editor") for t in all_tokens):
                    if cap_id == "open_application":
                        score += 0.80
                        matched_terms.append("context:open_app")
                    elif cap_id == "open_file":
                        score -= 0.80

            # 2. Verb matches (+0.35 specific action, +0.10 generic)
            matched_verbs = entry.verbs.intersection(q_tokens)
            if matched_verbs:
                for v in matched_verbs:
                    w = 0.10 if v in generic_verbs else 0.35
                    score += w
                    matched_terms.append(f"verb:{v}")

            # 3. Domain matches (+0.35 each)
            matched_domains = entry.domains.intersection(q_tokens)
            if matched_domains:
                score += 0.35 * len(matched_domains)
                matched_terms.extend([f"domain:{d}" for d in matched_domains])

            # 4. Noun / keyword matches (+0.15 each)
            matched_nouns = entry.nouns.intersection(q_tokens)
            if matched_nouns:
                score += 0.15 * len(matched_nouns)
                matched_terms.extend([f"noun:{n}" for n in matched_nouns])

            # 5. Output / Input keyword matches (+0.20 each)
            input_matches = set(entry.inputs).intersection(q_tokens)
            if input_matches:
                score += 0.20 * len(input_matches)
                matched_terms.extend([f"arg:{a}" for a in input_matches])

            # 6. Interaction tier preference: Tier A > Tier B > Tier C
            if entry.interaction_tier == InteractionTier.TIER_A_NATIVE:
                score += 0.05
            elif entry.interaction_tier == InteractionTier.TIER_B_STRUCTURED_CLI:
                score += 0.03

            # If arrange_desktop, require explicit arrangement action verb
            if cap_id == "arrange_desktop" and not any(w in all_tokens for w in ("arrange", "tile", "cascade", "organize", "grid", "layout")):
                score = 0.0

            # If snap_window, require explicit window management terms (disallow accidental match on adverbial "right now")
            if cap_id in ("snap_window_right", "snap_window_left"):
                if not any(w in all_tokens for w in ("snap", "tile", "dock", "window", "half")):
                    score = 0.0

            # If dynamic tool execution or delegation, require explicit execution/compilation intent, not conversational code request
            if "dynamic" in cap_id.lower() or "delegate" in cap_id.lower():
                if any(w in all_tokens for w in ("example", "analogy", "explain", "explanation", "why", "how", "what", "show", "tell", "teach")):
                    if not any(w in all_tokens for w in ("run", "execute", "build", "compile", "eval", "launch")):
                        score = 0.0

            # 7. Hardware Subsystem Specificity & Domain Conflict Rules
            hw_domains = {"battery", "memory", "ram", "cpu", "gpu", "vram", "disk", "storage"}
            query_hw = hw_domains.intersection(all_tokens)
            cap_hw = set()
            for hw in ("battery", "memory", "cpu", "gpu", "disk"):
                if hw in cap_id.lower():
                    cap_hw.add(hw)
                if hw == "memory" and "ram" in cap_id.lower():
                    cap_hw.add("memory")
            if cap_id == "gpu_status":
                cap_hw.add("gpu")
                cap_hw.add("vram")
                if "vram" in all_tokens:
                    matched_terms.append("domain:gpu_vram")
            if cap_id == "memory_status" and ("ram" in all_tokens or "memory" in all_tokens):
                cap_hw.add("ram")
                matched_terms.append("domain:system_memory")

            if query_hw:
                # If query specifically mentions a hardware domain and capability belongs to an opposing domain, penalize
                if cap_hw and not (query_hw.intersection(cap_hw) or ("ram" in query_hw and "memory" in cap_hw)):
                    score -= 1.0

                # If query mentions a specific hardware domain, boost capabilities specializing in it
                if cap_hw.intersection(query_hw) or ("memory" in cap_hw and "ram" in query_hw):
                    score += 0.40

                # Broad summary tools yield to specialized tools when a specific subsystem is requested
                if cap_id == "system_summary" and query_hw:
                    score -= 0.25

            # Grounding check: Incidental noun-only matches without verb/domain/id/arg get downweighted
            has_grounding = any(
                t.startswith(("exact_id:", "id_token:", "verb:", "domain:", "arg:", "context:"))
                for t in matched_terms
            )
            if not has_grounding:
                score *= 0.5

            if score >= min_score:
                results.append(
                    CapabilityRetrievalResult(
                        capability_id=cap_id,
                        score=round(score, 3),
                        matched_terms=matched_terms,
                        entry=entry,
                    )
                )

        # Sort descending by score
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def get_entry(self, cap_id: str) -> Optional[SemanticCapabilityEntry]:
        """Retrieve indexed entry by capability ID."""
        if cap_id not in self._entries:
            cap = self.registry.get(cap_id)
            if cap:
                self.index_capability(cap)
        return self._entries.get(cap_id)
