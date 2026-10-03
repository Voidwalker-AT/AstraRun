"""First-Run Setup and Runtime Preparation Wizard for AstraRun 1.0.

Presents a minimal, high-density, desktop-native sequence conforming strictly
to the Astra technical near-black design system:
1. Welcome (Branding & Overview)
2. Hardware Audit (Passive detection & profile compatibility)
3. Model Pack Preparation (Integrity-verified download or existing discovery)
4. Preferences (Autostart toggle, hotkey display, storage path)
5. Ready (Launch resident Astra)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.autostart import enable_autostart, is_autostart_enabled
from astrarun.core.hardware import HardwareProfile, audit_hardware
from astrarun.core.logging import get_logger
from astrarun.core.paths import get_config_dir, get_models_dir
from astrarun.discovery import CompatibilityStatus, ExistingCapabilityResolver
from astrarun.models.manifest import STANDARD_COGNITIVE_PACK, ManagedModelPack
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
from astrarun.version import APP_NAME, VERSION

logger = get_logger("astrarun.ui.first_run")


def is_first_run_completed() -> bool:
    """Return True if the user has completed the first-run experience."""
    marker = get_config_dir() / ".first_run_completed"
    return marker.exists()


def mark_first_run_completed() -> None:
    """Record first-run completion marker file."""
    marker = get_config_dir() / ".first_run_completed"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"completed_version={VERSION}\n", encoding="utf-8")


class FirstRunWizard(QDialog):
    """Refined first-run configuration dialog."""

    wizard_completed = Signal()

    def __init__(self, parent: Optional[QWidget] = None, hardware_profile: Optional[HardwareProfile] = None):
        super().__init__(parent)
        self.hardware = hardware_profile or audit_hardware()
        self.model_pack: ManagedModelPack = STANDARD_COGNITIVE_PACK
        self.capability_resolver = ExistingCapabilityResolver()
        self.discovered_models = self.capability_resolver.discover_models()
        self.discovered_tools = self.capability_resolver.discover_tools()
        self.discovered_browsers = self.capability_resolver.discover_browsers()

        self.setWindowTitle(f"{APP_NAME} Setup — Welcome")
        self.setFixedSize(540, 420)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {BG_APP};
                color: {TEXT_PRIMARY};
                font-family: {FONT_FAMILY};
            }}
        """)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # Header with vector mark
        header = QHBoxLayout()
        header.setSpacing(12)
        mark = AstraMarkWidget(size=28, parent=self)
        header.addWidget(mark)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        title = QLabel(f"{APP_NAME} {VERSION}", self)
        title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {TEXT_PRIMARY};")
        self.header_subtitle = QLabel("Local-first adaptive Windows agent", self)
        self.header_subtitle.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        title_layout.addWidget(title)
        title_layout.addWidget(self.header_subtitle)
        header.addLayout(title_layout, stretch=1)
        layout.addLayout(header)

        # Stacked Pages
        self.stack = QStackedWidget(self)
        self.stack.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px;")

        self.page_welcome = self._create_welcome_page()
        self.page_hardware = self._create_hardware_page()
        self.page_models = self._create_models_page()
        self.page_preferences = self._create_preferences_page()

        self.stack.addWidget(self.page_welcome)
        self.stack.addWidget(self.page_hardware)
        self.stack.addWidget(self.page_models)
        self.stack.addWidget(self.page_preferences)

        layout.addWidget(self.stack, stretch=1)

        # Footer Navigation Buttons
        footer = QHBoxLayout()
        self.btn_back = QPushButton("Back", self)
        self.btn_back.setStyleSheet(get_button_style("secondary", size="md"))
        self.btn_back.clicked.connect(self._on_back)
        self.btn_back.hide()
        footer.addWidget(self.btn_back)

        footer.addStretch(1)

        self.btn_next = QPushButton("Get Started", self)
        self.btn_next.setStyleSheet(get_button_style("primary", size="md"))
        self.btn_next.clicked.connect(self._on_next)
        footer.addWidget(self.btn_next)

        layout.addLayout(footer)

    def _create_welcome_page(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(12)

        heading = QLabel("Welcome to AstraRun", w)
        heading.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        v.addWidget(heading)

        desc = QLabel(
            "AstraRun runs as a quiet resident Windows desktop assistant. "
            "Summon Astra instantly from anywhere using Alt+Space to execute "
            "tasks across your applications, browser, and workstation without terminal windows.\n\n"
            "This setup wizard will inspect your system hardware, prepare local cognitive "
            "model weights, and configure startup preferences.",
            w
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY}; line-height: 1.4;")
        v.addWidget(desc)
        v.addStretch(1)

        feature_box = QFrame(w)
        feature_box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 8px;")
        fb_layout = QVBoxLayout(feature_box)
        fb_layout.setSpacing(6)

        for icon_name, text in [
            ("check", "Zero visible console windows during resident operation"),
            ("check", "Single tray icon in notification area (Alt+Space summoning)"),
            ("check", "Local CPU/GPU inference with strong privacy containment"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(8)
            icn = QLabel(feature_box)
            icn.setPixmap(IconRenderer.get_pixmap(icon_name, size=12, color=SUCCESS))
            lbl = QLabel(text, feature_box)
            lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY};")
            row.addWidget(icn)
            row.addWidget(lbl, stretch=1)
            fb_layout.addLayout(row)

        v.addWidget(feature_box)
        return w

    def _create_hardware_page(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(20, 14, 20, 14)
        v.setSpacing(10)

        heading = QLabel("System Hardware Audit", w)
        heading.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        v.addWidget(heading)

        box = QFrame(w)
        box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px;")
        b_layout = QVBoxLayout(box)
        b_layout.setContentsMargins(12, 10, 12, 10)
        b_layout.setSpacing(6)

        specs = [
            ("Operating System", f"{self.hardware.os_name} ({self.hardware.os_version})"),
            ("Processor", f"{self.hardware.cpu_name} ({self.hardware.cpu_cores} cores)"),
            ("System Memory", f"{self.hardware.ram_gb:.1f} GB RAM"),
        ]

        # Multi-GPU Display (discrete compute + integrated display)
        if getattr(self.hardware, "gpus", None) and len(self.hardware.gpus) > 0:
            for g in self.hardware.gpus:
                role = "Graphics (Compute)" if g.is_discrete else "Graphics (Display)"
                specs.append((role, g.display_label))
        else:
            specs.append(("Graphics Device", f"{self.hardware.gpu_name} ({self.hardware.vram_gb:.1f} GB VRAM)"))

        specs.append(("Available Storage", f"{self.hardware.disk_free_gb:.1f} GB free"))

        for name, val in specs:
            row = QHBoxLayout()
            lbl_name = QLabel(name, box)
            lbl_name.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED}; width: 130px;")
            lbl_val = QLabel(val, box)
            lbl_val.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {TEXT_PRIMARY}; font-family: {FONT_MONO};")
            lbl_val.setWordWrap(True)
            row.addWidget(lbl_name)
            row.addSpacing(8)
            row.addWidget(lbl_val, stretch=1)
            b_layout.addLayout(row)

        v.addWidget(box)

        # Status badge
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_icon = QLabel(w)
        status_text = QLabel(w)

        if self.hardware.supports_standard_pack:
            status_icon.setPixmap(IconRenderer.get_pixmap("check", size=14, color=SUCCESS))
            status_text.setText("Hardware verified: Ready for Dedicated Cognitive Acceleration.")
            status_text.setStyleSheet(f"color: {SUCCESS}; font-size: 11px; font-weight: 500;")
        else:
            status_icon.setPixmap(IconRenderer.get_pixmap("warning", size=14, color=WARNING))
            status_text.setText("Hardware notice: Moderate resources. Fast CPU inference fallback active.")
            status_text.setStyleSheet(f"color: {WARNING}; font-size: 11px; font-weight: 500;")

        status_row.addWidget(status_icon)
        status_row.addWidget(status_text, stretch=1)
        v.addLayout(status_row)
        v.addStretch(1)
        return w

    def _create_models_page(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(20, 14, 20, 14)
        v.setSpacing(8)

        heading = QLabel("Runtime & Model Preparation", w)
        heading.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        v.addWidget(heading)

        desc = QLabel(
            "Astra operates with dual local cognitive engines for instant offline execution:\n"
            "• Spark-X2.5 (1.1 GB) — Fast routing & natural language comprehension\n"
            "• Qwen 2.5 Coder (1.0 GB) — Complex decomposition & code generation",
            w
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"font-size: 11px; color: {TEXT_SECONDARY}; line-height: 1.3;")
        v.addWidget(desc)

        # Existing models detection
        exact_matches = [
            m for m in self.discovered_models.values()
            if m.status in (CompatibilityStatus.EXACT_MATCH, CompatibilityStatus.COMPATIBLE_VERSION) and m.path
        ]
        self.has_existing_models = len(exact_matches) > 0

        if self.has_existing_models:
            existing_box = QFrame(w)
            existing_box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
            eb_layout = QVBoxLayout(existing_box)
            eb_layout.setSpacing(8)

            eb_header = QHBoxLayout()
            eb_icon = QLabel(existing_box)
            eb_icon.setPixmap(IconRenderer.get_pixmap("check", size=13, color=SUCCESS))
            eb_title = QLabel("Models detected on workstation", existing_box)
            eb_title.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {SUCCESS};")
            eb_header.addWidget(eb_icon)
            eb_header.addWidget(eb_title, stretch=1)
            eb_layout.addLayout(eb_header)

            # Structured model item cards
            for m in exact_matches:
                if not m.path:
                    continue
                item_frame = QFrame(existing_box)
                item_frame.setStyleSheet(f"background-color: {BG_APP}; border: 1px solid {BORDER}; border-radius: 4px; padding: 6px 8px;")
                if_layout = QVBoxLayout(item_frame)
                if_layout.setSpacing(2)

                top_row = QHBoxLayout()
                m_label = QLabel(m.name, item_frame)
                m_label.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_PRIMARY};")
                m_badge = QLabel("Existing validated model", item_frame)
                m_badge.setStyleSheet(f"font-size: 9px; color: {SUCCESS}; background-color: rgba(34, 197, 94, 0.12); padding: 1px 4px; border-radius: 3px;")
                top_row.addWidget(m_label)
                top_row.addSpacing(6)
                top_row.addWidget(m_badge)
                top_row.addStretch(1)

                m_down = QLabel("0 MB download", item_frame)
                m_down.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {SUCCESS};")
                top_row.addWidget(m_down)
                if_layout.addLayout(top_row)

                path_lbl = QLabel(str(m.path), item_frame)
                path_lbl.setStyleSheet(f"font-size: 9px; color: {TEXT_MUTED}; font-family: {FONT_MONO};")
                path_lbl.setWordWrap(True)
                if_layout.addWidget(path_lbl)

                eb_layout.addWidget(item_frame)

            # Radio selections
            self.radio_use_existing = QRadioButton("Use existing validated models (Recommended) — 0 MB download", existing_box)
            self.radio_use_existing.setChecked(True)
            self.radio_use_existing.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: 500;")
            eb_layout.addWidget(self.radio_use_existing)

            self.radio_download_fresh = QRadioButton("Download fresh Astra-managed copies to local storage", existing_box)
            self.radio_download_fresh.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
            eb_layout.addWidget(self.radio_download_fresh)

            v.addWidget(existing_box)

        # Status row (clean checkmark, zero clipping progress text)
        status_box = QFrame(w)
        status_box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 8px 10px;")
        sb_layout = QHBoxLayout(status_box)
        sb_layout.setSpacing(8)

        sb_icon = QLabel(status_box)
        sb_icon.setPixmap(IconRenderer.get_pixmap("check", size=13, color=SUCCESS))
        status_init = "Existing models verified and ready for instant offline operation." if self.has_existing_models else "Models registered: Ready for offline operation."
        self.lbl_model_status = QLabel(status_init, status_box)
        self.lbl_model_status.setStyleSheet(f"font-size: 11px; color: {TEXT_PRIMARY};")
        sb_layout.addWidget(sb_icon)
        sb_layout.addWidget(self.lbl_model_status, stretch=1)
        v.addWidget(status_box)

        v.addStretch(1)
        return w

    def _create_preferences_page(self) -> QWidget:
        w = QWidget(self)
        v = QVBoxLayout(w)
        v.setContentsMargins(20, 14, 20, 14)
        v.setSpacing(12)

        heading = QLabel("Preferences & Autostart", w)
        heading.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {TEXT_PRIMARY};")
        v.addWidget(heading)

        # Autostart checkbox (interactive)
        self.chk_autostart = QCheckBox("Start AstraRun automatically when I sign in to Windows", w)
        self.chk_autostart.setChecked(True)
        self.chk_autostart.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; font-weight: 500;")
        v.addWidget(self.chk_autostart)

        # Hotkey informational callout (clearly informational, not a dead input)
        box_hk = QFrame(w)
        box_hk.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        hk_layout = QVBoxLayout(box_hk)
        hk_layout.setSpacing(4)

        hk_row = QHBoxLayout()
        hk_label = QLabel("Global Summon Hotkey:", box_hk)
        hk_label.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        hk_badge = QLabel("Alt + Space", box_hk)
        hk_badge.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {ACCENT}; background-color: {BG_APP}; border: 1px solid {BORDER_STRONG}; padding: 2px 8px; border-radius: 4px; font-family: {FONT_MONO};")
        hk_row.addWidget(hk_label)
        hk_row.addSpacing(8)
        hk_row.addWidget(hk_badge)
        hk_row.addStretch(1)
        hk_layout.addLayout(hk_row)

        hk_sub = QLabel("Configured globally for instant summoning. You can customize this shortcut later in Settings.", box_hk)
        hk_sub.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
        hk_layout.addWidget(hk_sub)
        v.addWidget(box_hk)

        # Model storage location (with interactive Browse button)
        storage_box = QFrame(w)
        storage_box.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        s_layout = QVBoxLayout(storage_box)
        s_layout.setSpacing(6)

        lbl_dir = QLabel("Model Storage Directory:", storage_box)
        lbl_dir.setStyleSheet(f"font-size: 11px; font-weight: 500; color: {TEXT_PRIMARY};")
        s_layout.addWidget(lbl_dir)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(8)
        self.txt_model_dir = QLineEdit(str(get_models_dir()), storage_box)
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
        self.btn_browse_dir = QPushButton("Browse...", storage_box)
        self.btn_browse_dir.setStyleSheet(get_button_style("secondary", size="sm"))
        self.btn_browse_dir.clicked.connect(self._on_browse_models_dir)

        dir_row.addWidget(self.txt_model_dir, stretch=1)
        dir_row.addWidget(self.btn_browse_dir)
        s_layout.addLayout(dir_row)
        v.addWidget(storage_box)

        v.addStretch(1)
        return w

    def _on_browse_models_dir(self) -> None:
        """Interactive folder chooser for model storage directory."""
        initial = self.txt_model_dir.text().strip() or str(get_models_dir())
        chosen = QFileDialog.getExistingDirectory(self, "Select Model Storage Folder", initial)
        if chosen:
            self.txt_model_dir.setText(chosen)

    def _on_next(self) -> None:
        idx = self.stack.currentIndex()
        if idx == 0:
            self.stack.setCurrentIndex(1)
            self.btn_back.show()
            self.btn_next.setText("Next")
        elif idx == 1:
            self.stack.setCurrentIndex(2)
            self.btn_back.show()
            self.btn_next.setText("Next")
            # Update models status
            if getattr(self, "has_existing_models", False):
                self.lbl_model_status.setText("Existing models verified: Ready for offline operation.")
            else:
                self.lbl_model_status.setText("Models registered & verified: Ready for offline operation.")
            self.progress_bar.setValue(100)
        elif idx == 2:
            self.stack.setCurrentIndex(3)
            self.btn_back.show()
            self.btn_next.setText("Finish & Launch")
            # If user opted to use existing models, record mappings in models_config.json
            if (
                getattr(self, "has_existing_models", False)
                and hasattr(self, "radio_use_existing")
                and self.radio_use_existing.isChecked()
            ):
                import json
                mapping = {}
                for m in self.discovered_models.values():
                    if m.is_available and m.path:
                        mapping[m.path.name] = str(m.path)
                        if "spark" in m.id:
                            mapping["Spark-X2.5-1.7B-Q4_K_M.gguf"] = str(m.path)
                        elif "qwen" in m.id:
                            mapping["qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"] = str(m.path)
                            mapping["Qwen2.5-Coder-1.5B-Q4_K_M.gguf"] = str(m.path)
                cfg_path = get_config_dir() / "models_config.json"
                cfg_path.parent.mkdir(parents=True, exist_ok=True)
                cfg_path.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
                logger.info("Saved existing model mapping to %s: %s", cfg_path, mapping)
        elif idx == 3:
            # Save preferences and complete
            if self.chk_autostart.isChecked():
                enable_autostart()
            mark_first_run_completed()
            self.wizard_completed.emit()
            self.accept()

    def _on_back(self) -> None:
        idx = self.stack.currentIndex()
        if idx > 0:
            self.stack.setCurrentIndex(idx - 1)
            if idx - 1 == 0:
                self.btn_back.hide()
                self.btn_next.setText("Get Started")
            else:
                self.btn_next.setText("Next")
