"""Unit tests for the unified MemoryService facade."""

import pytest
from astrarun.memory.service import MemoryService
from astrarun.memory.skills import SkillDefinition


def test_memory_service_working_memory():
    mem = MemoryService()
    mem.working.set("user_active_intent", "plot_metrics")
    assert mem.working.get("user_active_intent") == "plot_metrics"
    assert "user_active_intent" in mem.working.snapshot()
    mem.working.clear()
    assert mem.working.get("user_active_intent") is None


def test_memory_service_procedural_skills():
    mem = MemoryService()
    skill = SkillDefinition(
        name="save_plot",
        description="Saves a matplotlib figure to disk",
        parameters={"filename": "str", "dpi": "int"},
    )
    mem.procedural.register_skill(skill)
    retrieved = mem.procedural.get_skill("save_plot")
    assert retrieved is not None
    assert retrieved.name == "save_plot"
    tier1 = mem.procedural.get_tier_1_catalog()
    assert any(s["name"] == "save_plot" for s in tier1)


def test_memory_service_workspace_indexing(tmp_path):
    mem = MemoryService()
    mem.workspace.db_path = tmp_path / "test_workspace.db"
    mem.workspace.index_document(
        doc_id="doc1",
        source_path="src/main.py",
        content="def calculate_cpu_metrics(): return 42",
    )
    results = mem.workspace.search_workspace("calculate_cpu_metrics")
    assert len(results) >= 1
    assert "cpu_metrics" in results[0]["content"]
