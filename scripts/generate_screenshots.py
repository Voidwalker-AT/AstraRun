"""Script to generate actual production screenshots A through J for Milestone 5V.

Captures real instantiated UI components:
- screenshot_A_command_surface_empty.png
- screenshot_B_command_surface_query.png
- screenshot_C_active_task_hud.png
- screenshot_D_expanded_task_hud.png
- screenshot_E_task_center.png
- screenshot_F_actiongate_confirm.png
- screenshot_G_clarification_card.png
- screenshot_H_user_takeover.png
- screenshot_I_completed_result.png
- screenshot_J_tray_menu.png
"""

import os
import sys
import time
from pathlib import Path

# Ensure Qt platform and high DPI
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont
from PySide6.QtWidgets import QApplication

from astrarun.app import AstraApplication
from astrarun.tasks.models import Task, TaskEvent, TaskEventType, TaskStatus
from astrarun.ui.hud import FloatingTaskHUD, HUDState
from astrarun.ui.launcher import LauncherWindow
from astrarun.ui.task_center import TaskCenterWindow
from astrarun.ui.tray import AstraTrayIcon, TrayState


def main():
    qapp = QApplication.instance() or QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)

    out_dir = Path("docs/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Initializing AstraApplication composition root...")
    astra_app = AstraApplication()

    # 1. Instantiate Widgets
    hud = FloatingTaskHUD()
    hud.animations_enabled = False  # Instant positioning for deterministic pixel captures
    launcher = LauncherWindow(app=astra_app, hud=hud)
    tray = AstraTrayIcon(parent=launcher)

    from astrarun.ui.presentation import LauncherPresentationController
    pres_ctrl = LauncherPresentationController(launcher=launcher, hud=hud, app=astra_app)

    print("Generating Screenshot A: Command Surface — empty...")
    launcher.animations_enabled = False
    pres_ctrl.present()
    launcher.input_field.setText("")
    qapp.processEvents()
    time.sleep(0.1)
    launcher.grab().save(str(out_dir / "screenshot_A_command_surface_empty.png"))
    print("  -> Saved screenshot_A_command_surface_empty.png")

    print("Generating Screenshot B: Command Surface — query entered...")
    launcher.input_field.setText("open calculator")
    qapp.processEvents()
    time.sleep(0.1)
    launcher.grab().save(str(out_dir / "screenshot_B_command_surface_query.png"))
    print("  -> Saved screenshot_B_command_surface_query.png")
    launcher.hide()

    print("Generating Screenshot C: Active Task HUD...")
    hud.show_progress(
        task_id="task-live-demo-01",
        title="Open Calculator",
        message="Resolving executable and launching via Win32 CreateProcessW...",
        progress_mode="DETERMINATE",
        progress_pct=65.0,
    )
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_C_active_task_hud.png"))
    print("  -> Saved screenshot_C_active_task_hud.png")

    print("Generating Screenshot D: Expanded Task HUD / Details...")
    hud.set_steps([
        {"step_id": "s1", "description": "Resolve target project path (E:\\Workspace\\Active\\AstraRun)", "state": "COMPLETED"},
        {"step_id": "s2", "description": "Execute approved safe test command (pytest -k test_user_sid)", "state": "RUNNING"},
        {"step_id": "s3", "description": "Verify zero console windows and check stdout observation", "state": "PENDING"},
    ])
    hud.update_step_state("s1", "COMPLETED")
    hud.update_step_state("s2", "RUNNING")
    hud.toggle_steps_expansion()
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_D_expanded_task_hud.png"))
    print("  -> Saved screenshot_D_expanded_task_hud.png")

    print("Generating Screenshot E: Task Center...")
    # Populate tasks in ledger for Task Center display
    conv = astra_app.task_ledger.create_conversation("Milestone 5V Live Acceptance")
    t1 = Task(id="task-c01", conversation_id=conv.id, request_text="open calculator", status=TaskStatus.COMPLETED)
    t2 = Task(id="task-c02", conversation_id=conv.id, request_text="run a battery report and save it to the AstraRun temporary test directory", status=TaskStatus.RUNNING)
    t3 = Task(id="task-c03", conversation_id=conv.id, request_text="kill rogue-daemon-process --force", status=TaskStatus.CANCELLED)
    astra_app.task_ledger.save_task(t1)
    astra_app.task_ledger.save_task(t2)
    astra_app.task_ledger.save_task(t3)

    task_center = TaskCenterWindow(
        task_runtime=getattr(astra_app, "task_runtime", None),
        app=astra_app,
    )
    task_center.show()
    task_center.refresh_tasks()
    qapp.processEvents()
    time.sleep(0.1)
    task_center.grab().save(str(out_dir / "screenshot_E_task_center.png"))
    print("  -> Saved screenshot_E_task_center.png")
    task_center.hide()

    print("Generating Screenshot F: ActionGate confirmation card...")
    hud.show_confirmation(
        task_id="task-sec-01",
        prompt="Destructive action requested: Terminate process node.exe (PID 14280)? Action is irreversible.",
        token="gate-token-9988",
        tool="kill_process",
        arguments={"pid": 14280, "name": "node.exe"},
    )
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_F_actiongate_confirm.png"))
    print("  -> Saved screenshot_F_actiongate_confirm.png")

    print("Generating Screenshot G: Clarification card...")
    hud.show_clarification(
        task_id="task-clar-01",
        prompt="Multiple projects matching 'Astra' found. Which project would you like to open?",
        candidates=[
            {"title": "AstraRun (Active/AstraRun)", "id": "astrarun"},
            {"title": "Astra-Bridge (Active/AI-Bridge)", "id": "ai-bridge"},
            {"title": "Astra-Mobile (Active/termux-ai-workstation)", "id": "termux-ai"},
        ],
    )
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_G_clarification_card.png"))
    print("  -> Saved screenshot_G_clarification_card.png")

    print("Generating Screenshot H: User takeover state...")
    hud.show_user_takeover(
        task_id="task-takeover-01",
        message="✦ Paused — you're using the computer",
    )
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_H_user_takeover.png"))
    print("  -> Saved screenshot_H_user_takeover.png")

    print("Generating Screenshot I: Completed result state...")
    hud.show_success(
        task_id="task-comp-01",
        message="Battery report generated successfully at data/test_milestone5v_battery.html (248 KB)",
    )
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_I_completed_result.png"))
    print("  -> Saved screenshot_I_completed_result.png")
    hud.hide()

    print("Generating Screenshot J: Tray context menu...")
    tray.set_state(TrayState.READY)
    menu = tray.contextMenu()
    menu.show()
    qapp.processEvents()
    time.sleep(0.1)
    menu.grab().save(str(out_dir / "screenshot_J_tray_menu.png"))
    print("  -> Saved screenshot_J_tray_menu.png")
    menu.hide()

    print("\nALL 10 SCREENSHOTS SUCCESSFULLY CAPTURED INTO docs/screenshots/:")
    for f in sorted(out_dir.glob("screenshot_*.png")):
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
