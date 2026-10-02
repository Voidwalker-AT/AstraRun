"""Task Center UI window for AstraRun 1.0.

Presents multi-task management:
  - ACTIVE, QUEUED, WAITING, and RECENT task sections
  - Polished empty state with vector Astra mark
  - Fact-based task progress, capabilities, and durations
  - Pause, Resume, and Cancel actions
  - Bounded memory queries from TaskLedger
"""

from __future__ import annotations

import sys
import time
from typing import Any, Dict, List, Optional, Tuple

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
from astrarun.ui.icons import IconRenderer
from astrarun.ui.theme import (
    ACCENT,
    ACCENT_BORDER,
    ACCENT_SUBTLE,
    ATTENTION,
    ATTENTION_BORDER,
    ATTENTION_BG,
    BG_APP,
    BORDER,
    BORDER_STRONG,
    BORDER_SUBTLE,
    DANGER,
    DANGER_BORDER,
    DANGER_BG,
    FONT_FAMILY,
    FONT_MONO,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_SMALL,
    FONT_SIZE_TITLE,
    FONT_SIZE_TITLE_LG,
    RADIUS_MD,
    RADIUS_SM,
    SCROLLBAR_STYLE,
    SUCCESS,
    SUCCESS_BORDER,
    SUCCESS_BG,
    SURFACE,
    SURFACE_HOVER,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
    WARNING_BORDER,
    WARNING_BG,
    get_badge_style,
    get_button_style,
)

logger = get_logger("astrarun.ui.task_center")


def _get_status_presentation(status: TaskStatus) -> Tuple[str, str, str, str, str]:
    """Map TaskStatus to (icon_name, fg_color, bg_color, border_color, display_label)."""
    if status == TaskStatus.RUNNING:
        return ("running", ACCENT, ACCENT_SUBTLE, ACCENT_BORDER, "Running")
    elif status == TaskStatus.PLANNING:
        return ("spark", ACCENT, ACCENT_SUBTLE, ACCENT_BORDER, "Planning")
    elif status == TaskStatus.WAITING_CONFIRMATION:
        return ("warning", WARNING, WARNING_BG, WARNING_BORDER, "Needs Review")
    elif status == TaskStatus.WAITING_CLARIFICATION:
        return ("question", ATTENTION, ATTENTION_BG, ATTENTION_BORDER, "Clarifying")
    elif status in (TaskStatus.PAUSED, TaskStatus.PAUSED_USER_ACTIVE):
        return ("pause", WARNING, WARNING_BG, WARNING_BORDER, "Paused")
    elif status == TaskStatus.COMPLETED:
        return ("check", SUCCESS, SUCCESS_BG, SUCCESS_BORDER, "Completed")
    elif status == TaskStatus.FAILED:
        return ("error", DANGER, DANGER_BG, DANGER_BORDER, "Failed")
    elif status == TaskStatus.CANCELLED:
        return ("close", TEXT_MUTED, SURFACE_RAISED, BORDER, "Cancelled")
    elif status == TaskStatus.BLOCKED:
        return ("close", DANGER, DANGER_BG, DANGER_BORDER, "Blocked")
    elif status == TaskStatus.QUEUED:
        return ("pending", TEXT_MUTED, SURFACE_RAISED, BORDER, "Queued")
    else:
        return ("pending", TEXT_SECONDARY, SURFACE_RAISED, BORDER, status.value.title())


class TaskCardWidget(QFrame):
    """Card representing a single active, queued, waiting, or completed task."""

    pause_clicked = Signal(str)
    resume_clicked = Signal(str)
    cancel_clicked = Signal(str)

    def __init__(self, task: Task, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.task = task
        self.setObjectName("task_card")
        self.setMinimumHeight(76)

        self.setStyleSheet(f"""
            QFrame#task_card {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_MD}px;
            }}
            QFrame#task_card:hover {{
                border-color: {BORDER_STRONG};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header Row: [Vector Icon] [Title/Goal] [Status Badge]
        header = QHBoxLayout()
        header.setSpacing(8)

        icon_name, fg_col, bg_col, b_col, label_text = _get_status_presentation(task.status)

        self.status_icon = IconRenderer.create_label(
            icon_name,
            size=16,
            color=fg_col,
            bg_circle=True,
            bg_color=bg_col,
            parent=self,
        )
        header.addWidget(self.status_icon)

        title_text = task.request_text.strip() if task.request_text else f"Task {task.id}"
        self.title_label = QLabel(title_text[:64], self)
        self.title_label.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_BODY};
            font-weight: 600;
            font-family: {FONT_FAMILY};
        """)
        header.addWidget(self.title_label, stretch=1)

        self.status_badge = QLabel(label_text, self)
        self.status_badge.setStyleSheet(get_badge_style(fg_col, bg_col, b_col))
        header.addWidget(self.status_badge)

        layout.addLayout(header)

        # Latest Fact / Observation Row
        latest_event = task.events[-1] if task.events else None
        if latest_event and (latest_event.summary or latest_event.title):
            fact_text = latest_event.summary or latest_event.title
        elif task.status == TaskStatus.COMPLETED:
            fact_text = "Completed successfully"
        elif task.status == TaskStatus.RUNNING:
            fact_text = "Executing plan step..."
        elif task.status == TaskStatus.QUEUED:
            fact_text = "Waiting in execution queue"
        elif task.status in (TaskStatus.PAUSED, TaskStatus.PAUSED_USER_ACTIVE):
            fact_text = "Paused — computer active"
        else:
            fact_text = "Initialized"

        self.fact_label = QLabel(fact_text, self)
        self.fact_label.setWordWrap(True)
        self.fact_label.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-size: {FONT_SIZE_CAPTION};
            font-family: {FONT_FAMILY};
        """)
        layout.addWidget(self.fact_label)

        # Actions Row (Duration + Pause / Resume / Cancel)
        actions_row = QHBoxLayout()
        actions_row.setSpacing(6)

        dur_sec = (time.time() - task.created_at) if not task.status.is_terminal else (task.duration_ms() / 1000.0)
        time_text = f"{dur_sec:.1f}s" if dur_sec < 60 else f"{int(dur_sec // 60)}m {int(dur_sec % 60)}s"
        time_lbl = QLabel(time_text, self)
        time_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: {FONT_SIZE_SMALL}; font-family: {FONT_MONO};")
        actions_row.addWidget(time_lbl)
        actions_row.addStretch(1)

        if task.status in (TaskStatus.RUNNING, TaskStatus.PLANNING):
            btn_pause = QPushButton("Pause", self)
            btn_pause.setStyleSheet(get_button_style("subtle", size="sm"))
            btn_pause.clicked.connect(lambda: self.pause_clicked.emit(self.task.id))
            actions_row.addWidget(btn_pause)

        elif task.status in (TaskStatus.PAUSED, TaskStatus.PAUSED_USER_ACTIVE):
            btn_resume = QPushButton("Resume", self)
            btn_resume.setStyleSheet(get_button_style("primary", size="sm"))
            btn_resume.clicked.connect(lambda: self.resume_clicked.emit(self.task.id))
            actions_row.addWidget(btn_resume)

        if not task.status.is_terminal:
            btn_cancel = QPushButton("Cancel", self)
            btn_cancel.setStyleSheet(get_button_style("danger", size="sm"))
            btn_cancel.clicked.connect(lambda: self.cancel_clicked.emit(self.task.id))
            actions_row.addWidget(btn_cancel)

        layout.addLayout(actions_row)


class EmptyStateWidget(QWidget):
    """Quiet, high-polish empty state displayed when no tasks exist."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 60, 20, 60)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Astra Mark Icon
        self.icon_lbl = IconRenderer.create_label("spark", size=44, color=BORDER_STRONG, parent=self)
        layout.addWidget(self.icon_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        # Primary Title
        self.title_lbl = QLabel("No recent tasks", self)
        self.title_lbl.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_TITLE};
            font-weight: 600;
            font-family: {FONT_FAMILY};
        """)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_lbl)

        # Subtitle
        self.desc_lbl = QLabel("Tasks you summon with Alt+Space will appear here.", self)
        self.desc_lbl.setStyleSheet(f"""
            color: {TEXT_MUTED};
            font-size: {FONT_SIZE_BODY};
            font-family: {FONT_FAMILY};
        """)
        self.desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.desc_lbl)


class SectionHeaderWidget(QWidget):
    """Subtle section header partition."""

    def __init__(self, title: str, count: int = 0, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.setSpacing(6)

        header_text = f"{title.upper()} ({count})" if count > 0 else title.upper()
        lbl = QLabel(header_text, self)
        lbl.setStyleSheet(f"""
            color: {TEXT_MUTED};
            font-size: {FONT_SIZE_SMALL};
            font-weight: 700;
            font-family: {FONT_FAMILY};
            letter-spacing: 0.5px;
        """)
        layout.addWidget(lbl)
        layout.addStretch(1)


class TaskCenterWindow(QDialog):
    """
    Unified Astra Task Center window displaying active, waiting, and historical tasks.
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
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_APP};
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY};
            }}
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # Header: [Vector Astra Mark] [Astra Task Center] [Active count badge] [Refresh]
        header = QHBoxLayout()
        header.setSpacing(10)

        mark = IconRenderer.create_label("spark", size=18, color=ACCENT, parent=self)
        header.addWidget(mark)

        title = QLabel("Task Center", self)
        title.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_TITLE_LG};
            font-weight: 700;
            font-family: {FONT_FAMILY};
        """)
        header.addWidget(title)

        header.addStretch(1)

        self.active_count_lbl = QLabel("0 active", self)
        self.active_count_lbl.setStyleSheet(get_badge_style(TEXT_SECONDARY, SURFACE_RAISED, BORDER))
        header.addWidget(self.active_count_lbl)

        btn_refresh = QPushButton("Refresh", self)
        btn_refresh.setStyleSheet(get_button_style("subtle", size="sm"))
        btn_refresh.clicked.connect(self.refresh_tasks)
        header.addWidget(btn_refresh)

        layout.addLayout(header)

        # Scrollable Task Cards Area
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            {SCROLLBAR_STYLE}
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
        raw_tasks: List[Task] = []
        if self.task_runtime is not None:
            raw_tasks = self.task_runtime.get_recent_tasks(limit=30)
        elif self.app is not None and hasattr(self.app, "task_ledger"):
            raw_tasks = self.app.task_ledger.list_tasks(limit=30)

        # Filter out invalid or ghost fixture tasks
        tasks = [t for t in raw_tasks if t and (t.request_text or t.events or t.id)]

        # Count active tasks
        active_count = sum(1 for t in tasks if not t.status.is_terminal)
        self.active_count_lbl.setText(f"{active_count} active")

        # Clear existing cards and section headers
        while self.cards_layout.count() > 1:
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

        if not tasks:
            empty_state = EmptyStateWidget(self.cards_container)
            self.cards_layout.insertWidget(0, empty_state)
            return

        # Partition into Active, Waiting, and Recent
        active_tasks = [t for t in tasks if t.status in (
            TaskStatus.RUNNING, TaskStatus.PLANNING, TaskStatus.PAUSED,
            TaskStatus.PAUSED_USER_ACTIVE, TaskStatus.WAITING_CONFIRMATION, TaskStatus.WAITING_CLARIFICATION
        )]
        waiting_tasks = [t for t in tasks if t.status in (TaskStatus.QUEUED, TaskStatus.BLOCKED)]
        recent_tasks = [t for t in tasks if t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)]

        insert_idx = 0

        # Section 1: Active Tasks
        if active_tasks:
            sec_header = SectionHeaderWidget("Active", len(active_tasks), self.cards_container)
            self.cards_layout.insertWidget(insert_idx, sec_header)
            insert_idx += 1
            for t in active_tasks:
                card = self._create_card(t)
                self.cards_layout.insertWidget(insert_idx, card)
                insert_idx += 1

        # Section 2: Waiting Tasks
        if waiting_tasks:
            sec_header = SectionHeaderWidget("Waiting", len(waiting_tasks), self.cards_container)
            self.cards_layout.insertWidget(insert_idx, sec_header)
            insert_idx += 1
            for t in waiting_tasks:
                card = self._create_card(t)
                self.cards_layout.insertWidget(insert_idx, card)
                insert_idx += 1

        # Section 3: Recent Tasks
        if recent_tasks:
            sec_header = SectionHeaderWidget("Recent", len(recent_tasks), self.cards_container)
            self.cards_layout.insertWidget(insert_idx, sec_header)
            insert_idx += 1
            for t in recent_tasks:
                card = self._create_card(t)
                self.cards_layout.insertWidget(insert_idx, card)
                insert_idx += 1

    def _create_card(self, task: Task) -> TaskCardWidget:
        card = TaskCardWidget(task, self.cards_container)
        card.pause_clicked.connect(self._on_pause)
        card.resume_clicked.connect(self._on_resume)
        card.cancel_clicked.connect(self._on_cancel)
        return card

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
