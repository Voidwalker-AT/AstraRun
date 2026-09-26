"""Modern, low-latency PySide6 launcher window for AstraRun."""

from __future__ import annotations

from typing import Callable
from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.logging import get_logger
from astrarun.core.models import Decision, RoutingContext
from astrarun.routing.base import BaseRouter
from astrarun.tools.registry import ToolRegistry

logger = get_logger("astrarun.ui.launcher")


class LauncherWindow(QDialog):
    """Sleek, keyboard-first command launcher interface."""

    def __init__(
        self,
        router: BaseRouter,
        registry: ToolRegistry,
        context: RoutingContext,
        settings: dict | None = None,
    ):
        super().__init__()
        self.router = router
        self.registry = registry
        self.context = context
        self.settings = settings or {}

        # Configuration options
        ui_cfg = self.settings.get("ui", {})
        self.launcher_width = int(ui_cfg.get("width", 640))
        self.launcher_height = int(ui_cfg.get("height", 56))
        self.placeholder_text = str(ui_cfg.get("placeholder", "What do you want to do?"))
        self.hide_on_focus_loss = bool(ui_cfg.get("hide_on_focus_loss", True))

        self._init_window()
        self._init_ui()
        self._init_timer()

    def _init_window(self) -> None:
        """Set frameless, top-most, tool-window flags and translucent attributes."""
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(self.launcher_width, self.launcher_height)

    def _init_ui(self) -> None:
        """Build the UI structure with modern dark styling."""
        # Main layout
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(10, 10, 10, 10)
        self.root_layout.setSpacing(0)

        # Container Card
        self.card = QWidget(self)
        self.card.setObjectName("card")
        self.card.setStyleSheet("""
            QWidget#card {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 12px;
            }
        """)

        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 140))
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)

        # Card internal layout
        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(16, 10, 16, 10)
        self.card_layout.setSpacing(6)

        # Top Command Bar Row
        self.bar_row = QWidget()
        bar_layout = QHBoxLayout(self.bar_row)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(12)

        # Prompt Glyph (">")
        self.prompt_label = QLabel(">", self.bar_row)
        self.prompt_label.setStyleSheet("""
            color: #89b4fa;
            font-size: 20px;
            font-weight: bold;
            padding-bottom: 2px;
        """)
        bar_layout.addWidget(self.prompt_label)

        # Input Field
        self.input_field = QLineEdit(self.bar_row)
        self.input_field.setPlaceholderText(self.placeholder_text)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #cdd6f4;
                font-size: 17px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                selection-background-color: #45475a;
                selection-color: #cdd6f4;
            }
        """)
        self.input_field.textChanged.connect(self._on_text_changed)
        self.input_field.returnPressed.connect(self.execute_command)
        bar_layout.addWidget(self.input_field, stretch=1)

        # Status / Feedback label (e.g. for errors or confirmations)
        self.status_label = QLabel("", self.bar_row)
        self.status_label.setStyleSheet("""
            color: #f38ba8;
            font-size: 13px;
            font-family: 'Segoe UI', system-ui, sans-serif;
        """)
        self.status_label.hide()
        bar_layout.addWidget(self.status_label)

        self.card_layout.addWidget(self.bar_row)

        # Suggestions list widget (hidden initially)
        self.suggestions_list = QListWidget(self.card)
        self.suggestions_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                border-top: 1px solid #313244;
                color: #a6adc8;
                font-size: 14px;
                padding-top: 6px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background-color: #313244;
                color: #89b4fa;
            }
        """)
        self.suggestions_list.itemClicked.connect(self._on_suggestion_clicked)
        self.suggestions_list.hide()
        self.card_layout.addWidget(self.suggestions_list)

        self.root_layout.addWidget(self.card)

    def _init_timer(self) -> None:
        """Timer for auto-clearing temporary error messages."""
        self.error_timer = QTimer(self)
        self.error_timer.setSingleShot(True)
        self.error_timer.timeout.connect(self._clear_status)

    def position_on_active_screen(self) -> None:
        """Position the launcher centered horizontally on the screen containing the cursor."""
        cursor_pos = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor_pos) or QGuiApplication.primaryScreen()
        if not screen:
            return

        avail = screen.availableGeometry()
        x = avail.x() + (avail.width() - self.width()) // 2
        # Position at ~32% from the top of the monitor for ideal ergonomics
        y = avail.y() + int(avail.height() * 0.30)
        self.move(x, y)

    def show_and_activate(self) -> None:
        """Bring the launcher to foreground on the active screen and focus the input."""
        self.position_on_active_screen()
        self.input_field.clear()
        self._clear_status()
        self.suggestions_list.hide()
        self._adjust_height(expanded=False)

        self.show()
        self.raise_()
        self.activateWindow()
        self.input_field.setFocus()
        logger.debug("Launcher shown and activated.")

    def dismiss(self) -> None:
        """Dismiss the launcher window."""
        self.hide()
        self._clear_status()
        logger.debug("Launcher dismissed.")

    def toggle_visibility(self) -> None:
        """Toggle between visible/active and hidden states."""
        if self.isVisible() and self.isActiveWindow():
            self.dismiss()
        else:
            self.show_and_activate()

    def show_feedback(self, message: str, is_error: bool = True) -> None:
        """Display an inline status/error message for the user."""
        color = "#f38ba8" if is_error else "#a6e3a1"
        self.status_label.setStyleSheet(f"""
            color: {color};
            font-size: 13px;
            font-family: 'Segoe UI', system-ui, sans-serif;
            font-weight: 500;
        """)
        self.status_label.setText(message)
        self.status_label.show()
        # Keep message visible for 3 seconds unless user types
        self.error_timer.start(3000)

    def _clear_status(self) -> None:
        """Clear inline status label."""
        self.status_label.setText("")
        self.status_label.hide()

    def _adjust_height(self, expanded: bool, count: int = 0) -> None:
        """Adjust widget height based on suggestions list visibility."""
        base_h = self.launcher_height + 20  # +20 for layout margins
        if expanded and count > 0:
            item_h = 32
            max_items = min(count, 5)
            new_h = base_h + (item_h * max_items) + 12
            self.resize(self.launcher_width, new_h)
        else:
            self.resize(self.launcher_width, base_h)

    def _on_text_changed(self, text: str) -> None:
        """Handle real-time suggestions based on current input text."""
        self._clear_status()
        clean = text.strip().lower()
        if not clean or len(clean) < 2:
            self.suggestions_list.hide()
            self._adjust_height(expanded=False)
            return

        # Simple prefix matching for apps, folders, and URLs
        matches: list[tuple[str, str]] = []

        # Check applications
        for k, app in self.context.apps.items():
            if k.startswith(clean) or app.name.lower().startswith(clean):
                matches.append((f"Open {app.name}", f"open {k}"))

        # Check folders
        for k, folder in self.context.folders.items():
            if k.startswith(clean):
                matches.append((f"Open {folder.name} Folder", f"open {k}"))

        # Check URLs
        for k, url in self.context.urls.items():
            if k.startswith(clean):
                matches.append((f"Open {k.title()}", f"open {k}"))

        if matches:
            self.suggestions_list.clear()
            for label, cmd in matches[:5]:
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, cmd)
                self.suggestions_list.addItem(item)
            self.suggestions_list.show()
            self._adjust_height(expanded=True, count=len(matches[:5]))
        else:
            self.suggestions_list.hide()
            self._adjust_height(expanded=False)

    def _on_suggestion_clicked(self, item: QListWidgetItem) -> None:
        """Execute command associated with clicked suggestion."""
        cmd = item.data(Qt.ItemDataRole.UserRole)
        if cmd:
            self.input_field.setText(cmd)
            self.execute_command()

    def execute_command(self) -> None:
        """Interpret the input through the router and dispatch to the tool registry."""
        query = self.input_field.text().strip()
        if not query:
            return

        logger.info("Processing command: '%s'", query)
        decision: Decision = self.router.route(query, self.context)
        success, message = self.registry.execute(decision)

        if success:
            logger.info("Command executed successfully: '%s'", query)
            self.dismiss()
        else:
            logger.warning("Command execution failed: '%s' -> %s", query, message)
            self.show_feedback(message, is_error=True)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle navigation keys."""
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss()
            event.accept()
            return

        if event.key() == Qt.Key.Key_Down and self.suggestions_list.isVisible():
            self.suggestions_list.setFocus()
            if self.suggestions_list.count() > 0:
                self.suggestions_list.setCurrentRow(0)
            event.accept()
            return

        super().keyPressEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        """Hide window on focus loss if configured."""
        if event.type() == QEvent.Type.ActivationChange:
            if not self.isActiveWindow() and self.isVisible():
                if self.hide_on_focus_loss:
                    self.dismiss()
        super().changeEvent(event)
