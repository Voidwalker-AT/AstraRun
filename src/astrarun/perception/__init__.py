"""Perception and Windows Control Surfaces for AstraRun.

Implements the 9-tier escalation hierarchy (Win32 -> COM -> CDP -> UIA ->
OCR -> CV -> Grounder -> Local VLM -> External VLM), zero cursor hijacking
via UIA, Win32 SendInput physical control, Per-Monitor-V2 DPI awareness,
anti-misclick target verification, user takeover detection (PAUSED_USER_ACTIVE),
and visual prompt injection defense.
"""

from astrarun.perception.capture import ScreenCapture
from astrarun.perception.cdp import CDPProvider, DOMCompressor
from astrarun.perception.com import COMProvider
from astrarun.perception.cv import ClassicalCVProvider
from astrarun.perception.grounder import VisualGrounder
from astrarun.perception.input import (
    InputError,
    InputState,
    NativeInputController,
    StaleElementError,
    UserInterferenceError,
)
from astrarun.perception.models import (
    BoundingBox,
    DOMElementObservation,
    ElementBinding,
    GroundedTargetObservation,
    Observation,
    ObservationGeneration,
    PerceptionTier,
    ProcessObservation,
    TextRegionObservation,
    UIElementObservation,
    VisualSemanticObservation,
    WindowObservation,
)
from astrarun.perception.ocr import OCRProvider
from astrarun.perception.router import PerceptionRouter, PerceptionTelemetry
from astrarun.perception.vlm import VisionReasoner

__all__ = [
    "BoundingBox",
    "CDPProvider",
    "COMProvider",
    "ClassicalCVProvider",
    "DOMCompressor",
    "DOMElementObservation",
    "ElementBinding",
    "GroundedTargetObservation",
    "InputError",
    "InputState",
    "NativeInputController",
    "OCRProvider",
    "Observation",
    "ObservationGeneration",
    "PerceptionRouter",
    "PerceptionTelemetry",
    "PerceptionTier",
    "ProcessObservation",
    "ScreenCapture",
    "StaleElementError",
    "TextRegionObservation",
    "UIElementObservation",
    "UserInterferenceError",
    "VisionReasoner",
    "VisualGrounder",
    "VisualSemanticObservation",
    "WindowObservation",
]
