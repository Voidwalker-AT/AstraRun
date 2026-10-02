"""System Tray icon and context menu for resident AstraRun operation.

Implements:
  - Exactly ONE notification area icon with the Astra star/spark visual identity
  - Discrete states: READY, WORKING, PAUSED, ATTENTION_REQUIRED, ERROR
  - Exact menu: Open Astra, Task Center, Pause/Resume, Settings, Restart, Quit
  - Conforms to AstraRun 1.0 Unified Design System (Restrained Dark Theme)
"""

from __future__ import annotations

import sys
from enum import Enum
from typing import Any, Callable, Optional
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap, QPolygonF
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from astrarun.core.logging import get_logger
from astrarun.ui.icons import IconRenderer
from astrarun.ui.theme import (
    ACCENT,
    ATTENTION,
    BG_APP,
    BORDER,
    BORDER_STRONG,
    BORDER_SUBTLE,
    DANGER,
    FONT_FAMILY,
    FONT_SIZE_BODY,
    SUCCESS,
    SURFACE,
    SURFACE_HOVER,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
)

logger = get_logger("astrarun.ui.tray")


class TrayState(str, Enum):
    READY = "READY"
    WORKING = "WORKING"
    PAUSED = "PAUSED"
    ATTENTION_REQUIRED = "ATTENTION_REQUIRED"
    ERROR = "ERROR"


STATE_COLORS = {
    TrayState.READY: ACCENT,              # #5b8cf7 Cool Astra Blue/Periwinkle
    TrayState.WORKING: WARNING,           # #d99b38 Muted Amber
    TrayState.PAUSED: WARNING,            # #d99b38 Muted Amber
    TrayState.ATTENTION_REQUIRED: ATTENTION, # #8270db Muted Violet
    TrayState.ERROR: DANGER,              # #d64545 Muted Red
}

STATE_TOOLTIPS = {
    TrayState.READY: "AstraRun — Ready (Alt+Space)",
    TrayState.WORKING: "AstraRun — Working...",
    TrayState.PAUSED: "AstraRun — Paused (User active)",
    TrayState.ATTENTION_REQUIRED: "AstraRun — Attention Required",
    TrayState.ERROR: "AstraRun — Subsystem Error",
}


def create_tray_icon_pixmap(size: int = 32, state: TrayState = TrayState.READY) -> QIcon:
    """Generate the Astra 4-point star/spark icon with state-dependent coloration."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 1. Dark circular container (near-black with subtle border)
    spark_color_hex = STATE_COLORS.get(state, ACCENT)
    spark_color = QColor(spark_color_hex)
    painter.setBrush(QColor(BG_APP))
    painter.setPen(QColor(BORDER))
    painter.drawEllipse(2, 2, size - 4, size - 4)

    # 2. Draw 4-point Astra Star/Spark in center
    cx, cy = size / 2.0, size / 2.0
    outer_r = size * 0.32
    inner_r = size * 0.10

    path = QPainterPath()
    points = [
        QPointF(cx, cy - outer_r),               # Top
        QPointF(cx + inner_r, cy - inner_r),     # Top-Right
        QPointF(cx + outer_r, cy),               # Right
        QPointF(cx + inner_r, cy + inner_r),     # Bottom-Right
        QPointF(cx, cy + outer_r),               # Bottom
        QPointF(cx - inner_r, cy + inner_r),     # Bottom-Left
        QPointF(cx - outer_r, cy),               # Left
        QPointF(cx - inner_r, cy - inner_r),     # Top-Left
    ]
    poly = QPolygonF(points)
    path.addPolygon(poly)
    path.closeSubpath()

    painter.setBrush(spark_color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPath(path)

    painter.end()
    return QIcon(pixmap)


class AstraTrayIcon(QSystemTrayIcon):
    """Resident system tray controller for AstraRun."""

    # Primary signals
    open_astra_requested = Signal()
    open_task_center_requested = Signal()
    pause_astra_requested = Signal()
    resume_astra_requested = Signal()
    open_settings_requested = Signal()
    restart_requested = Signal()
    exit_requested = Signal()

    # Backwards compatibility signals
    toggle_launcher_requested = Signal()
    open_history_requested = Signal()
    open_memory_requested = Signal()
    open_skills_requested = Signal()
    open_diagnostics_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        self.state: TrayState = TrayState.READY
        self.is_paused: bool = False
        icon = create_tray_icon_pixmap(32, self.state)
        super().__init__(icon, parent)
        self.setToolTip(STATE_TOOLTIPS[self.state])

        self._build_menu()
        self.activated.connect(self._on_activated)

        # Wire backwards compat signals
        self.open_astra_requested.connect(self.toggle_launcher_requested.emit)
        self.open_task_center_requested.connect(self.open_history_requested.emit)

    def set_state(self, new_state: TrayState, detail: Optional[str] = None) -> None:
        """Update visual tray state and tooltip."""
        self.state = new_state
        self.setIcon(create_tray_icon_pixmap(32, new_state))
        tt = STATE_TOOLTIPS.get(new_state, "AstraRun")
        if detail:
            tt = f"{tt}: {detail}"
        self.setToolTip(tt)
        logger.debug("Tray icon state updated to %s (%s)", new_state.value, tt)

    def _build_menu(self) -> None:
        """Construct the exact canonical tray context menu."""
        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {SURFACE};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 8px;
                padding: 6px;
                font-family: {FONT_FAMILY};
                font-size: 13px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
                color: {TEXT_PRIMARY};
            }}
            QMenu::item:selected {{
                background-color: {SURFACE_HOVER};
                color: #ffffff;
            }}
            QMenu::item:disabled {{
                color: {TEXT_MUTED};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {BORDER_SUBTLE};
                margin: 4px 6px;
            }}
        """)

        # 1. Open Astra
        open_action = QAction("Open Astra  (Alt+Space)", self)
        open_action.setIcon(IconRenderer.get_icon("spark", size=14, color=ACCENT))
        open_action.triggered.connect(self.open_astra_requested.emit)
        menu.addAction(open_action)

        # 2. Task Center
        task_center_action = QAction("Task Center", self)
        task_center_action.setIcon(IconRenderer.get_icon("history", size=14, color=TEXT_SECONDARY))
        task_center_action.triggered.connect(self.open_task_center_requested.emit)
        menu.addAction(task_center_action)

        menu.addSeparator()

        # 3. Pause / Resume Astra
        self.pause_action = QAction("Pause Astra", self)
        self.pause_action.setIcon(IconRenderer.get_icon("pause", size=14, color=WARNING))
        self.pause_action.triggered.connect(self._toggle_pause)
        menu.addAction(self.pause_action)

        # 4. Settings
        settings_action = QAction("Settings", self)
        settings_action.setIcon(IconRenderer.get_icon("settings", size=14, color=TEXT_SECONDARY))
        settings_action.triggered.connect(self.open_settings_requested.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        # 5. Restart Astra
        restart_action = QAction("Restart Astra", self)
        restart_action.setIcon(IconRenderer.get_icon("running", size=14, color=TEXT_SECONDARY))
        restart_action.triggered.connect(self.restart_requested.emit)
        menu.addAction(restart_action)

        # 6. Quit Astra
        exit_action = QAction("Quit Astra", self)
        exit_action.setIcon(IconRenderer.get_icon("close", size=14, color=TEXT_MUTED))
        exit_action.triggered.connect(self.exit_requested.emit)
        menu.addAction(exit_action)

        self.setContextMenu(menu)

    def _toggle_pause(self) -> None:
        """Toggle pause state from tray menu."""
        if self.is_paused:
            self.is_paused = False
            self.pause_action.setText("Pause Astra")
            self.pause_action.setIcon(IconRenderer.get_icon("pause", size=14, color=WARNING))
            self.set_state(TrayState.READY)
            self.resume_astra_requested.emit()
        else:
            self.is_paused = True
            self.pause_action.setText("Resume Astra")
            self.pause_action.setIcon(IconRenderer.get_icon("running", size=14, color=SUCCESS))
            self.set_state(TrayState.PAUSED)
            self.pause_astra_requested.emit()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle click/double-click on the tray icon."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_astra_requested.emit()
