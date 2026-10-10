"""Desktop lifecycle management for AstraRun ComputerUse."""

from __future__ import annotations

import sys
import time
from typing import Any, Dict, List, Optional

from astrarun.capabilities.models import CapabilityResult
from astrarun.core.logging import get_logger
from astrarun.tasks.resource_ledger import AstraResourceLedger, CleanupPolicy, ContentClassification
from astrarun.tools.apps import open_app

logger = get_logger("astrarun.computer_use.desktop.lifecycle")


class DesktopLifecycle:
    """
    Manages desktop application launch, focus, and closure under strict F0-15 ownership invariants.
    """

    def __init__(self, ledger: Optional[AstraResourceLedger] = None) -> None:
        self.ledger = ledger or AstraResourceLedger.get_instance()

    def launch_application(
        self,
        app_name: str,
        path: Optional[str] = None,
        target: Optional[str] = None,
        task_id: Optional[str] = None,
        cleanup_policy: CleanupPolicy = CleanupPolicy.AUTO_CLOSE_ON_COMPLETION,
    ) -> CapabilityResult:
        """Launch application and record ownership in resource ledger."""
        from astrarun.discovery.entity_resolver import SemanticEntityResolver
        resolver = SemanticEntityResolver()
        resolved = resolver.resolve_application(app_name)
        exe_path = resolved.target_path if resolved else path

        # Pre-launch desktop snapshot
        snapshot = self.ledger.capture_pre_launch_snapshot()

        ok = open_app(app=app_name, path=exe_path, target=target)
        if not ok:
            return CapabilityResult.error(f"Failed to launch application '{app_name}'.")

        time.sleep(0.5)

        # Disambiguate newly created process/window
        captured = self.ledger.disambiguate_and_register_launch(
            pre_snapshot=snapshot,
            task_id=task_id or f"task_{int(time.time())}",
            launching_capability="open_application",
            cleanup_policy=cleanup_policy,
            content_classification=ContentClassification.TEMPORARY_TEST_CONTENT if "test" in (task_id or "") else ContentClassification.NONE,
            document_path=target,
        )

        hwnd = captured.hwnd if captured else None
        pid = captured.pid if captured else None

        return CapabilityResult.ok(
            capability="open_application",
            message=f"Launched '{app_name}'.",
            data={
                "app": app_name,
                "path": exe_path,
                "hwnd": hwnd,
                "pid": pid,
                "resource_id": captured.resource_id if captured else None,
            },
        )

    def close_application(self, task_id: str, task_status: str = "COMPLETED") -> CapabilityResult:
        """Clean up only Astra-owned resources for the given task_id."""
        try:
            report = self.ledger.cleanup_task_resources(task_id, task_status)
        except Exception as err:
            return CapabilityResult.fail(
                capability="close_application",
                message=f"Cleanup raised exception: {err}",
                data={"cleanup_exception": str(err), "verdict": "FAIL", "clean": False},
            )
        ok = bool(report.get("clean", False)) and report.get("verdict") == "PASS_CLEAN"
        if ok:
            return CapabilityResult.ok(
                capability="close_application",
                message=(
                    f"Cleaned up task resources: {report['cleaned_count']} closed, "
                    f"{report['detached_count']} detached."
                ),
                data=report,
            )
        return CapabilityResult.fail(
            capability="close_application",
            message=(
                "Cleanup did not verify clean: "
                f"process_cleaned_up={report.get('process_cleaned_up')}, "
                f"remaining_active={report.get('remaining_active_resources')}, "
                f"exception={report.get('cleanup_exception')}"
            ),
            data=report,
        )
