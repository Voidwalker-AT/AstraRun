"""Unit tests for MotionTokens and Live Task HUD V2."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from astrarun.agent.models import ProgressMode
from astrarun.ui.hud import FloatingTaskHUD, HUDState, TaskETAEstimator
from astrarun.ui.motion import MotionTokens


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class TestMotionTokens:
    """Tests for centralized motion tokens and reduced-motion compliance."""

    def test_default_durations(self):
        assert MotionTokens.ENTER_DURATION_MS == 200
        assert MotionTokens.EXIT_DURATION_MS == 150
        assert MotionTokens.EXPAND_DURATION_MS == 220
        assert MotionTokens.STEP_TRANSITION_MS == 120

    def test_reduced_motion_collapses_to_zero(self):
        assert MotionTokens.get_enter_duration(force_reduced=True) == 0
        assert MotionTokens.get_exit_duration(force_reduced=True) == 0
        assert MotionTokens.get_expand_duration(force_reduced=True) == 0
        assert MotionTokens.get_step_duration(force_reduced=True) == 0

    def test_reduced_motion_query_runs_safely(self):
        # Querying Windows accessibility setting must not throw
        res = MotionTokens.is_reduced_motion_enabled()
        assert isinstance(res, bool)


class TestTaskETAEstimator:
    """Tests for real measured ETA estimation."""

    def test_eta_calculation(self):
        estimator = TaskETAEstimator()
        estimator.completed_durations = [1.0, 1.2, 0.8]  # avg = 1.0s

        rem_s = estimator.estimate_remaining_s(completed_steps=3, total_steps=5)
        assert rem_s == 2.0  # 2 remaining * 1.0s = 2.0s
        assert estimator.format_eta(rem_s) == "~2.0s"

    def test_eta_zero_when_complete(self):
        estimator = TaskETAEstimator()
        estimator.completed_durations = [1.0]
        assert estimator.estimate_remaining_s(completed_steps=5, total_steps=5) == 0.0
        assert estimator.format_eta(0.0) == ""


class TestLiveTaskHUDV2:
    """Tests for FloatingTaskHUD V2 progress modes, step list, and cancellation."""

    def test_non_focus_stealing_flags(self, qapp):
        hud = FloatingTaskHUD(animations_enabled=False)
        flags = hud.windowFlags()
        assert flags & Qt.WindowType.FramelessWindowHint
        assert flags & Qt.WindowType.WindowStaysOnTopHint
        assert flags & Qt.WindowType.Tool
        assert flags & Qt.WindowType.WindowDoesNotAcceptFocus
        assert hud.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def test_progress_modes(self, qapp):
        hud = FloatingTaskHUD(animations_enabled=False)

        # INSTANT mode hides progress bar
        hud.set_progress_mode("INSTANT")
        assert hud.progress_bar.isHidden()

        # DETERMINATE mode sets range 0..100 and value
        hud.set_progress_mode("DETERMINATE", progress_pct=45.0)
        assert not hud.progress_bar.isHidden()
        assert hud.progress_bar.maximum() == 100
        assert hud.progress_bar.value() == 45

        # INDETERMINATE mode sets marquee range 0..0
        hud.set_progress_mode("INDETERMINATE")
        assert not hud.progress_bar.isHidden()
        assert hud.progress_bar.maximum() == 0

    def test_dynamic_step_list(self, qapp):
        hud = FloatingTaskHUD(animations_enabled=False)
        steps = [
            {"step_id": "step1", "description": "Download asset", "state": "PENDING"},
            {"step_id": "step2", "description": "Verify hash", "state": "PENDING"},
        ]
        hud.set_steps(steps)
        assert not hud.expand_btn.isHidden()
        assert len(hud._step_widgets) == 2

        # Update step state to RUNNING
        hud.update_step_state("step1", "RUNNING")
        assert hud._step_widgets["step1"]["glyph"].text() == "►"

        # Update step state to COMPLETED
        hud.update_step_state("step1", "COMPLETED")
        assert hud._step_widgets["step1"]["glyph"].text() == "✓"

        # Toggle expansion
        assert hud.steps_container.isHidden()
        hud.toggle_steps_expansion()
        assert not hud.steps_container.isHidden()
        assert hud.expand_btn.text() == "▴ Steps"

    def test_cancellation_signal(self, qapp):
        hud = FloatingTaskHUD(animations_enabled=False)
        cancelled_events = []
        hud.cancelled.connect(lambda: cancelled_events.append(True))

        hud.show_progress("task_123", "Long running task")
        assert hud.current_state == HUDState.PASSIVE_PROGRESS

        # Clicking close/cancel button during passive progress should emit cancelled
        hud._on_close_clicked()
        assert len(cancelled_events) == 1
        assert "cancelling" in hud.detail_label.text().lower()
