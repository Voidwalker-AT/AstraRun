"""Offline Dataset Builder for AstraRun Learning Foundation.

Exports sanitized JSONL training/evaluation datasets from verified task histories
and semantic memories ONLY when explicitly authorized. Performs ZERO online training.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional, Sequence

from astrarun.core.logging import get_logger
from astrarun.learning.models import SemanticMemory
from astrarun.tasks.models import Task

logger = get_logger("astrarun.learning.dataset_builder")

# Sensitive token sanitization patterns
TOKEN_PATTERNS = [
    re.compile(r"\b(?:sk-[a-zA-Z0-9_-]{20,})\b"),
    re.compile(r"\b(?:ghp_[a-zA-Z0-9]{36})\b"),
    re.compile(r"\b(?:bearer\s+[a-zA-Z0-9_\-\.]{20,})\b", re.IGNORECASE),
    re.compile(r"\b(?:password|passwd|pwd)\s*[=:]\s*[^\s]+", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9+/]{40,}={0,2}"),  # Generic base64 blobs
]

USER_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[Uu]sers\\[^\\]+", re.IGNORECASE)


class DatasetBuilder:
    """
    Sanitizes and exports offline JSONL datasets from historical task evidence.
    """

    def __init__(self, allow_export: bool = False) -> None:
        self.allow_export = allow_export

    def sanitize_text(self, text: str) -> str:
        """Strip secrets and normalize user paths."""
        sanitized = text
        for pat in TOKEN_PATTERNS:
            sanitized = pat.sub("[REDACTED_SECRET]", sanitized)
        sanitized = USER_PATH_PATTERN.sub(r"C:\\Users\\User", sanitized)
        return sanitized

    def build_dataset(
        self,
        tasks: Sequence[Task],
        memories: Sequence[SemanticMemory],
        output_file: Path | str = "data/learning_dataset.jsonl",
        force: bool = False,
    ) -> int:
        """
        Export verified task and memory pairs to JSONL format.
        Refuses to run unless allow_export is True or force is True.
        """
        if not self.allow_export and not force:
            logger.warning("Dataset export blocked: 'allow_training_dataset_export' is False")
            raise PermissionError("Dataset export is disabled by configuration.")

        out_path = Path(output_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        count = 0
        with open(out_path, "w", encoding="utf-8") as f:
            # 1. Export confirmed semantic memories
            for m in memories:
                if m.user_confirmed or m.confidence >= 0.85:
                    entry = {
                        "type": "memory",
                        "namespace": m.namespace.value,
                        "key": self.sanitize_text(m.key),
                        "value": self.sanitize_text(str(m.value)),
                        "target_type": m.target_type,
                        "confidence": m.confidence,
                        "support_count": m.support_count,
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    count += 1

            # 2. Export successful completed task mappings
            for t in tasks:
                if t.final_result and t.final_result.success and t.request_text:
                    entry = {
                        "type": "task",
                        "request": self.sanitize_text(t.request_text),
                        "capabilities": t.final_result.capabilities_used,
                        "status": t.status.value,
                    }
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    count += 1

        logger.info("Exported %d sanitized training/eval entries to %s", count, out_path)
        return count
