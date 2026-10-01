"""Model-independent PerceptionRouter for AstraRun 1.0.

Orchestrates the 9-tier perception escalation hierarchy (Tiers 0–8), stopping
at the cheapest valid tier, maintaining generation tracking for stale element
protection, and logging structured escalation telemetry.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrarun.core.logging import get_logger
from astrarun.perception.capture import ScreenCapture
from astrarun.perception.cdp import CDPProvider
from astrarun.perception.com import COMProvider
from astrarun.perception.cv import ClassicalCVProvider
from astrarun.perception.grounder import VisualGrounder
from astrarun.perception.models import (
    BoundingBox,
    ElementBinding,
    GroundedTargetObservation,
    ObservationGeneration,
    PerceptionTier,
    UIElementObservation,
    VisualSemanticObservation,
    WindowObservation,
)
from astrarun.perception.ocr import OCRProvider
from astrarun.perception.vlm import VisionReasoner
from dataclasses import dataclass

logger = get_logger("astrarun.perception.router")


@dataclass
class PerceptionTelemetry:
    """Structured telemetry event recording perception escalation across tiers."""
    timestamp: float
    hwnd: int
    from_tier: PerceptionTier
    to_tier: PerceptionTier
    reason: str
    target: str


class PerceptionRouter:
    """
    Directs perception requests to the cheapest valid tier and governs element generation bindings.
    """

    def __init__(
        self,
        cdp: Optional[CDPProvider] = None,
        com: Optional[COMProvider] = None,
        ocr: Optional[OCRProvider] = None,
        cv: Optional[ClassicalCVProvider] = None,
        grounder: Optional[VisualGrounder] = None,
        vlm: Optional[VisionReasoner] = None,
        capture: Optional[ScreenCapture] = None,
        enable_simulated: bool = False,
    ):
        self.cdp = cdp or CDPProvider()
        self.com = com or COMProvider(enable_simulated=enable_simulated)
        self.ocr = ocr or OCRProvider()
        self.cv = cv or ClassicalCVProvider()
        self.grounder = grounder or VisualGrounder(enable_simulated=enable_simulated)
        self.vlm = vlm or VisionReasoner(enable_simulated=enable_simulated)
        self.capture = capture or ScreenCapture(enable_simulated=enable_simulated)
        self.enable_simulated = enable_simulated

        self._current_generation_id = 0
        self._active_generations: Dict[int, ObservationGeneration] = {}
        self.escalation_log: List[Dict[str, Any]] = []

    def create_generation(self, hwnd: int, window_bounds: BoundingBox) -> ObservationGeneration:
        """Create and track a new atomic observation generation."""
        self._current_generation_id += 1
        gen = ObservationGeneration(
            generation_id=self._current_generation_id,
            hwnd=hwnd,
            window_bounds=window_bounds,
            created_at=time.time(),
        )
        self._active_generations[gen.generation_id] = gen
        return gen

    def get_generation(self, generation_id: int) -> Optional[ObservationGeneration]:
        """Fetch active observation generation by ID."""
        return self._active_generations.get(generation_id)

    def observe_window(
        self,
        hwnd: int,
        target_name: Optional[str] = None,
        timeout_sec: float = 2.0,
        max_elements: int = 50,
    ) -> Tuple[List[UIElementObservation], ObservationGeneration, PerceptionTier]:
        """
        Observe window controls starting at Tier 3 (UIA), bounded by timeout and element limits.
        Generates compact @e1, @e2 element identifiers.
        """
        from astrarun.interaction.discovery import inspect_window_ui

        t0 = time.perf_counter()
        bounds = BoundingBox(x=100, y=100, width=800, height=600)
        generation = self.create_generation(hwnd, bounds)

        # 1. Attempt Tier 3: Bounded UIA inspection
        raw_elements = inspect_window_ui(
            hwnd=hwnd,
            max_elements=max_elements,
            timeout_sec=timeout_sec,
        )

        ui_observations: List[UIElementObservation] = []
        for idx, el in enumerate(raw_elements, start=1):
            elem_id = f"@e{idx}"
            b = BoundingBox(x=el.bounds[0], y=el.bounds[1], width=el.bounds[2], height=el.bounds[3])
            c_type = el.control_type.value if hasattr(el.control_type, "value") else str(el.control_type)

            obs = UIElementObservation(
                element_id=elem_id,
                hwnd=hwnd,
                pid=el.pid,
                name=el.name or "",
                control_type=c_type,
                automation_id=el.automation_id or "",
                class_name=el.class_name or "",
                bbox=b,
                is_enabled=el.is_enabled,
                is_offscreen=el.is_offscreen,
                supported_patterns=el.supported_patterns,
                depth=el.depth,
                generation_id=generation.generation_id,
            )
            ui_observations.append(obs)

            # Register in generation binding
            binding = ElementBinding(
                semantic_id=elem_id,
                tier=PerceptionTier.TIER_3_UIA,
                hwnd=hwnd,
                pid=el.pid,
                runtime_id=el.automation_id or f"elem_{idx}",
                bbox=b,
                generation_id=generation.generation_id,
                control_type=c_type,
                name=el.name or "",
            )
            generation.bindings[elem_id] = binding

        logger.debug(
            "Perception observed %d elements for HWND %d in %.2f ms",
            len(ui_observations),
            hwnd,
            (time.perf_counter() - t0) * 1000.0,
        )
        return ui_observations, generation, PerceptionTier.TIER_3_UIA

    def resolve_target(
        self,
        hwnd: int,
        target_description: str,
        image_path: Optional[str | Path] = None,
    ) -> Tuple[Optional[BoundingBox], PerceptionTier, str]:
        """
        Escalation cascade resolving a target across tiers:
        Tier 3 UIA -> Tier 4 OCR -> Tier 6 Grounder -> Tier 7 VLM.
        Stops at the cheapest tier providing valid resolution.
        """
        # 1. Tier 3: Structured UIA
        observations, generation, _ = self.observe_window(hwnd)
        desc_lower = target_description.lower()
        for obs in observations:
            if obs.name and obs.name.lower() == desc_lower:
                return obs.bbox, PerceptionTier.TIER_3_UIA, "RESOLVED_UIA_NAME_MATCH"
            if obs.automation_id and obs.automation_id.lower() == desc_lower:
                return obs.bbox, PerceptionTier.TIER_3_UIA, "RESOLVED_UIA_AUTOMATION_ID"

        # Log escalation
        self._record_escalation(
            hwnd=hwnd,
            from_tier=PerceptionTier.TIER_3_UIA,
            to_tier=PerceptionTier.TIER_4_OCR,
            reason="UIA_FAILED_NO_NAMED_TARGET",
            target=target_description,
        )

        # If no image path provided, capture window region
        if not image_path:
            img, _ = self.capture.capture_window(hwnd)
        else:
            img = None

        # 2. Tier 4: Local OCR
        if image_path and self.ocr.is_available:
            ocr_regions = self.ocr.extract_text_regions(image_path)
            for region in ocr_regions:
                if desc_lower in region.text.lower():
                    return region.bbox, PerceptionTier.TIER_4_OCR, "RESOLVED_OCR_TEXT_MATCH"

        self._record_escalation(
            hwnd=hwnd,
            from_tier=PerceptionTier.TIER_4_OCR,
            to_tier=PerceptionTier.TIER_6_GROUNDER,
            reason="OCR_NO_TEXT_MATCH",
            target=target_description,
        )

        # 3. Tier 6: Visual Grounder (OmniParser)
        if image_path:
            grounded = self.grounder.ground_target(image_path, target_description)
            if grounded:
                return grounded.bbox, PerceptionTier.TIER_6_GROUNDER, "RESOLVED_VISUAL_GROUNDER"

        self._record_escalation(
            hwnd=hwnd,
            from_tier=PerceptionTier.TIER_6_GROUNDER,
            to_tier=PerceptionTier.TIER_7_LOCAL_VLM,
            reason="GROUNDER_AMBIGUOUS_REQUIRES_SEMANTIC_REASONING",
            target=target_description,
        )

        # 4. Tier 7: Local VLM (SmolVLM)
        if image_path:
            vlm_obs = self.vlm.reason_about_image(image_path, f"Where is the {target_description}?")
            if vlm_obs and vlm_obs.referenced_bboxes:
                return vlm_obs.referenced_bboxes[0], PerceptionTier.TIER_7_LOCAL_VLM, "RESOLVED_LOCAL_VLM"

        return None, PerceptionTier.TIER_7_LOCAL_VLM, "UNRESOLVED_ACROSS_ALL_TIERS"

    def _record_escalation(
        self,
        hwnd: int,
        from_tier: PerceptionTier,
        to_tier: PerceptionTier,
        reason: str,
        target: str,
    ) -> None:
        """Record escalation event telemetry."""
        event = {
            "timestamp": time.time(),
            "hwnd": hwnd,
            "from_tier": from_tier.name,
            "to_tier": to_tier.name,
            "reason": reason,
            "target": target,
        }
        self.escalation_log.append(event)
        logger.info("Perception Escalation: %s -> %s (Reason: %s)", from_tier.name, to_tier.name, reason)
