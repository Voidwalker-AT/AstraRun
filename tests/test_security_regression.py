"""Security regression suite validating injection resistance and scheme safety."""

import pytest
from astrarun.core.models import Decision, RoutingContext
from astrarun.routing.deterministic import DeterministicRouter
from astrarun.tools.registry import ToolRegistry
from astrarun.tools.web import open_url


@pytest.fixture
def mock_context():
    return RoutingContext()


def test_command_injection_symbols_are_not_evaluated(mock_context):
    router = DeterministicRouter()
    registry = ToolRegistry()

    dangerous_inputs = [
        "notepad & del something",
        "notepad ; whoami",
        "notepad | calc",
        "$(whoami)",
        "`whoami`",
        "powershell -Command Remove-Item -Force C:\\test",
        "cmd.exe /c dir",
        "notepad && calc",
    ]

    for attack in dangerous_inputs:
        decision = router.route(attack, mock_context)
        # The router must NOT evaluate shell syntax, and must either classify it as unknown or safe target lookup
        if decision.is_resolved:
            # If resolved, ensure it doesn't invoke raw shell
            assert decision.tool in ("open_app", "open_folder", "open_url", "refresh_apps")
            # And the registry must not allow execution of blocked tools
            tool_meta = registry.get(decision.tool)
            assert tool_meta is not None
            assert tool_meta.risk.value != "BLOCKED"
        else:
            assert decision.tool == "unknown"


def test_url_tool_blocks_dangerous_schemes():
    # Only http and https are allowed
    assert not open_url("javascript:alert(1)")
    assert not open_url("file:///C:/Windows/System32/calc.exe")
    assert not open_url("data:text/html,<script>alert(1)</script>")
    assert not open_url("vbscript:MsgBox(1)")
    assert not open_url("shell:AppsFolder")
    assert not open_url("ftp://example.com/file")


def test_url_tool_allows_safe_schemes():
    # Valid domain http/https should pass validation logic (mock webbrowser.open)
    from unittest.mock import patch

    with patch("webbrowser.open", return_value=True):
        assert open_url("https://github.com")
        assert open_url("http://example.com")
