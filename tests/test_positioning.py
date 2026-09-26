"""Unit tests for active window and display monitor positioning."""

from PySide6.QtCore import QPoint, QRect
from astrarun.ui.positioning import compute_launcher_position, get_target_screen_geometry


def test_compute_launcher_position():
    pos = compute_launcher_position(640, 56)
    assert isinstance(pos, QPoint)
    assert pos.x() >= 0
    assert pos.y() >= 0


def test_target_screen_geometry():
    geom = get_target_screen_geometry()
    assert isinstance(geom, QRect)
    assert geom.width() > 0
    assert geom.height() > 0
