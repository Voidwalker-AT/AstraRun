"""Task Center UI window for AstraRun 1.0.

Presents multi-task management:
  - ACTIVE, QUEUED, WAITING, COMPLETED, FAILED task views
  - Fact-based task progress, capabilities, and durations
  - Pause, Resume, and Cancel actions
  - Bounded memory queries from TaskLedger
"""

from __future__ import annotations

import sys
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.logging import get_logger
from astrarun.tasks.models import Task, TaskEvent, TaskStatus

logger = get_logger("astrarun.ui.task_center")


class TaskCardWidget(QFrame):
    """Card representing a single active, queued, waiting, or completed task."""

    pause_clicked = Signal(str)
    resume_clicked = Signal(str)
    cancel_clicked = Signal(str)

    def __init__(self, task: Task, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.task = task

        self.setStyleSheet("""
            QFrame {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 8px;
                padding: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header Row: [Glyph] [Title/Goal] [Status Badge]
        header = QHBoxLayout()
        header.setSpacing(8)

        status_glyphs = {
            TaskStatus.RUNNING: ("►", "#89b4fa"),
            TaskStatus.QUEUED: ("↓", "#a6adc8"),
            TaskStatus.PLANNING: ("✦", "#cba6f7"),
            TaskStatus.WAITING_CONFIRMATION: ("!", "#fab387"),
            TaskStatus.WAITING_CLARIFICATION: ("?", "#cba6f7"),
            TaskStatus.PAUSED: ("❚❚", "#fab387"),
            TaskStatus.PAUSED_USER_ACTIVE: ("❚❚", "#fab387"),
            TaskStatus.COMPLETED: ("✓", "#a6e3a1"),
            TaskStatus.FAILED: ("✗", "#f38ba8"),
            TaskStatus.CANCELLED: ("—", "#6c7086"),
            TaskStatus.BLOCKED: ("⊘", "#f38ba8"),
        }
        glyph, color = status_glyphs.get(task.status, ("●", "#89b4fa"))

        glyph_lbl = QLabel(glyph, self)
        glyph_lbl.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
        header.addWidget(glyph_lbl)

        title_text = task.request_text or "Workstation Goal"
        self.title_label = QLabel(title_text[:60], self)
        self.title_label.setStyleSheet("color: #cdd6f4; font-size: 13px; font-weight: 600;")
        header.addWidget(self.title_label, stretch=1)

        self.status_badge = QLabel(task.status.value.replace("_", " ").title(), self)
        self.status_badge.setStyleSheet(f"""
            color: {color};
            background-color: #181825;
            border: 1px solid {color}44;
            border-radius: 4px;
            padding: 2px 6px;
            font-size: 10px;
            font-weight: bold;
        """)
        header.addWidget(self.status_badge)

        layout.addLayout(header)

        # Latest Fact / Observation Row
        latest_event = task.events[-1] if task.events else None
        fact_text = latest_event.summary or latest_event.title if latest_event else "Initializing..."
        self.fact_label = QLabel(fact_text, self)
        self.fact_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        layout.addWidget(self.fact_label)

        # Actions Row (Pause / Resume / Cancel)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        dur_sec = (time.time() - task.created_at) if not task.status.is_terminal else (task.duration_ms() / 1000.0)
        time_text = f"{dur_sec:.1f}s" if dur_sec < 60 else f"{int(dur_sec // 60)}m {int(dur_sec % 60)}s"
        time_lbl = QLabel(time_text, self)
        time_lbl.setStyleSheet("color: #6c7086; font-size: 10px; font-family: monospace;")
        actions_row.addWidget(time_lbl)
        actions_row.addStretch(1)

        if task.status in (TaskStatus.RUNNING, TaskStatus.PLANNING):
            btn_pause = QPushButton("Pause", self)
            btn_pause.setStyleSheet(self._btn_style("#313244", "#fab387"))
            btn_pause.clicked.connect(lambda: self.pause_clicked.emit(self.task.id))
            actions_row.addWidget(btn_pause)

        elif task.status in (TaskStatus.PAUSED, TaskStatus.PAUSED_USER_ACTIVE):
            btn_resume = QPushButton("Resume", self)
            btn_resume.setStyleSheet(self._btn_style("#313244", "#a6e3a1"))
            btn_resume.clicked.connect(lambda: self.resume_clicked.emit(self.task.id))
            actions_row.addWidget(btn_resume)

        if not task.status.is_terminal:
            btn_cancel = QPushButton("Cancel", self)
            btn_cancel.setStyleSheet(self._btn_style("#313244", "#f38ba8"))
            btn_cancel.clicked.connect(lambda: self.cancel_clicked.emit(self.task.id))
            actions_row.addWidget(btn_cancel)

        layout.addLayout(actions_row)

    def _btn_style(self, bg: str, fg: str) -> str:
        return f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #45475a;
            }}
        """


class TaskCenterWindow(QDialog):
    """
    Unified Astra Task Center window displaying active, queued, and historical tasks.
    """

    task_pause_requested = Signal(str)
    task_resume_requested = Signal(str)
    task_cancel_requested = Signal(str)

    def __init__(self, task_runtime: Any = None, app: Any = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.task_runtime = task_runtime
        self.app = app
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh_tasks)

        self.setWindowTitle("Astra Task Center")
        self.resize(520, 580)
        self.setStyleSheet("""
            QDialog {
                background-color: #11111b;
                color: #cdd6f4;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Header: [✦ Astra Task Center] [Active count]
        header = QHBoxLayout()
        title = QLabel("✦ Astra Task Center", self)
        title.setStyleSheet("color: #89b4fa; font-size: 18px; font-weight: bold;")
        header.addWidget(title)

        header.addStretch(1)

        self.active_count_lbl = QLabel("0 active", self)
        self.active_count_lbl.setStyleSheet("color: #a6adc8; font-size: 13px; font-weight: 500;")
        header.addWidget(self.active_count_lbl)

        btn_refresh = QPushButton("Refresh", self)
        btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #313244;
            }
        """)
        btn_refresh.clicked.connect(self.refresh_tasks)
        header.addWidget(btn_refresh)

        layout.addLayout(header)

        # Scrollable Task Cards Area
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                width: 8px;
                background-color: transparent;
            }
            QScrollBar::handle:vertical {
                background-color: #313244;
                border-radius: 4px;
            }
        """)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch(1)

        self.scroll.setWidget(self.cards_container)
        layout.addWidget(self.scroll, stretch=1)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self.refresh_tasks()
        self._refresh_timer.start(1000)

    def hideEvent(self, event: Any) -> None:
        self._refresh_timer.stop()
        super().hideEvent(event)

    def refresh_tasks(self) -> None:
        """Fetch tasks from TaskRuntime or TaskLedger and update the UI."""
        tasks: List[Task] = []
        if self.task_runtime is not None:
            tasks = self.task_runtime.get_recent_tasks(limit=30)
        elif self.app is not None and hasattr(self.app, "task_ledger"):
            tasks = self.app.task_ledger.list_tasks(limit=30)

        # Count active tasks
        active_count = sum(1 for t in tasks if not t.status.is_terminal)
        self.active_count_lbl.setText(f"{active_count} active")

        # Clear existing cards
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # Render tasks
        for t in tasks:
            card = TaskCardWidget(t, self.cards_container)
            card.pause_clicked.connect(self._on_pause)
            card.resume_clicked.connect(self._on_resume)
            card.cancel_clicked.connect(self._on_cancel)
            self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

    def _on_pause(self, task_id: str) -> None:
        if self.task_runtime:
            self.task_runtime.pause_task(task_id)
        self.task_pause_requested.emit(task_id)
        self.refresh_tasks()

    def _on_resume(self, task_id: str) -> None:
        if self.task_runtime:
            self.task_runtime.resume_task(task_id)
        self.task_resume_requested.emit(task_id)
        self.refresh_tasks()

    def _on_cancel(self, task_id: str) -> None:
        if self.task_runtime:
            self.task_runtime.cancel_task(task_id)
        elif self.app is not None and hasattr(self.app, "task_manager"):
            self.app.task_manager.cancel_task(task_id)
        self.task_cancel_requested.emit(task_id)
        self.refresh_tasks()
