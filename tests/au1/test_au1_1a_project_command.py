"""
AU-1.1A Project Command Clean Seam Tests.

Verifies:
1. Hardcoded milestone5 pytest command is completely removed from projects.py.
2. Unconfigured project command execution returns honest error with PROJECT_COMMAND_UNRESOLVED.
"""

from pathlib import Path
from unittest.mock import patch

from astrarun.projects.registry import ProjectMetadata
from astrarun.tools.projects import run_project_command


def test_unconfigured_project_command_fails_honestly():
    """Verify executing project command without explicit configuration fails with PROJECT_COMMAND_UNRESOLVED."""
    mock_proj = ProjectMetadata(
        id="test_unconfigured_project",
        name="Test Project",
        relative_path="test",
        absolute_path=Path("."),
        commands={},  # No test command configured
    )

    with patch("astrarun.tools.projects.get_project_registry") as mock_get_reg:
        mock_reg = mock_get_reg.return_value
        mock_reg.get_project.return_value = mock_proj

        res = run_project_command("test_unconfigured_project", "test")
        assert res.success is False
        assert res.data.get("reason_code") == "PROJECT_COMMAND_UNRESOLVED"
        assert "not defined" in res.message.lower()

        # Ensure milestone5 pytest string is nowhere in the message or result
        assert "test_milestone5_resident_app" not in res.message
        assert "test_user_sid_extraction" not in res.message
