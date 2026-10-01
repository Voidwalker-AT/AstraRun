"""Normalized typed observation schemas and element bindings for AstraRun Perception.

Provides uniform representations across Win32, COM, CDP, UIA, OCR, CV, Grounder,
and VLM tiers, enforcing generation tracking and stale-element validation.
"""

from __future__ import annotations

import time
import uuid
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field


class PerceptionTier(IntEnum):
    """Canonical 9-tier perception escalation hierarchy."""
    TIER_0_WIN32 = 0         # Native Win32 OS APIs
    TIER_1_COM = 1           # Application-native COM surfaces
    TIER_2_CDP = 2           # Browser Chrome DevTools Protocol / DOM
    TIER_3_UIA = 3           # Windows UI Automation (UIAutomationCore)
    TIER_4_OCR = 4           # Local OCR (WinRT / fallback)
    TIER_5_CV = 5            # Classical Computer Vision
    TIER_6_GROUNDER = 6      # Visual Grounder (OmniParser v2.0 YOLO)
    TIER_7_LOCAL_VLM = 7     # Local On-Demand VLM (SmolVLM-500M)
    TIER_8_EXTERNAL_VLM = 8  # External Cloud VLM Fallback


class BoundingBox(BaseModel):
    """Standardized coordinate box: (x, y, width, height) in physical pixels."""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    def __init__(self, x: int = 0, y: int = 0, width: int = 0, height: int = 0, **kwargs):
        super().__init__(x=x, y=y, width=width, height=height, **kwargs)

    @property
    def center(self) -> Tuple[int, int]:
        """Compute pixel center point (x_center, y_center)."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def right(self) -> int:
        """Right edge coordinate."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """Bottom edge coordinate."""
        return self.y + self.height

    @property
    def area(self) -> int:
        """Bounding box area in square pixels."""
        return self.width * self.height

    def contains(self, px: int, py: int) -> bool:
        """Test if a 2D point lies strictly within the bounding box."""
        return (self.x <= px <= self.x + self.width) and (self.y <= py <= self.y + self.height)

    def scale(self, scale_factor: float) -> BoundingBox:
        """Scale box dimensions by a DPI scaling factor."""
        return BoundingBox(
            x=int(self.x * scale_factor),
            y=int(self.y * scale_factor),
            width=int(self.width * scale_factor),
            height=int(self.height * scale_factor),
        )


class Observation(BaseModel):
    """Base model for all normalized perception observations."""
    observation_id: str = Field(default_factory=lambda: f"obs_{uuid.uuid4().hex[:8]}")
    tier: PerceptionTier
    provider: str
    timestamp: float = Field(default_factory=time.time)
    confidence: float = 1.0
    generation_id: int = 1
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def perception_tier(self) -> PerceptionTier:
        return self.tier


class WindowObservation(Observation):
    """Tier 0: Normalized Win32 desktop window observation."""
    tier: PerceptionTier = PerceptionTier.TIER_0_WIN32
    provider: str = "win32_user32"
    hwnd: int
    title: str
    app_name: str = ""
    pid: int
    bounds: BoundingBox
    client_bounds: Optional[BoundingBox] = None
    is_foreground: bool = False
    is_minimized: bool = False
    is_maximized: bool = False
    is_visible: bool = True
    monitor_handle: int = 0
    dpi_scale: float = 1.0


class ProcessObservation(Observation):
    """Tier 0: Normalized Win32 process observation."""
    tier: PerceptionTier = PerceptionTier.TIER_0_WIN32
    provider: str = "win32_psutil"
    pid: int
    name: str
    exe_path: str = ""
    memory_rss_mb: float = 0.0
    cpu_percent: float = 0.0
    window_hwnds: List[int] = Field(default_factory=list)


class UIElementObservation(Observation):
    """Tier 3: Normalized Windows UI Automation element."""
    tier: PerceptionTier = PerceptionTier.TIER_3_UIA
    provider: str = "uia_com"
    element_id: str  # Compact semantic ID, e.g. "@e14"
    hwnd: int
    pid: int
    name: str = ""
    control_type: str = "custom"
    automation_id: str = ""
    class_name: str = ""
    bbox: BoundingBox
    is_enabled: bool = True
    is_offscreen: bool = False
    supported_patterns: List[str] = Field(default_factory=list)
    depth: int = 0


class DOMElementObservation(Observation):
    """Tier 2: Normalized Browser DOM element from CDP."""
    tier: PerceptionTier = PerceptionTier.TIER_2_CDP
    provider: str = "browser_cdp"
    element_id: str  # Compact semantic ID, e.g. "@e14"
    tag_name: str
    text: str = ""
    role: str = ""
    selector: str = ""
    bbox: BoundingBox
    is_interactive: bool = True
    is_visible: bool = True
    attributes: Dict[str, str] = Field(default_factory=dict)

    @property
    def tag(self) -> str:
        """Alias for tag_name."""
        return self.tag_name


class TextRegionObservation(Observation):
    """Tier 4: Normalized OCR text region observation."""
    tier: PerceptionTier = PerceptionTier.TIER_4_OCR
    provider: str = "winrt_ocr"
    text: str
    bbox: BoundingBox
    line_index: int = 0
    word_boxes: List[BoundingBox] = Field(default_factory=list)


class GroundedTargetObservation(Observation):
    """Tier 6: Normalized visual grounding observation (OmniParser v2.0)."""
    tier: PerceptionTier = PerceptionTier.TIER_6_GROUNDER
    provider: str = "omniparser_yolo"
    target_description: str
    bbox: BoundingBox
    center: Tuple[int, int]
    visual_class: str = "icon"


class VisualSemanticObservation(Observation):
    """Tier 7 / 8: Normalized VLM visual reasoning observation (SmolVLM)."""
    tier: PerceptionTier = PerceptionTier.TIER_7_LOCAL_VLM
    provider: str = "smolvlm_500m"
    query: str
    response_text: str
    referenced_bboxes: List[BoundingBox] = Field(default_factory=list)
    is_quarantined_text: bool = True  # Untrusted by default for prompt injection defense

    @property
    def semantic_description(self) -> str:
        """Alias for response_text."""
        return self.response_text


class ElementBinding(BaseModel):
    """
    Internal binding mapping an ephemeral semantic ID (e.g. '@e14') to physical targets.
    Valid strictly for the generation in which it was produced.
    """
    semantic_id: str
    tier: PerceptionTier
    hwnd: int
    pid: int
    runtime_id: str
    bbox: BoundingBox
    generation_id: int
    created_at: float = Field(default_factory=time.time)
    control_type: str = ""
    name: str = ""


class ObservationGeneration(BaseModel):
    """
    Generation container ensuring atomic staleness protection across frames.
    """
    generation_id: int
    hwnd: int
    window_bounds: BoundingBox
    created_at: float = Field(default_factory=time.time)
    bindings: Dict[str, ElementBinding] = Field(default_factory=dict)
    ttl_seconds: float = 5.0

    def is_stale(self, current_bounds: Optional[BoundingBox] = None, current_hwnd: Optional[int] = None) -> bool:
        """
        Determine if the generation has been invalidated by elapsed time,
        window movement, window resizing, or foreground focus loss.
        """
        # 1. TTL expiration
        if (time.time() - self.created_at) > self.ttl_seconds:
            return True

        # 2. Target HWND changed / closed
        if current_hwnd is not None and current_hwnd != self.hwnd:
            return True

        # 3. Target window moved or resized (> 5px delta)
        if current_bounds is not None:
            dx = abs(current_bounds.x - self.window_bounds.x)
            dy = abs(current_bounds.y - self.window_bounds.y)
            dw = abs(current_bounds.width - self.window_bounds.width)
            dh = abs(current_bounds.height - self.window_bounds.height)
            if dx > 5 or dy > 5 or dw > 5 or dh > 5:
                return True

        return False
