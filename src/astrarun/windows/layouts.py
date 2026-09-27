"""Desktop layout tiling math and multi-window composition engine."""

from __future__ import annotations

from typing import Optional, Union

from astrarun.core.logging import get_logger
from astrarun.windows.models import LayoutType, MonitorEntity

logger = get_logger("astrarun.windows.layouts")


class DesktopLayoutEngine:
    """Computes exact window coordinates for standard and custom tiling layouts."""

    @staticmethod
    def parse_layout(name: str | LayoutType) -> LayoutType:
        """Parse natural layout specifications into standard LayoutType."""
        if isinstance(name, LayoutType):
            return name
        clean = str(name).strip().lower().replace("-", "_").replace(" ", "_")

        mapping = {
            "left": LayoutType.LEFT_HALF,
            "snap_left": LayoutType.LEFT_HALF,
            "left_half": LayoutType.LEFT_HALF,
            "right": LayoutType.RIGHT_HALF,
            "snap_right": LayoutType.RIGHT_HALF,
            "right_half": LayoutType.RIGHT_HALF,
            "top": LayoutType.TOP_HALF,
            "top_half": LayoutType.TOP_HALF,
            "bottom": LayoutType.BOTTOM_HALF,
            "bottom_half": LayoutType.BOTTOM_HALF,
            "full": LayoutType.FULL,
            "maximize": LayoutType.FULL,
            "maximized": LayoutType.FULL,
            "center": LayoutType.FULL,
            "top_left": LayoutType.TOP_LEFT,
            "top_right": LayoutType.TOP_RIGHT,
            "bottom_left": LayoutType.BOTTOM_LEFT,
            "bottom_right": LayoutType.BOTTOM_RIGHT,
            "left_two_thirds": LayoutType.LEFT_TWO_THIRDS,
            "two_thirds": LayoutType.LEFT_TWO_THIRDS,
            "right_one_third": LayoutType.RIGHT_ONE_THIRD,
            "one_third": LayoutType.RIGHT_ONE_THIRD,
        }
        return mapping.get(clean, LayoutType.FULL)

    @classmethod
    def compute_bounds(
        cls,
        layout: Union[str, LayoutType],
        work_area: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int]:
        """
        Compute (x, y, width, height) within the given monitor work area.
        work_area is (left, top, width, height).
        """
        lt = cls.parse_layout(layout)
        wx, wy, ww, wh = work_area

        half_w = ww // 2
        half_h = wh // 2
        rem_w = ww - half_w
        rem_h = wh - half_h

        two_thirds_w = int(ww * 2 / 3)
        one_third_w = ww - two_thirds_w

        if lt == LayoutType.FULL:
            return (wx, wy, ww, wh)
        elif lt == LayoutType.LEFT_HALF:
            return (wx, wy, half_w, wh)
        elif lt == LayoutType.RIGHT_HALF:
            return (wx + half_w, wy, rem_w, wh)
        elif lt == LayoutType.TOP_HALF:
            return (wx, wy, ww, half_h)
        elif lt == LayoutType.BOTTOM_HALF:
            return (wx, wy + half_h, ww, rem_h)
        elif lt == LayoutType.TOP_LEFT:
            return (wx, wy, half_w, half_h)
        elif lt == LayoutType.TOP_RIGHT:
            return (wx + half_w, wy, rem_w, half_h)
        elif lt == LayoutType.BOTTOM_LEFT:
            return (wx, wy + half_h, half_w, rem_h)
        elif lt == LayoutType.BOTTOM_RIGHT:
            return (wx + half_w, wy + half_h, rem_w, rem_h)
        elif lt == LayoutType.LEFT_TWO_THIRDS:
            return (wx, wy, two_thirds_w, wh)
        elif lt == LayoutType.RIGHT_ONE_THIRD:
            return (wx + two_thirds_w, wy, one_third_w, wh)
        else:
            return (wx, wy, ww, wh)
