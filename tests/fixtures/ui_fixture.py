"""PySide6 reference UI fixture application exposing deterministic accessible controls."""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import os
import subprocess
import sys
import time
from typing import Generator, Optional, Tuple


def create_fixture_window():
    """Create and return the reference PySide6 window with standard accessible controls."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QPushButton,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )

    app = QApplication.instance() or QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("AstraRun UI Fixture Application")
    window.resize(600, 500)

    central = QWidget()
    main_layout = QVBoxLayout(central)

    status_lbl = QLabel("Status: Ready")
    status_lbl.setObjectName("lbl_status")
    status_lbl.setAccessibleName("Status Message")
    main_layout.addWidget(status_lbl)

    # 1. Action Buttons
    btn_layout = QHBoxLayout()

    btn_save = QPushButton("Save")
    btn_save.setObjectName("btn_save")
    btn_save.setAccessibleName("Save")
    btn_save.clicked.connect(lambda: status_lbl.setText("Status: Saved"))
    btn_layout.addWidget(btn_save)

    btn_cancel = QPushButton("Cancel")
    btn_cancel.setObjectName("btn_cancel")
    btn_cancel.setAccessibleName("Cancel")
    btn_cancel.clicked.connect(lambda: status_lbl.setText("Status: Cancelled"))
    btn_layout.addWidget(btn_cancel)

    btn_delete = QPushButton("Delete All")
    btn_delete.setObjectName("btn_delete_all")
    btn_delete.setAccessibleName("Delete All")
    btn_delete.clicked.connect(lambda: status_lbl.setText("Status: Deleted All"))
    btn_layout.addWidget(btn_delete)

    main_layout.addLayout(btn_layout)

    # 2. Input Fields
    form_layout = QFormLayout()

    edit_search = QLineEdit("initial query")
    edit_search.setObjectName("edit_search")
    edit_search.setAccessibleName("Search Query")
    form_layout.addRow("Search:", edit_search)

    edit_pwd = QLineEdit("secret_pass123")
    edit_pwd.setEchoMode(QLineEdit.EchoMode.Password)
    edit_pwd.setObjectName("edit_password")
    edit_pwd.setAccessibleName("Password")
    form_layout.addRow("Password:", edit_pwd)

    chk_feature = QCheckBox("Enable Feature")
    chk_feature.setObjectName("chk_feature")
    chk_feature.setAccessibleName("Enable Feature")
    chk_feature.stateChanged.connect(
        lambda s: status_lbl.setText(f"Status: Feature {'Enabled' if s else 'Disabled'}")
    )
    form_layout.addRow("Feature:", chk_feature)

    combo_choices = QComboBox()
    combo_choices.setObjectName("combo_choices")
    combo_choices.setAccessibleName("Choices Combo")
    combo_choices.addItems(["Option Alpha", "Option Beta", "Option Gamma"])
    form_layout.addRow("Choices:", combo_choices)

    main_layout.addLayout(form_layout)

    # 3. Tabs
    tabs = QTabWidget()
    tabs.setObjectName("tabs_main")
    tabs.setAccessibleName("Settings Tabs")

    tab_general = QWidget()
    tab_gen_layout = QVBoxLayout(tab_general)
    tab_gen_layout.addWidget(QLabel("General Tab Content"))
    tabs.addTab(tab_general, "General")

    tab_advanced = QWidget()
    tab_adv_layout = QVBoxLayout(tab_advanced)
    tab_adv_layout.addWidget(QLabel("Advanced Tab Content"))
    tabs.addTab(tab_advanced, "Advanced")

    tabs.currentChanged.connect(lambda idx: status_lbl.setText(f"Status: Tab {idx} Selected"))
    main_layout.addWidget(tabs)

    # 4. Multiline Document
    doc_edit = QTextEdit("Initial document line 1.\nSecond line of document.")
    doc_edit.setObjectName("edit_document")
    doc_edit.setAccessibleName("Notes Document")
    main_layout.addWidget(doc_edit)

    window.setCentralWidget(central)
    return app, window


@contextlib.contextmanager
def spawn_ui_fixture(timeout: float = 30.0) -> Generator[Tuple[int, int], None, None]:
    """
    Context manager to spawn the UI fixture application in an isolated subprocess.
    Yields (hwnd, pid). Automatically kills the process upon context exit.
    """
    fixture_script = os.path.abspath(__file__)
    proc = subprocess.Popen(
        [sys.executable, fixture_script, "--timeout", str(timeout)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    hwnd = 0
    t_start = time.perf_counter()

    if sys.platform == "win32":
        user32 = ctypes.windll.user32
        while (time.perf_counter() - t_start) < 10.0:
            hwnd = user32.FindWindowW(None, "AstraRun UI Fixture Application")
            if hwnd:
                break
            time.sleep(0.1)

    try:
        if not hwnd and sys.platform == "win32":
            raise RuntimeError(f"Timed out waiting for AstraRun UI Fixture Application window to appear.")
        yield hwnd or 12345, proc.pid
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def main():
    parser = argparse.ArgumentParser(description="AstraRun UI Fixture")
    parser.add_argument("--timeout", type=float, default=30.0, help="Auto-close timeout in seconds")
    args = parser.parse_args()

    app, window = create_fixture_window()
    window.show()

    from PySide6.QtCore import QTimer
    QTimer.singleShot(int(args.timeout * 1000), app.quit)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
