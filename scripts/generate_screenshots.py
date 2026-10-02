"""Script to generate actual production screenshots A through L for Milestone 5P.

Captures all 12 real instantiated UI components conforming to the
technical dark design system (Near-black / Charcoal / Graphite) with zero emoji:
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
- screenshot_K_task_center_empty.png
- screenshot_L_error_state.png
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
from astrarun.tasks.events import TaskEventBus
from astrarun.tasks.ledger import TaskLedger
from astrarun.tasks.models import Task, TaskEvent, TaskEventType, TaskStatus
from astrarun.tasks.runtime import TaskRuntime
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

    # 1. Instantiate Core Widgets
    hud = FloatingTaskHUD(animations_enabled=False)
    launcher = LauncherWindow(app=astra_app, hud=hud, animations_enabled=False)
    tray = AstraTrayIcon(parent=launcher)

    from astrarun.ui.presentation import LauncherPresentationController
    pres_ctrl = LauncherPresentationController(launcher=launcher, hud=hud, app=astra_app)

    # -------------------------------------------------------------------------
    # Screenshot A: Command Surface — empty
    # -------------------------------------------------------------------------
    print("Generating Screenshot A: Command Surface — empty...")
    pres_ctrl.present()
    launcher.input_field.setText("")
    qapp.processEvents()
    time.sleep(0.1)
    launcher.grab().save(str(out_dir / "screenshot_A_command_surface_empty.png"))
    print("  -> Saved screenshot_A_command_surface_empty.png")

    # -------------------------------------------------------------------------
    # Screenshot B: Command Surface — query entered
    # -------------------------------------------------------------------------
    print("Generating Screenshot B: Command Surface — query entered...")
    launcher.input_field.setText("open calculator")
    qapp.processEvents()
    time.sleep(0.1)
    launcher.grab().save(str(out_dir / "screenshot_B_command_surface_query.png"))
    print("  -> Saved screenshot_B_command_surface_query.png")
    launcher.hide()

    # -------------------------------------------------------------------------
    # Screenshot C: Active Task HUD
    # -------------------------------------------------------------------------
    print("Generating Screenshot C: Active Task HUD...")
    hud.show_progress(
        task_id="task-live-demo-01",
        title="Open Calculator",
        message="Resolving executable and launching workstation application...",
        progress_mode="DETERMINATE",
        progress_pct=65.0,
    )
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_C_active_task_hud.png"))
    print("  -> Saved screenshot_C_active_task_hud.png")

    # -------------------------------------------------------------------------
    # Screenshot D: Expanded Task HUD / Details
    # -------------------------------------------------------------------------
    print("Generating Screenshot D: Expanded Task HUD / Details...")
    hud.set_steps([
        {"step_id": "s1", "description": "Resolve project path (E:\\Workspace\\Active\\AstraRun)", "state": "COMPLETED"},
        {"step_id": "s2", "description": "Execute approved test suite (pytest -k test_user_sid)", "state": "RUNNING"},
        {"step_id": "s3", "description": "Verify zero console windows and check process exit code", "state": "PENDING"},
    ])
    hud.update_step_state("s1", "COMPLETED")
    hud.update_step_state("s2", "RUNNING")
    hud.toggle_steps_expansion()
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_D_expanded_task_hud.png"))
    print("  -> Saved screenshot_D_expanded_task_hud.png")

    # -------------------------------------------------------------------------
    # Screenshot E: Task Center (Populated)
    # -------------------------------------------------------------------------
    print("Generating Screenshot E: Task Center (Populated)...")
    import tempfile
    db_pop_path = Path(tempfile.gettempdir()) / f"_temp_tc_pop_{os.getpid()}.db"
    if db_pop_path.exists():
        try:
            db_pop_path.unlink()
        except Exception:
            pass
    tc_ledger = TaskLedger(str(db_pop_path))
    tc_bus = TaskEventBus()
    tc_runtime = TaskRuntime(event_bus=tc_bus, ledger=tc_ledger)

    # 1. Active Task
    t_act = tc_runtime.create_and_enqueue_task("Generate Windows Battery Health Report")
    t_act.status = TaskStatus.RUNNING
    t_act.events.append(TaskEvent(id="ev-act-1", task_id=t_act.id, type=TaskEventType.CAPABILITY_STARTED, title="Sampling system telemetry via powercfg /batteryreport"))
    tc_ledger.save_task(t_act)

    # 2. Waiting Task
    t_wait = tc_runtime.create_and_enqueue_task("Backup project workspace to external drive")
    t_wait.status = TaskStatus.QUEUED
    t_wait.events.append(TaskEvent(id="ev-wait-1", task_id=t_wait.id, type=TaskEventType.TASK_CREATED, title="Waiting in execution queue (1 ahead)"))
    tc_ledger.save_task(t_wait)

    # 3. Recent Tasks
    t_rec1 = tc_runtime.create_and_enqueue_task("Launch Visual Studio Code in AstraRun directory")
    t_rec1.status = TaskStatus.COMPLETED
    t_rec1.events.append(TaskEvent(id="ev-rec-1", task_id=t_rec1.id, type=TaskEventType.TASK_COMPLETED, title="Application launched successfully (PID 18420)"))
    tc_ledger.save_task(t_rec1)

    t_rec2 = tc_runtime.create_and_enqueue_task("Terminate unresponsive background worker (PID 14280)")
    t_rec2.status = TaskStatus.CANCELLED
    t_rec2.events.append(TaskEvent(id="ev-rec-2", task_id=t_rec2.id, type=TaskEventType.TASK_CANCELLED, title="User cancelled via confirmation dialog"))
    tc_ledger.save_task(t_rec2)

    task_center_pop = TaskCenterWindow(task_runtime=tc_runtime)
    task_center_pop.show()
    task_center_pop.refresh_tasks()
    qapp.processEvents()
    time.sleep(0.1)
    task_center_pop.grab().save(str(out_dir / "screenshot_E_task_center.png"))
    print("  -> Saved screenshot_E_task_center.png")
    task_center_pop.hide()
    tc_ledger.close()

    # -------------------------------------------------------------------------
    # Screenshot F: ActionGate confirmation card
    # -------------------------------------------------------------------------
    print("Generating Screenshot F: ActionGate confirmation card...")
    hud._clear_steps()
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

    # -------------------------------------------------------------------------
    # Screenshot G: Clarification card
    # -------------------------------------------------------------------------
    print("Generating Screenshot G: Clarification card...")
    hud._clear_steps()
    hud.show_clarification(
        task_id="task-clar-01",
        prompt="Multiple projects matching 'Astra' found. Which project would you like to open?",
        candidates=[
            {"title": "AstraRun (Active/AstraRun)", "id": "astrarun"},
            {"title": "Astra-Bridge (Active/AI-Bridge)", "id": "ai-bridge"},
            {"title": "Astra-Mobile (Active/termux-ai)", "id": "termux-ai"},
        ],
    )
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_G_clarification_card.png"))
    print("  -> Saved screenshot_G_clarification_card.png")

    # -------------------------------------------------------------------------
    # Screenshot H: User takeover state
    # -------------------------------------------------------------------------
    print("Generating Screenshot H: User takeover state...")
    hud._clear_steps()
    hud.show_user_takeover(
        task_id="task-takeover-01",
        message="Paused — you're using the computer",
    )
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_H_user_takeover.png"))
    print("  -> Saved screenshot_H_user_takeover.png")

    # -------------------------------------------------------------------------
    # Screenshot I: Completed result state
    # -------------------------------------------------------------------------
    print("Generating Screenshot I: Completed result state...")
    hud._clear_steps()
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

    # -------------------------------------------------------------------------
    # Screenshot J: Tray context menu
    # -------------------------------------------------------------------------
    print("Generating Screenshot J: Tray context menu...")
    tray.set_state(TrayState.READY)
    menu = tray.contextMenu()
    menu.show()
    qapp.processEvents()
    time.sleep(0.1)
    menu.grab().save(str(out_dir / "screenshot_J_tray_menu.png"))
    print("  -> Saved screenshot_J_tray_menu.png")
    menu.hide()

    # -------------------------------------------------------------------------
    # Screenshot K: Task Center Empty State
    # -------------------------------------------------------------------------
    print("Generating Screenshot K: Task Center (Empty State)...")
    db_empty_path = Path(tempfile.gettempdir()) / f"_temp_tc_empty_{os.getpid()}.db"
    if db_empty_path.exists():
        try:
            db_empty_path.unlink()
        except Exception:
            pass
    tc_empty_ledger = TaskLedger(str(db_empty_path))
    tc_empty_runtime = TaskRuntime(event_bus=TaskEventBus(), ledger=tc_empty_ledger)

    task_center_empty = TaskCenterWindow(task_runtime=tc_empty_runtime)
    task_center_empty.show()
    task_center_empty.refresh_tasks()
    qapp.processEvents()
    time.sleep(0.1)
    task_center_empty.grab().save(str(out_dir / "screenshot_K_task_center_empty.png"))
    print("  -> Saved screenshot_K_task_center_empty.png")
    task_center_empty.hide()
    tc_empty_ledger.close()

    # -------------------------------------------------------------------------
    # Screenshot L: Error State
    # -------------------------------------------------------------------------
    print("Generating Screenshot L: Error State...")
    hud._clear_steps()
    hud.show_error(
        task_id="task-err-01",
        message="Process execution failed: Access is denied for protected system service (PID 1024).",
    )
    hud.adjustSize()
    qapp.processEvents()
    time.sleep(0.1)
    hud.card.grab().save(str(out_dir / "screenshot_L_error_state.png"))
    print("  -> Saved screenshot_L_error_state.png")
    hud.hide()

    # Clean up temporary screenshot databases
    for p in (db_pop_path, db_empty_path):
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass

    print("\nALL 12 SCREENSHOTS (A through L) SUCCESSFULLY CAPTURED INTO docs/screenshots/:")
    for f in sorted(out_dir.glob("screenshot_*.png")):
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
