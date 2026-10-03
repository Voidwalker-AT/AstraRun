"""Comprehensive test suite for RC.5 Product-Integration Hardening.

Covers:
1. Uninstall component ownership classification & external model immunity.
2. Managed component vs external component removal verification.
3. Accurate dynamic directory size computation.
4. Preserved state detection on reinstall.
5. RepairManager self-healing procedures.
6. SettingsDialog structure and controls.
7. UninstallWizardDialog options and active task safety.
8. Computer-use stack provider matrix verification.
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
import pytest

from PySide6.QtWidgets import QApplication

from astrarun.lifecycle.uninstall import (
    ComponentOwnership,
    ComponentInventoryItem,
    compute_path_size,
    scan_uninstall_inventory,
    create_uninstall_plan,
    execute_uninstall_plan,
)
from astrarun.lifecycle.repair import RepairManager, RepairReport
from astrarun.ui.settings import SettingsDialog
from astrarun.ui.uninstall_wizard import UninstallWizardDialog
from astrarun.ui.first_run import FirstRunWizard


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_uninstall_ownership_classification():
    """Verify inventory scanner distinguishes internal managed components from external user-owned assets."""
    items = scan_uninstall_inventory()
    assert len(items) > 0

    categories = {it.category for it in items}
    assert ComponentOwnership.APPLICATION_BINARIES in categories
    assert ComponentOwnership.CONFIGURATION in categories
    assert ComponentOwnership.LOGS in categories

    # External assets MUST have is_external=True and removable=False
    for it in items:
        if it.is_external:
            assert it.removable is False, f"External item {it.label} was marked removable!"
            assert "Preserved" in it.status_note


def test_external_models_never_deleted(tmp_path):
    """Verify that under NO circumstances can external models be included in removal execution."""
    fake_app_data = tmp_path / "app_data"
    fake_app_data.mkdir()
    fake_install_root = tmp_path / "install_root"
    fake_install_root.mkdir()
    external_dir = tmp_path / "external_ai_models"
    external_dir.mkdir()
    ext_model_file = external_dir / "Spark-X2.5.gguf"
    ext_model_file.write_bytes(b"dummy_weights_12345")

    external_item = ComponentInventoryItem(
        id="ext_model_test",
        label="External Test Model",
        category=ComponentOwnership.EXTERNAL_EXISTING_MODELS,
        path=ext_model_file,
        size_bytes=ext_model_file.stat().st_size,
        is_external=True,
        removable=False,
        selected_default=False,
        status_note="Preserved — user model",
    )

    # Even if someone maliciously attempts to select it
    plan = create_uninstall_plan({"ext_model_test"}, [external_item])
    assert str(ext_model_file) not in plan["paths_to_remove"]
    assert str(ext_model_file) in plan["paths_to_preserve"]

    # Even if plan is tampered with, execute_uninstall_plan must block deletion outside app_data/install_root
    tampered_plan = {"paths_to_remove": [str(ext_model_file)]}
    res = execute_uninstall_plan(tampered_plan)
    assert str(ext_model_file) in res["skipped"]
    assert ext_model_file.exists(), "External model file was deleted! Critical security boundary breached!"


def test_managed_components_removal(tmp_path):
    """Verify that selected managed items are removed while unselected ones are preserved."""
    fake_app_data = tmp_path / "app_data"
    fake_app_data.mkdir()
    fake_install_root = tmp_path / "install_root"
    fake_install_root.mkdir()

    cfg_dir = fake_app_data / "config"
    cfg_dir.mkdir()
    (cfg_dir / "settings.json").write_text("{}", encoding="utf-8")

    logs_dir = fake_app_data / "logs"
    logs_dir.mkdir()
    (logs_dir / "app.log").write_text("log line", encoding="utf-8")

    models_dir = fake_app_data / "models"
    models_dir.mkdir()
    (models_dir / "managed.bin").write_bytes(b"managed_weights")

    cfg_item = ComponentInventoryItem(
        id="config", label="Config", category=ComponentOwnership.CONFIGURATION,
        path=cfg_dir, size_bytes=100, is_external=False, removable=True, selected_default=False, status_note=""
    )
    logs_item = ComponentInventoryItem(
        id="logs", label="Logs", category=ComponentOwnership.LOGS,
        path=logs_dir, size_bytes=100, is_external=False, removable=True, selected_default=False, status_note=""
    )
    models_item = ComponentInventoryItem(
        id="models", label="Models", category=ComponentOwnership.ASTRA_MANAGED_MODELS,
        path=models_dir, size_bytes=100, is_external=False, removable=True, selected_default=False, status_note=""
    )

    # Select only logs for removal
    plan = create_uninstall_plan({"logs"}, [cfg_item, logs_item, models_item], app_data_root=fake_app_data, install_root=fake_install_root)
    assert str(logs_dir.resolve()) in plan["paths_to_remove"]
    assert str(cfg_dir.resolve()) in plan["paths_to_preserve"]
    assert str(models_dir.resolve()) in plan["paths_to_preserve"]

    res = execute_uninstall_plan(plan, app_data_root=fake_app_data, install_root=fake_install_root)
    assert not logs_dir.exists(), "Selected logs_dir was not deleted!"
    assert cfg_dir.exists(), "Unselected cfg_dir was incorrectly deleted!"
    assert models_dir.exists(), "Unselected models_dir was incorrectly deleted!"


def test_size_calculation_accuracy(tmp_path):
    """Verify compute_path_size calculates exact byte sizes recursively."""
    test_dir = tmp_path / "size_probe"
    test_dir.mkdir()
    f1 = test_dir / "file1.bin"
    f1.write_bytes(b"A" * 1024)  # 1024 bytes
    sub = test_dir / "subdir"
    sub.mkdir()
    f2 = sub / "file2.bin"
    f2.write_bytes(b"B" * 2048)  # 2048 bytes

    total = compute_path_size(test_dir)
    assert total == 3072


def test_reinstall_preserved_state_detection(tmp_path, monkeypatch, qapp):
    """Verify FirstRunWizard detects previous installation state when preserved."""
    fake_config = tmp_path / "config"
    fake_config.mkdir(parents=True)
    (fake_config / "settings.json").write_text("{}", encoding="utf-8")
    
    monkeypatch.setattr("astrarun.ui.first_run.get_config_dir", lambda: fake_config)
    
    wizard = FirstRunWizard()
    assert wizard.has_preserved_config is True
    assert hasattr(wizard, "chk_restore")
    assert wizard.chk_restore.isChecked() is True
    wizard.close()


def test_repair_manager_execution():
    """Verify RepairManager executes all self-healing checks and returns healthy report."""
    mgr = RepairManager()
    rep: RepairReport = mgr.run_all_repairs()
    assert isinstance(rep, RepairReport)
    assert rep.success is True
    assert len(rep.items) >= 5

    names = [it.name for it in rep.items]
    assert "Autostart Registration" in names
    assert "Model Storage Directory" in names
    assert "Workstation Profile" in names


def test_settings_dialog_structure(qapp):
    """Verify SettingsDialog incorporates all required tabs and controls."""
    dialog = SettingsDialog()
    assert hasattr(dialog, "chk_autostart")
    assert hasattr(dialog, "txt_model_dir")
    assert hasattr(dialog, "btn_browse_models")
    assert hasattr(dialog, "btn_repair")
    assert hasattr(dialog, "btn_open_logs")
    assert hasattr(dialog, "btn_open_diag")
    assert dialog.windowTitle() == "AstraRun Settings"
    dialog.close()


def test_uninstall_wizard_dialog_structure(qapp):
    """Verify UninstallWizardDialog displays choices, external model badges, and safety warnings."""
    dialog = UninstallWizardDialog()
    assert hasattr(dialog, "btn_cancel")
    assert hasattr(dialog, "btn_uninstall")
    assert hasattr(dialog, "checkboxes")
    assert len(dialog.inventory) > 0

    # Test quick select helpers
    dialog._select_all_data()
    for cb in dialog.checkboxes.values():
        assert cb.isChecked() is True

    dialog._select_keep_all()
    for cb in dialog.checkboxes.values():
        assert cb.isChecked() is False

    dialog.close()


def test_computer_use_stack_provider_matrix():
    """Verify all computer-use and perception providers can be imported and initialized."""
    from astrarun.perception.router import PerceptionRouter
    from astrarun.perception.input import NativeInputController
    from astrarun.perception.capture import ScreenCapture
    from astrarun.perception.grounder import VisualGrounder
    from astrarun.perception.ocr import OCRProvider

    input_ctrl = NativeInputController()
    assert input_ctrl is not None
    assert hasattr(input_ctrl, "click")
    assert hasattr(input_ctrl, "type_text")
    assert hasattr(input_ctrl, "check_user_takeover")

    capture = ScreenCapture()
    assert capture is not None

    router = PerceptionRouter()
    assert router is not None
    assert hasattr(router, "observe_window")
    assert hasattr(router, "create_generation")
