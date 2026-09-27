"""Settings modal dialog for configuring AstraRun workstation behavior."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.ui.settings")


def is_windows_startup_enabled() -> bool:
    """Check if AstraRun is configured to run at Windows login."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        val, _ = winreg.QueryValueEx(key, "AstraRun")
        winreg.CloseKey(key)
        return bool(val)
    except (FileNotFoundError, OSError):
        return False


def set_windows_startup_enabled(enabled: bool) -> bool:
    """Enable or disable AstraRun launch at Windows user login."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        if enabled:
            # Build target command pointing to start-astrarun.ps1 or main.py
            launch_script = Path(__file__).resolve().parent.parent.parent.parent / "start-astrarun.ps1"
            cmd_val = f'pwsh.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File "{launch_script}"'
            winreg.SetValueEx(key, "AstraRun", 0, winreg.REG_SZ, cmd_val)
            logger.info("Enabled AstraRun Windows startup in HKCU\\...\\Run")
        else:
            try:
                winreg.DeleteValue(key, "AstraRun")
                logger.info("Disabled AstraRun Windows startup in HKCU\\...\\Run")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as err:
        logger.error("Failed to update Windows startup registry key: %s", err)
        return False


class SettingsDialog(QDialog):
    """User-facing settings panel for AstraRun preferences."""

    def __init__(self, app_instance: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.app = app_instance
        self.setWindowTitle("AstraRun Settings")
        self.setFixedSize(500, 380)
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QLabel {
                color: #cdd6f4;
            }
            QCheckBox {
                color: #cdd6f4;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #45475a;
                background-color: #181825;
            }
            QCheckBox::indicator:checked {
                background-color: #89b4fa;
                border: 1px solid #89b4fa;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header
        title = QLabel("AstraRun Preferences", self)
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(title)

        # Options Card
        card = QFrame(self)
        card.setStyleSheet("""
            QFrame {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 8px;
            }
        """)
        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(16, 16, 16, 16)
        c_layout.setSpacing(14)

        # Startup checkbox
        self.startup_cb = QCheckBox("Start AstraRun automatically with Windows", card)
        self.startup_cb.setChecked(is_windows_startup_enabled())
        c_layout.addWidget(self.startup_cb)

        # Learning toggle
        self.learning_cb = QCheckBox("Enable semantic memory and alias learning", card)
        learning_enabled = self.app.settings.get("learning", {}).get("enabled", True)
        self.learning_cb.setChecked(learning_enabled)
        c_layout.addWidget(self.learning_cb)

        # Training export toggle
        self.export_cb = QCheckBox("Allow offline sanitized dataset export (gated behind explicit opt-in)", card)
        export_allowed = self.app.settings.get("learning", {}).get("allow_training_dataset_export", False)
        self.export_cb.setChecked(export_allowed)
        c_layout.addWidget(self.export_cb)

        # Hotkey notice
        hotkey_lbl = QLabel("Global Summon Hotkey: Alt+Space", card)
        hotkey_lbl.setStyleSheet("color: #a6adc8; font-size: 12px; margin-top: 4px;")
        c_layout.addWidget(hotkey_lbl)

        layout.addWidget(card)
        layout.addStretch(1)

        # Actions Row
        btn_box = QHBoxLayout()
        btn_box.addStretch(1)

        cancel_btn = QPushButton("Cancel", self)
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings", self)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa;
                color: #11111b;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b4befe;
            }
        """)
        save_btn.clicked.connect(self._on_save)
        btn_box.addWidget(save_btn)

        layout.addLayout(btn_box)

    def _on_save(self) -> None:
        """Apply preferences to runtime and Windows registry."""
        want_startup = self.startup_cb.isChecked()
        if want_startup != is_windows_startup_enabled():
            set_windows_startup_enabled(want_startup)

        # Update in-memory settings
        self.app.settings.setdefault("learning", {})["enabled"] = self.learning_cb.isChecked()
        self.app.settings["learning"]["allow_training_dataset_export"] = self.export_cb.isChecked()

        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)
