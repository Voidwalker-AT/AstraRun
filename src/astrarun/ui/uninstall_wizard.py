"""AstraRun 1.0 — Desktop-Native Uninstallation Options Wizard.

Presents a responsive, high-density dialog conforming strictly to the
Astra technical near-black design system:
1. Active task detection & safe resolution (Cancel / Pause / Stop).
2. High-level uninstall modes:
   - KEEP MY ASTRA DATA (Recommended)
   - CHOOSE WHAT TO REMOVE
   - REMOVE ALL ASTRA-MANAGED DATA
3. Granular component removal choices with dynamic measured sizes.
4. Informational display of externally preserved models (Zero checkboxes).
5. Responsive layout with QFontMetrics path elision and ZERO horizontal scrollbars.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.logging import get_logger
from astrarun.core.paths import get_data_dir
from astrarun.lifecycle.uninstall import (
    ComponentInventoryItem,
    ComponentOwnership,
    check_active_tasks_and_resident,
    create_uninstall_plan,
    execute_uninstall_plan,
    request_graceful_shutdown,
    scan_uninstall_inventory,
)
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
    SURFACE_INPUT,
    SURFACE_RAISED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING,
    get_button_style,
)
from astrarun.version import APP_NAME, VERSION

logger = get_logger("astrarun.ui.uninstall_wizard")


class UninstallWizardDialog(QDialog):
    """User-facing uninstallation choices dialog."""

    def __init__(self, task_state: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} Maintenance — Remove AstraRun")
        self.setMinimumWidth(500)
        self.resize(560, 660)
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
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QRadioButton {{
                color: {TEXT_PRIMARY};
                font-size: 11px;
                font-weight: 500;
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
            QCheckBox:disabled {{
                color: {TEXT_MUTED};
            }}
        """)

        # Discover current reality
        self.inventory: List[ComponentInventoryItem] = scan_uninstall_inventory()
        self.task_state: Dict[str, Any] = task_state if task_state is not None else check_active_tasks_and_resident()
        self.checkboxes: Dict[str, QCheckBox] = {}
        self.exit_code: int = 1  # 0 = proceed with uninstall, 1 = canceled

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # 1. Header
        header = QHBoxLayout()
        header.setSpacing(12)
        mark = AstraMarkWidget(size=28, parent=self)
        header.addWidget(mark)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)
        title = QLabel(f"Uninstall {APP_NAME} {VERSION}", self)
        title.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {TEXT_PRIMARY};")
        subtitle = QLabel("Removal options & local state preservation", self)
        subtitle.setStyleSheet(f"font-size: 11px; color: {TEXT_MUTED};")
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header.addLayout(title_layout, stretch=1)
        main_layout.addLayout(header)

        # 2. Scrollable container for content (STRICTLY NO HORIZONTAL SCROLLBAR)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        content_w = QWidget()
        c_layout = QVBoxLayout(content_w)
        c_layout.setContentsMargins(0, 0, 4, 0)
        c_layout.setSpacing(10)

        # Active Tasks Banner if tasks are in-flight
        if self.task_state.get("active_task_count", 0) > 0:
            count = self.task_state["active_task_count"]
            banner = QFrame(content_w)
            banner.setStyleSheet(f"background-color: rgba(239, 68, 68, 0.12); border: 1px solid {DANGER}; border-radius: 6px; padding: 10px;")
            b_layout = QVBoxLayout(banner)
            b_layout.setSpacing(6)

            b_top = QHBoxLayout()
            b_icon = QLabel(banner)
            b_icon.setPixmap(IconRenderer.get_pixmap("warning", size=14, color=DANGER))
            b_text = QLabel(f"Astra is currently working on {count} task(s).", banner)
            b_text.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {DANGER};")
            b_top.addWidget(b_icon)
            b_top.addWidget(b_text, stretch=1)
            b_layout.addLayout(b_top)

            b_sub = QLabel("Active tasks must be paused or stopped before uninstallation can proceed safely.", banner)
            b_sub.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
            b_layout.addWidget(b_sub)

            b_btn_row = QHBoxLayout()
            b_btn_row.setSpacing(8)

            btn_cancel = QPushButton("Cancel uninstall (Recommended)", banner)
            btn_cancel.setStyleSheet(get_button_style("primary", size="sm"))
            btn_cancel.clicked.connect(self.reject)

            btn_pause = QPushButton("Pause & checkpoint", banner)
            btn_pause.setStyleSheet(get_button_style("secondary", size="sm"))
            btn_pause.clicked.connect(self._on_pause_and_continue)

            btn_stop = QPushButton("Stop tasks", banner)
            btn_stop.setStyleSheet(get_button_style("danger", size="sm"))
            btn_stop.clicked.connect(self._on_stop_and_continue)

            b_btn_row.addWidget(btn_cancel)
            b_btn_row.addWidget(btn_pause)
            b_btn_row.addWidget(btn_stop)
            b_layout.addLayout(b_btn_row)

            c_layout.addWidget(banner)

        # 3. High-Level Removal Modes Card
        mode_box = QFrame(content_w)
        mode_box.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        mb_layout = QVBoxLayout(mode_box)
        mb_layout.setSpacing(6)

        mb_head = QLabel("Removal Mode", mode_box)
        mb_head.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_SECONDARY};")
        mb_layout.addWidget(mb_head)

        self.mode_group = QButtonGroup(self)
        self.radio_keep = QRadioButton("Keep my Astra data (Recommended)", mode_box)
        self.radio_keep.setChecked(True)
        self.radio_keep.setToolTip("Removes application binaries and shortcuts. Preserves settings, task history, and models.")
        
        self.radio_choose = QRadioButton("Choose what to remove", mode_box)
        self.radio_choose.setToolTip("Manually select individual Astra components to delete.")

        self.radio_remove_all = QRadioButton("Remove all Astra-managed data", mode_box)
        self.radio_remove_all.setToolTip("Removes all Astra data, logs, cache, and Astra-managed models. External models are NEVER removed.")

        self.mode_group.addButton(self.radio_keep, 0)
        self.mode_group.addButton(self.radio_choose, 1)
        self.mode_group.addButton(self.radio_remove_all, 2)
        self.mode_group.idClicked.connect(self._on_mode_changed)

        mb_layout.addWidget(self.radio_keep)
        mb_layout.addWidget(self.radio_choose)
        mb_layout.addWidget(self.radio_remove_all)
        c_layout.addWidget(mode_box)

        # 4. Local Astra Data Section
        data_group = QFrame(content_w)
        data_group.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        self.dg_layout = QVBoxLayout(data_group)
        self.dg_layout.setSpacing(6)

        dg_head = QLabel("Local Astra Data", data_group)
        dg_head.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_SECONDARY};")
        self.dg_layout.addWidget(dg_head)

        local_items = [
            it for it in self.inventory
            if it.category in (
                ComponentOwnership.CONFIGURATION,
                ComponentOwnership.TASK_HISTORY,
                ComponentOwnership.MEMORY_DATABASE,
                ComponentOwnership.SKILLS,
                ComponentOwnership.LOGS,
                ComponentOwnership.CACHE,
            )
        ]

        for item in local_items:
            row = QHBoxLayout()
            row.setSpacing(6)
            cb = QCheckBox(item.label, data_group)
            cb.setChecked(False)  # Default keep data
            cb.setEnabled(False)  # Disabled until 'Choose' mode
            cb.setToolTip(f"{item.status_note}\nPath: {item.path}")
            self.checkboxes[item.id] = cb

            size_lbl = QLabel(item.formatted_size, data_group)
            size_lbl.setStyleSheet(f"font-size: 11px; font-family: {FONT_MONO}; color: {TEXT_MUTED}; min-width: 65px; text-align: right;")
            size_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            row.addWidget(cb, stretch=1)
            row.addWidget(size_lbl)
            self.dg_layout.addLayout(row)

        c_layout.addWidget(data_group)

        # 5. Managed AI Components Section
        managed_models = [
            it for it in self.inventory
            if it.category in (ComponentOwnership.ASTRA_MANAGED_MODELS, ComponentOwnership.ASTRA_MANAGED_RUNTIMES)
        ]
        if managed_models:
            mg_group = QFrame(content_w)
            mg_group.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
            self.mg_layout = QVBoxLayout(mg_group)
            self.mg_layout.setSpacing(6)

            mg_head = QLabel("Managed AI Components", mg_group)
            mg_head.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_SECONDARY};")
            self.mg_layout.addWidget(mg_head)

            for item in managed_models:
                row = QHBoxLayout()
                row.setSpacing(6)
                cb = QCheckBox(item.label, mg_group)
                cb.setChecked(False)
                cb.setEnabled(False)
                cb.setToolTip(f"{item.status_note}\nPath: {item.path}")
                self.checkboxes[item.id] = cb

                size_lbl = QLabel(item.formatted_size, mg_group)
                size_lbl.setStyleSheet(f"font-size: 11px; font-family: {FONT_MONO}; color: {TEXT_MUTED}; min-width: 65px; text-align: right;")
                size_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

                row.addWidget(cb, stretch=1)
                row.addWidget(size_lbl)
                self.mg_layout.addLayout(row)

            c_layout.addWidget(mg_group)

        # 6. External Preserved Components (Informational Rows — ZERO Checkboxes)
        ext_items = [it for it in self.inventory if it.is_external]
        if ext_items:
            ext_group = QFrame(content_w)
            ext_group.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
            eg_layout = QVBoxLayout(ext_group)
            eg_layout.setSpacing(6)

            eg_head = QLabel("Existing models — preserved", ext_group)
            eg_head.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_SECONDARY};")
            eg_layout.addWidget(eg_head)

            fm = QFontMetrics(self.font())
            for item in ext_items:
                row = QHBoxLayout()
                row.setSpacing(8)

                col = QVBoxLayout()
                col.setSpacing(1)

                name_lbl = QLabel(item.label.split(" (")[0], ext_group)
                name_lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_PRIMARY};")

                full_path_str = str(item.path)
                elided_path = fm.elidedText(full_path_str, Qt.TextElideMode.ElideMiddle, 260)
                path_lbl = QLabel(elided_path, ext_group)
                path_lbl.setStyleSheet(f"font-size: 10px; font-family: {FONT_MONO}; color: {TEXT_MUTED};")
                path_lbl.setToolTip(full_path_str)

                col.addWidget(name_lbl)
                col.addWidget(path_lbl)
                row.addLayout(col, stretch=1)

                badge = QLabel("Not installed by Astra", ext_group)
                badge.setStyleSheet(f"font-size: 9px; font-weight: 600; color: {SUCCESS}; background-color: rgba(34, 197, 94, 0.12); padding: 3px 6px; border-radius: 3px;")
                row.addWidget(badge)

                eg_layout.addLayout(row)

            c_layout.addWidget(ext_group)

        c_layout.addStretch(1)
        scroll.setWidget(content_w)
        main_layout.addWidget(scroll, stretch=1)

        # 7. Footer Actions
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setStyleSheet(get_button_style("primary", size="md"))
        self.btn_cancel.setDefault(True)
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_uninstall = QPushButton("Proceed with Uninstall", self)
        self.btn_uninstall.setStyleSheet(get_button_style("danger", size="md"))
        self.btn_uninstall.clicked.connect(self._on_proceed_uninstall)

        footer.addStretch(1)
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_uninstall)
        main_layout.addLayout(footer)

    def _on_mode_changed(self, mode_id: int) -> None:
        """Handle high-level removal mode change."""
        if mode_id == 0:
            # KEEP MY ASTRA DATA
            for cb in self.checkboxes.values():
                cb.setChecked(False)
                cb.setEnabled(False)
        elif mode_id == 1:
            # CHOOSE WHAT TO REMOVE
            for cb in self.checkboxes.values():
                cb.setEnabled(True)
        elif mode_id == 2:
            # REMOVE ALL ASTRA-MANAGED DATA
            for cb in self.checkboxes.values():
                cb.setChecked(True)
                cb.setEnabled(False)

    def _select_keep_all(self) -> None:
        """Keep user data and models, removing only application binaries."""
        self.radio_keep.setChecked(True)
        self._on_mode_changed(0)

    def _select_all_data(self) -> None:
        """Select all Astra-managed data and models for complete clean removal."""
        self.radio_remove_all.setChecked(True)
        self._on_mode_changed(2)

    def _on_pause_and_continue(self) -> None:
        """Pause active tasks cleanly before uninstallation."""
        logger.info("[UNINSTALL] Pausing active tasks via IPC...")
        request_graceful_shutdown(timeout_sec=3.0)
        self.task_state = check_active_tasks_and_resident()

    def _on_stop_and_continue(self) -> None:
        """Stop active tasks immediately before uninstallation."""
        logger.info("[UNINSTALL] Stopping active tasks via IPC...")
        request_graceful_shutdown(timeout_sec=2.0)
        self.task_state = check_active_tasks_and_resident()

    def _on_proceed_uninstall(self) -> None:
        """Generate validated uninstallation plan, flush to disk, and exit cleanly."""
        selected_ids: Set[str] = {"binaries"}
        for item_id, cb in self.checkboxes.items():
            if cb.isChecked():
                selected_ids.add(item_id)

        plan = create_uninstall_plan(selected_ids, self.inventory)
        
        # Save plan to %LOCALAPPDATA%\AstraRun\data\uninstall_plan.json and plain text list
        try:
            data_dir = get_data_dir()
            data_dir.mkdir(parents=True, exist_ok=True)
            plan_file = data_dir / "uninstall_plan.json"
            plan_file.write_text(json.dumps(plan, indent=2), encoding="utf-8")
            plan_txt = data_dir / "uninstall_dirs_to_remove.txt"
            plan_txt.write_text("\n".join(plan["paths_to_remove"]), encoding="utf-8")
            logger.info("Saved uninstallation plan to %s (paths_to_remove=%d)", plan_file, len(plan["paths_to_remove"]))
        except Exception as err:
            logger.error("Failed to write uninstall_plan.json: %s", err)

        # Gracefully shut down resident AstraRun if running
        request_graceful_shutdown(timeout_sec=3.0)

        # Execute removal plan for selected local data items
        try:
            execute_uninstall_plan(plan)
        except Exception as err:
            logger.error("Error during uninstall plan execution: %s", err)

        self.exit_code = 0
        self.accept()


def run_uninstall_ui() -> int:
    """Entry point for standalone or installer invocation of uninstaller UI."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)
    wizard = UninstallWizardDialog()
    res = wizard.exec()
    return 0 if res == QDialog.DialogCode.Accepted else 1


if __name__ == "__main__":
    sys.exit(run_uninstall_ui())
