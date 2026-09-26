"""Main entry point for AstraRun."""

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

from astrarun.config.loader import load_config
from astrarun.core.logging import get_logger, setup_logging
from astrarun.core.models import RoutingContext
from astrarun.discovery.apps import AppDiscoveryCache
from astrarun.discovery.folders import FolderResolver
from astrarun.hotkeys.manager import HotkeyManager
from astrarun.routing.deterministic import DeterministicRouter
from astrarun.tools.registry import ToolRegistry
from astrarun.ui.launcher import LauncherWindow


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
    """Initialize subsystems, hotkey listener, and Qt event loop."""
    args = parse_args()

    # 1. Load configuration
    config = load_config(args.config_dir)

    # 2. Setup logging
    log_cfg = config.settings.get("logging", {})
    setup_logging(
        log_file=log_cfg.get("file", "logs/astrarun.log"),
        level=log_cfg.get("level", "INFO"),
        max_bytes=int(log_cfg.get("max_bytes", 10_485_760)),
        backup_count=int(log_cfg.get("backup_count", 3)),
    )
    logger = get_logger("astrarun.main")
    logger.info("Initializing AstraRun v0.1...")

    # 3. Discover applications and known folders
    app_cache = AppDiscoveryCache(config.configured_apps)
    folder_resolver = FolderResolver()

    routing_context = RoutingContext(
        apps=app_cache.apps,
        folders=folder_resolver.folders,
        urls=config.urls,
        aliases=config.aliases,
    )

    # 4. Initialize router and tool registry
    router = DeterministicRouter()
    registry = ToolRegistry()

    # Headless CLI command execution mode
    if args.run_command:
        logger.info("Headless command execution mode: '%s'", args.run_command)
        decision = router.route(args.run_command, routing_context)
        success, message = registry.execute(decision)
        logger.info("Result: success=%s, message='%s'", success, message)
        print(f"[{'SUCCESS' if success else 'FAILURE'}] {message}")
        return 0 if success else 1

    # 5. Initialize PySide6 GUI Application
    app = QApplication(sys.argv)
    app.setApplicationName("AstraRun")
    app.setOrganizationName("Astra")
    # AstraRun runs resident in background; do not quit when launcher is hidden
    app.setQuitOnLastWindowClosed(False)

    # 6. Instantiate Launcher Window (pre-warmed)
    launcher = LauncherWindow(
        router=router,
        registry=registry,
        context=routing_context,
        settings=config.settings,
    )

    # 7. Setup Global Hotkey Manager
    hotkey_cfg = config.settings.get("hotkey", {})
    modifiers = hotkey_cfg.get("modifiers", ["Alt"])
    key = hotkey_cfg.get("key", "Space")

    hotkey_manager = HotkeyManager(config_modifiers=modifiers, config_key=key)
    hotkey_manager.hotkey_activated.connect(launcher.toggle_visibility)

    def on_hotkey_error(err_msg: str):
        logger.warning("Hotkey registration issue: %s", err_msg)
        # Show window immediately if hotkey could not be bound so user knows AstraRun started
        launcher.show_and_activate()
        launcher.show_feedback("Hotkey conflict: check logs/astrarun.log", is_error=True)

    hotkey_manager.error_occurred.connect(on_hotkey_error)
    hotkey_manager.start()

    # Clean shutdown hook
    def cleanup():
        logger.info("AstraRun shutting down...")
        hotkey_manager.stop()

    app.aboutToQuit.connect(cleanup)

    # Allow Ctrl+C to terminate from console cleanly
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())

    # Heartbeat timer to allow Python signal handlers to run in Qt loop
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(500)

    if args.show_now:
        launcher.show_and_activate()

    logger.info("AstraRun is resident and listening for %s+%s.", "+".join(modifiers), key)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
