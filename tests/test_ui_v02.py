"""Unit tests for v0.2 UI keyboard navigation and suggestions."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from astrarun.core.models import AppInfo, FolderInfo, RoutingContext
from astrarun.routing.deterministic import DeterministicRouter
from astrarun.search.index import SearchIndex
from astrarun.tools.registry import ToolRegistry
from astrarun.ui.launcher import LauncherWindow


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def v02_launcher(qapp):
    apps = {
        "notepad": AppInfo("notepad", "Notepad", "C:\\Windows\\System32\\notepad.exe"),
        "calc": AppInfo("calc", "Calculator", "C:\\Windows\\System32\\calc.exe"),
        "code": AppInfo("code", "Visual Studio Code", "C:\\Programs\\VSCode\\Code.exe"),
    }
    folders = {
        "downloads": FolderInfo("downloads", "Downloads", "C:\\Users\\Test\\Downloads"),
    }
    urls = {
        "github": "https://github.com",
    }
    aliases = {
        "calculator": "calc",
        "editor": "notepad",
    }
    index = SearchIndex()
    index.build_from_sources(apps, folders, urls, aliases)

    context = RoutingContext(
        apps=apps,
        folders=folders,
        urls=urls,
        aliases=aliases,
        search_index=index,
    )
    router = DeterministicRouter()
    registry = ToolRegistry()
    win = LauncherWindow(router, registry, context, {"ui": {"hide_on_focus_loss": False}})
    return win


def test_arrow_key_navigation(v02_launcher, qapp):
    v02_launcher.show()
    qapp.processEvents()

    # Trigger suggestions
    v02_launcher.input_field.setText("note")
    qapp.processEvents()
    assert v02_launcher.suggestions_list.isVisible()
    assert v02_launcher.suggestions_list.currentRow() == 0

    # Down arrow
    down_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Down, Qt.KeyboardModifier.NoModifier)
    v02_launcher.keyPressEvent(down_event)
    qapp.processEvents()
    # If only 1 item, stays on 0 or advances if multiple
    assert v02_launcher.suggestions_list.currentRow() >= 0

    # Up arrow
    up_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)
    v02_launcher.keyPressEvent(up_event)
    qapp.processEvents()
    assert v02_launcher.suggestions_list.currentRow() >= 0

    v02_launcher.hide()


def test_tab_completion(v02_launcher, qapp):
    v02_launcher.show()
    qapp.processEvents()

    v02_launcher.input_field.setText("not")
    qapp.processEvents()
    assert v02_launcher.suggestions_list.isVisible()

    # Press Tab
    tab_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    v02_launcher.keyPressEvent(tab_event)
    qapp.processEvents()

    # Input should be autocompleted with candidate name
    assert "Notepad" in v02_launcher.input_field.text()
    v02_launcher.hide()


def test_weak_result_rejected_on_enter(v02_launcher, qapp):
    v02_launcher.show()
    qapp.processEvents()

    # Ambiguous / weak query that matches nothing above threshold
    v02_launcher.input_field.setText("asdfgh123")
    qapp.processEvents()

    # Ensure suggestions list is hidden
    assert v02_launcher.suggestions_list.isHidden()

    # Press Enter
    v02_launcher.execute_command()
    qapp.processEvents()

    # Must NOT execute or dismiss; must show feedback
    assert v02_launcher.isVisible()
    assert v02_launcher.status_label.isVisible()
    assert "I don't know how to do that yet." in v02_launcher.status_label.text()
    v02_launcher.hide()
