"""Learning Engine Orchestrator for AstraRun Learning Foundation.

Coordinates background evidence extraction, semantic memory accumulation,
alias resolution, pattern mining, and skill proposals completely off the hot path.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, Optional, Sequence

from astrarun.core.logging import get_logger
from astrarun.learning.aliases import AliasManager
from astrarun.learning.confidence import ConfidenceCalculator
from astrarun.learning.evidence import EvidenceExtractor
from astrarun.learning.memory import MemoryStore
from astrarun.learning.models import (
    MemoryNamespace,
    MemoryStatus,
    SemanticMemory,
    SkillCandidate,
)
from astrarun.learning.patterns import PatternMiner
from astrarun.learning.persistence import LearningPersistence
from astrarun.learning.skills import SkillManager
from astrarun.tasks.models import Task, TaskEvent

logger = get_logger("astrarun.learning.engine")


class LearningEngine:
    """
    High-level background coordinator for workstation learning, aliases, and skills.
    Guarantees 0ms overhead on interactive launcher hot path.
    """

    def __init__(
        self,
        config: Optional[dict[str, Any]] = None,
        persistence: Optional[LearningPersistence] = None,
        memory_store: Optional[MemoryStore] = None,
        alias_manager: Optional[AliasManager] = None,
        skill_manager: Optional[SkillManager] = None,
        evidence_extractor: Optional[EvidenceExtractor] = None,
        pattern_miner: Optional[PatternMiner] = None,
    ) -> None:
        self.config = config or {}
        self.enabled = self.config.get("enabled", True)
        self.learn_from_history = self.config.get("learn_from_history", True)
        self.auto_propose_skills = self.config.get("auto_propose_skills", True)

        db_path = self.config.get("db_path", "data/astra_learning.db")
        self.persistence = persistence or LearningPersistence(db_path=db_path)

        conf_threshold = float(self.config.get("confidence_threshold", 0.85))
        min_support = int(self.config.get("min_support_count", 3))
        self.calculator = ConfidenceCalculator(
            promotion_threshold=conf_threshold,
            min_support_count=min_support,
        )

        self.memory_store = memory_store or MemoryStore(
            persistence=self.persistence,
            calculator=self.calculator,
        )
        self.alias_manager = alias_manager or AliasManager(
            memory_store=self.memory_store,
        )
        self.skill_manager = skill_manager or SkillManager(
            persistence=self.persistence,
        )
        self.evidence_extractor = evidence_extractor or EvidenceExtractor()
        self.pattern_miner = pattern_miner or PatternMiner(
            min_support=min_support,
        )

        self._last_task: Optional[Task] = None
        self._lock = threading.Lock()

    def ingest_task_async(self, task: Task) -> None:
        """
        Non-blocking ingestion hook called when a task finishes.
        Dispatches processing to a daemon thread to guarantee 0ms hot-path delay.
        """
        if not self.enabled or not self.learn_from_history:
            return

        thread = threading.Thread(
            target=self.ingest_task,
            args=(task,),
            name=f"astrarun-learning-{task.id[:8]}",
            daemon=True,
        )
        thread.start()

    def ingest_task(self, task: Task) -> None:
        """
        Synchronous task ingestion extracting teaching, corrections, and evidence.
        """
        if not self.enabled:
            return

        with self._lock:
            try:
                # 1. Check for explicit teaching statements
                teaching_mem = self.evidence_extractor.extract_teaching(task)
                if teaching_mem:
                    self.memory_store.persistence.save_memory(teaching_mem)
                    logger.info("Learned explicit teaching: '%s' = '%s'", teaching_mem.key, teaching_mem.value)
                    self._last_task = task
                    return

                # 2. Check for user corrections against previous task
                if self._last_task:
                    correction = self.evidence_extractor.detect_correction(self._last_task, task)
                    if correction:
                        self.memory_store.apply_correction(correction)
                        logger.info("Detected and applied user correction: %s", correction.id)

                # 3. Extract standard evidence references from task events
                evidence_items = self.evidence_extractor.extract_task_evidence(task)
                for key, target, ref in evidence_items:
                    # Clean key: if key was a full user query like "open calculator", extract entity
                    clean_key = self._extract_subject_key(key)
                    if clean_key:
                        self.memory_store.add_or_update_memory(
                            namespace=MemoryNamespace.ALIAS,
                            key=clean_key,
                            value=target,
                            target_type="application",
                            evidence_ref=ref,
                        )

                self._last_task = task

            except Exception as err:
                logger.error("Error during task ingestion in LearningEngine: %s", err, exc_info=True)

    def mine_and_propose_skills(self, task_history: Sequence[Task]) -> list[SkillCandidate]:
        """
        Mine repetitive patterns from task history and submit them as proposed skills.
        """
        if not self.enabled or not self.auto_propose_skills:
            return []

        candidates = self.pattern_miner.mine_patterns(task_history)
        proposed: list[SkillCandidate] = []

        for cand in candidates:
            # Check if skill with this name already exists
            existing = self.skill_manager.list_skills()
            if any(s.name == cand.name for s in existing):
                continue
            p = self.skill_manager.propose_skill(cand)
            proposed.append(p)

        return proposed

    def teach(self, statement: str) -> Optional[SemanticMemory]:
        """
        Programmatic teaching interface.
        """
        dummy_task = Task(
            id=f"teach_{int(time.time())}",
            conversation_id="explicit_teaching",
            request_text=statement,
        )
        mem = self.evidence_extractor.extract_teaching(dummy_task)
        if mem:
            self.memory_store.persistence.save_memory(mem)
            return mem
        return None

    def resolve_alias(
        self,
        alias_key: str,
        expected_target_type: Optional[str] = None,
    ) -> Optional[tuple[str, str, float]]:
        """
        Resolve an alias through AliasManager.
        """
        if not self.enabled:
            return None
        return self.alias_manager.resolve(alias_key, expected_target_type=expected_target_type)

    def clear_all(self) -> None:
        """Wipe all learned data."""
        self.memory_store.persistence.clear_all_learning()

    @staticmethod
    def _extract_subject_key(query: str) -> Optional[str]:
        """Extract core subject from a query for alias binding."""
        clean = query.strip().lower()
        if not clean:
            return None
        # Remove common prefixes like "open", "launch", "start", "run"
        for prefix in ["open ", "launch ", "start ", "run ", "show "]:
            if clean.startswith(prefix):
                clean = clean[len(prefix):].strip()
                break
        return clean if clean else None
