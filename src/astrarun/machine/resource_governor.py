"""Adaptive Resource Governor for AstraRun 1.0.

Monitors host RAM, VRAM, CPU load, and active job counts to dynamically
throttle and serialize heavy model or sandbox workloads, protecting system
stability on memory-constrained workstations (e.g. RTX 2050 4GB / 16GB RAM).
"""

from __future__ import annotations

import gc
import threading
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.machine.resource_snapshot import ResourceSnapshot

logger = get_logger("astrarun.machine.resource_governor")


class GovernorDecision(str, Enum):
    """Authoritative operational decisions emitted by ResourceGovernor."""
    NORMAL = "NORMAL"
    SERIALIZE_HEAVY_WORK = "SERIALIZE_HEAVY_WORK"
    PAUSE_BACKGROUND_WORK = "PAUSE_BACKGROUND_WORK"
    DEFER_NONESSENTIAL_MODEL_LOAD = "DEFER_NONESSENTIAL_MODEL_LOAD"
    LOW_MEMORY_EXECUTION_PROFILE = "LOW_MEMORY_EXECUTION_PROFILE"


@dataclass
class GovernorEvent:
    """Historical audit record of an adaptation decision."""
    timestamp: float
    decision: GovernorDecision
    reason: str
    ram_used_percent: float
    available_ram_gb: float
    free_vram_gb: float
    cpu_percent: float
    active_sandboxes: int
    active_models: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "decision": self.decision.value,
            "reason": self.reason,
            "ram_used_percent": self.ram_used_percent,
            "available_ram_gb": self.available_ram_gb,
            "free_vram_gb": self.free_vram_gb,
            "cpu_percent": self.cpu_percent,
            "active_sandboxes": self.active_sandboxes,
            "active_models": self.active_models,
        }


class ResourceGovernor:
    """Authoritative singleton governor managing compute resource pressure."""

    _instance: Optional[ResourceGovernor] = None

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_sandboxes = 0
        self._active_models = 0
        self.decision_history: List[GovernorEvent] = []

    @classmethod
    def get_instance(cls) -> ResourceGovernor:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_sandbox_start(self) -> None:
        with self._lock:
            self._active_sandboxes += 1

    def register_sandbox_end(self) -> None:
        with self._lock:
            if self._active_sandboxes > 0:
                self._active_sandboxes -= 1

    def register_model_start(self) -> None:
        with self._lock:
            self._active_models += 1

    def register_model_end(self) -> None:
        with self._lock:
            if self._active_models > 0:
                self._active_models -= 1

    def assess_state(
        self,
        target_workload: str = "sandbox_execution",
        snapshot_override: Optional[ResourceSnapshot] = None,
    ) -> Tuple[GovernorDecision, str]:
        """
        Evaluate current host resources and emit a bounded operational decision.
        Records every governor decision and reason into audit history.
        """
        snap = snapshot_override or ResourceSnapshot.capture(include_gpu=True)
        now = time.time()

        with self._lock:
            active_s = self._active_sandboxes
            active_m = self._active_models

        # 1. Critical Low Memory Profile (< 2.0 GB RAM free or > 88% utilized)
        if snap.available_ram_gb < 2.0 or snap.ram_used_percent > 88.0:
            gc.collect()
            decision = GovernorDecision.LOW_MEMORY_EXECUTION_PROFILE
            reason = (
                f"Critical host RAM pressure: {snap.ram_used_percent:.1f}% used "
                f"({snap.available_ram_gb:.2f} GB free). Single-thread sandbox profile enforced."
            )

        # 2. Battery / Power Constraint
        elif not snap.power_plugged and snap.battery_percent is not None and snap.battery_percent < 20.0:
            decision = GovernorDecision.PAUSE_BACKGROUND_WORK
            reason = f"Battery critically low ({snap.battery_percent:.1f}%) and on battery power. Background tasks deferred."

        # 3. Workload Serialization (RTX 2050 4GB / 16GB RAM preference)
        # If available RAM is tight (< 3.5 GB), VRAM is tight (< 1.0 GB), or another sandbox is active
        elif (
            snap.available_ram_gb < 3.5
            or (snap.has_cuda_gpu and snap.free_vram_gb < 1.0)
            or active_s > 0
            or snap.cpu_percent > 85.0
        ):
            decision = GovernorDecision.SERIALIZE_HEAVY_WORK
            reason = (
                f"Resource limits warrant serialization: {active_s} active sandboxes, "
                f"RAM free {snap.available_ram_gb:.2f} GB, VRAM free {snap.free_vram_gb:.2f} GB, CPU {snap.cpu_percent:.1f}%."
            )

        # 4. Defer non-essential model load
        elif target_workload == "model_load" and snap.has_cuda_gpu and snap.free_vram_gb < 1.2:
            decision = GovernorDecision.DEFER_NONESSENTIAL_MODEL_LOAD
            reason = f"Insufficient free VRAM ({snap.free_vram_gb:.2f} GB) to safely initialize additional model backend."

        # 5. Normal operation
        else:
            decision = GovernorDecision.NORMAL
            reason = (
                f"System resources healthy: {snap.available_ram_gb:.2f} GB RAM free, "
                f"{snap.free_vram_gb:.2f} GB VRAM free, CPU {snap.cpu_percent:.1f}%."
            )

        event = GovernorEvent(
            timestamp=now,
            decision=decision,
            reason=reason,
            ram_used_percent=snap.ram_used_percent,
            available_ram_gb=snap.available_ram_gb,
            free_vram_gb=snap.free_vram_gb,
            cpu_percent=snap.cpu_percent,
            active_sandboxes=active_s,
            active_models=active_m,
        )

        with self._lock:
            self.decision_history.append(event)
            # Bound history size
            if len(self.decision_history) > 200:
                self.decision_history = self.decision_history[-100:]

        logger.info("ResourceGovernor decision: %s (%s)", decision.value, reason)
        return decision, reason

    def get_recent_events(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self.decision_history[-limit:]]
