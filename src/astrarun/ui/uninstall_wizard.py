"""AstraRun 1.0 — Desktop-Native Uninstallation Options Wizard.

Presents a refined, high-density dialog conforming strictly to the
Astra technical near-black design system:
1. Active task detection & safe resolution (Cancel / Pause / Stop).
2. Granular component removal choices with dynamic measured sizes.
3. Explicit preservation of externally owned models and runtimes.
4. Learned skills & memory context warning.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from astrarun.core.logging import get_logger
from astrarun.core.paths import get_data_dir, get_app_data_dir
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

logger = get_logger("astrarun.ui.uninstall_wizard")


class UninstallWizardDialog(QDialog):
    """User-facing uninstallation choices dialog."""

    def __init__(self, task_state: Optional[Dict[str, Any]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} Maintenance — Remove AstraRun")
        self.setFixedSize(580, 650)
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

        # Discover current reality
        self.inventory: List[ComponentInventoryItem] = scan_uninstall_inventory()
        self.task_state: Dict[str, Any] = task_state if task_state is not None else check_active_tasks_and_resident()
        self.checkboxes: Dict[str, QCheckBox] = {}
        self.exit_code: int = 1  # 0 = proceed with uninstall, 1 = canceled

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(14)

        # Header
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

        # Scrollable container for content
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content_w = QWidget()
        c_layout = QVBoxLayout(content_w)
        c_layout.setContentsMargins(0, 0, 8, 0)
        c_layout.setSpacing(12)

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

            btn_pause = QPushButton("Pause & checkpoint tasks", banner)
            btn_pause.setStyleSheet(get_button_style("secondary", size="sm"))
            btn_pause.clicked.connect(self._on_pause_and_continue)

            btn_stop = QPushButton("Stop tasks immediately", banner)
            btn_stop.setStyleSheet(get_button_style("danger", size="sm"))
            btn_stop.clicked.connect(self._on_stop_and_continue)

            b_btn_row.addWidget(btn_cancel)
            b_btn_row.addWidget(btn_pause)
            b_btn_row.addWidget(btn_stop)
            b_layout.addLayout(b_btn_row)

            c_layout.addWidget(banner)

        # 1. Application Binaries card (Always removed)
        app_box = QFrame(content_w)
        app_box.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        ab_layout = QHBoxLayout(app_box)
        ab_layout.setSpacing(10)
        ab_icon = QLabel(app_box)
        ab_icon.setPixmap(IconRenderer.get_pixmap("check", size=13, color=ACCENT))
        ab_title = QLabel("AstraRun application binaries & shortcuts", app_box)
        ab_title.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_PRIMARY};")
        ab_status = QLabel("Always removed", app_box)
        ab_status.setStyleSheet(f"font-size: 10px; font-weight: 600; color: {TEXT_MUTED};")
        ab_layout.addWidget(ab_icon)
        ab_layout.addWidget(ab_title, stretch=1)
        ab_layout.addWidget(ab_status)
        c_layout.addWidget(app_box)

        # 2. Local Astra Data Section
        data_group = QFrame(content_w)
        data_group.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
        dg_layout = QVBoxLayout(data_group)
        dg_layout.setSpacing(8)

        dg_head = QLabel("Your Local Astra Data", data_group)
        dg_head.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_SECONDARY};")
        dg_layout.addWidget(dg_head)

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
            cb = QCheckBox(item.label, data_group)
            cb.setChecked(item.selected_default)
            self.checkboxes[item.id] = cb

            size_lbl = QLabel(item.formatted_size, data_group)
            size_lbl.setStyleSheet(f"font-size: 10px; font-family: {FONT_MONO}; color: {TEXT_MUTED};")

            row.addWidget(cb, stretch=1)
            row.addWidget(size_lbl)
            dg_layout.addLayout(row)

        c_layout.addWidget(data_group)

        # 3. Managed AI Components Section
        managed_models = [
            it for it in self.inventory
            if it.category in (ComponentOwnership.ASTRA_MANAGED_MODELS, ComponentOwnership.ASTRA_MANAGED_RUNTIMES)
        ]
        if managed_models:
            mg_group = QFrame(content_w)
            mg_group.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
            mg_layout = QVBoxLayout(mg_group)
            mg_layout.setSpacing(8)

            mg_head = QLabel("Managed AI Components", mg_group)
            mg_head.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_SECONDARY};")
            mg_layout.addWidget(mg_head)

            for item in managed_models:
                row = QHBoxLayout()
                cb = QCheckBox(item.label, mg_group)
                cb.setChecked(item.selected_default)
                self.checkboxes[item.id] = cb

                size_lbl = QLabel(item.formatted_size, mg_group)
                size_lbl.setStyleSheet(f"font-size: 10px; font-family: {FONT_MONO}; color: {TEXT_MUTED};")

                row.addWidget(cb, stretch=1)
                row.addWidget(size_lbl)
                mg_layout.addLayout(row)

            c_layout.addWidget(mg_group)

        # 4. Externally Managed Components Section (ALWAYS PRESERVED)
        ext_items = [it for it in self.inventory if it.is_external]
        if ext_items:
            ext_group = QFrame(content_w)
            ext_group.setStyleSheet(f"background-color: {SURFACE_RAISED}; border: 1px solid {BORDER}; border-radius: 6px; padding: 10px;")
            eg_layout = QVBoxLayout(ext_group)
            eg_layout.setSpacing(6)

            eg_head = QLabel("Externally Managed Components", ext_group)
            eg_head.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {TEXT_SECONDARY};")
            eg_layout.addWidget(eg_head)

            for item in ext_items:
                row = QHBoxLayout()
                lbl = QLabel(item.label, ext_group)
                lbl.setStyleSheet(f"font-size: 11px; color: {TEXT_PRIMARY};")

                badge = QLabel("Preserved — not installed by Astra", ext_group)
                badge.setStyleSheet(f"font-size: 9px; font-weight: 600; color: {SUCCESS}; background-color: rgba(34, 197, 94, 0.12); padding: 2px 6px; border-radius: 3px;")

                row.addWidget(lbl, stretch=1)
                row.addWidget(badge)
                eg_layout.addLayout(row)

            c_layout.addWidget(ext_group)

        # 5. Skills & Memory Continuity Warning Notice
        warn_box = QFrame(content_w)
        warn_box.setStyleSheet(f"background-color: {SURFACE}; border: 1px solid {BORDER}; border-radius: 6px; padding: 8px 10px;")
        wb_layout = QHBoxLayout(warn_box)
        wb_layout.setSpacing(8)
        wb_icon = QLabel(warn_box)
        wb_icon.setPixmap(IconRenderer.get_pixmap("warning", size=13, color=WARNING))
        wb_text = QLabel("Removing memory and learned skills resets Astra's locally learned context.", warn_box)
        wb_text.setStyleSheet(f"font-size: 10px; color: {TEXT_MUTED};")
        wb_layout.addWidget(wb_icon)
        wb_layout.addWidget(wb_text, stretch=1)
        c_layout.addWidget(warn_box)

        # 6. Quick selection helpers
        sel_row = QHBoxLayout()
        btn_keep_data = QPushButton("Keep everything except application (Default)", content_w)
        btn_keep_data.setStyleSheet(get_button_style("secondary", size="sm"))
        btn_keep_data.clicked.connect(self._select_keep_all)

        btn_select_all = QPushButton("Select all Astra data", content_w)
        btn_select_all.setStyleSheet(get_button_style("secondary", size="sm"))
        btn_select_all.clicked.connect(self._select_all_data)

        sel_row.addWidget(btn_keep_data)
        sel_row.addWidget(btn_select_all)
        sel_row.addStretch(1)
        c_layout.addLayout(sel_row)

        c_layout.addStretch(1)
        scroll.setWidget(content_w)
        main_layout.addWidget(scroll, stretch=1)

        # Footer Actions
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.setStyleSheet(get_button_style("secondary", size="md"))
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_uninstall = QPushButton("Proceed with Uninstall", self)
        self.btn_uninstall.setStyleSheet(get_button_style("danger", size="md"))
        self.btn_uninstall.clicked.connect(self._on_proceed_uninstall)

        footer.addStretch(1)
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_uninstall)
        main_layout.addLayout(footer)

    def _select_keep_all(self) -> None:
        """Keep user data and models, removing only application binaries."""
        for cb in self.checkboxes.values():
            cb.setChecked(False)

    def _select_all_data(self) -> None:
        """Select all Astra-managed data and models for complete clean removal."""
        for cb in self.checkboxes.values():
            cb.setChecked(True)

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
