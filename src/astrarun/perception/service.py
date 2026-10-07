"""Unified Perception Service and Observation Router for AstraRun.

Implements the structured perception escalation hierarchy:
Win32 / UIA -> COM -> DOM / CDP -> OCR -> Classical CV -> Visual Grounder (OmniParser) -> VLM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from astrarun.capabilities.models import CapabilityResult
from astrarun.perception.router import PerceptionRouter
from astrarun.perception.models import PerceptionTier, UIElementObservation

logger = logging.getLogger("astrarun.perception.service")


class PerceptionService:
    """Canonical perception engine coordinating structured UI observations."""

    _instance: Optional[PerceptionService] = None

    def __init__(self, router: Optional[PerceptionRouter] = None) -> None:
        self.router = router or PerceptionRouter()

    @classmethod
    def get_instance(cls) -> PerceptionService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def observe_window(
        self,
        hwnd: int,
        target_name: Optional[str] = None,
        timeout_sec: float = 2.0,
    ) -> List[Dict[str, Any]]:
        """
        Query window elements through the cheapest viable perception tier (UIA first).
        Returns normalized list of element observations.
        """
        # First try UIA observation via native Windows UIA tree
        try:
            from astrarun.interaction.discovery import inspect_window_ui
            uia_elements = inspect_window_ui(hwnd=hwnd, max_elements=50)
            if uia_elements:
                logger.debug("Observed %d elements in HWND %d via Tier 3 (UIA)", len(uia_elements), hwnd)
                return [
                    {
                        "name": getattr(e, "name", ""),
                        "control_type": e.control_type.value if hasattr(getattr(e, "control_type", None), "value") else str(getattr(e, "control_type", "")),
                        "bounds": getattr(e, "bounds", None),
                        "automation_id": getattr(e, "automation_id", ""),
                        "tier": "UIA",
                    }
                    for e in uia_elements
                ]
        except Exception as err:
            logger.debug("Tier 3 UIA observation error: %s; falling back to Router", err)

        # Fallback to perception router ladder
        try:
            obs_list, gen, tier = self.router.observe_window(hwnd=hwnd, target_name=target_name, timeout_sec=timeout_sec)
            return [
                {
                    "name": getattr(o, "name", ""),
                    "control_type": getattr(o, "control_type", "custom"),
                    "bounds": [o.bbox.x, o.bbox.y, o.bbox.width, o.bbox.height] if getattr(o, "bbox", None) else None,
                    "tier": tier.value if hasattr(tier, "value") else str(tier),
                }
                for o in obs_list
            ]
        except Exception as err:
            logger.warning("PerceptionRouter observation failed: %s", err)
            return []
