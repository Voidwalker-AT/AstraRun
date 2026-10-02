"""Tests for Milestone 5P: Astra Visual System & UX Polish.

Verifies:
  - Unified theme tokens and color contrast (Near-black / Charcoal / Graphite)
  - Programmatic vector IconRenderer & AstraMark generation (no emoji / Unicode text glyphs)
  - Task Center section partitioning (Active, Waiting, Recent) and EmptyStateWidget
  - TaskCardWidget geometry invariants (min-height >= 76, no squished rows)
  - ActionGate confirmation card Danger variant
  - HUD visual states (vector icons, quiet progress bar, clean copy)
"""

import time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from astrarun.core.models import ToolRisk
from astrarun.tasks.events import TaskEventBus
from astrarun.tasks.ledger import TaskLedger
from astrarun.tasks.models import Task, TaskStatus
from astrarun.tasks.runtime import TaskRuntime
from astrarun.ui.cards import ConfirmationCard, DisambiguationCard
from astrarun.ui.hud import FloatingTaskHUD, HUDState
from astrarun.ui.icons import AstraMarkWidget, IconRenderer
from astrarun.ui.launcher import LauncherWindow
from astrarun.ui.task_center import EmptyStateWidget, SectionHeaderWidget, TaskCardWidget, TaskCenterWindow
from astrarun.ui.theme import (
    ACCENT,
    BG_APP,
    BORDER,
    DANGER,
    FONT_FAMILY,
    SUCCESS,
    SURFACE,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
    get_badge_style,
    get_button_style,
)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_theme_tokens():
    """Verify canonical color tokens conform to the technical dark design system."""
    assert BG_APP.lower() == "#0c0d10"
    assert SURFACE.lower() == "#141519"
    assert SURFACE_RAISED.lower() == "#1c1e24"
    assert ACCENT.lower() == "#5b8cf7"
    assert SUCCESS.lower() == "#38b26e"
    assert WARNING.lower() == "#d99b38"
    assert DANGER.lower() == "#d64545"

    # Contrast verification: text is light, canvas is dark
    bg_luma = QColor(BG_APP).lightness()
    text_luma = QColor(TEXT_PRIMARY).lightness()
    assert text_luma > 200
    assert bg_luma < 30

    # Button stylesheets
    p_style = get_button_style("primary")
    assert ACCENT in p_style
    d_style = get_button_style("danger")
    assert DANGER in d_style
    s_style = get_button_style("secondary")
    assert SURFACE_RAISED in s_style

    # Badge style
    badge_css = get_badge_style(ACCENT, SURFACE_RAISED)
    assert ACCENT in badge_css
    assert "border-radius: 4px" in badge_css


def test_vector_icon_renderer(qapp):
    """Verify IconRenderer produces crisp, valid, non-null vector pixmaps for all icons."""
    icon_names = [
        "spark",
        "check",
        "close",
        "running",
        "pause",
        "pending",
        "warning",
        "question",
        "chevron_down",
        "chevron_up",
        "folder",
        "external",
        "copy",
        "settings",
        "history",
        "error",
    ]

    for name in icon_names:
        for sz in (12, 16, 24, 32):
            pix = IconRenderer.get_pixmap(name, size=sz)
            assert not pix.isNull(), f"Icon {name} at size {sz} returned null pixmap"
            assert pix.width() == sz
            assert pix.height() == sz

            # Wrap in QIcon
            icon = IconRenderer.get_icon(name, size=sz)
            assert not icon.isNull()

    # Test AstraMarkWidget
    mark_widget = AstraMarkWidget(size=28, color=ACCENT)
    assert mark_widget.width() == 28
    assert mark_widget.height() == 28


def test_task_center_empty_state(qapp):
    """Verify TaskCenterWindow displays a dedicated EmptyStateWidget when no tasks exist."""
    bus = TaskEventBus()
    db_path = f"data/test_tc_empty_{int(time.time()*1000)}.db"
    ledger = TaskLedger(db_path)
    runtime = TaskRuntime(event_bus=bus, ledger=ledger)

    center = TaskCenterWindow(task_runtime=runtime)
    center.refresh_tasks()

    # Must contain EmptyStateWidget
    empty_widgets = center.findChildren(EmptyStateWidget)
    assert len(empty_widgets) == 1
    assert "No recent tasks" in empty_widgets[0].title_lbl.text()


def test_task_center_sections_and_card_geometry(qapp):
    """Verify TaskCenterWindow organizes cards into sections with proper minimum heights."""
    bus = TaskEventBus()
    db_path = f"data/test_tc_geom_{int(time.time()*1000)}.db"
    ledger = TaskLedger(db_path)
    runtime = TaskRuntime(event_bus=bus, ledger=ledger)

    t1 = runtime.create_and_enqueue_task("Task 1 - Active Running")
    t1.status = TaskStatus.RUNNING
    t2 = runtime.create_and_enqueue_task("Task 2 - Historical Finished")
    t2.status = TaskStatus.COMPLETED
    t3 = runtime.create_and_enqueue_task("Task 3 - Queued Waiting")
    t3.status = TaskStatus.QUEUED

    center = TaskCenterWindow(task_runtime=runtime)
    center.refresh_tasks()

    # Verify SectionHeaderWidgets exist
    headers = center.findChildren(SectionHeaderWidget)
    assert len(headers) >= 2

    # Verify TaskCardWidgets
    cards = center.findChildren(TaskCardWidget)
    assert len(cards) == 3

    for card in cards:
        # Invariant: minimum height >= 76px to prevent squished row collapse
        assert card.minimumHeight() >= 76
        assert card.objectName() == "task_card"
        assert card.status_icon is not None
        assert not card.status_icon.pixmap().isNull()


def test_actiongate_confirmation_card_danger_styling(qapp):
    """Verify ActionGate ConfirmationCard applies Danger button variant for destructive operations."""
    card = ConfirmationCard(
        token="token-xyz",
        tool="kill_process",
        arguments={"pid": 9999, "name": "rogue.exe"},
        title="Confirm Termination",
        description="Terminating rogue.exe (PID 9999)",
        risk=ToolRisk.HIGH,
    )

    # Invariant: high risk or kill tool must use danger styling
    assert DANGER in card.confirm_btn.styleSheet()
    assert "Terminate" in card.confirm_btn.text()
    assert card.warn_icon is not None
    assert not card.warn_icon.pixmap().isNull()


def test_floating_hud_visual_system(qapp):
    """Verify FloatingTaskHUD uses vector icons and clean copy without emoji artifacts."""
    hud = FloatingTaskHUD(animations_enabled=False)

    # 1. Progress State
    hud.show_progress("t1", "Open Calculator", "Launching application...")
    assert hud.title_label.text() == "Open Calculator"
    assert not hud.status_icon.pixmap().isNull()
    assert hud.progress_bar.height() <= 4

    # 2. User Takeover State: NO ✦ emoji in message
    hud.show_user_takeover("t1", "✦ Paused — you're using the computer")
    assert "✦" not in hud.detail_label.text()
    assert "Paused — you're using the computer" in hud.detail_label.text()
    assert not hud.status_icon.pixmap().isNull()

    # 3. Success State
    hud.show_success("t1", "File saved at data/output.html (120 KB)")
    assert hud.title_label.text() == "Completed"
    assert not hud.status_icon.pixmap().isNull()

    # 4. Error State
    hud.show_error("t1", "Process failed with exit code 1")
    assert hud.title_label.text() == "Failed"
    assert not hud.status_icon.pixmap().isNull()
