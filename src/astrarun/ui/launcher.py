"""Modern, low-latency PySide6 launcher window for AstraRun v0.9."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Optional
from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
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
from astrarun.ui.icons import IconRenderer
from astrarun.ui.motion import MotionTokens
from astrarun.ui.positioning import compute_launcher_position
from astrarun.ui.theme import (
    ACCENT,
    BORDER,
    BORDER_STRONG,
    BORDER_SUBTLE,
    CATEGORY_COLORS,
    DANGER,
    FONT_FAMILY,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    SUCCESS,
    SURFACE,
    SURFACE_HOVER,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    get_badge_style,
)
from astrarun.windows.policy import register_astrarun_hwnd, unregister_astrarun_hwnd

if TYPE_CHECKING:
    from astrarun.app import AstraApplication, ExecutionResult

logger = get_logger("astrarun.ui.launcher")

if sys.platform == "win32":
    try:
        WM_ASTRARUN_SUMMON = ctypes.windll.user32.RegisterWindowMessageW("AstraRun_Summon_Message")
    except Exception:
        WM_ASTRARUN_SUMMON = 0
else:
    WM_ASTRARUN_SUMMON = 0


class LauncherState(str, Enum):
    """Explicit lifecycle state machine for command bar presentation and interaction."""
    HIDDEN = "HIDDEN"
    ENTERING = "ENTERING"
    ACTIVATING = "ACTIVATING"
    INTERACTIVE = "INTERACTIVE"
    SUBMITTING = "SUBMITTING"
    EXITING = "EXITING"


class SuggestionRowWidget(QWidget):
    """Custom row widget displaying candidate title, match subtitle, and category badge."""

    def __init__(self, result: SearchResult, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Candidate name
        self.title_label = QLabel(result.name, self)
        self.title_label.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: 13px;
            font-weight: 500;
            font-family: {FONT_FAMILY};
        """)
        layout.addWidget(self.title_label)

        # Subtitle (match term or hint)
        subtitle_text = f"({result.matched_alias})" if result.matched_alias.lower() != result.name.lower() else ""
        if subtitle_text:
            self.sub_label = QLabel(subtitle_text, self)
            self.sub_label.setStyleSheet(f"""
                color: {TEXT_MUTED};
                font-size: 11px;
                font-family: {FONT_FAMILY};
            """)
            layout.addWidget(self.sub_label)

        layout.addStretch(1)

        # Category Badge
        cat_str = (result.category.value if hasattr(result.category, "value") else str(result.category)).upper()
        fg_col, bg_col, b_col = CATEGORY_COLORS.get(cat_str, (TEXT_SECONDARY, SURFACE_RAISED, BORDER))

        self.badge = QLabel(cat_str, self)
        self.badge.setStyleSheet(get_badge_style(fg_col, bg_col, b_col))
        layout.addWidget(self.badge)


class LauncherWindow(QDialog):
    """Sleek, keyboard-first command launcher interface with ranked fuzzy suggestions and card hosts."""

    def __init__(
        self,
        router: BaseRouter | None = None,
        registry: ToolRegistry | None = None,
        context: RoutingContext | None = None,
        settings: dict | None = None,
        on_refresh_callback: Callable[[], None] | None = None,
        app: Optional[AstraApplication] = None,
        hud: Optional[Any] = None,
        animations_enabled: bool = True,
    ):
        super().__init__()
        self.app = app
        self.hud = hud
        self.animations_enabled = animations_enabled
        self._is_animating: bool = False
        self._has_been_active: bool = False

        # Support both new unified AstraApplication composition and legacy parameters
        if self.app is not None:
            self.router = router or self.app.deterministic_router
            self.registry = registry or self.app.capability_registry
            self.context = context or self.app.routing_context
            self.settings = settings or self.app.settings
            self.on_refresh_callback = on_refresh_callback or self.app.refresh_discovery
        else:
            self.router = router  # type: ignore
            self.registry = registry  # type: ignore
            self.context = context  # type: ignore
            self.settings = settings or {}
            self.on_refresh_callback = on_refresh_callback

        # Auto-initialize search index if missing from context
        if self.context and self.context.search_index is None:
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
        # Section 4: remove "focus loss = immediate dismiss" as architectural invariant
        self.hide_on_focus_loss = bool(ui_cfg.get("hide_on_focus_loss", False))
        self.launcher_debug = bool(ui_cfg.get("launcher_debug", False))
        self.max_suggestions = int(ui_cfg.get("max_suggestions", 5))

        # Explicit State Machine and Telemetry
        self.state: LauncherState = LauncherState.HIDDEN
        self._last_origin_hwnd: int = 0
        self._activation_timer = QTimer(self)
        self._activation_timer.setSingleShot(True)
        self._activation_timer.timeout.connect(self._stabilize_activation)

        self.active_card: Optional[QWidget] = None
        self._memory_view_ref: Optional[QWidget] = None
        self._user_navigated_suggestions: bool = False
        import uuid
        self.session_id: str = f"launcher-sess-{uuid.uuid4().hex[:12]}"

        self._init_window()
        self._init_ui()
        self._init_animations()
        self._init_timer()

        self._registered_hwnd: int | None = None
        # Register self HWND so AstraRun never targets its own windows for window actions
        if sys.platform == "win32":
            try:
                self._registered_hwnd = int(self.winId())
                register_astrarun_hwnd(self._registered_hwnd)
            except Exception as err:
                logger.debug("Could not register launcher HWND: %s", err)

    def reset_session(self) -> str:
        """Start a completely fresh conversation session with zero cross-session state."""
        import uuid
        self.session_id = f"launcher-sess-{uuid.uuid4().hex[:12]}"
        return self.session_id

    def _init_window(self) -> None:
        """Set frameless, top-most, tool-window flags and translucent attributes."""
        self.setWindowTitle("AstraRun")
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
        self.card.setStyleSheet(f"""
            QWidget#card {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: {RADIUS_LG}px;
            }}
        """)

        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 180))
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

        # Vector Astra Mark Icon (displays vector spark; returns ✦ for text assertions)
        class PromptMarkLabel(QLabel):
            def text(self) -> str:
                return super().text() or "✦"

        self.prompt_label = PromptMarkLabel(self.bar_row)
        self.prompt_label.setPixmap(IconRenderer.get_pixmap("spark", size=18, color=ACCENT))
        self.prompt_label.setFixedSize(20, 20)
        self.prompt_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bar_layout.addWidget(self.prompt_label)

        # Input Field
        self.input_field = QLineEdit(self.bar_row)
        self.input_field.setPlaceholderText(self.placeholder_text)
        self.input_field.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {TEXT_PRIMARY};
                font-size: 16px;
                font-family: {FONT_FAMILY};
                selection-background-color: {SURFACE_HOVER};
                selection-color: {TEXT_PRIMARY};
            }}
        """)
        self.input_field.textChanged.connect(self._on_text_changed)
        self.input_field.returnPressed.connect(self.execute_command)
        bar_layout.addWidget(self.input_field, stretch=1)

        # Status / Feedback label
        self.status_label = QLabel("", self.bar_row)
        self.status_label.setStyleSheet(f"""
            color: {DANGER};
            font-size: 12px;
            font-family: {FONT_FAMILY};
        """)
        self.status_label.hide()
        bar_layout.addWidget(self.status_label)

        self.card_layout.addWidget(self.bar_row)

        # Suggestions list widget
        self.suggestions_list = QListWidget(self.card)
        self.suggestions_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                border-top: 1px solid {BORDER_SUBTLE};
                padding-top: 4px;
            }}
            QListWidget::item {{
                border-radius: {RADIUS_SM}px;
                padding: 3px 6px;
            }}
            QListWidget::item:selected {{
                background-color: {SURFACE_RAISED};
                border: 1px solid {BORDER_STRONG};
            }}
            QListWidget::item:hover {{
                background-color: {SURFACE_HOVER};
            }}
        """)
        self.suggestions_list.itemClicked.connect(self._on_suggestion_clicked)
        self.suggestions_list.hide()
        self.card_layout.addWidget(self.suggestions_list)

        # Dynamic Card Container for ResultCard, ListResultCard, ConfirmationCard, DisambiguationCard
        self.card_container = QWidget(self.card)
        self.card_container_layout = QVBoxLayout(self.card_container)
        self.card_container_layout.setContentsMargins(0, 4, 0, 0)
        self.card_container_layout.setSpacing(0)
        self.card_container.hide()
        self.card_layout.addWidget(self.card_container)

        self.root_layout.addWidget(self.card)

    def _init_timer(self) -> None:
        """Timer for auto-clearing temporary error messages."""
        self.error_timer = QTimer(self)
        self.error_timer.setSingleShot(True)
        self.error_timer.timeout.connect(self._clear_status)

    def _log_lifecycle(self, event_name: str, reason: str = "", extra: str = "") -> None:
        """Log granular high-resolution lifecycle events for launcher debugging."""
        ts = datetime.now().strftime("%H:%M:%S.%f")
        fg_hwnd = 0
        if sys.platform == "win32":
            try:
                fg_hwnd = ctypes.windll.user32.GetForegroundWindow() or 0
            except Exception:
                pass

        parts = [
            f"[LIFECYCLE {ts}]",
            f"{event_name:<24}",
            f"state={self.state.value:<11}",
            f"vis={self.isVisible()}",
            f"act={self.isActiveWindow()}",
            f"focus={self.input_field.hasFocus()}",
            f"fg_hwnd={fg_hwnd}",
            f"origin={self._last_origin_hwnd}",
            f"anim={self._is_animating}",
            f"has_act={self._has_been_active}",
        ]
        if reason:
            parts.append(f"reason='{reason}'")
        if extra:
            parts.append(f"extra='{extra}'")
        line = " | ".join(parts)
        logger.info(line)
        if getattr(self, "launcher_debug", False):
            print(line, flush=True)

    def _transition_state(self, new_state: LauncherState, reason: str = "") -> None:
        """Explicit state transition with lifecycle logging."""
        old_state = self.state
        self.state = new_state
        self._log_lifecycle(
            f"STATE_{new_state.value}",
            reason=reason,
            extra=f"from={old_state.value}",
        )

    def _init_animations(self) -> None:
        """Setup slide and native windowOpacity animations without nested QGraphicsEffect."""
        self.setWindowOpacity(1.0)

        dur = MotionTokens.get_enter_duration() if self.animations_enabled else 0
        self.pos_anim = QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(dur)
        self.pos_anim.setEasingCurve(MotionTokens.EASING_ENTER)

        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity")
        self.opacity_anim.setDuration(dur)
        self.opacity_anim.setEasingCurve(MotionTokens.EASING_ENTER)

        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(self.pos_anim)
        self.anim_group.addAnimation(self.opacity_anim)
        self.anim_group.finished.connect(self._on_animation_finished)

    def _on_animation_finished(self) -> None:
        """Handle animation completion."""
        self._is_animating = False
        self._log_lifecycle("ANIMATION_FINISHED", extra=f"state={self.state.value}")
        if self.state == LauncherState.ENTERING:
            self._transition_state(LauncherState.ACTIVATING, reason="entrance_animation_finished")
            # Explicit activation grace period (150ms after animation = ~300ms total)
            self._activation_timer.start(150)
        elif self.state == LauncherState.EXITING or self.windowOpacity() <= 0.05:
            self.hide()
            self._clear_status()
            self.clear_card()
            self._transition_state(LauncherState.HIDDEN, reason="exit_animation_finished")
            self._log_lifecycle("HIDE_EVENT")

    def _stabilize_activation(self) -> None:
        """Reinforce input focus and transition to INTERACTIVE after grace period."""
        if self.state != LauncherState.ACTIVATING or not self.isVisible():
            return
        self.raise_()
        self.activateWindow()
        self.input_field.setFocus()
        self._transition_state(LauncherState.INTERACTIVE, reason="activation_grace_period_ended")
        self._log_lifecycle("INPUT_FOCUS_IN", extra="interactive_ready")

        try:
            from astrarun.ui.attestation import attest_window_visibility
            import os
            win_id = int(self.winId()) if self else 0
            attestation = attest_window_visibility(win_id, expected_pid=os.getpid())
            if attestation["is_visible"]:
                self._log_lifecycle("LAUNCHER_VISIBLE", extra=f"facts={attestation['facts']}")
            else:
                self._log_lifecycle("LAUNCHER_VISIBILITY_FAILED", extra=f"reasons={attestation['failure_reasons']}")
        except Exception as e:
            self._log_lifecycle("LAUNCHER_VISIBILITY_FAILED", extra=f"attestation_exception={e}")

    def present_animated(self, target_geometry: QRect, target_screen: Any = None) -> None:
        """
        Show the command bar with gentle slide/drop from above (150ms, OutCubic).
        Prewarmed and kept resident.
        """
        self._log_lifecycle("PRESENT_REQUESTED")
        self._is_animating = True
        self._has_been_active = False
        self._user_navigated_suggestions = False

        self.input_field.clear()
        self._clear_status()
        self.clear_card()
        self.suggestions_list.hide()
        self._adjust_height(expanded=False)

        target_pos = target_geometry.topLeft()
        if not self.animations_enabled:
            self.move(target_pos)
            self.setWindowOpacity(1.0)
            self._log_lifecycle("SHOW_CALLED")
            self.show()
            self.raise_()
            self.activateWindow()
            self.input_field.setFocus()
            self._is_animating = False
            self._transition_state(LauncherState.INTERACTIVE, reason="animations_disabled")
            return

        self._transition_state(LauncherState.ENTERING, reason="present_animated_start")
        start_pos = QPoint(target_pos.x(), target_pos.y() - 25)
        self.move(start_pos)
        self.setWindowOpacity(1.0)

        self._log_lifecycle("SHOW_CALLED")
        self.show()
        self.raise_()
        self.activateWindow()
        self.input_field.setFocus()

        enter_dur = MotionTokens.get_enter_duration() if self.animations_enabled else 0
        self.pos_anim.setDuration(enter_dur)
        self.pos_anim.setEasingCurve(MotionTokens.EASING_ENTER)
        self.pos_anim.setStartValue(start_pos)
        self.pos_anim.setEndValue(target_pos)

        self.opacity_anim.setDuration(enter_dur)
        self.opacity_anim.setEasingCurve(MotionTokens.EASING_ENTER)
        self.opacity_anim.setStartValue(1.0)
        self.opacity_anim.setEndValue(1.0)

        self._log_lifecycle("ANIMATION_STARTED")
        self.anim_group.start()

    def dismiss_animated(self, reason: str = "unspecified") -> None:
        """Dismiss command bar smoothly with slide up/fade respecting MotionTokens."""
        self._log_lifecycle("DISMISS_REQUESTED", reason=reason)
        if not self.isVisible():
            self._log_lifecycle("DISMISS_BLOCKED", reason="already_hidden")
            return

        if self.state == LauncherState.EXITING:
            self._log_lifecycle("DISMISS_BLOCKED", reason="already_exiting")
            return

        if not self.animations_enabled:
            self.dismiss(reason=reason)
            return

        self._transition_state(LauncherState.EXITING, reason=reason)
        self._is_animating = True
        self._activation_timer.stop()
        end_pos = QPoint(self.x(), self.y() - 20)

        exit_dur = MotionTokens.get_exit_duration() if self.animations_enabled else 0
        self.pos_anim.setDuration(exit_dur)
        self.pos_anim.setEasingCurve(MotionTokens.EASING_EXIT)
        self.pos_anim.setStartValue(self.pos())
        self.pos_anim.setEndValue(end_pos)

        self.opacity_anim.setDuration(exit_dur)
        self.opacity_anim.setEasingCurve(MotionTokens.EASING_EXIT)
        self.opacity_anim.setStartValue(self.windowOpacity())
        self.opacity_anim.setEndValue(0.0)

        self._log_lifecycle("EXIT_ANIMATION_STARTED", reason=reason)
        self.anim_group.start()

    def position_on_active_screen(self) -> None:
        """Position window upper-middle centered on the monitor hosting the active window."""
        pos = compute_launcher_position(self.width(), self.height())
        self.move(pos)

    def show_and_activate(self) -> None:
        """Bring the launcher to foreground on the active screen and focus the input."""
        if self.app is not None:
            self.app.capture_origin_window()

        pos = compute_launcher_position(self.width(), self.height())
        geom = QRect(pos.x(), pos.y(), self.width(), self.height())
        self.present_animated(geom)
        logger.debug("Launcher shown and activated.")

    def dismiss(self, reason: str = "unspecified") -> None:
        """Dismiss the launcher window immediately."""
        self._log_lifecycle("HIDE_REQUESTED", reason=reason)
        self._activation_timer.stop()
        self.hide()
        self._is_animating = False
        self._clear_status()
        self.clear_card()
        self._transition_state(LauncherState.HIDDEN, reason=reason)
        self._log_lifecycle("HIDE_EVENT", reason=reason)
        logger.debug("Launcher dismissed.")

    def toggle_visibility(self) -> None:
        """Toggle between visible/active and hidden states."""
        if self.isVisible() and self.state == LauncherState.INTERACTIVE:
            self.dismiss_animated(reason="toggle_visibility")
        elif self.state in (LauncherState.ENTERING, LauncherState.ACTIVATING):
            logger.debug("Toggle ignored during presentation state.")
        else:
            self.show_and_activate()

    def show_feedback(self, message: str, is_error: bool = True) -> None:
        """Display an inline status/error message for the user."""
        color = DANGER if is_error else SUCCESS
        self.status_label.setStyleSheet(f"""
            color: {color};
            font-size: 12px;
            font-family: {FONT_FAMILY};
            font-weight: 500;
        """)
        self.status_label.setText(message)
        self.status_label.show()
        self.error_timer.start(3500)

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

    def mount_card(self, card_widget: QWidget, target_height: int = 240) -> None:
        """Mount an interactive card below the command bar."""
        self.clear_card()
        self.active_card = card_widget
        self.card_container_layout.addWidget(card_widget)
        self.card_container.show()
        self.suggestions_list.hide()
        self.resize(self.launcher_width, self.launcher_height + target_height + 20)

    def clear_card(self) -> None:
        """Remove and destroy active interactive card, restoring normal launcher height."""
        if self.active_card is not None:
            self.card_container_layout.removeWidget(self.active_card)
            self.active_card.deleteLater()
            self.active_card = None
        self.card_container.hide()
        self._adjust_height(expanded=False)

    def _is_compound_or_nlp_query(self, query: str) -> bool:
        """Check if query is compound, contains conjunctions, or action verbs with multiple clauses."""
        clean = query.strip()
        lower = f" {clean.lower()} "
        for conj in (" and ", " then ", " with ", " & ", ";", ", then ", ", and "):
            if conj in lower:
                return True
        words = clean.split()
        if len(words) > 1 and words[0].lower() in ("type", "press", "click", "toggle", "focus", "select", "snap"):
            return True
        return False

    def _on_text_changed(self, text: str) -> None:
        """Query unified search index and update ranked interactive suggestions."""
        self._clear_status()
        self.clear_card()
        self._user_navigated_suggestions = False
        clean = text.strip()
        if not clean or self._is_compound_or_nlp_query(clean):
            self.suggestions_list.hide()
            self._adjust_height(expanded=False)
            return

        # 1. Deterministic Input Router Classification
        from astrarun.routing.input_router import classify_launcher_input, InputIntent
        intent = classify_launcher_input(clean)

        # Action commands, Natural language, Questions, and Goals must NEVER show auto-complete dropdown
        action_prefixes = ("open ", "launch ", "start ", "run ", "close ", "type ", "press ", "click ", "can u ", "can you ")
        if intent in (InputIntent.NATURAL_LANGUAGE, InputIntent.QUESTION, InputIntent.GOAL, InputIntent.DIRECT_APP_INTENT) or \
           clean.lower().startswith(action_prefixes):
            self.suggestions_list.hide()
            self._adjust_height(expanded=False)
            return

        # Explicit search prefixes: only show search dropdown if explicitly searching or raw keyword
        is_explicit_search = clean.lower().startswith(("search ", "find ", "? "))
        if is_explicit_search:
            search_query = clean.split(maxsplit=1)[1] if len(clean.split()) > 1 else ""
        else:
            search_query = clean

        if len(search_query) < 2 or not self.context or not self.context.search_index:
            self.suggestions_list.hide()
            self._adjust_height(expanded=False)
            return

        raw_results = self.context.search_index.search(search_query, limit=self.max_suggestions)
        # Strict confidence filter: only show candidates with score >= 0.75
        results = [r for r in raw_results if r.score >= 0.75]

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

        # Fast execution via app or tool registry
        if self.app is not None:
            from astrarun.ingress import RequestEnvelope, RequestOrigin
            envelope = RequestEnvelope.create(
                raw_query=res.matched_alias or res.name,
                origin=RequestOrigin.LAUNCHER,
                origin_hwnd=getattr(self.app, "origin_window", None).hwnd if getattr(self.app, "origin_window", None) else None,
            )
            exec_res = self.app.handle_request(envelope)
            if exec_res.success:
                self.dismiss(reason="suggestion_fast_path")
            else:
                self.show_feedback(exec_res.message, is_error=True)
            return

        success, msg = self.registry.execute(decision)
        if success:
            if self.context and self.context.usage_store:
                self.context.usage_store.record_launch(res.id)
            self.dismiss(reason="suggestion_executed")
        else:
            self.show_feedback(msg, is_error=True)

    def execute_command(self) -> None:
        """Execute selected suggestion if present, or route typed input through canonical ingress."""
        query = self.input_field.text().strip()
        if not query:
            return

        from astrarun.ingress import RequestEnvelope, RequestOrigin

        # 1. If suggestions list is visible and user navigated to an item, or input closely matches
        current_row = self.suggestions_list.currentRow()
        if self.suggestions_list.isVisible() and current_row >= 0:
            item = self.suggestions_list.item(current_row)
            if item:
                res = item.data(Qt.ItemDataRole.UserRole)
                if res and isinstance(res, SearchResult):
                    q_lower = query.lower()
                    name_lower = res.name.lower()
                    alias_lower = (res.matched_alias or "").lower()
                    user_nav = getattr(self, "_user_navigated_suggestions", False)
                    # Strict matching: requires explicit navigation OR prefix / token startswith match
                    prefix_match = (
                        name_lower.startswith(q_lower)
                        or alias_lower.startswith(q_lower)
                        or any(tok.startswith(q_lower) for tok in name_lower.split())
                    )
                    if not self._is_compound_or_nlp_query(query) and (user_nav or prefix_match):
                        self._execute_result(res)
                        return

        # 2. Canonical execution: ALL human typed text enters RequestBoundaryRouter via RequestEnvelope
        self.suggestions_list.hide()
        self._adjust_height(expanded=False)
        logger.info("Processing command: '%s'", query)

        # Canonical execution through AstraApplication composition root
        if self.app is not None:
            envelope = RequestEnvelope.create(
                raw_query=query,
                origin=RequestOrigin.LAUNCHER,
                origin_hwnd=getattr(self.app, "origin_window", None).hwnd if getattr(self.app, "origin_window", None) else None,
                session_id=self.session_id,
            )
            exec_res = self.app.handle_request(envelope)
            if hasattr(exec_res, "data") and isinstance(exec_res.data, dict) and "session_id" in exec_res.data:
                self.session_id = exec_res.data["session_id"]
            self._handle_execution_result(exec_res, query)
            return

        # Fallback to legacy router
        decision: Decision = self.router.route(query, self.context)

        if decision.tool == "refresh_apps":
            if self.on_refresh_callback:
                self.on_refresh_callback()
            self.show_feedback("Applications refreshed.", is_error=False)
            return

        success, message = self.registry.execute(decision)
        if success:
            logger.info("Command executed successfully: '%s'", query)
            self.dismiss(reason="command_executed")
        else:
            logger.warning("Command execution failed: '%s' -> %s", query, message)
            self.show_feedback(message, is_error=True)

    def _handle_execution_result(self, res: ExecutionResult, query: str) -> None:
        """Handle execution result returned by AstraApplication."""
        if res.type == "fast_path":
            if res.success:
                logger.info("Fast path command executed successfully: '%s'", query)
                self.dismiss(reason="fast_path_executed")
            else:
                self.show_feedback(res.message, is_error=True)

        elif res.type in ("conversational", "conversational_response"):
            from astrarun.ui.cards import AssistantCard
            tool_status = None
            if res.data and isinstance(res.data, dict) and res.data.get("tool_observations"):
                tool_status = "Action Verified"
            card = AssistantCard(
                text=res.message,
                title="Astra",
                tool_status=tool_status,
                parent=self,
            )
            card.dismissed.connect(self.clear_card)
            self.mount_card(card, target_height=min(280, max(140, len(res.message) // 3)))
            self.input_field.selectAll()

        elif res.type == "command":
            if res.message == "open_history":
                self.open_history()
            elif res.message == "open_memory":
                self.open_memory()
            elif res.message == "open_skills":
                self.open_skills()
            elif res.message == "open_settings":
                self.open_settings()
            elif res.message == "open_diagnostics":
                self.open_diagnostics()

        elif res.type == "confirm":
            from astrarun.ui.cards import ConfirmationCard
            tool_name = "action"
            args: dict[str, Any] = {}
            if res.data:
                args = res.data
            card = ConfirmationCard(
                token=res.confirmation_token or "",
                tool=tool_name,
                arguments=args,
                title="Confirm Action",
                description=res.prompt or res.message,
                risk=res.risk,
                parent=self,
            )
            card.confirmed.connect(self._on_confirmation_accepted)
            card.cancelled.connect(self.clear_card)
            self.mount_card(card, target_height=180)

        elif res.type == "clarify":
            from astrarun.ui.cards import DisambiguationCard
            cand_list = res.candidates if isinstance(res.candidates, list) else []
            card = DisambiguationCard(
                candidates=cand_list,
                title=res.prompt or "Which target did you mean?",
                parent=self,
            )
            card.candidate_selected.connect(self._on_candidate_chosen)
            card.cancelled.connect(self.clear_card)
            self.mount_card(card, target_height=200)

        elif res.type == "list_result":
            if self.hud:
                self.dismiss_animated(reason="list_result_hud")
                return
            from astrarun.ui.cards import ListResultCard
            items = []
            if res.data and "grouped_capabilities" in res.data:
                for cat, caps in res.data["grouped_capabilities"].items():
                    for c in caps:
                        items.append({"name": c, "category": cat})
            elif isinstance(res.data, dict):
                for k, v in res.data.items():
                    if isinstance(v, list):
                        for it in v:
                            items.append(it if isinstance(it, dict) else {"name": str(it)})
            if not items:
                items = [{"name": res.message}]
            card = ListResultCard(
                title=res.message or "Results",
                items=items,
                parent=self,
            )
            card.dismissed.connect(self.clear_card)
            self.mount_card(card, target_height=240)

        elif res.type == "capability_result":
            if self.hud:
                self.dismiss_animated(reason="capability_result_hud")
                return
            from astrarun.ui.cards import ResultCard
            rows = []
            if res.data and isinstance(res.data, dict):
                for k, v in res.data.items():
                    rows.append((str(k), str(v)))
            if not rows:
                rows.append(("Status", "Success" if res.success else "Failed"))
                rows.append(("Message", res.message))
            card = ResultCard(
                title=res.message or "Capability Executed",
                rows=rows,
                status="SUCCESS" if res.success else "FAILED",
                parent=self,
            )
            card.dismissed.connect(self.clear_card)
            self.mount_card(card, target_height=180)

        elif res.type == "blocked":
            blocked_msg = res.message if res.message.startswith("Blocked:") else f"Blocked: {res.message}"
            self.show_feedback(blocked_msg, is_error=True)

        elif res.type == "reasoning_required":
            self.show_feedback("Complex diagnostic reasoning required (AI Bridge unconfigured).", is_error=True)

        else:
            if res.success:
                if self.hud:
                    self.dismiss_animated(reason="task_success_hud")
                else:
                    self.show_feedback(res.message, is_error=False)
            else:
                self.show_feedback(res.message or "Command failed", is_error=True)

    def _on_confirmation_accepted(self, token: str, tool: str, arguments: dict) -> None:
        """Handle user confirmation from ConfirmationCard."""
        self.clear_card()
        if not self.app:
            return
        if hasattr(self.app, "execution_broker") and self.app.execution_broker:
            from astrarun.security.execution_broker import ActionProposal
            prop = ActionProposal(
                capability_id=tool,
                parameters=arguments,
                source="launcher_confirmation",
            )
            broker_res = self.app.execution_broker.execute(prop, confirmation_token=token)
            if broker_res.success:
                self.show_feedback(f"Executed: {broker_res.message}", is_error=False)
            else:
                self.show_feedback(f"Failed: {broker_res.message}", is_error=True)
            return

        self.show_feedback("SECURITY_VIOLATION: ExecutionBroker is required for confirmed execution", is_error=True)

    def _on_candidate_chosen(self, candidate_data: dict) -> None:
        """Handle user disambiguation candidate selection."""
        self.clear_card()
        target = candidate_data.get("name") or candidate_data.get("title") or candidate_data.get("id") or str(candidate_data)
        self.input_field.setText(str(target))
        self.execute_command()

    def open_history(self) -> None:
        """Open HistoryView modal."""
        if not self.app or not self.app.task_ledger:
            self.show_feedback("Task history not available.", is_error=True)
            return
        from astrarun.ui.history import HistoryView
        dlg = QDialog(self)
        dlg.setWindowTitle("AstraRun History")
        dlg.resize(850, 500)
        dlg.setStyleSheet(f"background-color: {BG_APP}; color: {TEXT_PRIMARY};")
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(8, 8, 8, 8)
        view = HistoryView(ledger=self.app.task_ledger, parent=dlg)
        view.dismissed.connect(dlg.accept)
        layout.addWidget(view)
        dlg.exec()
 
    def open_task_center(self) -> None:
        """Open TaskCenterWindow modal dialog."""
        from astrarun.ui.task_center import TaskCenterWindow
        runtime = getattr(self.app, "task_runtime", None)
        dlg = TaskCenterWindow(task_runtime=runtime, app=self.app, parent=self)
        dlg.exec()

    def open_memory(self) -> None:
        """Open MemoryView inspector."""
        if not self.app or not self.app.memory_store:
            self.show_feedback("Memory store not available.", is_error=True)
            return
        from astrarun.ui.memory import MemoryView
        view = MemoryView(memory_store=self.app.memory_store)
        view.show()
        self._memory_view_ref = view

    def open_skills(self) -> None:
        """Open SkillReviewWidget or skills list."""
        if not self.app or not self.app.skill_manager:
            self.show_feedback("Skill manager not available.", is_error=True)
            return
        from astrarun.learning.models import SkillStatus
        from astrarun.ui.memory import SkillReviewWidget
        pending = self.app.skill_manager.persistence.get_skills_by_status(SkillStatus.PENDING_REVIEW)
        if pending:
            dlg = SkillReviewWidget(skill=pending[0], skill_manager=self.app.skill_manager, parent=self)
            dlg.exec()
        else:
            self.show_feedback("No pending skills awaiting review.", is_error=False)

    def open_settings(self) -> None:
        """Open SettingsDialog."""
        from astrarun.ui.settings import SettingsDialog
        dlg = SettingsDialog(app_instance=self.app, parent=self)
        dlg.exec()

    def open_diagnostics(self) -> None:
        """Open DiagnosticsDialog."""
        if not self.app:
            self.show_feedback("Application context not available.", is_error=True)
            return
        from astrarun.ui.diagnostics import DiagnosticsDialog
        dlg = DiagnosticsDialog(app_instance=self.app, start_time=time.time(), parent=self)
        dlg.exec()

    def showEvent(self, event: Any) -> None:
        self._log_lifecycle("SHOW_EVENT")
        super().showEvent(event)

    def hideEvent(self, event: Any) -> None:
        self._log_lifecycle("HIDE_EVENT")
        super().hideEvent(event)

    def closeEvent(self, event: Any) -> None:
        if hasattr(self, "_registered_hwnd") and self._registered_hwnd:
            unregister_astrarun_hwnd(self._registered_hwnd)
            self._registered_hwnd = None
        super().closeEvent(event)

    def focusInEvent(self, event: Any) -> None:
        self._log_lifecycle("FOCUS_IN")
        try:
            super().focusInEvent(event)
        except Exception:
            pass

    def focusOutEvent(self, event: Any) -> None:
        if self.state in (LauncherState.ENTERING, LauncherState.ACTIVATING):
            self._log_lifecycle("FOCUS_OUT", reason="transient_ignored_in_activation")
        else:
            self._log_lifecycle("FOCUS_OUT")
        try:
            super().focusOutEvent(event)
        except Exception:
            pass

    def nativeEvent(self, eventType: QByteArray | bytes, message: int | Any) -> tuple[bool, int]:
        """Intercept Win32 system menu invocations to prevent Alt key from triggering menu mode."""
        if sys.platform == "win32" and eventType in (b"windows_generic_MSG", "windows_generic_MSG"):
            try:
                msg = wintypes.MSG.from_address(int(message))
                WM_SYSCOMMAND = 0x0112
                SC_KEYMENU = 0xF100
                if msg.message == WM_SYSCOMMAND and (msg.wParam & 0xFFF0) == SC_KEYMENU:
                    self._log_lifecycle("SC_KEYMENU_SWALLOWED", extra="Alt_system_menu_blocked")
                    return True, 0
                if WM_ASTRARUN_SUMMON and msg.message == WM_ASTRARUN_SUMMON:
                    self._log_lifecycle("WM_ASTRARUN_SUMMON_RECEIVED")
                    if self.app and hasattr(self.app, "presentation_controller") and self.app.presentation_controller:
                        self.app.presentation_controller.present()
                    else:
                        self.present_animated(self.geometry())
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard-first navigation."""
        key = event.key()

        # Swallow Alt presses so they don't trigger Windows system menu
        if key in (Qt.Key.Key_Alt, Qt.Key.Key_AltGr):
            event.accept()
            return

        # Escape dismisses active card first, then dismisses launcher
        if key == Qt.Key.Key_Escape:
            if self.active_card is not None:
                self.clear_card()
            else:
                self.dismiss(reason="escape_key")
            event.accept()
            return

        # Down arrow: move selection down in suggestions
        if key == Qt.Key.Key_Down and self.suggestions_list.isVisible():
            self._user_navigated_suggestions = True
            count = self.suggestions_list.count()
            if count > 0:
                current = self.suggestions_list.currentRow()
                nxt = (current + 1) % count
                self.suggestions_list.setCurrentRow(nxt)
            event.accept()
            return

        # Up arrow: move selection up in suggestions
        if key == Qt.Key.Key_Up and self.suggestions_list.isVisible():
            self._user_navigated_suggestions = True
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

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        """Swallow standalone Alt release so it does not trigger Windows menu loop."""
        key = event.key()
        if key in (Qt.Key.Key_Alt, Qt.Key.Key_AltGr):
            event.accept()
            return
        super().keyReleaseEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        """Handle window activation changes with explicit state machine guards."""
        if event.type() == QEvent.Type.ActivationChange:
            is_act = self.isActiveWindow()
            self._log_lifecycle("ACTIVATION_CHANGE", extra=f"isActiveWindow={is_act}")
            if is_act:
                self._has_been_active = True
                self._log_lifecycle("WINDOW_ACTIVATE")
            else:
                self._log_lifecycle("WINDOW_DEACTIVATE")
                # In ENTERING or ACTIVATING: strictly block dismissal
                if self.state in (LauncherState.ENTERING, LauncherState.ACTIVATING):
                    self._log_lifecycle("DISMISS_BLOCKED", reason=f"protected_in_{self.state.value.lower()}")
                    super().changeEvent(event)
                    return

                # In INTERACTIVE: only dismiss if hide_on_focus_loss is explicitly True
                if self.state == LauncherState.INTERACTIVE:
                    if self.hide_on_focus_loss and self.active_card is None:
                        self.dismiss_animated(reason="focus_loss")
                    else:
                        self._log_lifecycle("DISMISS_BLOCKED", reason="focus_loss_dismissal_disabled")

        super().changeEvent(event)
