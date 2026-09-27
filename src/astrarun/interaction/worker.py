"""Background COM worker thread isolating UI Automation from the PySide6 UI event loop."""

from __future__ import annotations

import concurrent.futures
import queue
import sys
import threading
from typing import Any, Callable, Optional

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.interaction.worker")


class UIAutomationWorker:
    """
    Dedicated worker thread managing COM MTA apartment lifecycle.
    Prevents deep UI Automation tree inspections from blocking the PySide6 main event loop.
    """

    def __init__(self) -> None:
        self._work_queue: queue.Queue = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the background COM worker thread if not already running."""
        with self._lock:
            if self._running and self._thread and self._thread.is_alive():
                return

            self._running = True
            self._thread = threading.Thread(target=self._worker_loop, name="UIAutomationWorker", daemon=True)
            self._thread.start()
            logger.info("UIAutomationWorker thread started.")

    def stop(self) -> None:
        """Signal worker thread to shut down and uninitialize COM."""
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._work_queue.put(None)  # Sentinel to wake up queue

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            logger.info("UIAutomationWorker thread stopped.")

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> concurrent.futures.Future:
        """Submit a task to be executed on the COM worker thread."""
        self.start()
        future: concurrent.futures.Future = concurrent.futures.Future()
        self._work_queue.put((future, fn, args, kwargs))
        return future

    def _worker_loop(self) -> None:
        """Thread main loop initializing COM and processing queued automation tasks."""
        if sys.platform == "win32":
            try:
                import comtypes
                comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
            except Exception as e:
                logger.debug("COM initialization in worker: %s", e)

        try:
            while self._running:
                try:
                    item = self._work_queue.get(timeout=0.2)
                except queue.Empty:
                    continue

                if item is None:
                    break

                future, fn, args, kwargs = item
                if future.cancelled():
                    continue

                try:
                    result = fn(*args, **kwargs)
                    future.set_result(result)
                except Exception as ex:
                    logger.error("Error executing task in UIAutomationWorker: %s", ex, exc_info=True)
                    future.set_exception(ex)
                finally:
                    self._work_queue.task_done()
        finally:
            if sys.platform == "win32":
                try:
                    import comtypes
                    comtypes.CoUninitialize()
                except Exception:
                    pass
            logger.debug("UIAutomationWorker thread exited cleanly.")


# Global singleton instance
_GLOBAL_WORKER: Optional[UIAutomationWorker] = None
_WORKER_LOCK = threading.Lock()


def get_ui_worker() -> UIAutomationWorker:
    """Retrieve the global UIAutomationWorker singleton."""
    global _GLOBAL_WORKER
    with _WORKER_LOCK:
        if _GLOBAL_WORKER is None:
            _GLOBAL_WORKER = UIAutomationWorker()
        return _GLOBAL_WORKER
