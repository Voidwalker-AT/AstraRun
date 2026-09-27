"""Learned Alias Manager for AstraRun Learning Foundation.

Integrates learned workstation aliases with static configurations and EntityResolutionEngine.
Enforces strict evaluation precedence, type safety, conflict gating, and non-learnable security policies.
"""

from __future__ import annotations

from typing import Any, Optional

from astrarun.core.logging import get_logger
from astrarun.learning.memory import MemoryStore
from astrarun.learning.models import MemoryNamespace, MemoryStatus, SemanticMemory
from astrarun.routing.entity_resolver import PROTECTED_PROCESSES

logger = get_logger("astrarun.learning.aliases")


class AliasManager:
    """
    Resolves aliases using strict multi-tier precedence:
    1. Static Config Alias
    2. User-Confirmed Learned Alias (Active)
    3. High-Confidence Learned Alias (Active, C >= 0.85)
    """

    def __init__(
        self,
        memory_store: Optional[MemoryStore] = None,
        static_aliases: Optional[dict[str, str]] = None,
    ) -> None:
        self.memory_store = memory_store or MemoryStore()
        self.static_aliases: dict[str, str] = {
            k.strip().lower(): str(v).strip().lower()
            for k, v in (static_aliases or {}).items()
        }

    def register_static_aliases(self, aliases: dict[str, str]) -> None:
        """Register or update baseline static aliases from configuration."""
        for k, v in aliases.items():
            self.static_aliases[k.strip().lower()] = str(v).strip().lower()

    def resolve(
        self,
        alias_key: str,
        expected_target_type: Optional[str] = None,
    ) -> Optional[tuple[str, str, float]]:
        """
        Resolve an alias string to its concrete target, source, and confidence.

        Returns:
            Tuple of (resolved_target, source_label, confidence) or None.
            source_label is one of: "static_config", "user_confirmed_alias", "learned_alias".
        """
        clean_key = alias_key.strip().lower()
        if not clean_key:
            return None

        # Tier 1: Static Config Alias (Strict Authority)
        if clean_key in self.static_aliases:
            static_val = self.static_aliases[clean_key]
            if self._is_security_safe(static_val):
                return static_val, "static_config", 1.0

        # Check for learned memories in ALIAS namespace
        memories = self.memory_store.persistence.find_memories(
            namespace=MemoryNamespace.ALIAS,
            key=clean_key,
        )
        if not memories:
            return None

        # Check for conflicts
        if any(m.status == MemoryStatus.CONFLICTED for m in memories):
            logger.info("Alias '%s' has conflicting targets; gating resolution.", clean_key)
            return None

        # Filter to active memories
        active_memories = [m for m in memories if m.status == MemoryStatus.ACTIVE]
        if not active_memories:
            return None

        # Sort: user_confirmed first, then highest confidence
        active_memories.sort(key=lambda m: (m.user_confirmed, m.confidence), reverse=True)
        top = active_memories[0]

        # Verify type safety if expected_target_type is supplied
        if expected_target_type and top.target_type != expected_target_type:
            logger.warning(
                "Alias '%s' target_type mismatch: expected %s, found %s",
                clean_key, expected_target_type, top.target_type
            )
            return None

        # Verify non-learnable security policy
        val_str = str(top.value)
        if not self._is_security_safe(val_str):
            logger.error("Blocked learned alias '%s' pointing to unsafe target '%s'", clean_key, val_str)
            return None

        # Tier 2: User-Confirmed Learned Alias
        if top.user_confirmed:
            return val_str, "user_confirmed_alias", top.confidence

        # Tier 3: High-Confidence Learned Alias
        if top.confidence >= 0.85:
            return val_str, "learned_alias", top.confidence

        return None

    def get_conflicted_candidates(self, alias_key: str) -> list[SemanticMemory]:
        """Return candidate memories if alias is in a conflicted state."""
        clean_key = alias_key.strip().lower()
        memories = self.memory_store.persistence.find_memories(
            namespace=MemoryNamespace.ALIAS,
            key=clean_key,
        )
        return [m for m in memories if m.status in {MemoryStatus.CONFLICTED, MemoryStatus.ACTIVE, MemoryStatus.CANDIDATE}]

    def teach_alias(
        self,
        alias_key: str,
        target_value: str,
        target_type: str = "application",
    ) -> SemanticMemory:
        """
        Explicitly teach a new alias (user-confirmed, pinned).
        """
        clean_key = alias_key.strip().lower()
        clean_val = target_value.strip()

        if not self._is_security_safe(clean_val):
            raise ValueError(f"Target '{clean_val}' violates non-learnable security policies.")

        return self.memory_store.add_or_update_memory(
            namespace=MemoryNamespace.ALIAS,
            key=clean_key,
            value=clean_val,
            target_type=target_type,
            user_confirmed=True,
            pinned=True,
        )

    @staticmethod
    def _is_security_safe(target: str) -> bool:
        """Enforce non-learnable security invariant on targets."""
        clean = target.strip().lower()
        if clean in PROTECTED_PROCESSES:
            return False
        return True
