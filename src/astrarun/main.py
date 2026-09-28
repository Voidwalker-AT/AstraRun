"""Main entry point for AstraRun v0.9 Daily Driver & Window Intelligence."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

# Ensure src/ is on sys.path for direct script invocation
SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

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


def main() -> int:
    """Initialize composition root, single-instance enforcement, tray, hotkeys, and Qt event loop."""
    args = parse_args()

    # 1. Instantiate Application Composition Root
    astra_app = AstraApplication(config_dir=args.config_dir)

    # 2. Setup logging
    log_cfg = astra_app.settings.get("logging", {})
    setup_logging(
        log_file=log_cfg.get("file", "logs/astrarun.log"),
        level=log_cfg.get("level", "INFO"),
        max_bytes=int(log_cfg.get("max_bytes", 10_485_760)),
        backup_count=int(log_cfg.get("backup_count", 3)),
    )
    logger = get_logger("astrarun.main")
    logger.info("Initializing AstraRun v0.10.1 (Real Alt+Space Launcher & Floating Task HUD)...")

    # 3. Headless CLI command execution mode
    if args.run_command:
        logger.info("Headless command execution mode: '%s'", args.run_command)
        res = astra_app.handle_request(args.run_command)
        status_tag = "SUCCESS" if res.success else "FAILURE"
        logger.info("Result: %s -> %s", status_tag, res.message)
        print(f"[{status_tag}] {res.message}")
        astra_app.shutdown()
        return 0 if res.success else 1

    # 4. Single-Instance Enforcement
    if not astra_app.single_instance.acquire():
        logger.warning("Another instance of AstraRun is already running. Exiting cleanly.")
        print("[ASTRARUN] Another instance of AstraRun is already running. Exiting.")
        return 0

    # 5. Initialize PySide6 GUI Application
    qapp = QApplication(sys.argv)
    qapp.setApplicationName("AstraRun")
    qapp.setOrganizationName("Astra")
    # AstraRun runs resident in background; do not quit when launcher is hidden
    qapp.setQuitOnLastWindowClosed(False)

    # 6. Instantiate Floating Task HUD & HUD Controller
    hud = FloatingTaskHUD()
    hud_controller = TaskHUDController(hud=hud, event_bus=astra_app.task_event_bus, app=astra_app)

    # 7. Instantiate Launcher Window (Top-Center Floating Command Bar)
    launcher = LauncherWindow(app=astra_app, hud=hud)

    # 8. Setup Global Hotkey Manager & Presentation Controller
    hotkey_cfg = astra_app.settings.get("hotkey", {})
    modifiers = hotkey_cfg.get("modifiers", ["Alt"])
    key = hotkey_cfg.get("key", "Space")

    hotkey_manager = HotkeyManager(config_modifiers=modifiers, config_key=key)
    astra_app.hotkey_manager = hotkey_manager  # type: ignore

    presentation_controller = LauncherPresentationController(
        launcher=launcher,
        hud=hud,
        app=astra_app,
        hotkey_manager=hotkey_manager,
    )
    astra_app.presentation_controller = presentation_controller  # type: ignore

    # 9. Instantiate System Tray Icon
    tray_icon = AstraTrayIcon(parent=launcher)
    tray_icon.toggle_launcher_requested.connect(presentation_controller.toggle_presentation)
    tray_icon.open_history_requested.connect(launcher.open_history)
    tray_icon.open_memory_requested.connect(launcher.open_memory)
    tray_icon.open_skills_requested.connect(launcher.open_skills)
    tray_icon.open_settings_requested.connect(launcher.open_settings)
    tray_icon.open_diagnostics_requested.connect(launcher.open_diagnostics)
    tray_icon.exit_requested.connect(qapp.quit)
    tray_icon.show()

    # 10. Wire up Hotkey Manager to Presentation Controller
    hotkey_manager.hotkey_activated.connect(presentation_controller.toggle_presentation)

    def on_hotkey_error(err_msg: str):
        logger.warning("Hotkey registration issue: %s", err_msg)
        presentation_controller.present()
        launcher.show_feedback("Hotkey conflict: check logs/astrarun.log", is_error=True)

    hotkey_manager.error_occurred.connect(on_hotkey_error)
    hotkey_manager.start()

    # Clean shutdown hook
    def cleanup():
        logger.info("AstraRun shutting down...")
        try:
            hotkey_manager.stop()
            hud_controller.stop()
            hud.hide()
            tray_icon.hide()
            astra_app.shutdown()
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

    if args.show_now:
        presentation_controller.present()

    logger.info("AstraRun v0.10.1 is resident and listening for %s+%s.", "+".join(modifiers), key)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
