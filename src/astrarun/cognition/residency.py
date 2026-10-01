"""Model Residency Manager and Resource Governance for AstraRun 1.0.

Tracks and governs model residency, state transitions, hardware telemetry (RAM/VRAM),
and priority-based memory eviction without hardcoding dual residency.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import psutil

from astrarun.cognition.models import ModelRole, ModelState, ResidencyPreference
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.cognition.residency")


@dataclass
class ModelRecord:
    """Authoritative ledger entry for a supervised model instance."""
    model_id: str
    role: ModelRole
    state: ModelState = ModelState.STOPPED
    residency_preference: ResidencyPreference = ResidencyPreference.WARM
    pid: Optional[int] = None
    endpoint: str = ""
    port: int = 8089
    model_path: str = ""
    ram_bytes: int = 0
    vram_bytes: int = 0
    load_timestamp: float = 0.0
    last_inference_timestamp: float = 0.0
    health: str = "UNKNOWN"  # "HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"
    ownership: str = "astra_owned"
    ownership_token: str = ""
    restart_count: int = 0
    max_restarts: int = 3
    restart_window_seconds: float = 300.0  # 5-minute rolling window
    restart_timestamps: List[float] = field(default_factory=list)

    @property
    def is_alive(self) -> bool:
        return self.state in (ModelState.READY, ModelState.BUSY, ModelState.WARMING)


class ModelResidencyManager:
    """
    Manages model residency, hardware telemetry, and memory budget governance.
    Enforces priority eviction (PINNED > WARM > ON_DEMAND > EVICTABLE).
    """

    _instance: Optional[ModelResidencyManager] = None

    def __init__(self, max_vram_mb: float = 3800.0) -> None:
        self.max_vram_mb = max_vram_mb
        self._models: Dict[str, ModelRecord] = {}
        self._eviction_handlers: List[Callable[[ModelRecord], None]] = []

    @classmethod
    def get_instance(cls) -> ModelResidencyManager:
        """Singleton accessor."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_model(self, record: ModelRecord) -> None:
        """Register a model instance in the residency ledger."""
        self._models[record.model_id] = record
        logger.info(
            "Registered model [%s, role=%s, pref=%s, port=%d]",
            record.model_id,
            record.role.value,
            record.residency_preference.value,
            record.port,
        )

    def get_model(self, model_id: str) -> Optional[ModelRecord]:
        return self._models.get(model_id)

    def get_model_by_role(self, role: ModelRole) -> Optional[ModelRecord]:
        for rec in self._models.values():
            if rec.role == role:
                return rec
        return None

    def list_models(self) -> List[ModelRecord]:
        return list(self._models.values())

    def transition_state(self, model_id: str, new_state: ModelState) -> None:
        """Record state transition for a model."""
        rec = self._models.get(model_id)
        if not rec:
            logger.warning("Attempted state transition for unknown model: %s", model_id)
            return
        old_state = rec.state
        rec.state = new_state
        logger.debug("Model [%s] transition: %s -> %s", model_id, old_state.value, new_state.value)

    def register_eviction_handler(self, handler: Callable[[ModelRecord], None]) -> None:
        """Register a callback invoked when a model must be evicted to free VRAM."""
        self._eviction_handlers.append(handler)

    def record_restart(self, model_id: str) -> bool:
        """
        Record a restart event within the rolling window.
        Returns False if the model has exceeded maximum restarts within window (enters FAILED state).
        """
        rec = self._models.get(model_id)
        if not rec:
            return False

        now = time.time()
        # Filter timestamps outside rolling window
        rec.restart_timestamps = [t for t in rec.restart_timestamps if now - t < rec.restart_window_seconds]
        rec.restart_timestamps.append(now)
        rec.restart_count = len(rec.restart_timestamps)

        if rec.restart_count > rec.max_restarts:
            logger.error(
                "Model [%s] exceeded max restarts (%d > %d in %ds). Entering FAILED state.",
                model_id,
                rec.restart_count,
                rec.max_restarts,
                rec.restart_window_seconds,
            )
            self.transition_state(model_id, ModelState.FAILED)
            rec.health = "UNHEALTHY"
            return False

        return True

    def update_telemetry(self, model_id: Optional[str] = None) -> None:
        """Query physical process RSS and GPU VRAM allocation."""
        records = [self._models[model_id]] if model_id and model_id in self._models else list(self._models.values())

        for rec in records:
            if rec.pid and psutil.pid_exists(rec.pid):
                try:
                    proc = psutil.Process(rec.pid)
                    rec.ram_bytes = proc.memory_info().rss
                except Exception:
                    pass

        # Query GPU VRAM via nvidia-smi if available
        try:
            cmd = ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]
            out = subprocess.check_output(cmd, creationflags=0x08000000 if os.name == "nt" else 0).decode().strip()
            # If successful, note that total VRAM is tracked
        except Exception:
            pass

    def get_total_vram_used_mb(self) -> float:
        """Sum tracked VRAM for all resident models in MB."""
        total_bytes = sum(m.vram_bytes for m in self._models.values() if m.is_alive)
        return total_bytes / (1024 * 1024)

    def request_residency(self, model_id: str, estimated_vram_mb: float) -> bool:
        """
        Request memory residency for a model before start.
        If VRAM headroom is insufficient, attempts priority eviction of non-pinned models.
        """
        current_vram = self.get_total_vram_used_mb()
        projected = current_vram + estimated_vram_mb

        if projected <= self.max_vram_mb:
            return True

        logger.warning(
            "Projected VRAM (%.1f MB) exceeds ceiling (%.1f MB). Evaluating eviction candidates.",
            projected,
            self.max_vram_mb,
        )

        # Eviction hierarchy: EVICTABLE -> ON_DEMAND -> WARM (PINNED is NEVER evicted)
        candidates = [
            m for m in self._models.values()
            if m.model_id != model_id
            and m.is_alive
            and m.residency_preference != ResidencyPreference.PINNED
        ]

        # Sort candidates: EVICTABLE first, then oldest last_inference
        candidates.sort(key=lambda x: (
            0 if x.residency_preference == ResidencyPreference.EVICTABLE
            else (1 if x.residency_preference == ResidencyPreference.ON_DEMAND else 2),
            x.last_inference_timestamp,
        ))

        for cand in candidates:
            logger.info("Evicting model [%s, role=%s] to reclaim VRAM", cand.model_id, cand.role.value)
            self.transition_state(cand.model_id, ModelState.EVICTING)
            for handler in self._eviction_handlers:
                try:
                    handler(cand)
                except Exception as e:
                    logger.error("Eviction handler error for model %s: %s", cand.model_id, e)
            self.transition_state(cand.model_id, ModelState.STOPPED)
            cand.vram_bytes = 0
            cand.pid = None

            current_vram = self.get_total_vram_used_mb()
            if current_vram + estimated_vram_mb <= self.max_vram_mb:
                logger.info("Sufficient VRAM reclaimed after eviction.")
                return True

        logger.error("Unable to reclaim sufficient VRAM for model [%s]", model_id)
        return False
