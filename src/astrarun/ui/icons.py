"""High-fidelity vector icon renderer and AstraMark system for AstraRun.

Replaces all emoji and raw text glyphs with crisp, antialiased, resolution-independent
vector icons rendered via QPainter, QPainterPath, and QPixmap.
"""

from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QLabel, QWidget

from astrarun.ui.theme import (
    ACCENT,
    BORDER,
    BORDER_STRONG,
    DANGER,
    SUCCESS,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
)


class IconRenderer:
    """Central programmatic vector icon generator creating crisp QPixmap and QIcon instances."""

    _cache: Dict[Tuple[str, int, str], QPixmap] = {}

    @classmethod
    def get_pixmap(
        cls,
        name: str,
        size: int = 16,
        color: Optional[str] = None,
        bg_circle: bool = False,
        bg_color: Optional[str] = None,
    ) -> QPixmap:
        """Render a named vector icon to an antialiased QPixmap."""
        effective_color = color or TEXT_PRIMARY
        cache_key = (f"{name}_bg{bg_circle}_{bg_color}", size, effective_color)
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        s = float(size)
        q_color = QColor(effective_color)

        if bg_circle:
            bg_qcolor = QColor(bg_color or SURFACE_RAISED)
            painter.setBrush(QBrush(bg_qcolor))
            painter.setPen(QPen(QColor(BORDER), 1.0))
            painter.drawEllipse(QRectF(1.0, 1.0, s - 2.0, s - 2.0))

        if name in ("spark", "astra", "astra_mark"):
            cls._draw_spark(painter, s, q_color)
        elif name in ("check", "success"):
            cls._draw_check(painter, s, q_color)
        elif name in ("close", "cancel", "cross"):
            cls._draw_close(painter, s, q_color)
        elif name in ("running", "play", "resume"):
            cls._draw_play(painter, s, q_color)
        elif name in ("pause", "paused"):
            cls._draw_pause(painter, s, q_color)
        elif name in ("pending", "dot"):
            cls._draw_pending(painter, s, q_color)
        elif name in ("warning", "alert"):
            cls._draw_warning(painter, s, q_color)
        elif name in ("question", "clarify", "help"):
            cls._draw_question(painter, s, q_color)
        elif name in ("chevron_down", "arrow_down"):
            cls._draw_chevron_down(painter, s, q_color)
        elif name in ("chevron_up", "arrow_up"):
            cls._draw_chevron_up(painter, s, q_color)
        elif name in ("folder", "dir"):
            cls._draw_folder(painter, s, q_color)
        elif name in ("external", "link", "open"):
            cls._draw_external(painter, s, q_color)
        elif name in ("copy", "clone"):
            cls._draw_copy(painter, s, q_color)
        elif name in ("settings", "gear"):
            cls._draw_settings(painter, s, q_color)
        elif name in ("history", "recent"):
            cls._draw_history(painter, s, q_color)
        elif name in ("error", "failed"):
            cls._draw_error(painter, s, q_color)
        else:
            cls._draw_spark(painter, s, q_color)

        painter.end()
        cls._cache[cache_key] = pixmap
        return pixmap

    @classmethod
    def get_icon(
        cls,
        name: str,
        size: int = 16,
        color: Optional[str] = None,
        bg_circle: bool = False,
        bg_color: Optional[str] = None,
    ) -> QIcon:
        """Render a named vector icon and wrap in a QIcon."""
        pixmap = cls.get_pixmap(name, size, color, bg_circle, bg_color)
        return QIcon(pixmap)

    @classmethod
    def create_label(
        cls,
        name: str,
        size: int = 16,
        color: Optional[str] = None,
        parent: Optional[QWidget] = None,
        bg_circle: bool = False,
        bg_color: Optional[str] = None,
    ) -> QLabel:
        """Create a QLabel containing the specified vector icon pixmap."""
        lbl = QLabel(parent)
        lbl.setPixmap(cls.get_pixmap(name, size, color, bg_circle, bg_color))
        lbl.setFixedSize(size, size)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl

    # -------------------------------------------------------------------------
    # VECTOR PATH DRAWING IMPLEMENTATIONS
    # -------------------------------------------------------------------------

    @staticmethod
    def _draw_spark(p: QPainter, s: float, color: QColor) -> None:
        """Astra 4-point star/spark mark with pinched vertices."""
        cx, cy = s / 2.0, s / 2.0
        r_out = s * 0.44
        r_in = s * 0.13

        pts = [
            QPointF(cx, cy - r_out),
            QPointF(cx + r_in, cy - r_in),
            QPointF(cx + r_out, cy),
            QPointF(cx + r_in, cy + r_in),
            QPointF(cx, cy + r_out),
            QPointF(cx - r_in, cy + r_in),
            QPointF(cx - r_out, cy),
            QPointF(cx - r_in, cy - r_in),
        ]
        path = QPainterPath()
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()

        p.setBrush(QBrush(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)

    @staticmethod
    def _draw_check(p: QPainter, s: float, color: QColor) -> None:
        """Clean vector checkmark."""
        stroke = max(1.8, s * 0.12)
        pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(s * 0.22, s * 0.52)
        path.lineTo(s * 0.42, s * 0.74)
        path.lineTo(s * 0.80, s * 0.26)
        p.drawPath(path)

    @staticmethod
    def _draw_close(p: QPainter, s: float, color: QColor) -> None:
        """Crisp X / cancel mark."""
        stroke = max(1.6, s * 0.11)
        pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        pad = s * 0.26
        p.drawLine(QPointF(pad, pad), QPointF(s - pad, s - pad))
        p.drawLine(QPointF(s - pad, pad), QPointF(pad, s - pad))

    @staticmethod
    def _draw_play(p: QPainter, s: float, color: QColor) -> None:
        """Clean equilateral play/running triangle pointing right."""
        path = QPainterPath()
        left = s * 0.28
        right = s * 0.78
        top = s * 0.22
        bottom = s * 0.78
        mid_y = s * 0.50

        path.moveTo(left, top)
        path.lineTo(right, mid_y)
        path.lineTo(left, bottom)
        path.closeSubpath()

        p.setBrush(QBrush(color))
        p.setPen(QPen(color, 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)

    @staticmethod
    def _draw_pause(p: QPainter, s: float, color: QColor) -> None:
        """Two rounded vertical bars for pause."""
        bar_w = s * 0.18
        bar_h = s * 0.54
        y = (s - bar_h) / 2.0
        rad = max(1.0, bar_w * 0.3)

        p.setBrush(QBrush(color))
        p.setPen(Qt.PenStyle.NoPen)
        # Left bar
        p.drawRoundedRect(QRectF(s * 0.24, y, bar_w, bar_h), rad, rad)
        # Right bar
        p.drawRoundedRect(QRectF(s * 0.58, y, bar_w, bar_h), rad, rad)

    @staticmethod
    def _draw_pending(p: QPainter, s: float, color: QColor) -> None:
        """Quiet hollow circular outline for pending state."""
        stroke = max(1.5, s * 0.10)
        pad = s * 0.22
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color, stroke))
        p.drawEllipse(QRectF(pad, pad, s - 2.0 * pad, s - 2.0 * pad))

    @staticmethod
    def _draw_warning(p: QPainter, s: float, color: QColor) -> None:
        """Rounded triangle with exclamation mark."""
        path = QPainterPath()
        top_y = s * 0.16
        bot_y = s * 0.84
        cx = s / 2.0
        left_x = s * 0.14
        right_x = s * 0.86

        path.moveTo(cx, top_y)
        path.lineTo(right_x, bot_y)
        path.lineTo(left_x, bot_y)
        path.closeSubpath()

        p.setBrush(QBrush(color))
        p.setPen(QPen(color, 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)

        # Draw dark inner exclamation mark
        dark = QColor("#0c0d10")
        stroke = max(1.6, s * 0.09)
        p.setPen(QPen(dark, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(cx, s * 0.40), QPointF(cx, s * 0.60))
        p.setBrush(QBrush(dark))
        dot_r = max(1.0, stroke * 0.6)
        p.drawEllipse(QPointF(cx, s * 0.72), dot_r, dot_r)

    @staticmethod
    def _draw_question(p: QPainter, s: float, color: QColor) -> None:
        """Clean vector question mark."""
        cx = s / 2.0
        stroke = max(1.6, s * 0.11)
        pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(s * 0.32, s * 0.34)
        path.cubicTo(s * 0.32, s * 0.20, s * 0.68, s * 0.20, s * 0.68, s * 0.36)
        path.cubicTo(s * 0.68, s * 0.50, cx, s * 0.50, cx, s * 0.62)
        p.drawPath(path)

        p.setBrush(QBrush(color))
        dot_r = max(1.0, stroke * 0.55)
        p.drawEllipse(QPointF(cx, s * 0.78), dot_r, dot_r)

    @staticmethod
    def _draw_chevron_down(p: QPainter, s: float, color: QColor) -> None:
        """Downward chevron."""
        stroke = max(1.5, s * 0.11)
        pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(s * 0.26, s * 0.40)
        path.lineTo(s * 0.50, s * 0.64)
        path.lineTo(s * 0.74, s * 0.40)
        p.drawPath(path)

    @staticmethod
    def _draw_chevron_up(p: QPainter, s: float, color: QColor) -> None:
        """Upward chevron."""
        stroke = max(1.5, s * 0.11)
        pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(s * 0.26, s * 0.60)
        path.lineTo(s * 0.50, s * 0.36)
        path.lineTo(s * 0.74, s * 0.60)
        p.drawPath(path)

    @staticmethod
    def _draw_folder(p: QPainter, s: float, color: QColor) -> None:
        """Directory / folder outline."""
        stroke = max(1.3, s * 0.08)
        pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        path = QPainterPath()
        path.moveTo(s * 0.18, s * 0.76)
        path.lineTo(s * 0.18, s * 0.30)
        path.lineTo(s * 0.42, s * 0.30)
        path.lineTo(s * 0.50, s * 0.38)
        path.lineTo(s * 0.82, s * 0.38)
        path.lineTo(s * 0.82, s * 0.76)
        path.closeSubpath()
        p.drawPath(path)

    @staticmethod
    def _draw_external(p: QPainter, s: float, color: QColor) -> None:
        """Diagonal open / external link icon."""
        stroke = max(1.3, s * 0.09)
        pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Box
        p.drawLine(QPointF(s * 0.48, s * 0.28), QPointF(s * 0.24, s * 0.28))
        p.drawLine(QPointF(s * 0.24, s * 0.28), QPointF(s * 0.24, s * 0.76))
        p.drawLine(QPointF(s * 0.24, s * 0.76), QPointF(s * 0.76, s * 0.76))
        p.drawLine(QPointF(s * 0.76, s * 0.76), QPointF(s * 0.76, s * 0.52))

        # Arrow
        p.drawLine(QPointF(s * 0.46, s * 0.54), QPointF(s * 0.76, s * 0.24))
        p.drawLine(QPointF(s * 0.58, s * 0.24), QPointF(s * 0.76, s * 0.24))
        p.drawLine(QPointF(s * 0.76, s * 0.24), QPointF(s * 0.76, s * 0.42))

    @staticmethod
    def _draw_copy(p: QPainter, s: float, color: QColor) -> None:
        """Two overlapping rounded rectangles for copy."""
        stroke = max(1.2, s * 0.08)
        pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # Front rect
        p.drawRoundedRect(QRectF(s * 0.32, s * 0.32, s * 0.46, s * 0.50), 2, 2)
        # Back rect outline (top and left lines)
        path = QPainterPath()
        path.moveTo(s * 0.60, s * 0.20)
        path.lineTo(s * 0.22, s * 0.20)
        path.lineTo(s * 0.22, s * 0.62)
        p.drawPath(path)

    @staticmethod
    def _draw_settings(p: QPainter, s: float, color: QColor) -> None:
        """Mechanical gear for settings."""
        cx, cy = s / 2.0, s / 2.0
        r_outer = s * 0.38
        r_inner = s * 0.28
        hole_r = s * 0.14
        teeth = 6

        path = QPainterPath()
        for i in range(teeth * 2):
            angle = i * (math.pi / teeth)
            r = r_outer if i % 2 == 0 else r_inner
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()

        p.setBrush(QBrush(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawPath(path)

        # Center hole
        p.setBrush(QBrush(QColor("#0c0d10")))
        p.drawEllipse(QPointF(cx, cy), hole_r, hole_r)

    @staticmethod
    def _draw_history(p: QPainter, s: float, color: QColor) -> None:
        """Clock face with hands."""
        cx, cy = s / 2.0, s / 2.0
        r = s * 0.36
        stroke = max(1.4, s * 0.09)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color, stroke))
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Clock hands
        p.drawLine(QPointF(cx, cy), QPointF(cx, cy - r * 0.60))
        p.drawLine(QPointF(cx, cy), QPointF(cx + r * 0.45, cy))

    @staticmethod
    def _draw_error(p: QPainter, s: float, color: QColor) -> None:
        """Circle with inner cross for error/failed."""
        cx, cy = s / 2.0, s / 2.0
        r = s * 0.40
        p.setBrush(QBrush(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Inner cross
        dark = QColor("#0c0d10")
        stroke = max(1.6, s * 0.10)
        p.setPen(QPen(dark, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        pad = s * 0.32
        p.drawLine(QPointF(pad, pad), QPointF(s - pad, s - pad))
        p.drawLine(QPointF(s - pad, pad), QPointF(pad, s - pad))


class AstraMarkWidget(QWidget):
    """Reusable vector Astra Mark widget with optional pulsing/breathing animation."""

    def __init__(
        self,
        size: int = 24,
        color: Optional[str] = None,
        bg_circle: bool = False,
        bg_color: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._size = size
        self._color = color or ACCENT
        self._bg_circle = bg_circle
        self._bg_color = bg_color or SURFACE_RAISED
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pix = IconRenderer.get_pixmap(
            "spark",
            size=self._size,
            color=self._color,
            bg_circle=self._bg_circle,
            bg_color=self._bg_color,
        )
        painter.drawPixmap(0, 0, pix)
        painter.end()
