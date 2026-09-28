"""Decoupled Floating Task HUD and HUD Controller for AstraRun v0.10.1.

Provides a persistent, non-focus-stealing floating indicator on the top-right
of the active display, driven purely by real TaskEventBus events.
"""

from __future__ import annotations

import ctypes
import sys
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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.logging import get_logger
from astrarun.tasks.events import TaskEventBus
from astrarun.tasks.models import TaskEvent, TaskEventType
from astrarun.ui.positioning import compute_task_hud_position, get_screen_for_hwnd
from astrarun.windows.policy import register_astrarun_hwnd, unregister_astrarun_hwnd

logger = get_logger("astrarun.ui.hud")


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

    def __init__(self, parent: QWidget | None = None, animations_enabled: bool = True):
        super().__init__(parent)
        self.animations_enabled = animations_enabled
        self.current_state = HUDState.IDLE
        self.current_task_id: Optional[str] = None
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
        """Construct Catppuccin Mocha floating card interface."""
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(8, 8, 8, 8)
        self.root_layout.setSpacing(0)

        # Main Card Frame
        self.card = QFrame(self)
        self.card.setObjectName("hud_card")
        self.card.setStyleSheet("""
            QFrame#hud_card {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 10px;
            }
        """)

        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 6)
        self.card.setGraphicsEffect(shadow)

        self.card_layout = QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(14, 10, 14, 10)
        self.card_layout.setSpacing(6)

        # Header Row
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        # Status Indicator Glyph
        self.status_icon = QLabel("●", self.card)
        self.status_icon.setStyleSheet("color: #89b4fa; font-size: 14px; font-weight: bold;")
        header_row.addWidget(self.status_icon)

        # Task Title Label
        self.title_label = QLabel("Astra Task", self.card)
        self.title_label.setStyleSheet("""
            color: #cdd6f4;
            font-size: 13px;
            font-weight: 600;
            font-family: 'Segoe UI', system-ui, sans-serif;
        """)
        header_row.addWidget(self.title_label, stretch=1)

        # Dismiss / Close Button
        self.close_btn = QPushButton("✕", self.card)
        self.close_btn.setFixedSize(18, 18)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #6c7086;
                font-size: 11px;
                font-weight: bold;
                border-radius: 9px;
            }
            QPushButton:hover {
                background-color: #313244;
                color: #f38ba8;
            }
        """)
        self.close_btn.clicked.connect(self.dismiss)
        header_row.addWidget(self.close_btn)

        self.card_layout.addLayout(header_row)

        # Subtitle / Step Detail Label
        self.detail_label = QLabel("Processing...", self.card)
        self.detail_label.setWordWrap(True)
        self.detail_label.setStyleSheet("""
            color: #a6adc8;
            font-size: 12px;
            font-family: 'Segoe UI', system-ui, sans-serif;
        """)
        self.card_layout.addWidget(self.detail_label)

        # Interactive Container (for Confirmation / Disambiguation)
        self.action_container = QWidget(self.card)
        self.action_layout = QHBoxLayout(self.action_container)
        self.action_layout.setContentsMargins(0, 4, 0, 0)
        self.action_layout.setSpacing(8)
        self.action_container.hide()
        self.card_layout.addWidget(self.action_container)

        self.root_layout.addWidget(self.card)

    def _init_animations(self) -> None:
        """Setup slide and opacity animations."""
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)

        # Position Animation
        self.pos_anim = QPropertyAnimation(self, b"pos")
        self.pos_anim.setDuration(140)
        self.pos_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Opacity Animation
        self.opacity_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.opacity_anim.setDuration(140)
        self.opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

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
        self.move(start_pos)
        self.opacity_effect.setOpacity(0.0)
        self.show()

        self.pos_anim.setStartValue(start_pos)
        self.pos_anim.setEndValue(self._target_point)
        self.opacity_anim.setStartValue(0.0)
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

    def show_progress(
        self,
        task_id: str,
        title: str,
        message: str = "Processing...",
        target_screen: Any = None,
        origin_hwnd: int | None = None,
    ) -> None:
        """Transition to PASSIVE_PROGRESS state (never steals focus)."""
        self.dismiss_timer.stop()
        self._clear_actions()
        self.current_state = HUDState.PASSIVE_PROGRESS
        self.current_task_id = task_id

        self.status_icon.setText("✦")
        self.status_icon.setStyleSheet("color: #89b4fa; font-size: 15px; font-weight: bold;")
        self.title_label.setText(title or "Executing Task")
        self.detail_label.setText(message)

        if not self.isVisible():
            self.present_animated(target_screen=target_screen, origin_hwnd=origin_hwnd)

    def update_progress(self, task_id: str, message: str) -> None:
        """Update active progress message without activating or shifting focus."""
        if self.current_task_id == task_id or not self.current_task_id:
            self.detail_label.setText(message)

    def show_success(self, task_id: str, message: str = "Task completed successfully.") -> None:
        """Transition to SUCCESS state with automatic dismissal (2.5s)."""
        self._clear_actions()
        self.current_state = HUDState.SUCCESS
        self.current_task_id = task_id

        self.status_icon.setText("✓")
        self.status_icon.setStyleSheet("color: #a6e3a1; font-size: 15px; font-weight: bold;")
        self.title_label.setText("Completed")
        self.detail_label.setText(message)

        if not self.isVisible():
            self.present_animated()

        # Auto-dismiss after 2.5 seconds
        self.dismiss_timer.start(2500)

    def show_error(self, task_id: str, message: str = "Task failed.") -> None:
        """Transition to ERROR state with 5.0s dismissal."""
        self._clear_actions()
        self.current_state = HUDState.ERROR
        self.current_task_id = task_id

        self.status_icon.setText("✗")
        self.status_icon.setStyleSheet("color: #f38ba8; font-size: 15px; font-weight: bold;")
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
        self.current_state = HUDState.WAITING_CONFIRMATION
        self.current_task_id = task_id

        self.status_icon.setText("!")
        self.status_icon.setStyleSheet("color: #fab387; font-size: 16px; font-weight: bold;")
        self.title_label.setText("Confirmation Required")
        self.detail_label.setText(prompt or "Confirm action to proceed.")

        # Confirm Button
        btn_confirm = QPushButton("Confirm", self.action_container)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #a6e3a1;
                color: #11111b;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #94e2d5;
            }
        """)
        btn_confirm.clicked.connect(lambda: self._on_confirm_clicked(token, tool, arguments))
        self.action_layout.addWidget(btn_confirm)

        # Cancel Button
        btn_cancel = QPushButton("Cancel", self.action_container)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)
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
        self.current_state = HUDState.WAITING_CLARIFICATION
        self.current_task_id = task_id

        self.status_icon.setText("?")
        self.status_icon.setStyleSheet("color: #cba6f7; font-size: 15px; font-weight: bold;")
        self.title_label.setText("Clarification Needed")
        self.detail_label.setText(prompt or "Please select an option:")

        for cand in candidates[:3]:
            name = cand.get("title") or cand.get("name") or str(cand)
            btn = QPushButton(name, self.action_container)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #313244;
                    color: #89b4fa;
                    border: 1px solid #45475a;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #45475a;
                    color: #b4befe;
                }
            """)
            btn.clicked.connect(lambda _, c=cand: self.candidate_selected.emit(c))
            self.action_layout.addWidget(btn)

        self.action_container.show()
        if not self.isVisible():
            self.present_animated()

    def _clear_actions(self) -> None:
        """Clear dynamic interactive buttons."""
        while self.action_layout.count():
            item = self.action_layout.takeAt(0)
            widget = item.widget()
            if widget:
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
    ):
        super().__init__()
        self.hud = hud
        self.event_bus = event_bus
        self.app = app
        self._sub_id: Optional[int] = None

        # Cross-thread Qt signal connection
        self.event_received.connect(self._handle_event)

        # Wire up HUD interactive signals
        self.hud.confirmed.connect(self._on_hud_confirmed)
        self.hud.candidate_selected.connect(self._on_hud_candidate_selected)

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

    def _on_hud_confirmed(self, token: str, tool: str, arguments: dict) -> None:
        """Dispatch confirmed capability execution through composition root."""
        if not self.app:
            return
        valid, msg = self.app.action_gate.validate_token(token, tool, arguments)
        if not valid:
            self.hud.show_error(self.hud.current_task_id or "", f"Confirmation rejected: {msg}")
            return
        cap_res = self.app.capability_registry.execute(tool, arguments)
        if cap_res.success:
            self.hud.show_success(self.hud.current_task_id or "", cap_res.message)
        else:
            self.hud.show_error(self.hud.current_task_id or "", cap_res.message)

    def _on_hud_candidate_selected(self, candidate: dict) -> None:
        """Reroute candidate through application request pipeline."""
        if not self.app:
            return
        target = candidate.get("title") or candidate.get("name") or str(candidate)
        self.hud.show_progress(self.hud.current_task_id or "", f"Selected: {target}", "Executing...")
        self.app.handle_request(target)

    def stop(self) -> None:
        """Unsubscribe from event bus."""
        if self.event_bus and self._sub_id is not None:
            self.event_bus.unsubscribe(self._sub_id)
            self._sub_id = None
