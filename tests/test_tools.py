"""Unit tests for tool registry and execution policy."""

from astrarun.core.models import Decision, ToolMetadata, ToolRisk
from astrarun.tools.registry import ToolRegistry


def test_registry_default_tools():
    registry = ToolRegistry()
    assert registry.get("open_app") is not None
    assert registry.get("open_folder") is not None
    assert registry.get("open_url") is not None
    assert registry.get("open_app").risk == ToolRisk.LOW


def test_registry_blocks_unknown():
    registry = ToolRegistry()
    decision = Decision.unknown("delete system32")
    success, msg = registry.execute(decision)
    assert not success
    assert "I don't know how to do that yet." in msg


def test_registry_blocks_unregistered():
    registry = ToolRegistry()
    decision = Decision(tool="unregistered_dangerous_tool", args={})
    success, msg = registry.execute(decision)
    assert not success
    assert "not registered" in msg


def test_registry_enforces_blocked_risk():
    registry = ToolRegistry()
    # Register a tool explicitly categorized as BLOCKED
    registry.register(
        ToolMetadata(
            name="arbitrary_shell",
            description="Prohibited shell tool",
            risk=ToolRisk.BLOCKED,
            args_schema={},
            handler=lambda: True,
        )
    )

    decision = Decision(tool="arbitrary_shell", args={})
    success, msg = registry.execute(decision)
    assert not success
    assert "prohibited" in msg


def test_mock_tool_execution():
    registry = ToolRegistry()
    called_with = []

    def mock_handler(target: str) -> bool:
        called_with.append(target)
        return True

    registry.register(
        ToolMetadata(
            name="mock_tool",
            description="Mock testing tool",
            risk=ToolRisk.LOW,
            args_schema={"target": str},
            handler=mock_handler,
        )
    )

    decision = Decision(tool="mock_tool", args={"target": "hello_astra"})
    success, msg = registry.execute(decision)
    assert success
    assert called_with == ["hello_astra"]
