"""Interactive UI cards for AstraRun: Confirmation, Disambiguation, ResultCard, and ListResultCard.

Conforms to AstraRun 1.0 Unified Design System (Restrained Dark Theme):
  - Black/Charcoal/Graphite surfaces (#0c0d10, #141519, #1c1e24)
  - Vector status icons via IconRenderer
  - Semantic button variants (Danger for destructive actions, Secondary for safe dismiss)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.models import ToolRisk
from astrarun.ui.icons import IconRenderer
from astrarun.ui.theme import (
    ACCENT,
    ATTENTION,
    BORDER,
    BORDER_STRONG,
    BORDER_SUBTLE,
    DANGER,
    DANGER_BG,
    DANGER_BORDER,
    FONT_FAMILY,
    FONT_MONO,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_SMALL,
    FONT_SIZE_TITLE,
    RADIUS_MD,
    RADIUS_SM,
    SUCCESS,
    SUCCESS_BG,
    SUCCESS_BORDER,
    SURFACE,
    SURFACE_HOVER,
    SURFACE_INPUT,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
    WARNING_BG,
    WARNING_BORDER,
    get_badge_style,
    get_button_style,
)


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
        self.setObjectName("confirmation_card")

        self.setStyleSheet(f"""
            QFrame#confirmation_card {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_MD}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(10)

        # Header row with vector warning icon, title & risk badge
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        warn_col = DANGER if risk == ToolRisk.HIGH else WARNING
        warn_bg = DANGER_BG if risk == ToolRisk.HIGH else WARNING_BG
        self.warn_icon = IconRenderer.create_label(
            "warning", size=16, color=warn_col, bg_circle=True, bg_color=warn_bg, parent=self
        )
        header_row.addWidget(self.warn_icon)

        self.title_label = QLabel(title, self)
        self.title_label.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_TITLE};
            font-weight: 700;
            font-family: {FONT_FAMILY};
        """)
        header_row.addWidget(self.title_label)
        header_row.addStretch(1)

        # Risk badge
        if risk == ToolRisk.HIGH:
            badge_fg, badge_bg, badge_border = DANGER, DANGER_BG, DANGER_BORDER
        elif risk == ToolRisk.MEDIUM:
            badge_fg, badge_bg, badge_border = WARNING, WARNING_BG, WARNING_BORDER
        else:
            badge_fg, badge_bg, badge_border = SUCCESS, SUCCESS_BG, SUCCESS_BORDER

        self.risk_badge = QLabel(f"{risk.value} RISK", self)
        self.risk_badge.setStyleSheet(get_badge_style(badge_fg, badge_bg, badge_border))
        header_row.addWidget(self.risk_badge)
        layout.addLayout(header_row)

        # Description text
        desc_text = description or f"Target: {arguments}"
        self.desc_label = QLabel(desc_text, self)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-size: {FONT_SIZE_BODY};
            font-family: {FONT_FAMILY};
        """)
        layout.addWidget(self.desc_label)

        # Notice label for high risk
        if risk == ToolRisk.HIGH:
            self.hint_label = QLabel("Deliberate confirmation required: Click or press Ctrl+Enter", self)
            self.hint_label.setStyleSheet(f"""
                color: {WARNING};
                font-size: {FONT_SIZE_CAPTION};
                font-family: {FONT_FAMILY};
            """)
            layout.addWidget(self.hint_label)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch(1)

        self.cancel_btn = QPushButton("Cancel (Esc)", self)
        self.cancel_btn.setStyleSheet(get_button_style("secondary", size="md"))
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)

        is_destructive = any(
            k in tool.lower() for k in ("kill", "terminate", "delete", "destroy", "remove")
        )
        action_btn_text = "Terminate (Ctrl+Enter)" if is_destructive else "Proceed (Ctrl+Enter)"
        btn_variant = "danger" if (risk == ToolRisk.HIGH or is_destructive) else "primary"
        self.confirm_btn = QPushButton(action_btn_text, self)
        self.confirm_btn.setStyleSheet(get_button_style(btn_variant, size="md"))
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
                    event.ignore()
            else:
                self._on_confirm()
                event.accept()
        else:
            super().keyPressEvent(event)


class DisambiguationCard(QFrame):
    """
    Card presenting ambiguous candidate entities for user selection.
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
        self.setObjectName("disambiguation_card")

        self.setStyleSheet(f"""
            QFrame#disambiguation_card {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_MD}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Header with vector question icon
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        icon_lbl = IconRenderer.create_label("question", size=16, color=ATTENTION, parent=self)
        header_row.addWidget(icon_lbl)

        self.title_label = QLabel(title, self)
        self.title_label.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_BODY};
            font-weight: 700;
            font-family: {FONT_FAMILY};
        """)
        header_row.addWidget(self.title_label)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        self.list_widget = QListWidget(self)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {SURFACE_INPUT};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 6px;
                color: {TEXT_PRIMARY};
                outline: none;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 6px 10px;
                border-radius: 4px;
                color: {TEXT_SECONDARY};
                font-family: {FONT_FAMILY};
                font-size: {FONT_SIZE_BODY};
            }}
            QListWidget::item:selected {{
                background-color: {SURFACE_RAISED};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_STRONG};
            }}
            QListWidget::item:hover {{
                background-color: {SURFACE_HOVER};
                color: {TEXT_PRIMARY};
            }}
        """)

        for cand in candidates:
            c_name = cand.get("name") or cand.get("alias") or cand.get("id") or cand.get("title") or cand.get("filename") or str(cand)
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


class ResultCard(QFrame):
    """
    Compact structured result card for informational queries (e.g. system status, file info).
    Includes title, key-value rows, optional status badge, and safe action buttons.
    """

    action_triggered = Signal(str, dict)  # capability_name, arguments
    dismissed = Signal()

    def __init__(
        self,
        title: str,
        rows: list[tuple[str, str]],
        status: str = "",
        actions: Optional[list[tuple[str, str, dict[str, Any]]]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.actions = actions or []
        self.setObjectName("result_card")

        self.setStyleSheet(f"""
            QFrame#result_card {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_MD}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        icon_lbl = IconRenderer.create_label("spark", size=16, color=ACCENT, parent=self)
        header.addWidget(icon_lbl)

        self.title_label = QLabel(title, self)
        self.title_label.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_BODY};
            font-weight: 700;
            font-family: {FONT_FAMILY};
        """)
        header.addWidget(self.title_label)
        header.addStretch(1)

        self.status_label: Optional[QLabel] = None
        if status:
            self.status_label = QLabel(status, self)
            self.status_label.setStyleSheet(get_badge_style(SUCCESS, SUCCESS_BG, SUCCESS_BORDER))
            header.addWidget(self.status_label)

        layout.addLayout(header)

        # Rows Grid
        grid = QGridLayout()
        grid.setSpacing(6)
        for i, (k, v) in enumerate(rows):
            k_lbl = QLabel(k, self)
            k_lbl.setStyleSheet(f"""
                color: {TEXT_MUTED};
                font-size: {FONT_SIZE_CAPTION};
                font-weight: 600;
                font-family: {FONT_FAMILY};
            """)
            v_lbl = QLabel(v, self)
            v_lbl.setStyleSheet(f"""
                color: {TEXT_PRIMARY};
                font-size: {FONT_SIZE_CAPTION};
                font-family: {FONT_MONO};
            """)
            grid.addWidget(k_lbl, i, 0)
            grid.addWidget(v_lbl, i, 1)
        layout.addLayout(grid)

        # Optional action buttons
        if self.actions:
            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            for label, cap_id, args in self.actions:
                btn = QPushButton(label, self)
                btn.setStyleSheet(get_button_style("subtle", size="sm"))
                btn.clicked.connect(lambda _, c=cap_id, a=args: self.action_triggered.emit(c, a))
                btn_row.addWidget(btn)
            layout.addLayout(btn_row)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.dismissed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class ListResultCard(QFrame):
    """
    Selectable list presentation card for listing processes, files, or ports.
    Bounded by default limits (5, 10, 20) with Esc to dismiss.
    """

    item_selected = Signal(dict)
    dismissed = Signal()

    def __init__(
        self,
        title: str,
        items: list[dict[str, Any]],
        display_fn: Optional[Callable[[dict[str, Any]], str]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.items = items
        self.setObjectName("list_result_card")

        self.setStyleSheet(f"""
            QFrame#list_result_card {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_MD}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Title
        self.title_label = QLabel(title, self)
        self.title_label.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_BODY};
            font-weight: 700;
            font-family: {FONT_FAMILY};
        """)
        layout.addWidget(self.title_label)

        # List Widget
        self.list_widget = QListWidget(self)
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: {SURFACE_INPUT};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 6px;
                color: {TEXT_PRIMARY};
                font-family: {FONT_MONO};
                font-size: 12px;
                outline: none;
                padding: 4px;
            }}
            QListWidget::item {{
                padding: 5px 8px;
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {SURFACE_RAISED};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_STRONG};
            }}
            QListWidget::item:hover {{
                background-color: {SURFACE_HOVER};
            }}
        """)

        for item_data in items:
            if display_fn:
                text = display_fn(item_data)
            else:
                name = item_data.get("name") or item_data.get("filename") or str(item_data)
                extra = f"PID {item_data.get('pid')}" if "pid" in item_data else ""
                text = f"{name:<20} {extra}" if extra else str(name)

            it = QListWidgetItem(text, self.list_widget)
            it.setData(Qt.UserRole, item_data)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        self.list_widget.itemActivated.connect(self._on_item_activated)
        layout.addWidget(self.list_widget)

    def _on_item_activated(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data:
            self.item_selected.emit(data)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            self.dismissed.emit()
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
