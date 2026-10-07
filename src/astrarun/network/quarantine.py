"""Download Quarantine Manager for AstraRun 1.0.

Stages downloaded external artifacts in an isolated quarantine directory with
cryptographic metadata. Disallows automatic execution of downloaded binaries
and scripts.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.network.quarantine")


@dataclass
class QuarantineRecord:
    """Metadata recorded for every quarantined artifact."""
    quarantine_id: str
    filename: str
    original_url: str
    sha256: str
    size_bytes: int
    content_type: str
    downloaded_at: float
    local_path: str
    meta_path: str
    status: str = "QUARANTINED"  # QUARANTINED, INSPECTED, APPROVED_FOR_READ, REJECTED
    execution_permitted: bool = False
    audit_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> QuarantineRecord:
        return cls(**d)


class DownloadQuarantine:
    """Authoritative staging boundary for external downloads."""

    def __init__(self, quarantine_dir: Optional[Path] = None) -> None:
        from astrarun.core.paths import AstraPaths
        self.quarantine_dir = Path(quarantine_dir or (AstraPaths.data_dir() / "quarantine")).resolve()
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

    def stage_file(
        self,
        content: bytes,
        filename: str,
        source_url: str,
        content_type: str = "application/octet-stream",
    ) -> QuarantineRecord:
        """Stage raw downloaded bytes into quarantine with metadata sidecar."""
        sha256 = hashlib.sha256(content).hexdigest()
        qid = f"quar_{uuid.uuid4().hex[:8]}"

        # Organize in hashed subfolder to avoid collisions
        target_dir = self.quarantine_dir / sha256[:12]
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = target_dir / filename
        target_file.write_bytes(content)

        meta_file = target_dir / f"{filename}.meta.json"
        record = QuarantineRecord(
            quarantine_id=qid,
            filename=filename,
            original_url=source_url,
            sha256=sha256,
            size_bytes=len(content),
            content_type=content_type,
            downloaded_at=time.time(),
            local_path=str(target_file),
            meta_path=str(meta_file),
            status="QUARANTINED",
            execution_permitted=False,
            audit_notes=["Downloaded into governed quarantine. Auto-execution strictly disabled."],
        )

        meta_file.write_text(json.dumps(record.to_dict(), indent=2), encoding="utf-8")
        logger.info("Artifact quarantined: %s (SHA256=%s, Size=%d)", filename, sha256[:8], len(content))
        return record

    def get_record(self, meta_path: Path | str) -> Optional[QuarantineRecord]:
        """Load quarantine record from sidecar metadata file."""
        p = Path(meta_path)
        if not p.exists():
            return None
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            return QuarantineRecord.from_dict(d)
        except Exception as e:
            logger.error("Failed to load quarantine record %s: %s", meta_path, e)
            return None

    def is_execution_permitted(self, file_path: Path | str) -> bool:
        """Return True only if artifact has explicit human approval to execute."""
        p = Path(file_path).resolve()
        meta_file = p.parent / f"{p.name}.meta.json"
        if not meta_file.exists():
            # If in quarantine directory without metadata, default deny
            if self.quarantine_dir in p.parents:
                return False
            return True

        record = self.get_record(meta_file)
        if not record:
            return False

        return record.execution_permitted and record.status == "APPROVED"
