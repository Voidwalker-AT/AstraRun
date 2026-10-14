"""Decoupled Floating Task HUD and HUD Controller for AstraRun v0.10.1.

Provides a persistent, non-focus-stealing floating indicator on the top-right
of the active display, driven purely by real TaskEventBus events.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.logging import get_logger
from astrarun.tasks.events import TaskEventBus
from astrarun.tasks.models import TaskEvent, TaskEventType
from astrarun.ui.icons import IconRenderer
from astrarun.ui.motion import MotionTokens
from astrarun.ui.positioning import compute_task_hud_position, get_screen_for_hwnd
from astrarun.ui.theme import (
    ACCENT,
    ATTENTION,
    BORDER,
    BORDER_STRONG,
    BORDER_SUBTLE,
    DANGER,
    FONT_FAMILY,
    FONT_MONO,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_SMALL,
    FONT_SIZE_TITLE,
    RADIUS_MD,
    RADIUS_SM,
    SUCCESS,
    SURFACE,
    SURFACE_HOVER,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
    get_button_style,
)
from astrarun.windows.policy import register_astrarun_hwnd, unregister_astrarun_hwnd

logger = get_logger("astrarun.ui.hud")


class CapabilityTimingStats:
    """Historical timing statistics for a capability."""
    def __init__(self, capability_id: str):
        self.capability_id = capability_id
        self.count: int = 0
        self.ema_duration_s: float = 0.5
        self.recent_durations: list[float] = []

    def update(self, duration_s: float) -> None:
        self.count += 1
        alpha = 0.3
        self.ema_duration_s = (alpha * duration_s) + ((1.0 - alpha) * self.ema_duration_s)
        self.recent_durations.append(duration_s)
        if len(self.recent_durations) > 20:
            self.recent_durations.pop(0)

    @property
    def p50(self) -> float:
        if not self.recent_durations:
            return self.ema_duration_s
        s = sorted(self.recent_durations)
        return s[len(s) // 2]

    @property
    def p90(self) -> float:
        if not self.recent_durations:
            return self.ema_duration_s
        s = sorted(self.recent_durations)
        idx = min(int(len(s) * 0.9), len(s) - 1)
        return s[idx]


class TaskETAEstimator:
    """Estimates remaining duration for multi-step agent tasks based on real measurements and per-capability stats."""

    def __init__(self):
        self.step_start_times: dict[str, float] = {}
        self.completed_durations: list[float] = []
        self.capability_stats: dict[str, CapabilityTimingStats] = {}

    def record_step_start(self, step_id: str) -> None:
        self.step_start_times[step_id] = time.time()

    def record_step_end(self, step_id: str, capability_id: Optional[str] = None) -> None:
        start = self.step_start_times.get(step_id)
        if start:
            dur = time.time() - start
            self.completed_durations.append(dur)
            if capability_id:
                if capability_id not in self.capability_stats:
                    self.capability_stats[capability_id] = CapabilityTimingStats(capability_id)
                self.capability_stats[capability_id].update(dur)

    def estimate_remaining_s(self, completed_steps: int, total_steps: int, remaining_capabilities: Optional[list[str]] = None) -> Optional[float]:
        if total_steps <= 0 or completed_steps >= total_steps:
            return 0.0

        # If remaining capability IDs are known, sum their expected durations
        if remaining_capabilities:
            total_est = 0.0
            for cap_id in remaining_capabilities:
                stats = self.capability_stats.get(cap_id)
                if stats:
                    total_est += stats.ema_duration_s
                elif self.completed_durations:
                    total_est += sum(self.completed_durations) / len(self.completed_durations)
                else:
                    total_est += 0.5
            return round(total_est, 1)

        if not self.completed_durations:
            return None
        avg_dur = sum(self.completed_durations) / len(self.completed_durations)
        remaining_steps = total_steps - completed_steps
        return round(avg_dur * remaining_steps, 1)

    def format_eta(self, remaining_s: Optional[float]) -> str:
        if remaining_s is None or remaining_s <= 0:
            return ""
        if remaining_s < 1.0:
            return "< 1s"
        if remaining_s < 60:
            return f"~{remaining_s:.1f}s"
        mins = int(remaining_s // 60)
        secs = int(remaining_s % 60)
        return f"~{mins}m {secs}s"



class HUDState(str, Enum):
    """Explicit lifecycle states of the Floating Task HUD."""
    IDLE = "IDLE"
    PASSIVE_PROGRESS = "PASSIVE_PROGRESS"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    RESULT = "RESULT"
    LIST_RESULT = "LIST_RESULT"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    WAITING_CLARIFICATION = "WAITING_CLARIFICATION"
    INTERACTIVE = "INTERACTIVE"
    PAUSED = "PAUSED"


class FloatingTaskHUD(QWidget):
    """
    Decoupled floating surface positioned top-right of origin monitor.
    
    NON-FOCUS-STEALING INVARIANT:
    This window uses Qt.WindowDoesNotAcceptFocus and Win32 WS_EX_NOACTIVATE
    to guarantee it NEVER steals keyboard focus from the active workstation app
    (e.g., Notepad, VS Code, Browser) during background task execution.
    """

    confirmed = Signal(str, str, dict)  # token, tool, arguments
    cancelled = Signal()
    candidate_selected = Signal(dict)
    dismissed = Signal()
    pause_requested = Signal(str)
    resume_requested = Signal(str)
    cancel_requested = Signal(str)
    details_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None, animations_enabled: bool = True):
        super().__init__(parent)
        self.animations_enabled = animations_enabled
        self.current_state = HUDState.IDLE
        self.current_task_id: Optional[str] = None
        self.eta_estimator = TaskETAEstimator()
        self.hud_width = 380
        self.hud_min_height = 80
        self._target_point = QPoint(0, 0)
        self._is_animating = False

        self._init_window_flags()
        self._init_ui()
        self._init_animations()
        self._init_timers()

        self._registered_hwnd: int | None = None
        # Register HWND so window management policy ignores this widget
        if sys.platform == "win32":
            try:
                self._registered_hwnd = int(self.winId())
                register_astrarun_hwnd(self._registered_hwnd)
            except Exception as err:
                logger.debug("Could not register HUD HWND: %s", err)

    def _init_window_flags(self) -> None:
        """Apply non-activating, frameless, topmost tool-window flags."""
        self.setWindowTitle("AstraRun Task HUD")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.resize(self.hud_width, self.hud_min_height)

        # Enforce Win32 WS_EX_NOACTIVATE style
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                hwnd = int(self.winId())
                GWL_EXSTYLE = -20
                WS_EX_NOACTIVATE = 0x08000000
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)
            except Exception as e:
                logger.debug("Could not set WS_EX_NOACTIVATE on HUD: %s", e)

    def _init_ui(self) -> None:
        """Construct restrained desktop-native floating card interface."""
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(8, 8, 8, 8)
        self.root_layout.setSpacing(0)

        # Main Card Frame
        self.card = QFrame(self)
        self.card.setObjectName("hud_card")
        self.card.setStyleSheet(f"""
            QFrame#hud_card {{
                background-color: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)

        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 6)
        self.card.setGraphicsEffect(shadow)

        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(14, 10, 14, 10)
        self.card_layout.setSpacing(6)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        # Vector Status Indicator
        self.status_icon = QLabel(self.card)
        self.status_icon.setPixmap(IconRenderer.get_pixmap("spark", size=16, color=ACCENT))
        self.status_icon.setFixedSize(16, 16)
        self.status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_row.addWidget(self.status_icon)

        # Task Title Label
        self.title_label = QLabel("Astra Task", self.card)
        self.title_label.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: {FONT_SIZE_BODY};
            font-weight: 600;
            font-family: {FONT_FAMILY};
        """)
        header_row.addWidget(self.title_label, stretch=1)

        # ETA Label
        self.eta_label = QLabel("", self.card)
        self.eta_label.setStyleSheet(f"""
            color: {TEXT_MUTED};
            font-size: {FONT_SIZE_CAPTION};
            font-weight: 500;
            font-family: {FONT_FAMILY};
        """)
        header_row.addWidget(self.eta_label)

        # Expand / Steps toggle
        self.expand_btn = QPushButton("Steps", self.card)
        self.expand_btn.setIcon(IconRenderer.get_icon("chevron_down", size=10, color=TEXT_SECONDARY))
        self.expand_btn.setFixedHeight(20)
        self.expand_btn.setStyleSheet(get_button_style("ghost", size="sm"))
        self.expand_btn.clicked.connect(self.toggle_steps_expansion)
        self.expand_btn.hide()
        header_row.addWidget(self.expand_btn)

        # Dismiss / Cancel Button
        self.close_btn = QPushButton(self.card)
        self.close_btn.setIcon(IconRenderer.get_icon("close", size=11, color=TEXT_MUTED))
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setStyleSheet(get_button_style("ghost", size="sm"))
        self.close_btn.clicked.connect(self._on_close_clicked)
        header_row.addWidget(self.close_btn)

        self.card_layout.addLayout(header_row)

        # Subtitle / Step Detail Label
        self.detail_label = QLabel("Processing...", self.card)
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet(f"""
            color: {TEXT_SECONDARY};
            font-size: {FONT_SIZE_CAPTION};
            font-family: {FONT_FAMILY};
        """)
        self.card_layout.addWidget(self.detail_label)

        # Authentic Progress Bar
        self.progress_bar = QProgressBar(self.card)
        self.progress_bar.setFixedHeight(3)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background-color: #1e2026;
                border: none;
                border-radius: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {ACCENT};
                border-radius: 2px;
            }}
        """)
        self.card_layout.addWidget(self.progress_bar)

        # Dynamic Steps Container
        self.steps_container = QWidget(self.card)
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(4, 4, 4, 4)
        self.steps_layout.setSpacing(4)
        self.steps_container.hide()
        self.card_layout.addWidget(self.steps_container)

        # Interactive Container (for Confirmation / Disambiguation)
        self.action_container = QWidget(self.card)
        self.action_layout = QHBoxLayout(self.action_container)
        self.action_layout.setContentsMargins(0, 4, 0, 0)
        self.action_layout.setSpacing(8)
        self.action_container.hide()
        self.card_layout.addWidget(self.action_container)

        self.root_layout.addWidget(self.card)

    def _init_animations(self) -> None:
        """Setup slide and opacity animations respecting MotionTokens."""
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        enter_ms = MotionTokens.get_enter_duration() if self.animations_enabled else 0

        # Position Animation
        self.pos_anim = QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(enter_ms)
        self.pos_anim.setEasingCurve(MotionTokens.EASING_ENTER)

        # Opacity Animation
        self.opacity_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_anim.setDuration(enter_ms)
        self.opacity_anim.setEasingCurve(MotionTokens.EASING_ENTER)

        # Group
        self.anim_group = QParallelAnimationGroup(self)
        self.anim_group.addAnimation(self.pos_anim)
        self.anim_group.addAnimation(self.opacity_anim)
        self.anim_group.finished.connect(self._on_animation_finished)

    def _init_timers(self) -> None:
        """Auto-dismissal timer for terminal success/error states."""
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.dismiss)

    def position_on_monitor(self, target_screen: Any = None, origin_hwnd: int | None = None) -> None:
        """Position HUD in upper-right corner of target monitor."""
        pos, avail = compute_task_hud_position(
            self.hud_width, self.height(), target_screen=target_screen, origin_hwnd=origin_hwnd
        )
        self._target_point = pos
        self.move(pos)

    def present_animated(self, target_screen: Any = None, origin_hwnd: int | None = None) -> None:
        """Show HUD with gentle slide and fade from top-right."""
        self.position_on_monitor(target_screen=target_screen, origin_hwnd=origin_hwnd)

        if not self.animations_enabled:
            self.move(self._target_point)
            self.opacity_effect.setOpacity(1.0)
            self.show()
            return

        self._is_animating = True
        start_pos = QPoint(self._target_point.x() + 25, self._target_point.y())
        self.opacity_effect.setOpacity(1.0)
        self.show()

        self.pos_anim.setStartValue(start_pos)
        self.pos_anim.setEndValue(self._target_point)
        self.opacity_anim.setStartValue(1.0)
        self.opacity_anim.setEndValue(1.0)
        self.anim_group.start()

    def dismiss(self, immediate: bool = False) -> None:
        """Animate out and hide HUD."""
        self.dismiss_timer.stop()
        if not self.isVisible():
            self.current_state = HUDState.IDLE
            return

        if immediate or not self.animations_enabled:
            self.hide()
            self.current_state = HUDState.IDLE
            self.dismissed.emit()
            return

        self._is_animating = True
        end_pos = QPoint(self.pos().x() + 20, self.pos().y())
        self.pos_anim.setStartValue(self.pos())
        self.pos_anim.setEndValue(end_pos)
        self.opacity_anim.setStartValue(self.opacity_effect.opacity())
        self.opacity_anim.setEndValue(0.0)
        self.anim_group.start()

    def _on_animation_finished(self) -> None:
        """Clean up post-animation state."""
        self._is_animating = False
        if self.opacity_effect.opacity() <= 0.05:
            self.hide()
            self.current_state = HUDState.IDLE
            self.dismissed.emit()

    def closeEvent(self, event: Any) -> None:
        if hasattr(self, "_registered_hwnd") and self._registered_hwnd:
            unregister_astrarun_hwnd(self._registered_hwnd)
            self._registered_hwnd = None
        super().closeEvent(event)

    # =========================================================================
    # STATE TRANSITION METHODS
    # =========================================================================

    def _on_close_clicked(self) -> None:
        """Handle user clicking close / cancel button on HUD."""
        if self.current_state in (
            HUDState.PASSIVE_PROGRESS,
            HUDState.WAITING_CONFIRMATION,
            HUDState.WAITING_CLARIFICATION,
            HUDState.INTERACTIVE,
            HUDState.PAUSED,
        ):
            logger.info("HUD cancel button clicked for task %s", self.current_task_id)
            if self.current_task_id:
                self.cancel_requested.emit(self.current_task_id)
            self.cancelled.emit()
            self.detail_label.setText("Cancelling task...")
            self.status_icon.setPixmap(IconRenderer.get_pixmap("close", size=16, color=WARNING))
        else:
            self.dismiss()

    def set_progress_mode(self, mode: str, progress_pct: float = 0.0) -> None:
        """Configure authentic progress bar mode (INSTANT, DETERMINATE, INDETERMINATE, EVENT_DRIVEN)."""
        mode_upper = str(mode).upper()
        if "INSTANT" in mode_upper:
            self.progress_bar.hide()
            self.eta_label.setText("")
        elif "INDETERMINATE" in mode_upper or "EVENT" in mode_upper:
            self.progress_bar.show()
            self.progress_bar.setRange(0, 0)
        elif "DETERMINATE" in mode_upper:
            self.progress_bar.show()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(max(0, min(100, int(progress_pct))))
        else:
            self.progress_bar.show()
            self.progress_bar.setRange(0, 0)

    def set_steps(self, steps: list[dict[str, Any]]) -> None:
        """Populate dynamic task graph step list."""
        self._clear_steps()
        self._step_widgets: dict[str, dict[str, Any]] = {}

        if not steps:
            self.expand_btn.hide()
            return

        class StepGlyphLabel(QLabel):
            def __init__(self, parent=None):
                super().__init__(parent)
                self._fallback_text = "●"
            def set_glyph(self, pixmap, fallback_text):
                self._fallback_text = fallback_text
                self.setPixmap(pixmap)
            def text(self) -> str:
                return super().text() or self._fallback_text

        for step in steps:
            sid = step.get("step_id", "")
            desc = step.get("description", sid)
            state = step.get("state", "PENDING")

            row = QWidget(self.steps_container)
            h_layout = QHBoxLayout(row)
            h_layout.setContentsMargins(2, 1, 2, 1)
            h_layout.setSpacing(6)

            glyph = StepGlyphLabel(row)
            glyph.set_glyph(IconRenderer.get_pixmap("pending", size=12, color=TEXT_MUTED), "●")
            glyph.setFixedSize(14, 14)
            glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
            h_layout.addWidget(glyph)

            lbl = QLabel(desc, row)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-family: {FONT_FAMILY};")
            lbl.setWordWrap(True)
            h_layout.addWidget(lbl, stretch=1)

            self.steps_layout.addWidget(row)
            self._step_widgets[sid] = {"row": row, "glyph": glyph, "label": lbl, "desc": desc}

        if len(steps) > 1:
            self.expand_btn.show()
        else:
            self.expand_btn.hide()

    def update_step_state(self, step_id: str, state: str, description: str = "") -> None:
        """Update vector status icon, typography, and ETA for a specific plan step."""
        state_upper = state.upper()
        step_entry = getattr(self, "_step_widgets", {}).get(step_id)

        if step_entry:
            glyph = step_entry["glyph"]
            lbl = step_entry["label"]
            if description:
                lbl.setText(description)

            if "RUNNING" in state_upper:
                glyph.set_glyph(IconRenderer.get_pixmap("running", size=12, color=ACCENT), "►")
                lbl.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 500; font-family: {FONT_FAMILY};")
                self.eta_estimator.record_step_start(step_id)
            elif "COMPLETED" in state_upper:
                glyph.set_glyph(IconRenderer.get_pixmap("check", size=12, color=SUCCESS), "✓")
                lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; font-family: {FONT_FAMILY};")
                self.eta_estimator.record_step_end(step_id)
            elif "FAILED" in state_upper:
                glyph.set_glyph(IconRenderer.get_pixmap("error", size=12, color=DANGER), "✗")
                lbl.setStyleSheet(f"color: {DANGER}; font-size: 11px; font-family: {FONT_FAMILY};")
            elif "CANCELLED" in state_upper:
                glyph.set_glyph(IconRenderer.get_pixmap("close", size=12, color=TEXT_MUTED), "○")
                lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-family: {FONT_FAMILY};")

        # Update ETA if we have step widgets
        if hasattr(self, "_step_widgets") and self._step_widgets:
            total = len(self._step_widgets)
            completed = len(self.eta_estimator.completed_durations)
            rem = self.eta_estimator.estimate_remaining_s(completed, total)
            self.eta_label.setText(self.eta_estimator.format_eta(rem))

    def toggle_steps_expansion(self) -> None:
        """Toggle step list expansion visibility."""
        is_hidden = self.steps_container.isHidden()
        self.steps_container.setVisible(is_hidden)
        self.expand_btn.setText("▴ Steps" if is_hidden else "▾ Steps")
        self.expand_btn.setIcon(IconRenderer.get_icon("chevron_up" if is_hidden else "chevron_down", size=10, color=TEXT_SECONDARY))
        self.adjustSize()

    def _clear_steps(self) -> None:
        """Clear dynamic steps list."""
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.steps_container.hide()
        self.expand_btn.hide()
        self.expand_btn.setText("▾ Steps")
        self.expand_btn.setIcon(IconRenderer.get_icon("chevron_down", size=10, color=TEXT_SECONDARY))

    def show_progress(
        self,
        task_id: str,
        title: str,
        message: str = "Processing...",
        target_screen: Any = None,
        origin_hwnd: int | None = None,
        progress_mode: str = "INDETERMINATE",
        progress_pct: float = 0.0,
    ) -> None:
        """Transition to PASSIVE_PROGRESS state (never steals focus)."""
        self.dismiss_timer.stop()
        self._clear_actions()
        if self.current_task_id != task_id:
            self._clear_steps()
        self.eta_estimator = TaskETAEstimator()
        self.eta_label.setText("")
        self.current_state = HUDState.PASSIVE_PROGRESS
        self.current_task_id = task_id

        self.status_icon.setPixmap(IconRenderer.get_pixmap("spark", size=16, color=ACCENT))
        self.title_label.setText(title or "Executing Task")
        self.detail_label.setText(message)

        self.set_progress_mode(progress_mode, progress_pct)

        if not self.isVisible():
            self.present_animated(target_screen=target_screen, origin_hwnd=origin_hwnd)

    def update_progress(self, task_id: str, message: str, progress_pct: Optional[float] = None) -> None:
        """Update active progress message and progress bar percentage without focus theft."""
        if self.current_task_id == task_id or not self.current_task_id:
            self.detail_label.setText(message)
            if progress_pct is not None:
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(max(0, min(100, int(progress_pct))))

    def show_success(self, task_id: str, message: str = "Task completed successfully.") -> None:
        """Transition to SUCCESS state with automatic dismissal."""
        self._clear_actions()
        if self.current_task_id != task_id:
            self._clear_steps()
        self.current_state = HUDState.SUCCESS
        self.current_task_id = task_id
        self.eta_label.setText("")

        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

        self.status_icon.setPixmap(IconRenderer.get_pixmap("check", size=16, color=SUCCESS))
        self.title_label.setText("Completed")
        self.detail_label.setText(message)

        # If result mentions a file/report path, provide Show in Folder & Open actions
        import re
        m = re.search(r'([A-Za-z0-9_\\/\-:]+\.[a-zA-Z0-9]+)', message)
        if m:
            btn_folder = QPushButton("Show in Folder", self.action_container)
            btn_folder.setIcon(IconRenderer.get_icon("folder", size=11, color=TEXT_SECONDARY))
            btn_folder.setStyleSheet(get_button_style("subtle", size="sm"))
            self.action_layout.addWidget(btn_folder)

            btn_open = QPushButton("Open", self.action_container)
            btn_open.setIcon(IconRenderer.get_icon("external", size=11, color=TEXT_PRIMARY))
            btn_open.setStyleSheet(get_button_style("secondary", size="sm"))
            self.action_layout.addWidget(btn_open)
            self.action_container.show()

        if not self.isVisible():
            self.present_animated()

        self.dismiss_timer.start(3500)

    def show_error(self, task_id: str, message: str = "Task failed.") -> None:
        """Transition to ERROR state with 5.0s dismissal."""
        self._clear_actions()
        if self.current_task_id != task_id:
            self._clear_steps()
        self.current_state = HUDState.ERROR
        self.current_task_id = task_id
        self.eta_label.setText("")

        self.progress_bar.hide()

        self.status_icon.setPixmap(IconRenderer.get_pixmap("error", size=16, color=DANGER))
        self.title_label.setText("Failed")
        self.detail_label.setText(message)

        if not self.isVisible():
            self.present_animated()

        self.dismiss_timer.start(5000)

    def show_confirmation(
        self,
        task_id: str,
        prompt: str,
        token: str,
        tool: str,
        arguments: dict,
    ) -> None:
        """Transition to WAITING_CONFIRMATION interactive state."""
        self.dismiss_timer.stop()
        self._clear_actions()
        if self.current_task_id != task_id:
            self._clear_steps()
        self.current_state = HUDState.WAITING_CONFIRMATION
        self.current_task_id = task_id

        self.status_icon.setPixmap(IconRenderer.get_pixmap("warning", size=16, color=WARNING))
        self.title_label.setText("Confirmation Required")
        self.detail_label.setText(prompt or "Confirm action to proceed.")

        is_destructive = any(
            k in tool.lower() or k in (prompt or "").lower()
            for k in ("kill", "terminate", "delete", "destroy", "remove", "destructive")
        )
        action_text = "Terminate" if ("kill" in tool.lower() or "terminate" in tool.lower()) else "Confirm"

        # Action Button (Danger variant for destructive operations)
        btn_confirm = QPushButton(action_text, self.action_container)
        btn_confirm.setStyleSheet(get_button_style("danger" if is_destructive else "primary", size="sm"))
        btn_confirm.clicked.connect(lambda: self._on_confirm_clicked(token, tool, arguments))
        self.action_layout.addWidget(btn_confirm)

        # Cancel Button (Safe default)
        btn_cancel = QPushButton("Cancel", self.action_container)
        btn_cancel.setStyleSheet(get_button_style("secondary", size="sm"))
        btn_cancel.clicked.connect(self._on_cancel_clicked)
        self.action_layout.addWidget(btn_cancel)
        self.action_container.show()

        if not self.isVisible():
            self.present_animated()

    def show_clarification(
        self,
        task_id: str,
        prompt: str,
        candidates: list[dict],
    ) -> None:
        """Transition to WAITING_CLARIFICATION interactive state."""
        self.dismiss_timer.stop()
        self._clear_actions()
        if self.current_task_id != task_id:
            self._clear_steps()
        self.current_state = HUDState.WAITING_CLARIFICATION
        self.current_task_id = task_id

        self.status_icon.setPixmap(IconRenderer.get_pixmap("question", size=16, color=ATTENTION))
        self.title_label.setText("Clarification Needed")
        self.detail_label.setText(prompt or "Please select an option:")

        for cand in candidates[:3]:
            name = cand.get("title") or cand.get("name") or str(cand)
            btn = QPushButton(name, self.action_container)
            btn.setStyleSheet(get_button_style("secondary", size="sm"))
            btn.clicked.connect(lambda _, c=cand: self.candidate_selected.emit(c))
            self.action_layout.addWidget(btn)

        self.action_container.show()
        if not self.isVisible():
            self.present_animated()

    def show_user_takeover(self, task_id: str, message: str = "Paused — you're using the computer") -> None:
        """Transition to PAUSED_USER_ACTIVE interactive state on user takeover."""
        self.dismiss_timer.stop()
        self._clear_actions()
        if self.current_task_id != task_id:
            self._clear_steps()
        self.current_state = HUDState.INTERACTIVE
        self.current_task_id = task_id

        self.status_icon.setPixmap(IconRenderer.get_pixmap("pause", size=16, color=WARNING))
        self.title_label.setText("Astra — Paused")
        clean_msg = (message or "Paused — you're using the computer").replace("✦", "").strip()
        self.detail_label.setText(clean_msg)

        # Resume Button
        btn_resume = QPushButton("Resume", self.action_container)
        btn_resume.setStyleSheet(get_button_style("primary", size="sm"))
        btn_resume.clicked.connect(lambda: self.resume_requested.emit(task_id))
        self.action_layout.addWidget(btn_resume)

        # Cancel Button
        btn_cancel = QPushButton("Cancel", self.action_container)
        btn_cancel.setStyleSheet(get_button_style("secondary", size="sm"))
        btn_cancel.clicked.connect(lambda: self.cancel_requested.emit(task_id))
        self.action_layout.addWidget(btn_cancel)
        self.action_container.show()

        if not self.isVisible():
            self.present_animated()

    def _clear_actions(self) -> None:
        """Clear dynamic interactive buttons."""
        while self.action_layout.count():
            item = self.action_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.action_container.hide()

    def _on_confirm_clicked(self, token: str, tool: str, arguments: dict) -> None:
        self._clear_actions()
        self.show_progress(self.current_task_id or "", "Confirmed", "Executing confirmed action...")
        self.confirmed.emit(token, tool, arguments)

    def _on_cancel_clicked(self) -> None:
        self.cancelled.emit()
        self.dismiss()

    def get_state(self) -> dict[str, Any]:
        """Return diagnostic inspection snapshot."""
        return {
            "state": self.current_state.value,
            "task_id": self.current_task_id,
            "visible": self.isVisible(),
            "geometry": {
                "x": self.x(),
                "y": self.y(),
                "width": self.width(),
                "height": self.height(),
            },
        }


class TaskHUDController(QObject):
    """
    Subscribes to TaskEventBus and drives the FloatingTaskHUD state machine.
    Ensures background thread events are safely marshalled onto the Qt GUI thread.
    """

    event_received = Signal(object)  # TaskEvent

    def __init__(
        self,
        hud: FloatingTaskHUD,
        event_bus: TaskEventBus | None = None,
        app: Any = None,
        task_runtime: Any = None,
    ):
        super().__init__()
        self.hud = hud
        self.event_bus = event_bus
        self.app = app
        self.task_runtime = task_runtime or getattr(app, "task_runtime", None)
        self._sub_id: Optional[int] = None

        # Cross-thread Qt signal connection
        self.event_received.connect(self._handle_event)

        # Wire up HUD interactive signals
        self.hud.confirmed.connect(self._on_hud_confirmed)
        self.hud.candidate_selected.connect(self._on_hud_candidate_selected)
        self.hud.pause_requested.connect(self._on_hud_pause)
        self.hud.resume_requested.connect(self._on_hud_resume)
        self.hud.cancel_requested.connect(self._on_hud_cancel)
        self.hud.details_requested.connect(self._on_hud_details)

        if self.event_bus is not None:
            self._sub_id = self.event_bus.subscribe(self._on_bus_event)

    def _on_bus_event(self, event: TaskEvent) -> None:
        """Receive event from TaskEventBus (may be background worker thread)."""
        self.event_received.emit(event)

    def _handle_event(self, event: TaskEvent) -> None:
        """Handle event on the Qt GUI thread."""
        ev_type = getattr(event, "type", None) or getattr(event, "event_type", None)
        ev_msg = getattr(event, "summary", None) or getattr(event, "message", None) or getattr(event, "title", "")
        ev_data = getattr(event, "data", {}) or {}

        if ev_type == TaskEventType.TASK_CREATED:
            query = ev_data.get("raw_query") or ev_msg or "Running Task"
            self.hud.show_progress(event.task_id, query, "Initializing...")

        elif ev_type in (
            TaskEventType.NLP_PARSE_STARTED,
            TaskEventType.ENTITY_RESOLUTION_STARTED,
            TaskEventType.CAPABILITY_STARTED,
            TaskEventType.WORKFLOW_STEP_STARTED,
        ):
            self.hud.update_progress(event.task_id, ev_msg or "Executing step...")

        elif ev_type in (TaskEventType.CONFIRMATION_REQUESTED, TaskEventType.ACTION_GATE_CONFIRM):
            token = ev_data.get("token") or ev_data.get("confirmation_token", "")
            tool = ev_data.get("tool", "")
            args = ev_data.get("args") or ev_data.get("arguments", {})
            self.hud.show_confirmation(event.task_id, ev_msg, token, tool, args)

        elif ev_type in (TaskEventType.CLARIFICATION_REQUESTED, TaskEventType.ACTION_GATE_CLARIFY):
            cands = ev_data.get("candidates", [])
            self.hud.show_clarification(event.task_id, ev_msg, cands)

        elif ev_type in (TaskEventType.TASK_COMPLETED, TaskEventType.WORKFLOW_COMPLETED):
            self.hud.show_success(event.task_id, ev_msg or "Completed successfully.")

        elif ev_type in (TaskEventType.TASK_FAILED, TaskEventType.CAPABILITY_FAILED, TaskEventType.WORKFLOW_STEP_FAILED):
            self.hud.show_error(event.task_id, ev_msg or "Task execution failed.")

        elif ev_type in (TaskEventType.TASK_BLOCKED, TaskEventType.ACTION_GATE_BLOCK):
            self.hud.show_error(event.task_id, f"Blocked: {ev_msg}")

        elif ev_type == TaskEventType.TASK_CANCELLED:
            self.hud.show_error(event.task_id, "Task cancelled.")

        elif ev_type == TaskEventType.TASK_INTERRUPTED:
            is_takeover = ev_data.get("is_user_takeover", False)
            msg = ev_msg or ("Paused — you're using the computer" if is_takeover else "Task paused")
            self.hud.show_user_takeover(event.task_id, msg)

    def _on_hud_confirmed(self, token: str, tool: str, arguments: dict) -> None:
        """Dispatch confirmed capability execution through composition root."""
        if not self.app:
            return
        if hasattr(self.app, "execution_broker") and self.app.execution_broker:
            from astrarun.security.execution_broker import ActionProposal
            prop = ActionProposal(
                capability_id=tool,
                parameters=arguments,
                source="hud_confirmation",
            )
            broker_res = self.app.execution_broker.execute(prop, confirmation_token=token)
            if broker_res.success:
                self.hud.show_success(self.hud.current_task_id or "", broker_res.message)
            else:
                self.hud.show_error(self.hud.current_task_id or "", broker_res.message)
            return

        self.hud.show_error(self.hud.current_task_id or "", "SECURITY_VIOLATION: ExecutionBroker is required for confirmed execution")

    def _on_hud_candidate_selected(self, candidate: dict) -> None:
        """Reroute candidate through application request pipeline."""
        if not self.app:
            return
        target = candidate.get("title") or candidate.get("name") or str(candidate)
        self.hud.show_progress(self.hud.current_task_id or "", f"Selected: {target}", "Executing...")
        self.app.handle_request(target)

    def _on_hud_pause(self, task_id: str) -> None:
        """Pause running task via TaskRuntime."""
        runtime = self.task_runtime or getattr(self.app, "task_runtime", None)
        if runtime and task_id:
            runtime.pause_task(task_id)

    def _on_hud_resume(self, task_id: str) -> None:
        """Resume paused task via TaskRuntime."""
        runtime = self.task_runtime or getattr(self.app, "task_runtime", None)
        if runtime and task_id:
            runtime.resume_task(task_id)

    def _on_hud_cancel(self, task_id: str) -> None:
        """Cancel task via TaskRuntime."""
        runtime = self.task_runtime or getattr(self.app, "task_runtime", None)
        if runtime and task_id:
            runtime.cancel_task(task_id)
        else:
            self.hud.dismiss()

    def _on_hud_details(self, task_id: str) -> None:
        """Open Task Center window for detailed task inspection."""
        if hasattr(self.app, "show_task_center"):
            self.app.show_task_center()

    def stop(self) -> None:
        """Unsubscribe from event bus."""
        if self.event_bus and self._sub_id is not None:
            self.event_bus.unsubscribe(self._sub_id)
            self._sub_id = None


class AgentTaskHUDListener:
    """
    Bridges AgentExecutionEngine callbacks to FloatingTaskHUD methods for real-time Live Task HUD V2 display.
    Domain-agnostic: renders generic Plan, PlanStep, progress, status, and ETA.
    """

    def __init__(self, hud: FloatingTaskHUD):
        self.hud = hud

    def on_task_started(self, task: Any) -> None:
        steps_data = [
            {
                "step_id": s.step_id,
                "description": s.human_label or s.description,
                "state": s.state.value,
            }
            for s in task.plan.steps
        ]
        self.hud.set_steps(steps_data)
        mode = getattr(task.progress_mode, "value", str(task.progress_mode))
        self.hud.show_progress(
            task_id=task.task_id,
            title=task.goal.intent or "Agent Task",
            message=task.goal.raw_prompt or "Executing...",
            progress_mode=mode,
            progress_pct=task.progress_pct,
        )

    def on_task_progress(self, task: Any, progress_pct: float, message: str) -> None:
        self.hud.update_progress(task.task_id, message, progress_pct=progress_pct)

    def on_step_started(self, task: Any, step: Any) -> None:
        lbl = step.human_label or step.description
        if hasattr(self.hud, "eta_estimator") and self.hud.eta_estimator:
            self.hud.eta_estimator.record_step_start(step.step_id)
        self.hud.update_step_state(step.step_id, "RUNNING", lbl)
        self.hud.update_progress(task.task_id, f"Running: {lbl}", task.progress_pct)

    def on_step_completed(self, task: Any, step: Any, verification: Any) -> None:
        lbl = step.human_label or step.description
        if hasattr(self.hud, "eta_estimator") and self.hud.eta_estimator:
            self.hud.eta_estimator.record_step_end(step.step_id, getattr(step, "capability_id", None))
        self.hud.update_step_state(step.step_id, "COMPLETED")
        self.hud.update_progress(task.task_id, f"Verified: {lbl}", task.progress_pct)

    def on_step_failed(self, task: Any, step: Any, error: str) -> None:
        lbl = step.human_label or step.description
        self.hud.update_step_state(step.step_id, "FAILED")
        self.hud.show_error(task.task_id, f"Failed: {lbl} ({error})")

    def on_replan(self, task: Any, event: Any) -> None:
        # Dynamically refresh step accordion when a replan adds or alters steps
        steps_data = [
            {
                "step_id": s.step_id,
                "description": s.human_label or s.description,
                "state": s.state.value,
            }
            for s in task.plan.steps
        ]
        self.hud.set_steps(steps_data)
        self.hud.update_progress(task.task_id, f"Replanning: {event.reason}", task.progress_pct)

    def on_task_completed(self, task: Any) -> None:
        self.hud.show_success(task.task_id, f"Goal achieved: {task.goal.intent or 'Complete'}")

    def on_task_failed(self, task: Any, error: str) -> None:
        self.hud.show_error(task.task_id, error or "Task failed")

    def on_task_cancelled(self, task: Any) -> None:
        self.hud.show_error(task.task_id, "Task was cancelled by user.")


