"""Application capability module."""

from astrarun.applications.service import (
    close_application,
    find_application,
    focus_application,
    is_application_running,
    list_running_applications,
    open_application,
)

__all__ = [
    "close_application",
    "find_application",
    "focus_application",
    "is_application_running",
    "list_running_applications",
    "open_application",
]
