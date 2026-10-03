"""MachineFact schema, freshness classes, and authority enumeration for AstraRun 1.0.

Provides strongly typed, provenanced, and freshness-aware representations of
workstation hardware, OS, software, and resource observations.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class FreshnessClass(str, Enum):
    """Temporal volatility classes for machine facts."""
    IMMUTABLE = "IMMUTABLE"  # CPU physical architecture, silicon features
    STABLE = "STABLE"        # CPU model, total RAM, Windows build, GPU model (24h TTL)
    SESSION = "SESSION"      # Installed applications, display topology, driver versions (1h TTL)
    VOLATILE = "VOLATILE"    # Available RAM, free disk space, battery level (30s TTL)
    REALTIME = "REALTIME"    # Free VRAM, foreground window, instantaneous process CPU (2s TTL)


class FactAuthority(str, Enum):
    """Authoritative source of observed machine facts."""
    OS_API = "OS_API"                        # Native Win32 / kernel APIs
    WMI_CIM = "WMI_CIM"                      # Windows Management Instrumentation / CIM
    NVIDIA_NVML = "NVIDIA_NVML"              # NVML / CUDA driver queries
    REGISTRY = "REGISTRY"                    # Windows Registry inspection
    FILESYSTEM = "FILESYSTEM"                # Path / filesystem metadata
    PROCESS_INSPECTION = "PROCESS_INSPECTION"  # psutil / Job Object / process queries
    APPLICATION_PROBE = "APPLICATION_PROBE"  # Headless version probe (e.g. tool --version)
    USER_DECLARED = "USER_DECLARED"          # Explicit user configuration
    INFERRED = "INFERRED"                    # Derived / synthesized predicates


class FactSensitivity(str, Enum):
    """Privacy and exposure boundaries for machine facts."""
    PUBLIC = "PUBLIC"                        # Safe for external context (e.g. GPU model, RAM size)
    INTERNAL = "INTERNAL"                    # Used locally within Astra planner/runtime
    CONFIDENTIAL_LOCAL_ONLY = "CONFIDENTIAL_LOCAL_ONLY"  # Never leave workstation (e.g. volume serials, exact paths)


# Default TTLs (in seconds) by freshness class
DEFAULT_TTLS: Dict[FreshnessClass, Optional[float]] = {
    FreshnessClass.IMMUTABLE: None,
    FreshnessClass.STABLE: 86400.0,    # 24 hours
    FreshnessClass.SESSION: 3600.0,    # 1 hour
    FreshnessClass.VOLATILE: 30.0,     # 30 seconds
    FreshnessClass.REALTIME: 2.0,      # 2 seconds
}


@dataclass
class MachineFact:
    """Strongly typed machine fact with provenance and freshness."""
    key: str
    value: Any
    unit: Optional[str] = None
    source: FactAuthority = FactAuthority.OS_API
    observed_at: float = field(default_factory=time.time)
    freshness_class: FreshnessClass = FreshnessClass.STABLE
    ttl_sec: Optional[float] = None
    confidence: float = 1.0
    authority: str = "AUTHORITATIVE"  # AUTHORITATIVE, PROBED, ESTIMATED
    sensitivity: FactSensitivity = FactSensitivity.INTERNAL
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.ttl_sec is None:
            self.ttl_sec = DEFAULT_TTLS.get(self.freshness_class)

    def is_fresh(self, now: Optional[float] = None) -> bool:
        """Return True if fact is within its freshness TTL window."""
        if self.freshness_class == FreshnessClass.IMMUTABLE or self.ttl_sec is None:
            return True
        current_time = now if now is not None else time.time()
        return (current_time - self.observed_at) <= self.ttl_sec

    def needs_refresh(self, now: Optional[float] = None) -> bool:
        """Return True if fact has expired and requires updated observation."""
        return not self.is_fresh(now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> MachineFact:
        d = dict(data)
        if "freshness_class" in d and isinstance(d["freshness_class"], str):
            d["freshness_class"] = FreshnessClass(d["freshness_class"])
        if "source" in d and isinstance(d["source"], str):
            d["source"] = FactAuthority(d["source"])
        if "sensitivity" in d and isinstance(d["sensitivity"], str):
            d["sensitivity"] = FactSensitivity(d["sensitivity"])
        return cls(**d)
