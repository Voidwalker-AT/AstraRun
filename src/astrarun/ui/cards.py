"""Interactive Confirmation and Disambiguation cards for AstraRun v0.6 UI."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.models import ToolRisk


class ConfirmationCard(QFrame):
    """
    Keyboard-safe interactive confirmation card for high-risk or sensitive actions.
    
    Safety rules:
    - Escape cancels confirmation.
    - For HIGH risk: Enter alone does NOT confirm (prevents accidental keystroke firing).
      Requires clicking [Proceed] or pressing Ctrl+Enter.
    """

    confirmed = Signal(str, str, dict)  # token, tool, arguments
    cancelled = Signal()

    def __init__(
        self,
        token: str,
        tool: str,
        arguments: dict[str, Any],
        title: str = "Confirm Action",
        description: str = "",
        risk: ToolRisk = ToolRisk.HIGH,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.token = token
        self.tool = tool
        self.arguments = arguments
        self.risk = risk

        self.setStyleSheet("""
            QFrame {
                background-color: #181825;
                border: 1px solid #45475a;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Header row with title & risk badge
        header_row = QHBoxLayout()
        self.title_label = QLabel(title, self)
        self.title_label.setStyleSheet("color: #cdd6f4; font-size: 15px; font-weight: bold;")
        header_row.addWidget(self.title_label)
        header_row.addStretch(1)

        # Risk badge
        risk_bg = "#f38ba8" if risk == ToolRisk.HIGH else "#f9e2af" if risk == ToolRisk.MEDIUM else "#a6e3a1"
        risk_fg = "#11111b"
        self.risk_badge = QLabel(f" {risk.value} RISK ", self)
        self.risk_badge.setStyleSheet(f"""
            background-color: {risk_bg};
            color: {risk_fg};
            font-size: 11px;
            font-weight: bold;
            border-radius: 4px;
            padding: 2px 4px;
        """)
        header_row.addWidget(self.risk_badge)
        layout.addLayout(header_row)

        # Description text
        desc_text = description or f"Target: {arguments}"
        self.desc_label = QLabel(desc_text, self)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #a6adc8; font-size: 13px;")
        layout.addWidget(self.desc_label)

        # Notice label for high risk
        if risk == ToolRisk.HIGH:
            self.hint_label = QLabel("Deliberate confirmation required: Click or press Ctrl+Enter", self)
            self.hint_label.setStyleSheet("color: #fab387; font-size: 11px; font-style: italic;")
            layout.addWidget(self.hint_label)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        self.cancel_btn = QPushButton("Cancel (Esc)", self)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)

        action_btn_text = "Stop Process (Ctrl+Enter)" if "terminate" in tool else "Proceed (Ctrl+Enter)"
        btn_bg = "#f38ba8" if risk == ToolRisk.HIGH else "#89b4fa"
        self.confirm_btn = QPushButton(action_btn_text, self)
        self.confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                color: #11111b;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                opacity: 0.9;
            }}
        """)
        self.confirm_btn.clicked.connect(self._on_confirm)
        btn_row.addWidget(self.confirm_btn)

        layout.addLayout(btn_row)

    def _on_cancel(self) -> None:
        self.cancelled.emit()

    def _on_confirm(self) -> None:
        self.confirmed.emit(self.token, self.tool, self.arguments)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self._on_cancel()
            event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self.risk == ToolRisk.HIGH:
                if event.modifiers() & Qt.ControlModifier:
                    self._on_confirm()
                    event.accept()
                else:
                    # Ignore Enter alone for high risk
                    event.ignore()
            else:
                self._on_confirm()
                event.accept()
        else:
            super().keyPressEvent(event)


class DisambiguationCard(QFrame):
    """
    Card presenting ambiguous candidate entities for user selection.
    Selecting a candidate feeds directly back into the proposed action pipeline.
    """

    candidate_selected = Signal(dict)
    cancelled = Signal()

    def __init__(
        self,
        candidates: list[dict[str, Any]],
        title: str = "Which target did you mean?",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.candidates = candidates

        self.setStyleSheet("""
            QFrame {
                background-color: #181825;
                border: 1px solid #45475a;
                border-radius: 8px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self.title_label = QLabel(title, self)
        self.title_label.setStyleSheet("color: #cdd6f4; font-size: 14px; font-weight: bold;")
        layout.addWidget(self.title_label)

        self.list_widget = QListWidget(self)
        self.list_widget.setStyleSheet("""
            QListWidget {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 6px;
                color: #cdd6f4;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 10px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #45475a;
                color: #89b4fa;
            }
            QListWidget::item:hover {
                background-color: #313244;
            }
        """)

        for cand in candidates:
            c_name = cand.get("name") or cand.get("alias") or cand.get("id") or str(cand)
            c_path = cand.get("path", "")
            display_text = f"{c_name} — {c_path}" if c_path else str(c_name)
            item = QListWidgetItem(display_text, self.list_widget)
            item.setData(Qt.UserRole, cand)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        self.list_widget.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self.list_widget)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        cand_data = item.data(Qt.UserRole)
        if cand_data:
            self.candidate_selected.emit(cand_data)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.cancelled.emit()
            event.accept()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            curr = self.list_widget.currentItem()
            if curr:
                self._on_item_activated(curr)
                event.accept()
        elif event.key() in (Qt.Key_Up, Qt.Key_Down):
            row = self.list_widget.currentRow()
            if event.key() == Qt.Key_Down and row < self.list_widget.count() - 1:
                self.list_widget.setCurrentRow(row + 1)
            elif event.key() == Qt.Key_Up and row > 0:
                self.list_widget.setCurrentRow(row - 1)
            event.accept()
        else:
            super().keyPressEvent(event)
