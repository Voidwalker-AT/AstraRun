"""Sandbox models, profiles, and result schemas for AstraRun 1.0."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class SandboxProfile(str, Enum):
    """Execution containment profiles."""
    EPHEMERAL_TOOL = "EPHEMERAL_TOOL"      # Strictly bounded, temp dir, no network, 15-30s timeout
    WORKSPACE_TEST = "WORKSPACE_TEST"      # Confined to target workspace directory, bounded writes
    RESEARCH_DOWNLOAD = "RESEARCH_DOWNLOAD"  # Quarantine staging only, NO execution permitted


@dataclass
class SandboxConfig:
    """Configuration applied to a contained sandbox run."""
    profile: SandboxProfile = SandboxProfile.EPHEMERAL_TOOL
    working_dir: Optional[Path] = None
    allow_network: bool = False
    timeout_sec: float = 30.0
    memory_limit_bytes: int = 512 * 1024 * 1024  # 512 MB
    stdout_max_bytes: int = 512 * 1024  # 512 KB output cap
    allow_read_paths: List[Path] = field(default_factory=list)
    allow_write_paths: List[Path] = field(default_factory=list)
    preserve_on_exit: bool = False
    extra_env: Dict[str, str] = field(default_factory=dict)
    run_id: str = field(default_factory=lambda: f"sb_{uuid.uuid4().hex[:8]}")


@dataclass
class SandboxResult:
    """Structured result returned from contained sandbox execution."""
    run_id: str
    profile: SandboxProfile
    status: str  # SUCCESS, FAILED, TIMEOUT, DENIED, ERROR
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_ms: float
    peak_memory_mb: float = 0.0
    working_dir: Optional[Path] = None
    created_artifacts: List[Path] = field(default_factory=list)
    redacted: bool = False
    violations: List[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.status == "SUCCESS" and self.exit_code == 0
