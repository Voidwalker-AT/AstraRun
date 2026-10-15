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


@pytest.fixture(autouse=True)
def clean_session_store():
    """Ensure conversation sessions do not leak across tests."""
    from astrarun.session.store import SessionStore
    store = SessionStore.get_instance()
    store.clear()
    yield
    store.clear()


@pytest.fixture(autouse=True)
def clean_drift_detector():
    """Ensure simulated faults and user takeover overrides do not leak across tests."""
    yield
    try:
        from astrarun.agent.coordinator import AgentCoordinator
        coord = AgentCoordinator.get_instance()
        if hasattr(coord, "drift_detector"):
            coord.drift_detector.inject_fault(None)
            coord.drift_detector.simulate_user_takeover(False)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def cleanup_test_spawned_processes():
    """Ensure tests never leak external processes (notepad, calc, etc.) to the host OS."""
    import psutil
    target_names = {"notepad.exe", "calc.exe", "calculatorapp.exe", "calculator.exe"}
    
    def get_target_pids():
        pids = set()
        for p in psutil.process_iter(["pid", "name"]):
            try:
                if p.info["name"] and p.info["name"].lower() in target_names:
                    pids.add(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return pids

    initial_pids = get_target_pids()
    yield
    final_pids = get_target_pids()
    leaked_pids = final_pids - initial_pids

    for pid in leaked_pids:
        try:
            proc = psutil.Process(pid)
            for child in proc.children(recursive=True):
                try:
                    child.kill()
                except Exception:
                    pass
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


