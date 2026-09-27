"""Live Task Activity Timeline UI widget rendering real-time observable system events."""

from __future__ import annotations

from typing import Any, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from astrarun.tasks.models import Task, TaskEvent, TaskEventType, TaskStatus


# Status Icons and Styles
STATUS_STYLES = {
    "SUCCESS": ("✓", "#a6e3a1", "Completed"),
    "RUNNING": ("●", "#89b4fa", "Running"),
    "PENDING": ("○", "#6c7086", "Pending"),
    "WAITING": ("⏳", "#f9e2af", "Waiting for input"),
    "WARNING": ("!", "#f9e2af", "Action required"),
    "FAILED": ("✗", "#f38ba8", "Failed"),
    "BLOCKED": ("⊘", "#f38ba8", "Blocked by policy"),
    "CANCELLED": ("—", "#585b70", "Cancelled"),
}


class ActivityEventRow(QFrame):
    """Single row in the activity timeline representing an observable TaskEvent."""

    def __init__(self, event: TaskEvent, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.task_event = event
        self._is_expanded = False

        self.setStyleSheet("""
            QFrame {
                background-color: transparent;
                border: none;
                padding: 2px 0px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 2, 4, 2)
        main_layout.setSpacing(2)

        # Header Row: [Icon] [Title] [Duration / Capability]
        header = QHBoxLayout()
        header.setSpacing(8)

        icon, color, _ = STATUS_STYLES.get(event.status.upper(), ("●", "#89b4fa", "Active"))
        self.icon_label = QLabel(icon, self)
        self.icon_label.setStyleSheet(f"color: {color}; font-size: 13px; font-weight: bold;")
        header.addWidget(self.icon_label)

        self.title_label = QLabel(event.title, self)
        self.title_label.setStyleSheet("color: #cdd6f4; font-size: 13px; font-weight: 600;")
        header.addWidget(self.title_label)
        header.addStretch(1)

        dur_text = f"{event.duration_ms:.1f} ms" if event.duration_ms is not None else ""
        if dur_text:
            self.dur_label = QLabel(dur_text, self)
            self.dur_label.setStyleSheet("color: #6c7086; font-size: 11px; font-family: Consolas, monospace;")
            header.addWidget(self.dur_label)

        main_layout.addLayout(header)

        # Optional Summary Row
        if event.summary:
            summary_row = QHBoxLayout()
            summary_row.setContentsMargins(20, 0, 0, 0)
            self.summary_label = QLabel(event.summary, self)
            self.summary_label.setStyleSheet("color: #a6adc8; font-size: 12px;")
            self.summary_label.setWordWrap(True)
            summary_row.addWidget(self.summary_label)
            main_layout.addLayout(summary_row)

        # Collapsible Detail Container (Debug / Deep inspection)
        self.detail_widget = QWidget(self)
        detail_layout = QVBoxLayout(self.detail_widget)
        detail_layout.setContentsMargins(20, 4, 0, 4)
        detail_layout.setSpacing(2)

        cap_text = f"Capability: {event.capability_id}" if event.capability_id else ""
        if cap_text:
            cap_lbl = QLabel(cap_text, self.detail_widget)
            cap_lbl.setStyleSheet("color: #89b4fa; font-size: 11px; font-family: Consolas, monospace;")
            detail_layout.addWidget(cap_lbl)

        if event.entity_ids:
            ent_lbl = QLabel(f"Entities: {', '.join(event.entity_ids)}", self.detail_widget)
            ent_lbl.setStyleSheet("color: #fab387; font-size: 11px; font-family: Consolas, monospace;")
            detail_layout.addWidget(ent_lbl)

        self.detail_widget.setVisible(False)
        main_layout.addWidget(self.detail_widget)

    def toggle_expanded(self) -> None:
        """Toggle detailed diagnostics visibility."""
        self._is_expanded = not self._is_expanded
        self.detail_widget.setVisible(self._is_expanded)

    def mousePressEvent(self, event: Any) -> None:
        """Click to expand/collapse details."""
        self.toggle_expanded()
        super().mousePressEvent(event)


class TaskActivityView(QFrame):
    """
    Live Activity Timeline UI component for AstraRun.
    
    Principles:
    - Reflects REAL internal system events.
    - Zero fabricated 'thinking' or fake progress narration.
    - Visual indicators for pending, running, success, warning, failed, and blocked states.
    - Keyboard-safe cancellation and dismissal.
    """

    task_cancelled = Signal(str)  # task_id
    dismissed = Signal()
    event_dispatched = Signal(object)  # TaskEvent (thread-safe signal bridge)

    def __init__(self, task: Optional[Task] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.task = task
        self._rows: list[ActivityEventRow] = []

        # Compatibility aliases
        self.cancel_requested = self.task_cancelled
        self.on_event = self.add_event

        self.setStyleSheet("""
            TaskActivityView {
                background-color: #181825;
                border: 1px solid #45475a;
                border-radius: 8px;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # Header Bar: [ASTRA · Status Badge] [Cancel / Dismiss Button]
        header = QHBoxLayout()
        self.status_badge = QLabel("ASTRA · Initializing", self)
        self.status_badge.setStyleSheet("color: #89b4fa; font-size: 14px; font-weight: bold;")
        header.addWidget(self.status_badge)
        header.addStretch(1)

        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_btn = self.cancel_button  # alias
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #f38ba8;
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
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        header.addWidget(self.cancel_button)

        main_layout.addLayout(header)

        # Request Label
        req_text = task.request_text if task and task.request_text else ""
        self.request_label = QLabel(f"> {req_text}" if req_text else "", self)
        self.request_label.setStyleSheet("color: #cdd6f4; font-size: 13px; font-weight: 500; font-style: italic;")
        self.request_label.setVisible(bool(req_text))
        main_layout.addWidget(self.request_label)

        # Timeline Scroll Area
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 6px;
            }
            QScrollBar:vertical {
                width: 6px;
                background-color: transparent;
            }
            QScrollBar::handle:vertical {
                background-color: #45475a;
                border-radius: 3px;
            }
        """)

        self.timeline_container = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_container)
        self.timeline_layout.setContentsMargins(8, 8, 8, 8)
        self.timeline_layout.setSpacing(6)
        self.timeline_layout.addStretch(1)
        self.scroll_area.setWidget(self.timeline_container)

        main_layout.addWidget(self.scroll_area, 1)

        # Connect thread-safe signal bridge
        self.event_dispatched.connect(self._handle_event_in_qt_thread)

        # Populate initial events if task provided
        if task:
            for ev in task.events:
                self.add_event(ev)
            self._update_status_header(task.status)

    def set_task(self, task: Task) -> None:
        """Set or update the active task displayed in this activity view."""
        self.task = task
        if task.request_text:
            self.request_label.setText(f"> {task.request_text}")
            self.request_label.setVisible(True)
        self._update_status_header(task.status)
        for ev in task.events:
            self.add_event(ev)

    def add_event(self, event: TaskEvent) -> None:
        """Thread-safe entry point to append an event to the timeline."""
        self.event_dispatched.emit(event)

    def _handle_event_in_qt_thread(self, event: TaskEvent) -> None:
        """Internal Qt thread handler to update timeline UI widgets."""
        row = ActivityEventRow(event, self.timeline_container)
        self._rows.append(row)

        # Insert before stretch item
        idx = max(0, self.timeline_layout.count() - 1)
        self.timeline_layout.insertWidget(idx, row)

        # Auto-scroll to latest event
        self.scroll_area.verticalScrollBar().setValue(
            self.scroll_area.verticalScrollBar().maximum()
        )

        # Update header status based on event
        if event.type == TaskEventType.TASK_COMPLETED:
            self._update_status_header(TaskStatus.COMPLETED)
        elif event.type == TaskEventType.TASK_FAILED:
            self._update_status_header(TaskStatus.FAILED)
        elif event.type == TaskEventType.TASK_BLOCKED:
            self._update_status_header(TaskStatus.BLOCKED)
        elif event.type == TaskEventType.TASK_CANCELLED:
            self._update_status_header(TaskStatus.CANCELLED)
        elif event.type in (TaskEventType.CONFIRMATION_REQUESTED, TaskEventType.CLARIFICATION_REQUESTED):
            self._update_status_header(TaskStatus.WAITING_CONFIRMATION)
        else:
            self._update_status_header(TaskStatus.RUNNING)

    def _update_status_header(self, status: TaskStatus) -> None:
        """Update status title and cancel button state."""
        if status == TaskStatus.RUNNING:
            self.status_badge.setText("ASTRA · Working")
            self.status_badge.setStyleSheet("color: #89b4fa; font-size: 14px; font-weight: bold;")
            self.cancel_button.setVisible(True)
        elif status == TaskStatus.WAITING_CONFIRMATION:
            self.status_badge.setText("ASTRA · Waiting for confirmation")
            self.status_badge.setStyleSheet("color: #f9e2af; font-size: 14px; font-weight: bold;")
            self.cancel_button.setVisible(True)
        elif status == TaskStatus.WAITING_CLARIFICATION:
            self.status_badge.setText("ASTRA · Waiting for clarification")
            self.status_badge.setStyleSheet("color: #f9e2af; font-size: 14px; font-weight: bold;")
            self.cancel_button.setVisible(True)
        elif status == TaskStatus.COMPLETED:
            self.status_badge.setText("ASTRA · Complete")
            self.status_badge.setStyleSheet("color: #a6e3a1; font-size: 14px; font-weight: bold;")
            self.cancel_button.setText("Done")
            self.cancel_button.setStyleSheet("""
                QPushButton {
                    background-color: #313244;
                    color: #a6e3a1;
                    border: 1px solid #45475a;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
        elif status == TaskStatus.FAILED:
            self.status_badge.setText("ASTRA · Failed")
            self.status_badge.setStyleSheet("color: #f38ba8; font-size: 14px; font-weight: bold;")
            self.cancel_button.setText("Close")
        elif status == TaskStatus.BLOCKED:
            self.status_badge.setText("ASTRA · Blocked by Policy")
            self.status_badge.setStyleSheet("color: #f38ba8; font-size: 14px; font-weight: bold;")
            self.cancel_button.setText("Close")
        elif status == TaskStatus.CANCELLED:
            self.status_badge.setText("ASTRA · Cancelled")
            self.status_badge.setStyleSheet("color: #6c7086; font-size: 14px; font-weight: bold;")
            self.cancel_button.setText("Close")

    def _on_cancel_clicked(self) -> None:
        """Handle cancel/done button click."""
        if self.task.status.is_terminal:
            self.dismissed.emit()
        else:
            self.task_cancelled.emit(self.task.id)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Keyboard dismissal with Escape key."""
        if event.key() == Qt.Key_Escape:
            if not self.task.status.is_terminal:
                self.task_cancelled.emit(self.task.id)
            self.dismissed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)
