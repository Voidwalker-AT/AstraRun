"""Astra-styled Hotkey Conflict Resolution Dialog.

Surfaces when the preferred global hotkey (e.g. Alt+Space) cannot be registered
due to an existing ownership conflict with another application.
"""

from __future__ import annotations

import sys
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.logging import get_logger
from astrarun.hotkeys.manager import HotkeyManager, format_shortcut_name
from astrarun.ui.icons import AstraMarkWidget
from astrarun.ui.theme import (
    ACCENT,
    BG_APP,
    BORDER,
    BORDER_STRONG,
    BORDER_SUBTLE,
    DANGER,
    FONT_FAMILY,
    FONT_MONO,
    FONT_SIZE_BODY,
    FONT_SIZE_TITLE,
    SUCCESS,
    SURFACE,
    SURFACE_HOVER,
    SURFACE_INPUT,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
    get_button_style,
)

logger = get_logger("astrarun.ui.hotkey_conflict")

PRESET_OPTIONS = [
    (["Ctrl"], "Space", "Ctrl + Space (Recommended alternative)"),
    (["Alt"], "F12", "Alt + F12 (Function key shortcut)"),
    (["Alt"], "\\", "Alt + \\ (Compact single-hand key)"),
]


class HotkeyConflictDialog(QDialog):
    """Clean Astra-styled conflict dialog allowing instant live rebind, retry, or settings access."""

    rebound_applied = Signal(list, str)  # Emits (modifiers, key)
    open_settings_requested = Signal()

    def __init__(
        self,
        hotkey_manager: HotkeyManager,
        failed_shortcut: str = "Alt+Space",
        parent: Optional[QWidget] = None,
        on_settings_callback: Optional[Callable[[], None]] = None,
    ):
        super().__init__(parent)
        self.hotkey_manager = hotkey_manager
        self.failed_shortcut = failed_shortcut
        self.on_settings_callback = on_settings_callback

        self.selected_modifiers = ["Ctrl"]
        self.selected_key = "Space"

        self.setWindowTitle("AstraRun — Shortcut Conflict")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(520, 420)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_APP};
                border: 1px solid {BORDER_STRONG};
                border-radius: 8px;
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY};
            }}
            QRadioButton {{
                color: {TEXT_PRIMARY};
                font-size: 12px;
                spacing: 8px;
            }}
            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 1px solid {BORDER_STRONG};
                background-color: {SURFACE_INPUT};
            }}
            QRadioButton::indicator:checked {{
                background-color: {ACCENT};
                border: 1px solid {ACCENT};
            }}
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(16)

        # Header with Astra Mark
        header = QHBoxLayout()
        header.setSpacing(12)
        mark = AstraMarkWidget(size=28, parent=self)
        header.addWidget(mark)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t_label = QLabel("Global Shortcut Conflict", self)
        t_label.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {TEXT_PRIMARY};")
        sub_label = QLabel("AstraRun Background Resident Shell", self)
        sub_label.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        title_col.addWidget(t_label)
        title_col.addWidget(sub_label)
        header.addLayout(title_col, stretch=1)
        layout.addLayout(header)

        # Conflict Banner
        banner = QFrame(self)
        banner.setStyleSheet(f"""
            QFrame {{
                background-color: {SURFACE_RAISED};
                border: 1px solid {BORDER};
                border-left: 3px solid {WARNING};
                border-radius: 6px;
                padding: 10px;
            }}
        """)
        b_layout = QVBoxLayout(banner)
        b_layout.setSpacing(4)

        b_title = QLabel(f"Astra couldn't use {self.failed_shortcut} because another application is using it.", banner)
        b_title.setWordWrap(True)
        b_title.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {TEXT_PRIMARY};")
        b_layout.addWidget(b_title)

        b_desc = QLabel(
            "Another running program (such as PowerToys Run or Windows system commands) is already using this key combination.",
            banner
        )
        b_desc.setWordWrap(True)
        b_desc.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        b_layout.addWidget(b_desc)
        layout.addWidget(banner)

        # Section: Choose Alternative Shortcut
        choose_lbl = QLabel("Choose an alternative shortcut for summoning Astra:", self)
        choose_lbl.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {TEXT_SECONDARY};")
        layout.addWidget(choose_lbl)

        # Presets container
        options_box = QFrame(self)
        options_box.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 6px;")
        opts_layout = QVBoxLayout(options_box)
        opts_layout.setSpacing(8)

        self.btn_group = QButtonGroup(self)
        self.radio_buttons: list[QRadioButton] = []

        for idx, (mods, key, label) in enumerate(PRESET_OPTIONS):
            rb = QRadioButton(label, options_box)
            if idx == 0:
                rb.setChecked(True)
                self.selected_modifiers = list(mods)
                self.selected_key = key
            rb.toggled.connect(lambda checked, m=mods, k=key: self._on_preset_toggled(checked, m, k))
            self.btn_group.addButton(rb, idx)
            opts_layout.addWidget(rb)
            self.radio_buttons.append(rb)

        layout.addWidget(options_box)

        # Test Status Label
        self.lbl_status = QLabel("", self)
        self.lbl_status.setStyleSheet(f"font-size: 11px; font-family: {FONT_FAMILY}; color: {SUCCESS};")
        self.lbl_status.hide()
        layout.addWidget(self.lbl_status)

        layout.addStretch(1)

        # Action Buttons
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(8)

        self.btn_settings = QPushButton("Open Settings", self)
        self.btn_settings.setStyleSheet(get_button_style("secondary", size="md"))
        self.btn_settings.clicked.connect(self._on_settings_clicked)
        actions_layout.addWidget(self.btn_settings)

        self.btn_retry = QPushButton(f"Retry {self.failed_shortcut}", self)
        self.btn_retry.setStyleSheet(get_button_style("secondary", size="md"))
        self.btn_retry.clicked.connect(self._on_retry_clicked)
        actions_layout.addWidget(self.btn_retry)

        actions_layout.addStretch(1)

        self.btn_dismiss = QPushButton("Dismiss", self)
        self.btn_dismiss.setStyleSheet(get_button_style("secondary", size="md"))
        self.btn_dismiss.clicked.connect(self.reject)
        actions_layout.addWidget(self.btn_dismiss)

        self.btn_apply = QPushButton("Apply Shortcut", self)
        self.btn_apply.setStyleSheet(get_button_style("primary", size="md"))
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        actions_layout.addWidget(self.btn_apply)

        layout.addLayout(actions_layout)

    def _on_preset_toggled(self, checked: bool, mods: list[str], key: str) -> None:
        if checked:
            self.selected_modifiers = list(mods)
            self.selected_key = key
            avail, code, desc = self.hotkey_manager.test_registration(mods, key)
            if avail:
                self.lbl_status.setText(f"✓ {format_shortcut_name(mods, key)} is available on this system.")
                self.lbl_status.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")
            else:
                self.lbl_status.setText(f"✗ {format_shortcut_name(mods, key)} is unavailable ({desc}).")
                self.lbl_status.setStyleSheet(f"color: {DANGER}; font-size: 11px;")
            self.lbl_status.show()

    def _on_apply_clicked(self) -> None:
        success, code, err = self.hotkey_manager.rebind(self.selected_modifiers, self.selected_key)
        if success:
            logger.info("Conflict resolved: rebound hotkey to %s", self.hotkey_manager.shortcut_name)
            self.rebound_applied.emit(self.selected_modifiers, self.selected_key)
            self.accept()
        else:
            self.lbl_status.setText(f"✗ Failed to bind {format_shortcut_name(self.selected_modifiers, self.selected_key)}: {err}")
            self.lbl_status.setStyleSheet(f"color: {DANGER}; font-size: 11px;")
            self.lbl_status.show()

    def _on_retry_clicked(self) -> None:
        # Re-parse failed shortcut
        parts = self.failed_shortcut.split("+")
        mods = parts[:-1] or ["Alt"]
        key = parts[-1] or "Space"
        success, code, err = self.hotkey_manager.rebind(mods, key)
        if success:
            logger.info("Conflict resolved: successfully registered %s", self.failed_shortcut)
            self.rebound_applied.emit(mods, key)
            self.accept()
        else:
            self.lbl_status.setText(f"✗ {self.failed_shortcut} is still in use by another application.")
            self.lbl_status.setStyleSheet(f"color: {DANGER}; font-size: 11px;")
            self.lbl_status.show()

    def _on_settings_clicked(self) -> None:
        self.accept()
        if self.on_settings_callback:
            self.on_settings_callback()
        self.open_settings_requested.emit()
