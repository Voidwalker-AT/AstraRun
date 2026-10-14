"""UI Automation package for AstraRun ComputerUse."""

from __future__ import annotations

from astrarun.computer_use.ui.automation import UIAutomationDriver
from astrarun.computer_use.ui.editable_surface import (
    EditableSurface,
    SelectionObservation,
    discover_editable_surface,
    observe_surface_selection,
    verify_select_all_predicate,
)

__all__ = [
    "UIAutomationDriver",
    "EditableSurface",
    "SelectionObservation",
    "discover_editable_surface",
    "observe_surface_selection",
    "verify_select_all_predicate",
]
