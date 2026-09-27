"""System Tray icon and context menu for resident AstraRun operation."""

from __future__ import annotations

import sys
from typing import Any, Callable, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.ui.tray")


def create_tray_icon_pixmap(size: int = 32) -> QIcon:
    """Generate a clean Catppuccin Mocha icon programmatically."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Outer circle (#181825 border #89b4fa)
    painter.setBrush(QColor("#1e1e2e"))
    painter.setPen(QColor("#89b4fa"))
    painter.drawEllipse(2, 2, size - 4, size - 4)

    # Inner emblem (Astra spark)
    painter.setBrush(QColor("#89b4fa"))
    painter.setPen(Qt.PenStyle.NoPen)
    cx, cy = size // 2, size // 2
    r = size // 4
    painter.drawEllipse(cx - r // 2, cy - r // 2, r, r)

    painter.end()
    return QIcon(pixmap)


class AstraTrayIcon(QSystemTrayIcon):
    """Resident system tray controller for AstraRun."""

    toggle_launcher_requested = Signal()
    open_history_requested = Signal()
    open_memory_requested = Signal()
    open_skills_requested = Signal()
    open_diagnostics_requested = Signal()
    open_settings_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        icon = create_tray_icon_pixmap()
        super().__init__(icon, parent)
        self.setToolTip("AstraRun — Workstation Control Plane (Alt+Space)")

        self._build_menu()
        self.activated.connect(self._on_activated)

    def _build_menu(self) -> None:
        """Construct the tray context menu."""
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 4px;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QMenu::item {
                padding: 6px 20px 6px 12px;
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

        # Open Astra
        open_action = QAction("Open AstraRun  (Alt+Space)", self)
        open_action.triggered.connect(self.toggle_launcher_requested.emit)
        menu.addAction(open_action)

        menu.addSeparator()

        # History & Tasks
        hist_action = QAction("Task Activity & History", self)
        hist_action.triggered.connect(self.open_history_requested.emit)
        menu.addAction(hist_action)

        # Memory & Learning
        mem_action = QAction("Semantic Memory & Aliases", self)
        mem_action.triggered.connect(self.open_memory_requested.emit)
        menu.addAction(mem_action)

        # Skills
        skill_action = QAction("Workflow Skills", self)
        skill_action.triggered.connect(self.open_skills_requested.emit)
        menu.addAction(skill_action)

        menu.addSeparator()

        # Diagnostics & Settings
        diag_action = QAction("Diagnostics", self)
        diag_action.triggered.connect(self.open_diagnostics_requested.emit)
        menu.addAction(diag_action)

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self.open_settings_requested.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        # Exit
        exit_action = QAction("Exit AstraRun", self)
        exit_action.triggered.connect(self.exit_requested.emit)
        menu.addAction(exit_action)

        self.setContextMenu(menu)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle click/double-click on the tray icon."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_launcher_requested.emit()
