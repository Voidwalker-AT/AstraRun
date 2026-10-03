"""Resource and Performance QoS Governor for AstraRun 1.0.

Enforces workload prioritization, memory degradation protection, and below-normal
background thread/process scheduling to ensure Windows remains silky smooth.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import psutil

from astrarun.core.logging import get_logger
from astrarun.machine.resource_snapshot import ResourceSnapshot

logger = get_logger("astrarun.core.qos")


class WorkloadQoS(str, Enum):
    """Workload execution tier defining priority and resource allocation."""
    INTERACTIVE = "INTERACTIVE"          # Qt UI, Alt+Space HUD, user takeover, lightweight routing
    ACTIVE_TASK = "ACTIVE_TASK"          # Direct task step execution, browser automation, dynamic scripts
    BACKGROUND = "BACKGROUND"            # RAG document indexing, asset downloads, stable-fact discovery
    IDLE_MAINTENANCE = "IDLE_MAINTENANCE"  # SQLite VACUUM, index defragmentation, log compaction


@dataclass
class QoSHealthState:
    """Current resource health and throttling verdict."""
    ram_pressure: bool = False
    vram_pressure: bool = False
    cpu_pressure: bool = False
    background_paused: bool = False
    concurrency_limit: int = 4
    evict_models_recommended: bool = False


class ResourceGovernor:
    """Monitors live resource pressure and regulates concurrency and priority."""

    _instance: Optional[ResourceGovernor] = None

    def __init__(
        self,
        min_ram_headroom_gb: float = 2.0,
        min_vram_headroom_gb: float = 1.0,
        max_cpu_percent: float = 85.0,
    ) -> None:
        self.min_ram_headroom_gb = min_ram_headroom_gb
        self.min_vram_headroom_gb = min_vram_headroom_gb
        self.max_cpu_percent = max_cpu_percent
        self._background_paused: bool = False

    @classmethod
    def get_instance(cls) -> ResourceGovernor:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def evaluate_health(self) -> QoSHealthState:
        """Evaluate instantaneous resource health and determine throttling directives."""
        snap = ResourceSnapshot.capture(include_gpu=True)

        ram_press = snap.available_ram_gb < self.min_ram_headroom_gb
        vram_press = snap.has_cuda_gpu and (snap.free_vram_gb < self.min_vram_headroom_gb)
        cpu_press = snap.cpu_percent > self.max_cpu_percent

        # If system is under severe memory pressure, throttle background work
        if ram_press or vram_press:
            self._background_paused = True
            concurrency = 1
        elif cpu_press:
            self._background_paused = False
            concurrency = 2
        else:
            self._background_paused = False
            concurrency = 4

        state = QoSHealthState(
            ram_pressure=ram_press,
            vram_pressure=vram_press,
            cpu_pressure=cpu_press,
            background_paused=self._background_paused,
            concurrency_limit=concurrency,
            evict_models_recommended=vram_press or (ram_press and snap.available_ram_gb < 1.0),
        )

        if ram_press or vram_press:
            logger.warning(
                "[QOS_GOVERNOR] Resource pressure detected: RAM=%.2fGB free, VRAM=%.2fGB free. Throttling background work.",
                snap.available_ram_gb, snap.free_vram_gb,
            )

        return state

    def apply_background_priority(self) -> None:
        """Lower CPU priority of background worker thread/process on Windows."""
        if sys.platform != "win32":
            return
        try:
            p = psutil.Process()
            # Set to below normal priority so interactive UI always stays responsive
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            logger.debug("Applied BELOW_NORMAL_PRIORITY_CLASS to background worker process.")
        except Exception as e:
            logger.debug("Could not adjust process priority: %s", e)

    def restore_normal_priority(self) -> None:
        """Restore process priority to NORMAL_PRIORITY_CLASS."""
        if sys.platform != "win32":
            return
        try:
            p = psutil.Process()
            p.nice(psutil.NORMAL_PRIORITY_CLASS)
            logger.debug("Restored NORMAL_PRIORITY_CLASS to process.")
        except Exception as e:
            logger.debug("Could not restore process priority: %s", e)

    def can_run_background_work(self) -> bool:
        """Check if background indexing or maintenance is permitted to proceed."""
        health = self.evaluate_health()
        return not health.background_paused
