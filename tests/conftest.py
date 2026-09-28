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


@pytest.fixture(autouse=True)
def clean_astrarun_hwnds():
    """Ensure mock or test HWND registrations do not leak across tests."""
    from astrarun.windows.policy import _ASTRARUN_HWNDS
    initial = set(_ASTRARUN_HWNDS)
    yield
    _ASTRARUN_HWNDS.clear()
    _ASTRARUN_HWNDS.update(initial)
