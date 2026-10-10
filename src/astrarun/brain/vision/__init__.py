"""Vision & Grounding package for AstraRun Brain."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class VisualGrounding:
    """
    Visual and spatial element localization engine.
    Perceives layout and maps semantic references to bounding boxes
    without executing OS input directly.
    """

    def __init__(self) -> None:
        pass

    def ground_element(self, description: str, ui_tree: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Map descriptive visual reference to the most matching UI control in tree."""
        desc_l = description.lower()
        for elem in ui_tree:
            name = (elem.get("name") or "").lower()
            if desc_l in name or name in desc_l:
                return elem
        return None


__all__ = ["VisualGrounding"]
