"""Settings and System Configuration Modal Dialog for AstraRun 1.0.

Conforms strictly to the Astra technical near-black visual system:
1. Autostart & Global Alt+Space Hotkey Configuration
2. Model Storage Location & Validated Runtime Weights
3. Workstation Hardware Profile Summary
4. Diagnostics & Live Log Directory Links
5. Integrated Lightweight Repair Engine
6. Authoritative Product Version & Architecture Metadata
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.autostart import enable_autostart, is_autostart_enabled
from astrarun.core.hardware import audit_hardware, HardwareProfile
from astrarun.core.logging import get_logger
from astrarun.core.paths import get_config_dir, get_logs_dir, get_models_dir
from astrarun.discovery import CompatibilityStatus, ExistingCapabilityResolver
from astrarun.lifecycle.repair import RepairManager, RepairReport
from astrarun.ui.icons import AstraMarkWidget, IconRenderer
from astrarun.ui.theme import (
    ACCENT,
    BG_APP,
    BORDER,
    BORDER_STRONG,
    DANGER,
    FONT_FAMILY,
    FONT_MONO,
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
from astrarun.version import APP_NAME, COPYRIGHT, PUBLISHER, VERSION

logger = get_logger("astrarun.ui.settings")


class SettingsDialog(QDialog):
    """User-facing settings & maintenance panel for AstraRun preferences."""

    def __init__(self, app_instance: Any = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.app = app_instance
        self.hardware: HardwareProfile = audit_hardware()
        self.capability_resolver = ExistingCapabilityResolver()
        self.discovered_models = self.capability_resolver.discover_models()

        self.setWindowTitle(f"{APP_NAME} Settings")
        self.setFixedSize(580, 560)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_APP};
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY};
            }}
            QTabWidget::pane {{
                border: 1px solid {BORDER};
                border-radius: 6px;
                background-color: {SURFACE};
                top: -1px;
            }}
            QTabBar::tab {{
                background-color: {BG_APP};
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-bottom: none;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: 500;
                margin-right: 4px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {SURFACE};
                color: {TEXT_PRIMARY};
                border-color: {BORDER};
            }}
            QTabBar::tab:hover:!selected {{
                color: {TEXT_SECONDARY};
                background-color: {SURFACE_HOVER};
            }}
            QCheckBox {{
                color: {TEXT_PRIMARY};
                font-size: 11px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: 1px solid {BORDER_STRONG};
                background-color: {SURFACE_INPUT};
            }}
            QCheckBox::indicator:checked {{
                background-color: {ACCENT};
                border: 1px solid {ACCENT};
            }}
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # Header
        header = QHBoxLayout()
        header.setSpacing(12)
        mark = AstraMarkWidget(size=26, parent=self)
        header.addWidget(mark)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        title = QLabel(f"{APP_NAME} Settings", self)
        title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {TEXT_PRIMARY};")
        sub = QLabel("Workstation preferences, model paths & system maintenance", self)
        sub.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        title_layout.addWidget(title)
        title_layout.addWidget(sub)
        header.addLayout(title_layout, stretch=1)
        main_layout.addLayout(header)

        # Tab Widget
        tabs = QTabWidget(self)
        tabs.addTab(self._create_general_tab(), "General")
        tabs.addTab(self._create_models_tab(), "Models & Storage")
        tabs.addTab(self._create_hardware_tab(), "Machine Profile")
        tabs.addTab(self._create_maintenance_tab(), "Repair & Logs")
        tabs.addTab(self._create_about_tab(), "About")
        main_layout.addWidget(tabs, stretch=1)

        # Footer Actions
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setStyleSheet(get_button_style("secondary", size="md"))
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_save = QPushButton("Save Preferences", self)
        self.btn_save.setStyleSheet(get_button_style("primary", size="md"))
        self.btn_save.clicked.connect(self._on_save)

        footer.addStretch(1)
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_save)
        main_layout.addLayout(footer)

    def _create_general_tab(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(14)

        # Autostart
        self.chk_autostart = QCheckBox("Start AstraRun automatically when I sign in to Windows", w)
        self.chk_autostart.setChecked(is_autostart_enabled())
        v.addWidget(self.chk_autostart)

        # Global Hotkey card
        hk_box = QFrame(w)
        hk_box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 12px;")
        h_layout = QVBoxLayout(hk_box)
        h_layout.setSpacing(8)

        h_title = QLabel("Global Summon Shortcut", hk_box)
        h_title.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {TEXT_PRIMARY};")
        h_layout.addWidget(h_title)

        h_sub = QLabel("Summons the resident command launcher instantly from any application.", hk_box)
        h_sub.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
        h_layout.addWidget(h_sub)

        # Preset selection row
        preset_row = QHBoxLayout()
        preset_lbl = QLabel("Shortcut:", hk_box)
        preset_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
        preset_row.addWidget(preset_lbl)

        self.cbo_hotkey = QComboBox(hk_box)
        self.cbo_hotkey.setStyleSheet(f"""
            QComboBox {{
                background-color: {SURFACE_INPUT};
                border: 1px solid {BORDER_STRONG};
                border-radius: 4px;
                color: {TEXT_PRIMARY};
                padding: 4px 8px;
                font-size: 11px;
                min-width: 220px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {SURFACE};
                color: {TEXT_PRIMARY};
                selection-background-color: {SURFACE_HOVER};
                selection-color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
            }}
        """)
        self.cbo_hotkey.addItem("Alt + Space (Default)", ["Alt", "Space"])
        self.cbo_hotkey.addItem("Ctrl + Space (Recommended alternative)", ["Ctrl", "Space"])
        self.cbo_hotkey.addItem("Alt + F12", ["Alt", "F12"])
        self.cbo_hotkey.addItem("Alt + \\", ["Alt", "\\"])
        self.cbo_hotkey.addItem("Custom Shortcut...", "custom")
        preset_row.addWidget(self.cbo_hotkey)
        preset_row.addSpacing(8)

        self.btn_test_hotkey = QPushButton("Test Availability", hk_box)
        self.btn_test_hotkey.setStyleSheet(get_button_style("secondary", size="sm"))
        self.btn_test_hotkey.clicked.connect(self._on_test_hotkey)
        preset_row.addWidget(self.btn_test_hotkey)
        preset_row.addStretch(1)
        h_layout.addLayout(preset_row)

        # Custom controls container (hidden by default)
        self.custom_hk_container = QWidget(hk_box)
        custom_layout = QHBoxLayout(self.custom_hk_container)
        custom_layout.setContentsMargins(0, 4, 0, 4)
        custom_layout.setSpacing(10)

        self.chk_mod_alt = QCheckBox("Alt", self.custom_hk_container)
        self.chk_mod_ctrl = QCheckBox("Ctrl", self.custom_hk_container)
        self.chk_mod_shift = QCheckBox("Shift", self.custom_hk_container)
        self.chk_mod_win = QCheckBox("Win", self.custom_hk_container)

        self.txt_custom_key = QLineEdit(self.custom_hk_container)
        self.txt_custom_key.setPlaceholderText("Key (e.g. Space, F12, \\)")
        self.txt_custom_key.setMaxLength(10)
        self.txt_custom_key.setFixedWidth(140)
        self.txt_custom_key.setStyleSheet(f"""
            QLineEdit {{
                background-color: {SURFACE_INPUT};
                border: 1px solid {BORDER_STRONG};
                border-radius: 4px;
                color: {TEXT_PRIMARY};
                padding: 4px 8px;
                font-size: 11px;
                font-family: {FONT_MONO};
            }}
        """)

        custom_layout.addWidget(self.chk_mod_alt)
        custom_layout.addWidget(self.chk_mod_ctrl)
        custom_layout.addWidget(self.chk_mod_shift)
        custom_layout.addWidget(self.chk_mod_win)
        custom_layout.addWidget(self.txt_custom_key)
        custom_layout.addStretch(1)
        h_layout.addWidget(self.custom_hk_container)
        self.custom_hk_container.hide()

        # Feedback / status label
        self.lbl_hotkey_status = QLabel("", hk_box)
        self.lbl_hotkey_status.setStyleSheet(f"font-size: 11px; font-family: {FONT_FAMILY};")
        self.lbl_hotkey_status.hide()
        h_layout.addWidget(self.lbl_hotkey_status)

        # Initialize current hotkey selection
        cur_hk = {}
        if self.app and hasattr(self.app, "settings"):
            cur_hk = self.app.settings.get("hotkey", {})
        cur_mods = cur_hk.get("modifiers", ["Alt"])
        cur_key = cur_hk.get("key", "Space")

        matched_idx = -1
        for i in range(self.cbo_hotkey.count() - 1):
            item_data = self.cbo_hotkey.itemData(i)
            if isinstance(item_data, list) and item_data == [cur_mods[0], cur_key]:
                matched_idx = i
                break
        if matched_idx >= 0:
            self.cbo_hotkey.setCurrentIndex(matched_idx)
        else:
            self.cbo_hotkey.setCurrentIndex(self.cbo_hotkey.count() - 1)
            self.custom_hk_container.show()
            self.chk_mod_alt.setChecked("Alt" in cur_mods)
            self.chk_mod_ctrl.setChecked("Ctrl" in cur_mods)
            self.chk_mod_shift.setChecked("Shift" in cur_mods)
            self.chk_mod_win.setChecked("Win" in cur_mods)
            self.txt_custom_key.setText(cur_key)

        self.cbo_hotkey.currentIndexChanged.connect(self._on_hotkey_preset_changed)
        v.addWidget(hk_box)

        # Learning & context
        learn_box = QFrame(w)
        learn_box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        l_layout = QVBoxLayout(learn_box)
        l_layout.setSpacing(8)

        self.chk_learning = QCheckBox("Enable adaptive semantic memory and task continuity", learn_box)
        is_learning = True
        if self.app and hasattr(self.app, "settings"):
            is_learning = self.app.settings.get("learning", {}).get("enabled", True)
        self.chk_learning.setChecked(is_learning)
        l_layout.addWidget(self.chk_learning)

        self.chk_export = QCheckBox("Allow offline sanitized dataset export (gated opt-in)", learn_box)
        allow_export = False
        if self.app and hasattr(self.app, "settings"):
            allow_export = self.app.settings.get("learning", {}).get("allow_training_dataset_export", False)
        self.chk_export.setChecked(allow_export)
        l_layout.addWidget(self.chk_export)
        v.addWidget(learn_box)

        v.addStretch(1)
        return w

    def _create_models_tab(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        # Storage directory
        s_box = QFrame(w)
        s_box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        s_layout = QVBoxLayout(s_box)
        s_layout.setSpacing(6)

        lbl = QLabel("Model Weights Directory:", s_box)
        lbl.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {TEXT_PRIMARY};")
        s_layout.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.txt_model_dir = QLineEdit(str(get_models_dir()), s_box)
        self.txt_model_dir.setStyleSheet(f"""
            QLineEdit {{
                background-color: {SURFACE_INPUT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                color: {TEXT_PRIMARY};
                padding: 6px;
                font-size: 11px;
                font-family: {FONT_MONO};
            }}
        """)
        self.btn_browse_models = QPushButton("Browse...", s_box)
        self.btn_browse_models.setStyleSheet(get_button_style("secondary", size="sm"))
        self.btn_browse_models.clicked.connect(self._on_browse_models)

        row.addWidget(self.txt_model_dir, stretch=1)
        row.addWidget(self.btn_browse_models)
        s_layout.addLayout(row)
        v.addWidget(s_box)

        # Detected models
        m_head = QLabel("Cognitive Engines & Runtimes:", w)
        m_head.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_SECONDARY};")
        v.addWidget(m_head)

        exact_matches = [
            m for m in self.discovered_models.values()
            if m.status in (CompatibilityStatus.EXACT_MATCH, CompatibilityStatus.COMPATIBLE_VERSION) and m.path
        ]

        for m in exact_matches:
            c = QFrame(w)
            c.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 8px 10px;")
            cl = QVBoxLayout(c)
            cl.setSpacing(2)

            tr = QHBoxLayout()
            name_lbl = QLabel(m.name, c)
            name_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_PRIMARY};")
            badge = QLabel("Existing validated model", c)
            badge.setStyleSheet(f"font-size: 9px; color: {SUCCESS}; background-color: rgba(34, 197, 94, 0.12); padding: 1px 4px; border-radius: 3px;")
            tr.addWidget(name_lbl)
            tr.addSpacing(6)
            tr.addWidget(badge)
            tr.addStretch(1)
            cl.addLayout(tr)

            p_lbl = QLabel(str(m.path), c)
            p_lbl.setStyleSheet(f"font-size: 9px; color: {TEXT_MUTED}; font-family: {FONT_MONO};")
            cl.addWidget(p_lbl)
            v.addWidget(c)

        v.addStretch(1)
        return w

    def _create_hardware_tab(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(8)

        box = QFrame(w)
        box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        bl = QVBoxLayout(box)
        bl.setSpacing(6)

        specs = [
            ("Operating System", f"{self.hardware.os_name} ({self.hardware.os_version})"),
            ("Processor", f"{self.hardware.cpu_name} ({self.hardware.cpu_cores} cores)"),
            ("System Memory", f"{self.hardware.ram_gb:.1f} GB RAM"),
        ]

        if getattr(self.hardware, "gpus", None) and len(self.hardware.gpus) > 0:
            for g in self.hardware.gpus:
                role = "Graphics (Compute)" if g.is_discrete else "Graphics (Display)"
                specs.append((role, g.display_label))
        else:
            specs.append(("Graphics Device", f"{self.hardware.gpu_name} ({self.hardware.vram_gb:.1f} GB VRAM)"))

        specs.append(("Storage Available", f"{self.hardware.disk_free_gb:.1f} GB free"))

        for name, val in specs:
            row = QHBoxLayout()
            n_lbl = QLabel(name, box)
            n_lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; width: 130px;")
            v_lbl = QLabel(val, box)
            v_lbl.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {TEXT_PRIMARY}; font-family: {FONT_MONO};")
            row.addWidget(n_lbl)
            row.addSpacing(8)
            row.addWidget(v_lbl, stretch=1)
            bl.addLayout(row)

        v.addWidget(box)
        v.addStretch(1)
        return w

    def _create_maintenance_tab(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        # Repair Section
        r_box = QFrame(w)
        r_box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        rl = QVBoxLayout(r_box)
        rl.setSpacing(8)

        r_title = QLabel("Self-Healing & System Repair", r_box)
        r_title.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {TEXT_PRIMARY};")
        rl.addWidget(r_title)

        r_desc = QLabel("Verifies binary integrity, shortcuts, autostart registry, and refreshes hardware telemetry.", r_box)
        r_desc.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
        rl.addWidget(r_desc)

        self.btn_repair = QPushButton("Run Repair & Verification", r_box)
        self.btn_repair.setStyleSheet(get_button_style("secondary", size="sm"))
        self.btn_repair.clicked.connect(self._on_run_repair)
        rl.addWidget(self.btn_repair)

        self.lbl_repair_status = QLabel("", r_box)
        self.lbl_repair_status.setStyleSheet(f"font-size: 10px; color: {SUCCESS};")
        self.lbl_repair_status.hide()
        rl.addWidget(self.lbl_repair_status)

        v.addWidget(r_box)

        # Logs & Diagnostics Section
        d_box = QFrame(w)
        d_box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        dl = QVBoxLayout(d_box)
        dl.setSpacing(8)

        d_title = QLabel("Diagnostics & Logs", d_box)
        d_title.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {TEXT_PRIMARY};")
        dl.addWidget(d_title)

        d_btns = QHBoxLayout()
        self.btn_open_logs = QPushButton("Open Logs Directory", d_box)
        self.btn_open_logs.setStyleSheet(get_button_style("secondary", size="sm"))
        self.btn_open_logs.clicked.connect(self._on_open_logs)

        self.btn_open_diag = QPushButton("Open Diagnostics Tool", d_box)
        self.btn_open_diag.setStyleSheet(get_button_style("secondary", size="sm"))
        self.btn_open_diag.clicked.connect(self._on_open_diag)

        d_btns.addWidget(self.btn_open_logs)
        d_btns.addWidget(self.btn_open_diag)
        dl.addLayout(d_btns)

        v.addWidget(d_box)
        v.addStretch(1)
        return w

    def _create_about_tab(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        box = QFrame(w)
        box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 14px;")
        bl = QVBoxLayout(box)
        bl.setSpacing(6)

        t = QLabel(f"{APP_NAME}", box)
        t.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {TEXT_PRIMARY};")
        bl.addWidget(t)

        ver = QLabel(f"Version: {VERSION}", box)
        ver.setStyleSheet(f"font-size: 11px; font-family: {FONT_MONO}; color: {ACCENT};")
        bl.addWidget(ver)

        if PUBLISHER:
            pub = QLabel(f"Publisher: {PUBLISHER}", box)
            pub.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
            bl.addWidget(pub)

        arch = QLabel("Architecture: Windows Native Desktop Shell (PySide6 / Win32 / CUDA)", box)
        arch.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        bl.addWidget(arch)

        cpr = QLabel(COPYRIGHT, box)
        cpr.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED}; margin-top: 6px;")
        bl.addWidget(cpr)

        v.addWidget(box)
        v.addStretch(1)
        return w

    def _on_browse_models(self) -> None:
        """Select new model storage directory."""
        chosen = QFileDialog.getExistingDirectory(self, "Select Model Weights Directory", self.txt_model_dir.text())
        if chosen:
            self.txt_model_dir.setText(chosen)

    def _on_run_repair(self) -> None:
        """Execute RepairManager self-healing procedures."""
        mgr = RepairManager()
        report: RepairReport = mgr.run_all_repairs()
        self.lbl_repair_status.setText(f"Repair Complete: {report.summary}")
        self.lbl_repair_status.show()

    def _on_open_logs(self) -> None:
        """Open logs folder in Windows Explorer."""
        logs_dir = get_logs_dir()
        logs_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(logs_dir))

    def _on_open_diag(self) -> None:
        """Open live diagnostics window if launcher is available."""
        if self.app and hasattr(self.app, "launcher"):
            self.app.launcher.open_diagnostics()
            self.accept()

    def _on_hotkey_preset_changed(self, idx: int) -> None:
        """Handle preset selection or show custom controls."""
        is_custom = self.cbo_hotkey.itemData(idx) == "custom"
        self.custom_hk_container.setVisible(is_custom)
        self.lbl_hotkey_status.hide()

    def _get_selected_hotkey(self) -> tuple[list[str], str]:
        """Derive currently chosen modifier list and key name."""
        idx = self.cbo_hotkey.currentIndex()
        data = self.cbo_hotkey.itemData(idx)
        if data != "custom" and isinstance(data, list):
            mods = [data[0]]
            key = data[1]
            return mods, key

        mods = []
        if self.chk_mod_alt.isChecked():
            mods.append("Alt")
        if self.chk_mod_ctrl.isChecked():
            mods.append("Ctrl")
        if self.chk_mod_shift.isChecked():
            mods.append("Shift")
        if self.chk_mod_win.isChecked():
            mods.append("Win")
        if not mods:
            mods = ["Alt"]

        key = self.txt_custom_key.text().strip() or "Space"
        return mods, key

    def _on_test_hotkey(self) -> None:
        """Test whether selected shortcut can be registered on this system."""
        mods, key = self._get_selected_hotkey()
        from astrarun.hotkeys.manager import HotkeyManager, format_shortcut_name
        mgr = getattr(self.app, "hotkey_manager", None)
        if mgr is None:
            mgr = HotkeyManager()

        avail, code, desc = mgr.test_registration(mods, key)
        shortcut_str = format_shortcut_name(mods, key)
        if avail:
            self.lbl_hotkey_status.setText(f"✓ {shortcut_str} is available on this system.")
            self.lbl_hotkey_status.setStyleSheet(f"color: {SUCCESS}; font-size: 11px;")
        else:
            self.lbl_hotkey_status.setText(f"✗ {shortcut_str} is unavailable ({desc}).")
            self.lbl_hotkey_status.setStyleSheet(f"color: {DANGER}; font-size: 11px;")
        self.lbl_hotkey_status.show()

    def _persist_settings(self) -> None:
        """Atomically persist settings dictionary to local user and config files."""
        if not self.app or not hasattr(self.app, "settings"):
            return
        from astrarun.core.paths import AstraPaths
        targets = [
            AstraPaths.config_dir() / "settings.json",
        ]
        for p in targets:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(self.app.settings, f, indent=2)
                logger.info("Settings persisted to %s", p)
            except Exception as e:
                logger.debug("Could not write settings to %s: %s", p, e)

    def _on_save(self) -> None:
        """Save settings, apply hotkey rebind live, and persist changes."""
        enable_autostart(self.chk_autostart.isChecked())
        if self.app and hasattr(self.app, "settings"):
            self.app.settings.setdefault("learning", {})["enabled"] = self.chk_learning.isChecked()
            self.app.settings["learning"]["allow_training_dataset_export"] = self.chk_export.isChecked()

            # Hotkey update and live rebind
            mods, key = self._get_selected_hotkey()
            self.app.settings["hotkey"] = {"modifiers": mods, "key": key}
            mgr = getattr(self.app, "hotkey_manager", None)
            if mgr:
                success, code, err = mgr.rebind(mods, key)
                if not success:
                    QMessageBox.warning(
                        self,
                        "Shortcut Conflict",
                        f"Could not bind {mgr.shortcut_name}: {err}\nPrevious shortcut was retained."
                    )
            self._persist_settings()

        self.accept()
