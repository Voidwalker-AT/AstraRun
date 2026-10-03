"""Domain models and compatibility classifications for existing workstation capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class CompatibilityStatus(str, Enum):
    """Compatibility classification for an existing workstation asset."""
    EXACT_MATCH = "EXACT_MATCH"
    COMPATIBLE_VERSION = "COMPATIBLE_VERSION"
    USABLE_FALLBACK = "USABLE_FALLBACK"
    INCOMPATIBLE = "INCOMPATIBLE"
    MISSING = "MISSING"


@dataclass
class ExistingCapabilityCandidate:
    """Represents an existing local tool, runtime, browser, or AI model candidate."""
    id: str
    name: str
    category: str  # "model", "runtime", "tool", "browser"
    path: Optional[Path] = None
    version: Optional[str] = None
    status: CompatibilityStatus = CompatibilityStatus.MISSING
    size_bytes: int = 0
    sha256: Optional[str] = None
    details: str = ""
    is_recommended: bool = False
    reuse_action: str = ""
    user_choice: str = "use_existing"  # "use_existing", "download_fresh", "custom_path"

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024.0 * 1024.0)

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024.0 * 1024.0 * 1024.0)

    @property
    def is_available(self) -> bool:
        return (
            self.status in {CompatibilityStatus.EXACT_MATCH, CompatibilityStatus.COMPATIBLE_VERSION, CompatibilityStatus.USABLE_FALLBACK}
            and self.path is not None
            and self.path.exists()
        )
