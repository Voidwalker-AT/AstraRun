"""System Tray icon and context menu for resident AstraRun operation.

Implements:
  - Exactly ONE notification area icon with the Astra star/spark visual identity
  - Discrete states: READY, WORKING, PAUSED, ATTENTION_REQUIRED, ERROR
  - Exact menu: Open Astra, Task Center, Pause/Resume, Settings, Restart, Quit
"""

from __future__ import annotations

import sys
from enum import Enum
from typing import Any, Callable, Optional
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap, QPolygonF
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.ui.tray")


class TrayState(str, Enum):
    READY = "READY"
    WORKING = "WORKING"
    PAUSED = "PAUSED"
    ATTENTION_REQUIRED = "ATTENTION_REQUIRED"
    ERROR = "ERROR"


STATE_COLORS = {
    TrayState.READY: "#89b4fa",             # Blue/Lavender
    TrayState.WORKING: "#f9e2af",           # Amber/Gold
    TrayState.PAUSED: "#fab387",            # Peach/Orange
    TrayState.ATTENTION_REQUIRED: "#cba6f7",# Mauve/Violet
    TrayState.ERROR: "#f38ba8",             # Red
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

    # 1. Dark circular container (#1e1e2e border)
    spark_color = QColor(STATE_COLORS.get(state, "#89b4fa"))
    painter.setBrush(QColor("#181825"))
    painter.setPen(spark_color)
    painter.drawEllipse(2, 2, size - 4, size - 4)

    # 2. Draw 4-point Astra Star/Spark in center
    cx, cy = size / 2.0, size / 2.0
    outer_r = size * 0.32
    inner_r = size * 0.10

    path = QPainterPath()
    # 4 points at 0, 90, 180, 270 deg with inner pinched vertices at 45, 135, 225, 315 deg
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
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 8px;
                padding: 6px;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #313244;
                color: #89b4fa;
            }
            QMenu::separator {
                height: 1px;
                background-color: #313244;
                margin: 4px 6px;
            }
        """)

        # 1. Open Astra
        open_action = QAction("Open Astra  (Alt+Space)", self)
        open_action.triggered.connect(self.open_astra_requested.emit)
        menu.addAction(open_action)

        # 2. Task Center
        task_center_action = QAction("Task Center", self)
        task_center_action.triggered.connect(self.open_task_center_requested.emit)
        menu.addAction(task_center_action)

        menu.addSeparator()

        # 3. Pause / Resume Astra
        self.pause_action = QAction("Pause Astra", self)
        self.pause_action.triggered.connect(self._toggle_pause)
        menu.addAction(self.pause_action)

        # 4. Settings
        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings_requested.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        # 5. Restart Astra
        restart_action = QAction("Restart Astra", self)
        restart_action.triggered.connect(self.restart_requested.emit)
        menu.addAction(restart_action)

        # 6. Quit Astra
        exit_action = QAction("Quit Astra", self)
        exit_action.triggered.connect(self.exit_requested.emit)
        menu.addAction(exit_action)

        self.setContextMenu(menu)

    def _toggle_pause(self) -> None:
        """Toggle pause state from tray menu."""
        if self.is_paused:
            self.is_paused = False
            self.pause_action.setText("Pause Astra")
            self.set_state(TrayState.READY)
            self.resume_astra_requested.emit()
        else:
            self.is_paused = True
            self.pause_action.setText("Resume Astra")
            self.set_state(TrayState.PAUSED)
            self.pause_astra_requested.emit()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle click/double-click on the tray icon."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_astra_requested.emit()
