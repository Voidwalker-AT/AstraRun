"""Modern, low-latency PySide6 launcher window for AstraRun v0.2."""

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
from astrarun.search.models import CandidateCategory, SearchResult
from astrarun.tools.registry import ToolRegistry
from astrarun.ui.positioning import compute_launcher_position

logger = get_logger("astrarun.ui.launcher")


class SuggestionRowWidget(QWidget):
    """Custom row widget displaying candidate title, match subtitle, and category badge."""

    def __init__(self, result: SearchResult, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Candidate name
        self.title_label = QLabel(result.name, self)
        self.title_label.setStyleSheet("""
            color: #cdd6f4;
            font-size: 14px;
            font-weight: 500;
            font-family: 'Segoe UI', system-ui, sans-serif;
        """)
        layout.addWidget(self.title_label)

        # Subtitle (match term or hint)
        subtitle_text = f"({result.matched_alias})" if result.matched_alias.lower() != result.name.lower() else ""
        if subtitle_text:
            self.sub_label = QLabel(subtitle_text, self)
            self.sub_label.setStyleSheet("""
                color: #6c7086;
                font-size: 12px;
                font-family: 'Segoe UI', system-ui, sans-serif;
            """)
            layout.addWidget(self.sub_label)

        layout.addStretch(1)

        # Category Badge
        cat_str = result.category.value if hasattr(result.category, "value") else str(result.category)
        badge_colors = {
            "APP": ("#89b4fa", "#1e1e2e"),
            "FOLDER": ("#f9e2af", "#1e1e2e"),
            "WEB": ("#a6e3a1", "#1e1e2e"),
            "COMMAND": ("#cba6f7", "#1e1e2e"),
        }
        fg_col, bg_col = badge_colors.get(cat_str.upper(), ("#bac2de", "#1e1e2e"))

        self.badge = QLabel(cat_str.upper(), self)
        self.badge.setStyleSheet(f"""
            color: {fg_col};
            background-color: #313244;
            font-size: 11px;
            font-weight: bold;
            font-family: 'Segoe UI', system-ui, sans-serif;
            border-radius: 4px;
            padding: 2px 6px;
        """)
        layout.addWidget(self.badge)


class LauncherWindow(QDialog):
    """Sleek, keyboard-first command launcher interface with ranked fuzzy suggestions."""

    def __init__(
        self,
        router: BaseRouter,
        registry: ToolRegistry,
        context: RoutingContext,
        settings: dict | None = None,
        on_refresh_callback: Callable[[], None] | None = None,
    ):
        super().__init__()
        self.router = router
        self.registry = registry
        self.context = context
        self.settings = settings or {}
        self.on_refresh_callback = on_refresh_callback

        # Auto-initialize search index if missing from context
        if self.context.search_index is None:
            from astrarun.search.index import SearchIndex
            self.context.search_index = SearchIndex(usage_store=self.context.usage_store)
            self.context.search_index.build_from_sources(
                apps=self.context.apps,
                folders=self.context.folders,
                urls=self.context.urls,
                aliases=self.context.aliases,
            )

        # Configuration options
        ui_cfg = self.settings.get("ui", {})
        self.launcher_width = int(ui_cfg.get("width", 640))
        self.launcher_height = int(ui_cfg.get("height", 56))
        self.placeholder_text = str(ui_cfg.get("placeholder", "What do you want to do?"))
        self.hide_on_focus_loss = bool(ui_cfg.get("hide_on_focus_loss", True))
        self.max_suggestions = int(ui_cfg.get("max_suggestions", 5))

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

        # Status / Feedback label
        self.status_label = QLabel("", self.bar_row)
        self.status_label.setStyleSheet("""
            color: #f38ba8;
            font-size: 13px;
            font-family: 'Segoe UI', system-ui, sans-serif;
        """)
        self.status_label.hide()
        bar_layout.addWidget(self.status_label)

        self.card_layout.addWidget(self.bar_row)

        # Suggestions list widget
        self.suggestions_list = QListWidget(self.card)
        self.suggestions_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                border-top: 1px solid #313244;
                padding-top: 4px;
            }
            QListWidget::item {
                border-radius: 6px;
                padding: 2px;
            }
            QListWidget::item:selected {
                background-color: #313244;
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
        """Position window upper-middle centered on the monitor hosting the active window."""
        pos = compute_launcher_position(self.width(), self.height())
        self.move(pos)

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
        self.error_timer.start(3000)

    def _clear_status(self) -> None:
        """Clear inline status label."""
        self.status_label.setText("")
        self.status_label.hide()

    def _adjust_height(self, expanded: bool, count: int = 0) -> None:
        """Adjust widget height based on suggestions list visibility."""
        base_h = self.launcher_height + 20
        if expanded and count > 0:
            item_h = 36
            max_items = min(count, self.max_suggestions)
            new_h = base_h + (item_h * max_items) + 8
            self.resize(self.launcher_width, new_h)
        else:
            self.resize(self.launcher_width, base_h)

    def _on_text_changed(self, text: str) -> None:
        """Query unified search index and update ranked interactive suggestions."""
        self._clear_status()
        clean = text.strip()
        if not clean:
            self.suggestions_list.hide()
            self._adjust_height(expanded=False)
            return

        # Strip action verb prefix for search
        from astrarun.routing.deterministic import normalize_request
        _, target = normalize_request(clean)
        search_query = target if target else clean

        if len(search_query) < 2 or not self.context.search_index:
            self.suggestions_list.hide()
            self._adjust_height(expanded=False)
            return

        results = self.context.search_index.search(search_query, limit=self.max_suggestions)
        if results:
            self.suggestions_list.clear()
            for res in results:
                item = QListWidgetItem()
                item.setSizeHint(QWidget().sizeHint())  # placeholder
                row_widget = SuggestionRowWidget(res, self.suggestions_list)
                item.setSizeHint(row_widget.sizeHint())
                item.setData(Qt.ItemDataRole.UserRole, res)
                self.suggestions_list.addItem(item)
                self.suggestions_list.setItemWidget(item, row_widget)

            self.suggestions_list.setCurrentRow(0)
            self.suggestions_list.show()
            self._adjust_height(expanded=True, count=len(results))
        else:
            self.suggestions_list.hide()
            self._adjust_height(expanded=False)

    def _on_suggestion_clicked(self, item: QListWidgetItem) -> None:
        """Execute command associated with clicked suggestion."""
        res: SearchResult = item.data(Qt.ItemDataRole.UserRole)
        if res:
            self._execute_result(res)

    def _execute_result(self, res: SearchResult) -> None:
        """Directly dispatch an executed SearchResult."""
        logger.info("Executing suggestion directly: %s (%s)", res.name, res.category)

        # Handle internal command
        if res.id == "cmd:refresh_apps" or res.command == "refresh apps":
            if self.on_refresh_callback:
                self.on_refresh_callback()
            self.show_feedback("Applications refreshed.", is_error=False)
            return

        # Build decision from SearchResult
        if res.category == CandidateCategory.APP:
            decision = Decision(tool="open_app", args={"app": res.matched_alias, "path": res.target})
        elif res.category == CandidateCategory.FOLDER:
            decision = Decision(tool="open_folder", args={"folder": res.target})
        elif res.category == CandidateCategory.WEB:
            decision = Decision(tool="open_url", args={"url": res.target})
        else:
            decision = Decision(tool="open_app", args={"app": res.name, "path": res.target})

        # Shadow evaluation in background thread (non-blocking, zero execution authority)
        if (
            self.context.laya_router
            and getattr(self.context.laya_router, "enabled", False)
            and getattr(self.context.laya_router, "mode", "") == "shadow"
            and self.context.shadow_collector
        ):
            raw_req = self.input_field.text().strip() or res.name
            def _async_shadow_res(q=raw_req, d=decision):
                try:
                    ld = self.context.laya_router.predict_intent(q)
                    self.context.shadow_collector.record_shadow_event(q, d, ld)
                except Exception as err:
                    logger.debug("Shadow evaluation error: %s", err)
            import threading
            threading.Thread(target=_async_shadow_res, daemon=True).start()

        success, msg = self.registry.execute(decision)
        if success:
            if self.context.usage_store:
                self.context.usage_store.record_launch(res.id)
            self.dismiss()
        else:
            self.show_feedback(msg, is_error=True)

    def execute_command(self) -> None:
        """Execute selected suggestion if present, or route typed input."""
        # 1. If an item is highlighted in the suggestions list, execute it!
        current_row = self.suggestions_list.currentRow()
        if self.suggestions_list.isVisible() and current_row >= 0:
            item = self.suggestions_list.item(current_row)
            if item:
                res = item.data(Qt.ItemDataRole.UserRole)
                if res and isinstance(res, SearchResult):
                    self._execute_result(res)
                    return

        # 2. Otherwise route raw typed command
        query = self.input_field.text().strip()
        if not query:
            return

        logger.info("Processing command: '%s'", query)
        decision: Decision = self.router.route(query, self.context)

        # Shadow evaluation in background thread (non-blocking, zero execution authority)
        if (
            self.context.laya_router
            and getattr(self.context.laya_router, "enabled", False)
            and getattr(self.context.laya_router, "mode", "") == "shadow"
            and self.context.shadow_collector
        ):
            def _async_shadow_cmd(q=query, d=decision):
                try:
                    ld = self.context.laya_router.predict_intent(q)
                    self.context.shadow_collector.record_shadow_event(q, d, ld)
                except Exception as err:
                    logger.debug("Shadow evaluation error: %s", err)
            import threading
            threading.Thread(target=_async_shadow_cmd, daemon=True).start()

        # Handle internal refresh command
        if decision.tool == "refresh_apps":
            if self.on_refresh_callback:
                self.on_refresh_callback()
            self.show_feedback("Applications refreshed.", is_error=False)
            return

        success, message = self.registry.execute(decision)
        if success:
            logger.info("Command executed successfully: '%s'", query)
            self.dismiss()
        else:
            logger.warning("Command execution failed: '%s' -> %s", query, message)
            self.show_feedback(message, is_error=True)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard-first navigation."""
        key = event.key()

        # Escape dismisses launcher
        if key == Qt.Key.Key_Escape:
            self.dismiss()
            event.accept()
            return

        # Down arrow: move selection down in suggestions
        if key == Qt.Key.Key_Down and self.suggestions_list.isVisible():
            count = self.suggestions_list.count()
            if count > 0:
                current = self.suggestions_list.currentRow()
                nxt = (current + 1) % count
                self.suggestions_list.setCurrentRow(nxt)
            event.accept()
            return

        # Up arrow: move selection up in suggestions
        if key == Qt.Key.Key_Up and self.suggestions_list.isVisible():
            count = self.suggestions_list.count()
            if count > 0:
                current = self.suggestions_list.currentRow()
                prev = (current - 1) if current > 0 else (count - 1)
                self.suggestions_list.setCurrentRow(prev)
            event.accept()
            return

        # Tab key: complete or cycle
        if key == Qt.Key.Key_Tab and self.suggestions_list.isVisible():
            current_row = self.suggestions_list.currentRow()
            if current_row >= 0:
                item = self.suggestions_list.item(current_row)
                res = item.data(Qt.ItemDataRole.UserRole)
                if res:
                    self.input_field.setText(res.name)
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
