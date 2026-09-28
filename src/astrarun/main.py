"""Main entry point for AstraRun Resident Service & Daily Driver."""

from __future__ import annotations

import argparse
import json
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

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from astrarun import __version__
from astrarun.app import AstraApplication, SingleInstanceLock
from astrarun.core.logging import get_logger, setup_logging
from astrarun.hotkeys.manager import HotkeyManager
from astrarun.ui.hud import FloatingTaskHUD, TaskHUDController
from astrarun.ui.launcher import LauncherWindow
from astrarun.ui.presentation import LauncherPresentationController
from astrarun.ui.tray import AstraTrayIcon


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="AstraRun - Windows Intelligent Command Launcher")
    parser.add_argument(
        "--config-dir",
        type=str,
        default="config",
        help="Path to configuration directory (default: config)",
    )
    parser.add_argument(
        "--run-command",
        type=str,
        default=None,
        help="Execute a single command headless and exit (useful for integration testing)",
    )
    parser.add_argument(
        "--show-now",
        action="store_true",
        help="Immediately show the launcher window upon launch instead of waiting for hotkey",
    )
    return parser.parse_args()


def write_state_file(
    status: str,
    ready: bool,
    stage: str,
    modifiers: list[str] | None = None,
    key: str = "Space",
    exit_code: int | None = None,
    started_at: str | None = None,
) -> None:
    """Write machine-readable runtime state file for wrapper process verification."""
    try:
        os.makedirs("data", exist_ok=True)
        state_path = Path("data/astrarun_state.json")
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
            "stage": stage,
            "exit_code": exit_code,
        }
        tmp_path = Path(f"data/astrarun_state_{os.getpid()}.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2)
        tmp_path.replace(state_path)
    except Exception as err:
        logging.getLogger("astrarun.main").warning("Could not write state file: %s", err)


def main() -> int:
    """Initialize composition root, single-instance enforcement, tray, hotkeys, and Qt event loop."""
    start_iso = datetime.now().isoformat()
    args = parse_args()

    # 1. Setup logging first to ensure all subsequent stages are captured
    astra_app = AstraApplication(config_dir=args.config_dir)
    log_cfg = astra_app.settings.get("logging", {})
    setup_logging(
        log_file=log_cfg.get("file", "logs/astrarun.log"),
        level=log_cfg.get("level", "INFO"),
        max_bytes=int(log_cfg.get("max_bytes", 10_485_760)),
        backup_count=int(log_cfg.get("backup_count", 3)),
    )
    logger = get_logger("astrarun.main")

    # Global uncaught exception logger to guard pythonw.exe silent exits
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Uncaught exception in AstraRun main process:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception

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
        logger.warning("[STARTUP_STAGE] SINGLE_INSTANCE_FAILED. Another instance is active. Exiting cleanly.")
        print("[ASTRARUN] Another instance of AstraRun is already running. Exiting.")
        return 0
    logger.info("[STARTUP_STAGE] SINGLE_INSTANCE_ACQUIRED (mutex=%s)", astra_app.single_instance.mutex_name)

    # 4. Initialize PySide6 GUI Application
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("AstraRun")
    qapp.setOrganizationName("Astra")
    # AstraRun runs resident in background; do not quit when launcher is hidden
    qapp.setQuitOnLastWindowClosed(False)
    logger.info("[STARTUP_STAGE] QT_APPLICATION_CREATED (quitOnLastWindowClosed=False)")

    # 5. Instantiate Floating Task HUD & HUD Controller
    hud = FloatingTaskHUD()
    hud_controller = TaskHUDController(hud=hud, event_bus=astra_app.task_event_bus, app=astra_app)
    logger.info("[STARTUP_STAGE] HUD_CREATED")

    # 6. Instantiate Launcher Window (Top-Center Floating Command Bar)
    launcher = LauncherWindow(app=astra_app, hud=hud)
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
    tray_icon.toggle_launcher_requested.connect(presentation_controller.toggle_presentation)
    tray_icon.open_history_requested.connect(launcher.open_history)
    tray_icon.open_memory_requested.connect(launcher.open_memory)
    tray_icon.open_skills_requested.connect(launcher.open_skills)
    tray_icon.open_settings_requested.connect(launcher.open_settings)
    tray_icon.open_diagnostics_requested.connect(launcher.open_diagnostics)
    tray_icon.exit_requested.connect(qapp.quit)
    tray_icon.show()
    astra_app.tray_icon = tray_icon  # type: ignore
    logger.info("[STARTUP_STAGE] TRAY_CREATED (tooltip='%s')", tray_icon.toolTip())

    # 9. Wire up Hotkey Manager to Presentation Controller
    hotkey_manager.hotkey_activated.connect(presentation_controller.toggle_presentation)

    def on_hotkey_error(err_msg: str):
        logger.warning("Hotkey registration issue: %s", err_msg)
        presentation_controller.present()
        launcher.show_feedback("Hotkey conflict: check logs/astrarun.log", is_error=True)

    hotkey_manager.error_occurred.connect(on_hotkey_error)
    hotkey_manager.start()
    logger.info("[STARTUP_STAGE] HOTKEY_REGISTERED (%s+%s)", "+".join(modifiers), key)

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
            astra_app.shutdown()
            # Clean up state file on normal exit
            state_path = Path("data/astrarun_state.json")
            if state_path.exists():
                state_path.unlink(missing_ok=True)
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
