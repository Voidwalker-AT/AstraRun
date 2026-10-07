"""Main entry point for AstraRun Resident Service & Daily Driver."""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure src/ is on sys.path for direct script invocation
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from astrarun import __version__
from astrarun.app import AstraApplication
from astrarun.core.logging import get_logger, setup_logging
from astrarun.hotkeys.manager import HotkeyManager
from astrarun.tasks.models import TaskEventType, TaskStatus
from astrarun.ui.hud import FloatingTaskHUD, TaskHUDController
from astrarun.ui.launcher import LauncherWindow
from astrarun.ui.presentation import LauncherPresentationController
from astrarun.ui.tray import AstraTrayIcon, TrayState


def parse_args() -> argparse.Namespace:
    """Parse command line arguments with resilient fallback for background/autostart."""
    parser = argparse.ArgumentParser(description="AstraRun - Windows Intelligent Command Launcher")
    parser.add_argument(
        "--config-dir",
        type=str,
        default="config",
        help="Path to configuration directory (default: config)",
    )
    parser.add_argument(
        "--run-command",
        nargs="*",
        default=None,
        help="Execute a single command headless and exit (useful for integration testing)",
    )
    parser.add_argument(
        "--show-now",
        action="store_true",
        help="Immediately show the launcher window upon launch instead of waiting for hotkey",
    )
    parser.add_argument(
        "--background",
        action="store_true",
        help="Run resident in system tray waiting for global summon hotkey",
    )
    parser.add_argument(
        "--first-run",
        action="store_true",
        help="Launch the first-run configuration wizard",
    )
    parsed, _ = parser.parse_known_args()
    if isinstance(parsed.run_command, list):
        parsed.run_command = " ".join(parsed.run_command) if parsed.run_command else None
    return parsed


def summon_existing_instance() -> bool:
    """If another AstraRun instance is already active, signal its launcher window to summon."""
    from astrarun.core.paths import AstraPaths
    # 1. Primary trigger file mechanism (works across all session & UIPI boundaries)
    try:
        trigger_path = AstraPaths.summon_trigger_path()
        trigger_path.parent.mkdir(parents=True, exist_ok=True)
        trigger_path.write_text(f"{time.time()}", encoding="utf-8")
    except Exception as err:
        logging.getLogger("astrarun.main").debug("Could not write summon trigger: %s", err)

    # 2. Win32 window message & foreground activation
    if sys.platform == "win32":
        state_path = AstraPaths.state_file_path()
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                launcher_hwnd = data.get("launcher_hwnd")
                if launcher_hwnd and ctypes.windll.user32.IsWindow(launcher_hwnd):
                    WM_ASTRARUN_SUMMON = ctypes.windll.user32.RegisterWindowMessageW("AstraRun_Summon_Message")
                    ctypes.windll.user32.PostMessageW(launcher_hwnd, WM_ASTRARUN_SUMMON, 0, 0)
                    from astrarun.ui.presentation import force_foreground_activation
                    force_foreground_activation(launcher_hwnd)
            except Exception as err:
                logging.getLogger("astrarun.main").debug("Could not signal window message: %s", err)
    return True


def write_state_file(
    status: str,
    ready: bool,
    stage: str,
    modifiers: list[str] | None = None,
    key: str = "Space",
    exit_code: int | None = None,
    started_at: str | None = None,
    launcher_hwnd: int | None = None,
) -> None:
    """Write machine-readable runtime state file for wrapper process verification."""
    from astrarun.core.paths import AstraPaths
    try:
        state_path = AstraPaths.state_file_path()
        state_path.parent.mkdir(parents=True, exist_ok=True)
        hk_str = f"{'+'.join(modifiers)}+{key}" if modifiers else "Alt+Space"
        state_data = {
            "pid": os.getpid(),
            "version": __version__,
            "status": status,
            "ready": ready,
            "timestamp": time.time(),
            "started_at": started_at or datetime.now().isoformat(),
            "hotkey": hk_str,
            "tray": True,
            "launcher_hwnd": launcher_hwnd,
            "stage": stage,
            "exit_code": exit_code,
        }
        tmp_path = AstraPaths.data_dir() / f"astrarun_state_{os.getpid()}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2)
        tmp_path.replace(state_path)
    except Exception as err:
        logging.getLogger("astrarun.main").warning("Could not write state file: %s", err)


def main() -> int:
    """Initialize composition root, single-instance enforcement, tray, hotkeys, and Qt event loop."""
    # 0. Check for isolated child subsystem worker execution mode first (bypasses Qt & mutex)
    if "--worker-type" in sys.argv:
        idx = sys.argv.index("--worker-type")
        worker_type = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        if worker_type == "laya":
            from astrarun.routing.laya_worker import run_worker_loop
            return run_worker_loop()

    # Dedicated Uninstaller UI dispatch (invoked by Inno Setup uninstaller)
    if "--uninstall-ui" in sys.argv:
        from astrarun.ui.uninstall_wizard import run_uninstall_ui
        return run_uninstall_ui()

    # Lightweight Repair CLI execution mode
    if "--repair" in sys.argv:
        from astrarun.lifecycle.repair import RepairManager
        mgr = RepairManager()
        rep = mgr.run_all_repairs()
        status_tag = "SUCCESS" if rep.success else "WARNING"
        print(f"[{status_tag}] {rep.summary}")
        for item in rep.items:
            print(f"  • {item.name}: [{item.status}] {item.detail}")
        return 0 if rep.success else 1

    start_iso = datetime.now().isoformat()
    args = parse_args()

    # 1. Setup logging first to ensure all subsequent stages are captured
    from astrarun.core.paths import AstraPaths
    effective_log_file = str(AstraPaths.logs_dir() / "astrarun.log")

    setup_logging(
        log_file=effective_log_file,
        level="INFO",
        max_bytes=10_485_760,
        backup_count=3,
    )
    logger = get_logger("astrarun.main")

    # Install sanitized crash diagnostics and detect prior abnormal terminations
    from astrarun.core.crash import detect_previous_abnormal_termination, install_crash_handler
    install_crash_handler()
    recovery = detect_previous_abnormal_termination()
    if recovery:
        logger.info("[STARTUP_STAGE] CRASH_RECOVERY_PROCESSED (prior_pid=%s, last_op=%s)",
                    recovery.get("prior_pid"), recovery.get("last_operation"))

    astra_app = AstraApplication(config_dir=args.config_dir)

    logger.info("[STARTUP_STAGE] STARTUP_BEGIN (PID=%d, version=%s)", os.getpid(), __version__)
    logger.info("Initializing AstraRun v%s (Real Alt+Space Launcher)... PID=%d", __version__, os.getpid())

    # 2. Headless CLI command execution mode
    if args.run_command:
        logger.info("Headless command execution mode: '%s'", args.run_command)
        res = astra_app.handle_request(args.run_command)
        status_tag = "SUCCESS" if res.success else "FAILURE"
        logger.info("Result: %s -> %s", status_tag, res.message)
        print(f"[{status_tag}] {res.message}")
        astra_app.shutdown()
        return 0 if res.success else 1

    # 3. Single-Instance Enforcement
    if not astra_app.single_instance.acquire():
        logger.warning("[STARTUP_STAGE] SINGLE_INSTANCE_FAILED. Another instance is active. Summoning existing launcher...")
        try:
            astra_app.single_instance.send_command("SHOW_MAIN_UI")
        except Exception as ipc_err:
            logger.debug("IPC summon failed: %s", ipc_err)
        summon_existing_instance()
        print("[ASTRARUN] Another instance of AstraRun is already running. Summoned existing launcher.")
        return 0
    logger.info("[STARTUP_STAGE] SINGLE_INSTANCE_ACQUIRED (mutex=%s)", astra_app.single_instance.mutex_name)

    # 4. Initialize PySide6 GUI Application
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("AstraRun")
    qapp.setOrganizationName("Astra")
    # AstraRun runs resident in background; do not quit when launcher is hidden
    qapp.setQuitOnLastWindowClosed(False)
    logger.info("[STARTUP_STAGE] QT_APPLICATION_CREATED (quitOnLastWindowClosed=False)")

    # 4b. First-Run Setup Experience
    from astrarun.ui.first_run import is_first_run_completed, FirstRunWizard
    if not is_first_run_completed() and not args.run_command:
        logger.info("[STARTUP_STAGE] FIRST_RUN_WIZARD_SUMMONED")
        wizard = FirstRunWizard()
        wizard.exec()

    # 4c. Initialize Windows Power and Session Lifecycle Subsystem
    from astrarun.power.listener import QtPowerNativeEventFilter, register_power_notifications
    from astrarun.power.manager import PowerLifecycleManager
    power_manager = PowerLifecycleManager.get_instance()
    if QtPowerNativeEventFilter:
        power_native_filter = QtPowerNativeEventFilter()
        qapp.installNativeEventFilter(power_native_filter)
        logger.info("[STARTUP_STAGE] POWER_EVENT_FILTER_INSTALLED")

    # 5. Instantiate Floating Task HUD & HUD Controller
    hud = FloatingTaskHUD()
    hud_controller = TaskHUDController(
        hud=hud,
        event_bus=astra_app.task_event_bus,
        app=astra_app,
        task_runtime=getattr(astra_app, "task_runtime", None),
    )
    logger.info("[STARTUP_STAGE] HUD_CREATED")

    # 6. Instantiate Launcher Window (Top-Center Floating Command Bar)
    launcher = LauncherWindow(app=astra_app, hud=hud)
    if sys.platform == "win32":
        register_power_notifications(int(launcher.winId()))
    logger.info("[STARTUP_STAGE] LAUNCHER_CREATED")

    # 7. Setup Global Hotkey Manager & Presentation Controller
    hotkey_cfg = astra_app.settings.get("hotkey", {})
    modifiers = hotkey_cfg.get("modifiers", ["Alt"])
    key = hotkey_cfg.get("key", "Space")

    hotkey_manager = HotkeyManager(config_modifiers=modifiers, config_key=key)
    presentation_controller = LauncherPresentationController(
        launcher=launcher,
        hud=hud,
        app=astra_app,
        hotkey_manager=hotkey_manager,
    )
    logger.info("[STARTUP_STAGE] HOTKEY_MANAGER_CREATED")

    # Retain strong references on composition root to prevent GC
    astra_app.launcher = launcher  # type: ignore
    astra_app.hud = hud  # type: ignore
    astra_app.hud_controller = hud_controller  # type: ignore
    astra_app.presentation_controller = presentation_controller  # type: ignore
    astra_app.hotkey_manager = hotkey_manager  # type: ignore

    # 8. Instantiate System Tray Icon
    tray_icon = AstraTrayIcon(parent=launcher)
    tray_icon.open_astra_requested.connect(presentation_controller.toggle_presentation)
    tray_icon.open_task_center_requested.connect(launcher.open_task_center)
    tray_icon.open_history_requested.connect(launcher.open_history)
    tray_icon.open_memory_requested.connect(launcher.open_memory)
    tray_icon.open_skills_requested.connect(launcher.open_skills)
    tray_icon.open_settings_requested.connect(launcher.open_settings)
    tray_icon.open_diagnostics_requested.connect(launcher.open_diagnostics)
    tray_icon.exit_requested.connect(qapp.quit)

    def on_tray_pause():
        if hasattr(astra_app, "task_runtime"):
            for t in astra_app.task_runtime.get_recent_tasks(limit=10):
                if not t.status.is_terminal and t.status.is_active:
                    astra_app.task_runtime.pause_task(t.id)

    def on_tray_resume():
        if hasattr(astra_app, "task_runtime"):
            for t in astra_app.task_runtime.get_recent_tasks(limit=10):
                if t.status in (TaskStatus.PAUSED, TaskStatus.PAUSED_USER_ACTIVE):
                    astra_app.task_runtime.resume_task(t.id)

    tray_icon.pause_astra_requested.connect(on_tray_pause)
    tray_icon.resume_astra_requested.connect(on_tray_resume)

    def on_tray_task_event(event: Any):
        ev_type = getattr(event, "type", None) or getattr(event, "event_type", None)
        if ev_type in (TaskEventType.TASK_CREATED, TaskEventType.CAPABILITY_STARTED):
            tray_icon.set_state(TrayState.WORKING)
        elif ev_type in (TaskEventType.CONFIRMATION_REQUESTED, TaskEventType.ACTION_GATE_CONFIRM, TaskEventType.CLARIFICATION_REQUESTED):
            tray_icon.set_state(TrayState.ATTENTION_REQUIRED)
        elif ev_type in (TaskEventType.TASK_INTERRUPTED, getattr(TaskEventType, "TASK_PAUSED", "TASK_PAUSED")):
            tray_icon.set_state(TrayState.PAUSED)
        elif ev_type in (TaskEventType.TASK_COMPLETED, TaskEventType.WORKFLOW_COMPLETED):
            tray_icon.set_state(TrayState.READY)
        elif ev_type in (TaskEventType.TASK_FAILED, TaskEventType.TASK_BLOCKED):
            tray_icon.set_state(TrayState.ERROR)

    astra_app.task_event_bus.subscribe(lambda ev: QTimer.singleShot(0, lambda: on_tray_task_event(ev)))

    def handle_restart():
        logger.info("[LIFECYCLE] Restart requested via tray menu / IPC. Releasing mutex and spawning fresh resident process...")
        try:
            if hasattr(astra_app, "single_instance") and astra_app.single_instance:
                astra_app.single_instance.release()
            import subprocess
            DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            if getattr(sys, "frozen", False):
                cmd = [sys.executable, "--background"]
                cwd = str(Path(sys.executable).parent)
            else:
                venv_pythonw = sys.executable
                main_script = str(Path(__file__).resolve())
                cmd = [venv_pythonw, main_script]
                cwd = str(Path(__file__).resolve().parent.parent.parent)
            subprocess.Popen(
                cmd,
                cwd=cwd,
                creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
                close_fds=True,
            )
        except Exception as err:
            logger.error("Failed to spawn restart process: %s", err)
        qapp.quit()

    tray_icon.restart_requested.connect(handle_restart)
    tray_icon.show()
    astra_app.tray_icon = tray_icon  # type: ignore
    logger.info("[STARTUP_STAGE] TRAY_CREATED (tooltip='%s')", tray_icon.toolTip())

    # 8b. Dedicated thread-safe IPC Signal Bridge
    class IPCSignalBridge(QObject):
        show_ui_requested = Signal()
        task_center_requested = Signal()
        pause_requested = Signal()
        resume_requested = Signal()
        restart_requested = Signal()
        submit_query_requested = Signal(str)
        populate_query_requested = Signal(str)
        quit_requested = Signal()

    ipc_bridge = IPCSignalBridge(parent=launcher)
    ipc_bridge.show_ui_requested.connect(presentation_controller.present)
    ipc_bridge.task_center_requested.connect(launcher.open_task_center)
    ipc_bridge.pause_requested.connect(on_tray_pause)
    ipc_bridge.resume_requested.connect(on_tray_resume)
    ipc_bridge.restart_requested.connect(handle_restart)
    def on_ipc_query(query: str):
        launcher.input_field.setText(query)
        launcher.execute_command()
    def on_ipc_populate(query: str):
        launcher.input_field.setText(query)
        presentation_controller.present()
    ipc_bridge.submit_query_requested.connect(on_ipc_query)
    ipc_bridge.populate_query_requested.connect(on_ipc_populate)
    ipc_bridge.quit_requested.connect(qapp.quit)
    astra_app.ipc_bridge = ipc_bridge  # type: ignore

    # Start local IPC server on primary instance
    def handle_ipc_command(command: str, args: dict) -> dict:
        logger.info("[IPC] Received local command: %s", command)
        cmd_upper = command.upper()
        if cmd_upper in ("SHOW_MAIN_UI", "ACTIVATE", "SUMMON"):
            ipc_bridge.show_ui_requested.emit()
            return {"action": "SHOW_MAIN_UI_TRIGGERED"}
        elif cmd_upper in ("SHOW_TASK_CENTER", "TASK_CENTER"):
            ipc_bridge.task_center_requested.emit()
            return {"action": "SHOW_TASK_CENTER_TRIGGERED"}
        elif cmd_upper == "PAUSE":
            ipc_bridge.pause_requested.emit()
            return {"action": "PAUSE_TRIGGERED"}
        elif cmd_upper == "RESUME":
            ipc_bridge.resume_requested.emit()
            return {"action": "RESUME_TRIGGERED"}
        elif cmd_upper == "RESTART":
            ipc_bridge.restart_requested.emit()
            return {"action": "RESTART_TRIGGERED"}
        elif cmd_upper in ("POPULATE_QUERY", "SET_QUERY"):
            query = args.get("query", "")
            ipc_bridge.populate_query_requested.emit(query)
            return {"action": "QUERY_POPULATED", "query": query}
        elif cmd_upper in ("SUBMIT_QUERY", "EXECUTE_COMMAND", "EXECUTE"):
            query = args.get("query", "")
            ipc_bridge.submit_query_requested.emit(query)
            return {"action": "QUERY_SUBMITTED", "query": query}
        elif cmd_upper in ("QUIT", "EXIT"):
            ipc_bridge.quit_requested.emit()
            return {"action": "QUIT_TRIGGERED"}
        return {"status": "UNKNOWN_COMMAND", "command": command}

    astra_app.single_instance.start_ipc_server(handle_ipc_command)

    # 9. Wire up Hotkey Manager to Presentation Controller
    hotkey_manager.hotkey_activated.connect(presentation_controller.toggle_presentation)

    def on_hotkey_registered(shortcut: str):
        tray_icon.setToolTip(f"AstraRun — Ready ({shortcut})")
        logger.info("[STARTUP_STAGE] HOTKEY_REGISTERED (%s)", shortcut)

    hotkey_manager.hotkey_registered.connect(on_hotkey_registered)

    conflict_dialog_holder = [None]

    def on_hotkey_conflict(shortcut: str, code: int, desc: str):
        logger.warning("[HOTKEY_CONFLICT_TRIGGERED] %s (code=%d, %s)", shortcut, code, desc)
        tray_icon.setToolTip(f"AstraRun — Shortcut Conflict ({shortcut})")
        from astrarun.ui.hotkey_conflict import HotkeyConflictDialog
        if conflict_dialog_holder[0] is None or not conflict_dialog_holder[0].isVisible():
            dlg = HotkeyConflictDialog(
                hotkey_manager=hotkey_manager,
                failed_shortcut=shortcut,
                parent=None,
                on_settings_callback=launcher.open_settings,
            )
            def on_rebound(mods, k):
                astra_app.settings.setdefault("hotkey", {})["modifiers"] = mods
                astra_app.settings["hotkey"]["key"] = k
                tray_icon.setToolTip(f"AstraRun — Ready ({hotkey_manager.shortcut_name})")
            dlg.rebound_applied.connect(on_rebound)
            conflict_dialog_holder[0] = dlg
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

    hotkey_manager.hotkey_conflict.connect(on_hotkey_conflict)

    reg_ok = hotkey_manager.start()
    if not reg_ok:
        logger.warning(
            "[STARTUP_STAGE] HOTKEY_REGISTRATION_FAILED (%s, code=%d)",
            hotkey_manager.shortcut_name, hotkey_manager.last_error_code
        )

    # 10. Clean shutdown hook
    def cleanup():
        logger.info("[SHUTDOWN_STAGE] SHUTDOWN_REQUESTED (reason='aboutToQuit')")
        try:
            write_state_file(
                status="STOPPED",
                ready=False,
                stage="SHUTDOWN_COMPLETED",
                modifiers=modifiers,
                key=key,
                exit_code=0,
                started_at=start_iso,
            )
            hotkey_manager.stop()
            hud_controller.stop()
            hud.hide()
            tray_icon.hide()
            power_manager.handle_session_end()
            astra_app.shutdown()
            # Clean up state file on normal exit ONLY if it belongs to current process
            state_path = AstraPaths.state_file_path()
            if state_path.exists():
                try:
                    with open(state_path, "r", encoding="utf-8") as f:
                        cur_data = json.load(f)
                    if cur_data.get("pid") == os.getpid():
                        state_path.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            logger.error("Error during cleanup: %s", e)

    qapp.aboutToQuit.connect(cleanup)

    # Allow Ctrl+C to terminate from console cleanly
    signal.signal(signal.SIGINT, lambda *_: qapp.quit())
    signal.signal(signal.SIGTERM, lambda *_: qapp.quit())

    # Heartbeat timer to allow Python signal handlers to run in Qt loop
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(500)
    astra_app.heartbeat = heartbeat  # type: ignore

    # Setup cross-process summon trigger watcher
    trigger_path = AstraPaths.summon_trigger_path()
    trigger_path.parent.mkdir(parents=True, exist_ok=True)
    if not trigger_path.exists():
        trigger_path.touch()

    summon_watcher = QFileSystemWatcher([str(trigger_path.resolve())])

    def on_trigger_summon(path: str):
        logger.info("[SUMMON] Summon trigger received from external process: %s", path)
        presentation_controller.present()
        if str(trigger_path.resolve()) not in summon_watcher.files():
            summon_watcher.addPath(str(trigger_path.resolve()))

    summon_watcher.fileChanged.connect(on_trigger_summon)
    astra_app.summon_watcher = summon_watcher  # type: ignore

    if args.show_now:
        presentation_controller.present()

    # 11. Write readiness state file and log stage entering event loop
    logger.info("[STARTUP_STAGE] EVENT_LOOP_ENTERING")
    write_state_file(
        status="READY",
        ready=True,
        stage="EVENT_LOOP_ENTERING",
        modifiers=modifiers,
        key=key,
        started_at=start_iso,
        launcher_hwnd=int(launcher.winId()) if sys.platform == "win32" else None,
    )

    logger.info(
        "AstraRun v%s is resident and listening for %s+%s. (PID=%d)",
        __version__,
        "+".join(modifiers),
        key,
        os.getpid(),
    )
    exit_code = qapp.exec()
    logger.info("[SHUTDOWN_STAGE] EVENT_LOOP_EXITED (code=%d)", exit_code)
    logger.info("[SHUTDOWN_STAGE] PROCESS_EXIT_CODE: %d", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
