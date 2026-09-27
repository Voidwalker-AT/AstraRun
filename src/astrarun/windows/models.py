"""Domain models for Window Intelligence and Desktop Composition."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class WindowState(str, Enum):
    """Window display state."""
    NORMAL = "normal"
    MAXIMIZED = "maximized"
    MINIMIZED = "minimized"


class LayoutType(str, Enum):
    """Deterministic tiling layout positions."""
    FULL = "full"
    LEFT_HALF = "left_half"
    RIGHT_HALF = "right_half"
    TOP_HALF = "top_half"
    BOTTOM_HALF = "bottom_half"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    LEFT_TWO_THIRDS = "left_two_thirds"
    RIGHT_ONE_THIRD = "right_one_third"


@dataclass(frozen=True)
class WindowBounds:
    """Rectangular window geometry (x, y, width, height)."""
    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class MonitorEntity:
    """Represents a physical display monitor and its usable work area."""
    monitor_id: int
    device_name: str
    work_area: tuple[int, int, int, int]  # (left, top, width, height) excluding taskbar
    full_bounds: tuple[int, int, int, int]  # (left, top, width, height) total screen
    is_primary: bool
    dpi: int = 96

    def to_dict(self) -> dict[str, Any]:
        return {
            "monitor_id": self.monitor_id,
            "device_name": self.device_name,
            "work_area": self.work_area,
            "full_bounds": self.full_bounds,
            "is_primary": self.is_primary,
            "dpi": self.dpi,
        }


@dataclass
class WindowLayoutSnapshot:
    """Snapshot of window geometry before modification for safe undo."""
    hwnd: int
    pid: int
    title: str
    bounds: tuple[int, int, int, int]
    state: str
    monitor_id: int
    timestamp: float = field(default_factory=time.time)

    def is_expired(self, ttl_seconds: float = 600.0) -> bool:
        """Check if snapshot has exceeded TTL (default: 10 minutes)."""
        return (time.time() - self.timestamp) > ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "hwnd": self.hwnd,
            "pid": self.pid,
            "title": self.title,
            "bounds": self.bounds,
            "state": self.state,
            "monitor_id": self.monitor_id,
            "timestamp": self.timestamp,
        }
