"""Unit tests for the PySide6 LauncherWindow."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from astrarun.core.models import AppInfo, FolderInfo, RoutingContext
from astrarun.routing.deterministic import DeterministicRouter
from astrarun.tools.registry import ToolRegistry
from astrarun.ui.launcher import LauncherWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def launcher(qapp):
    apps = {
        "notepad": AppInfo("notepad", "Notepad", "C:\\Windows\\System32\\notepad.exe"),
        "calc": AppInfo("calc", "Calculator", "C:\\Windows\\System32\\calc.exe"),
    }
    folders = {
        "downloads": FolderInfo("downloads", "Downloads", "C:\\Users\\Test\\Downloads"),
    }
    urls = {
        "github": "https://github.com",
    }
    aliases = {
        "calculator": "calc",
    }
    context = RoutingContext(apps=apps, folders=folders, urls=urls, aliases=aliases)
    router = DeterministicRouter()
    registry = ToolRegistry()
    win = LauncherWindow(router, registry, context, {"ui": {"hide_on_focus_loss": False}})
    return win


def test_launcher_initial_state(launcher):
    assert launcher.input_field.text() == ""
    assert launcher.placeholder_text == "What do you want to do?"
    assert launcher.suggestions_list.isHidden()


def test_launcher_show_and_dismiss(launcher, qapp):
    launcher.show_and_activate()
    qapp.processEvents()
    assert launcher.isVisible()

    launcher.dismiss()
    qapp.processEvents()
    assert not launcher.isVisible()


def test_launcher_escape_key(launcher, qapp):
    launcher.show_and_activate()
    qapp.processEvents()
    assert launcher.isVisible()

    esc_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    launcher.keyPressEvent(esc_event)
    qapp.processEvents()
    assert not launcher.isVisible()


def test_launcher_suggestions(launcher, qapp):
    launcher.show()
    qapp.processEvents()

    launcher.input_field.setText("note")
    qapp.processEvents()
    assert not launcher.suggestions_list.isHidden()
    assert launcher.suggestions_list.count() > 0

    launcher.input_field.setText("")
    qapp.processEvents()
    assert launcher.suggestions_list.isHidden()
    launcher.hide()


def test_launcher_feedback_message(launcher, qapp):
    launcher.show()
    qapp.processEvents()

    launcher.show_feedback("Test Error Message", is_error=True)
    qapp.processEvents()
    assert not launcher.status_label.isHidden()
    assert launcher.status_label.text() == "Test Error Message"

    launcher._clear_status()
    qapp.processEvents()
    assert launcher.status_label.isHidden()
    launcher.hide()
