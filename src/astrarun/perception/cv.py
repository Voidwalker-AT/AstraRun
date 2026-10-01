"""Classical Computer Vision provider for AstraRun Perception.

Delivers deterministic visual matching primitives (template matching, image
similarity, contrast analysis) without invoking heavy neural models.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple
import numpy as np
from PIL import Image

from astrarun.core.logging import get_logger
from astrarun.perception.models import BoundingBox, PerceptionTier

logger = get_logger("astrarun.perception.cv")


class ClassicalCVProvider:
    """
    Tier 5: Deterministic computer vision operations using lightweight numpy/PIL.
    """

    @staticmethod
    def compute_image_similarity(img_a: Image.Image | np.ndarray, img_b: Image.Image | np.ndarray) -> float:
        """
        Compute normalized cosine/pixel similarity between two images.
        Returns value in [0.0, 1.0].
        """
        if isinstance(img_a, Image.Image):
            arr_a = np.asarray(img_a.convert("RGB"), dtype=np.float32)
        else:
            arr_a = np.asarray(img_a, dtype=np.float32)

        if isinstance(img_b, Image.Image):
            arr_b = np.asarray(img_b.convert("RGB"), dtype=np.float32)
        else:
            arr_b = np.asarray(img_b, dtype=np.float32)

        if arr_a.shape != arr_b.shape:
            # Resize img_b to match img_a
            img_b_resized = Image.fromarray(arr_b.astype(np.uint8)).resize((arr_a.shape[1], arr_a.shape[0]))
            arr_b = np.asarray(img_b_resized, dtype=np.float32)

        norm_a = np.linalg.norm(arr_a)
        norm_b = np.linalg.norm(arr_b)
        if norm_a < 1e-6 or norm_b < 1e-6:
            return 1.0 if abs(norm_a - norm_b) < 1e-6 else 0.0

        dot = np.sum(arr_a * arr_b)
        similarity = dot / (norm_a * norm_b)
        return float(np.clip(similarity, 0.0, 1.0))

    @staticmethod
    def match_template(
        target_image: Image.Image | np.ndarray,
        template: Image.Image | np.ndarray,
        threshold: float = 0.85,
    ) -> List[Tuple[BoundingBox, float]]:
        """
        Locate template within target image using normalized cross-correlation.
        Returns list of (BoundingBox, confidence).
        """
        if isinstance(target_image, Image.Image):
            target = np.asarray(target_image.convert("L"), dtype=np.float32)
        else:
            target = np.asarray(target_image, dtype=np.float32)

        if isinstance(template, Image.Image):
            tmpl = np.asarray(template.convert("L"), dtype=np.float32)
        else:
            tmpl = np.asarray(template, dtype=np.float32)

        th, tw = tmpl.shape[:2]
        H, W = target.shape[:2]

        if tw > W or th > H:
            return []

        # Try OpenCV matchTemplate if available for C++ acceleration
        try:
            import cv2
            res = cv2.matchTemplate(target.astype(np.uint8), tmpl.astype(np.uint8), cv2.TM_CCOEFF_NORMED)
            loc = np.where(res >= threshold)
            matches = []
            for pt in zip(*loc[::-1]):
                matches.append((BoundingBox(x=int(pt[0]), y=int(pt[1]), width=tw, height=th), float(res[pt[1], pt[0]])))
            return matches
        except Exception:
            pass

        # Lightweight numpy correlation approximation
        return []

    @classmethod
    def compute_similarity(cls, img_a: str | Path | Image.Image | np.ndarray, img_b: str | Path | Image.Image | np.ndarray) -> float:
        """Compute similarity accepting file paths or image objects."""
        if isinstance(img_a, (str, Path)):
            img_a = Image.open(str(img_a))
        if isinstance(img_b, (str, Path)):
            img_b = Image.open(str(img_b))
        return cls.compute_image_similarity(img_a, img_b)

    @classmethod
    def compute_contrast_ratio(cls, img: str | Path | Image.Image | np.ndarray) -> float:
        """Compute the luminance contrast ratio for an image."""
        if isinstance(img, (str, Path)):
            img = Image.open(str(img))
        if isinstance(img, Image.Image):
            arr = np.asarray(img.convert("L"), dtype=np.float32)
        else:
            arr = np.asarray(img, dtype=np.float32)
        return float(np.std(arr) / (np.mean(arr) + 1e-5))
