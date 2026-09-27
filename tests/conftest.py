"""Global pytest fixtures for AstraRun test suite."""

import sys
import pytest


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Ensure a global headless QApplication exists for any test creating PySide6 widgets."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(["pytest", "-platform", "offscreen"])
    yield app
