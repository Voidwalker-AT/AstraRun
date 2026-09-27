"""History UI displaying past conversations, tasks, timelines, search, and safe semantic re-runs."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from astrarun.tasks.ledger import TaskLedger
from astrarun.tasks.models import Task, TaskEvent, TaskStatus
from astrarun.tasks.serialization import generate_task_title


class TaskDetailWidget(QFrame):
    """Right-hand panel showing full audit details and timeline for a selected Task."""

    rerun_requested = Signal(str)  # task_id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setStyleSheet("""
            TaskDetailWidget {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header: [Title] [Run Again Button]
        header = QHBoxLayout()
        self.title_label = QLabel("Task Details", self)
        self.title_label.setStyleSheet("color: #89b4fa; font-size: 14px; font-weight: bold;")
        header.addWidget(self.title_label)
        header.addStretch(1)

        self.rerun_button = QPushButton("Run Again", self)
        self.rerun_button.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #89b4fa;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)
        self.rerun_button.clicked.connect(self._on_rerun_clicked)
        self.rerun_button.setVisible(False)
        header.addWidget(self.rerun_button)

        layout.addLayout(header)

        # Meta summary
        self.meta_label = QLabel("Select a task from history to inspect timeline.", self)
        self.meta_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
        self.meta_label.setWordWrap(True)
        layout.addWidget(self.meta_label)

        # Timeline list container
        self.timeline_scroll = QScrollArea(self)
        self.timeline_scroll.setWidgetResizable(True)
        self.timeline_scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")

        self.timeline_container = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_container)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_layout.setSpacing(4)
        self.timeline_layout.addStretch(1)
        self.timeline_scroll.setWidget(self.timeline_container)

        layout.addWidget(self.timeline_scroll, 1)

        self._current_task_id: Optional[str] = None

    def display_task(self, task: Task) -> None:
        """Render task metadata and complete chronological timeline."""
        self._current_task_id = task.id
        self.rerun_button.setVisible(bool(task.request_text))

        # Clear existing timeline items
        while self.timeline_layout.count() > 1:
            item = self.timeline_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        date_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(task.created_at))
        self.title_label.setText(generate_task_title(task.request_text))

        status_color = "#a6e3a1" if task.status == TaskStatus.COMPLETED else "#f38ba8" if task.status in (TaskStatus.FAILED, TaskStatus.BLOCKED) else "#fab387"
        meta_text = (
            f"Status: {task.status.value} | Date: {date_str} | Duration: {task.duration_ms():.1f} ms\n"
            f"Request: {task.request_text or '[No request text]'}\n"
            f"Summary: {task.final_result.summary if task.final_result else 'In progress or incomplete'}"
        )
        self.meta_label.setText(meta_text)

        # Populate timeline steps
        for ev in task.events:
            dur = f" ({ev.duration_ms:.1f} ms)" if ev.duration_ms is not None else ""
            cap = f" [{ev.capability_id}]" if ev.capability_id else ""
            line_lbl = QLabel(f"• {ev.title}{cap}{dur}\n  {ev.summary or ''}", self.timeline_container)
            line_lbl.setStyleSheet("color: #cdd6f4; font-size: 11px; padding: 2px 0px;")
            line_lbl.setWordWrap(True)
            self.timeline_layout.insertWidget(self.timeline_layout.count() - 1, line_lbl)

    def _on_rerun_clicked(self) -> None:
        if self._current_task_id:
            self.rerun_requested.emit(self._current_task_id)


class HistoryView(QFrame):
    """
    Dedicated Task History and Conversation audit UI component for AstraRun.
    
    Features:
    - Real-time search across past queries and summaries.
    - Quick date and status filters.
    - Split-view inspection of task details and timeline events.
    - Safe semantic re-run triggering.
    - Total history clearing with confirmation.
    """

    task_rerun_requested = Signal(str)  # task_id
    dismissed = Signal()

    def __init__(self, ledger: TaskLedger, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.ledger = ledger

        self.setStyleSheet("""
            HistoryView {
                background-color: #181825;
                border: 1px solid #45475a;
                border-radius: 8px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # Top Bar: [ASTRA HISTORY Title] [Search Bar] [Clear History] [Close]
        top_bar = QHBoxLayout()
        title_lbl = QLabel("ASTRA HISTORY", self)
        title_lbl.setStyleSheet("color: #89b4fa; font-size: 14px; font-weight: bold;")
        top_bar.addWidget(title_lbl)

        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText("Search past tasks and commands...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e2e;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
        """)
        self.search_input.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_input, 1)

        self.clear_btn = QPushButton("Clear History", self)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #f38ba8;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)
        self.clear_btn.clicked.connect(self._on_clear_history_clicked)
        top_bar.addWidget(self.clear_btn)

        self.close_btn = QPushButton("Esc", self)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #a6adc8;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
        """)
        self.close_btn.clicked.connect(self.dismissed.emit)
        top_bar.addWidget(self.close_btn)

        main_layout.addLayout(top_bar)

        # Filter Chips Bar: [All] [Today] [Yesterday] [Completed] [Failed/Blocked]
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(6)
        filter_lbl = QLabel("Filter:", self)
        filter_lbl.setStyleSheet("color: #6c7086; font-size: 11px; font-weight: bold;")
        filter_bar.addWidget(filter_lbl)

        self.filter_buttons = []
        for name in ("All", "Today", "Yesterday", "Completed", "Blocked/Failed"):
            btn = QPushButton(name, self)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e1e2e;
                    color: #a6adc8;
                    border: 1px solid #313244;
                    border-radius: 4px;
                    padding: 2px 8px;
                    font-size: 11px;
                }
                QPushButton:checked {
                    background-color: #45475a;
                    color: #89b4fa;
                    font-weight: bold;
                }
            """)
            btn.clicked.connect(lambda checked, n=name: self._on_filter_clicked(n))
            filter_bar.addWidget(btn)
            self.filter_buttons.append(btn)

        self.filter_buttons[0].setChecked(True)
        filter_bar.addStretch(1)
        main_layout.addLayout(filter_bar)

        # Main Splitter: Left (Task List) / Right (Task Detail)
        self.splitter = QSplitter(Qt.Horizontal, self)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #313244;
                width: 2px;
            }
        """)

        # Left Task List Widget
        self.task_list = QListWidget(self.splitter)
        self.task_list.setStyleSheet("""
            QListWidget {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 6px;
                color: #cdd6f4;
                outline: none;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #28293d;
            }
            QListWidget::item:selected {
                background-color: #45475a;
                color: #89b4fa;
            }
        """)
        self.task_list.currentItemChanged.connect(self._on_task_selected)
        self.task_list.itemActivated.connect(self._on_item_activated)
        self.splitter.addWidget(self.task_list)

        # Right Detail Widget
        self.detail_widget = TaskDetailWidget(self.splitter)
        self.detail_widget.rerun_requested.connect(self.task_rerun_requested.emit)
        self.splitter.addWidget(self.detail_widget)

        self.splitter.setSizes([320, 480])
        main_layout.addWidget(self.splitter, 1)

        self._active_filter = "All"
        self.refresh()

    def refresh(self) -> None:
        """Reload tasks from ledger based on current filters and search query."""
        query = self.search_input.text().strip()
        if query:
            tasks = self.ledger.search_tasks(query, limit=50)
        else:
            tasks = self.ledger.get_recent_tasks(limit=50)

        # Apply chip filters
        now = time.time()
        start_of_today = time.mktime(time.strptime(time.strftime("%Y-%m-%d 00:00:00"), "%Y-%m-%d %H:%M:%S"))
        start_of_yesterday = start_of_today - 86400.0

        filtered = []
        for t in tasks:
            if self._active_filter == "Today" and t.created_at < start_of_today:
                continue
            if self._active_filter == "Yesterday" and (t.created_at < start_of_yesterday or t.created_at >= start_of_today):
                continue
            if self._active_filter == "Completed" and t.status != TaskStatus.COMPLETED:
                continue
            if self._active_filter == "Blocked/Failed" and t.status not in (TaskStatus.FAILED, TaskStatus.BLOCKED):
                continue
            filtered.append(t)

        self.task_list.clear()
        for t in filtered:
            time_str = time.strftime("%H:%M", time.localtime(t.created_at))
            badge = "✓" if t.status == TaskStatus.COMPLETED else "✗" if t.status == TaskStatus.FAILED else "⊘" if t.status == TaskStatus.BLOCKED else "—"
            title = generate_task_title(t.request_text)
            item_text = f"{time_str}  [{badge}]  {title}"
            item = QListWidgetItem(item_text, self.task_list)
            item.setData(Qt.UserRole, t.id)

        if self.task_list.count() > 0:
            self.task_list.setCurrentRow(0)

    def _on_search_changed(self, text: str) -> None:
        self.refresh()

    def _on_filter_clicked(self, filter_name: str) -> None:
        self._active_filter = filter_name
        for btn in self.filter_buttons:
            btn.setChecked(btn.text() == filter_name)
        self.refresh()

    def _on_task_selected(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]) -> None:
        if not current:
            return
        task_id = current.data(Qt.UserRole)
        task = self.ledger.get_task(task_id, include_events=True)
        if task:
            self.detail_widget.display_task(task)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        task_id = item.data(Qt.UserRole)
        if task_id:
            self.task_rerun_requested.emit(task_id)

    def _on_clear_history_clicked(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to clear all AstraRun task history?\nThis will purge past task logs and conversation threads.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.ledger.clear_history()
            self.refresh()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.dismissed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)
