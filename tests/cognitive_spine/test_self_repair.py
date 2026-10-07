"""Cognitive Spine Regression Suite: Bounded Self-Repair Tests."""

import pytest
from pathlib import Path

from astrarun.cognition.service import ModelService
from astrarun.tools.candidate import CandidateTool, CodeProvenance
from astrarun.tools.dynamic_builder import DynamicToolBuilder


def test_bounded_repair_ceiling():
    """Verify that DynamicToolBuilder strictly enforces max_repair_attempts (default 2)."""
    # A candidate tool that consistently fails with an unfixable syntax or logic error
    failing_cand = CandidateTool(
        goal="Perpetually failing script",
        source_files={
            "main.py": "raise RuntimeError('Permanent unfixable failure')",
        },
        entrypoint="main.py",
        task_id="test_repair_ceiling_001",
    )

    builder = DynamicToolBuilder(max_repair_attempts=2)
    report = builder.build_and_execute(failing_cand, timeout_sec=5.0)

    assert not report.is_success
    assert report.repair_attempts <= 2
    assert "exhausted" in report.error_message.lower() or "failed" in report.error_message.lower()


def test_self_repair_provenance_increment():
    """Verify that each repair attempt increments the revision number and records parent revision."""
    ms = ModelService.get_instance()
    initial_cand = CandidateTool(
        goal="Add two numbers",
        source_files={"main.py": "def add(a, b): return a + b\nadd(1)"},  # Missing argument error
        entrypoint="main.py",
        task_id="test_prov_inc_001",
    )
    initial_cand.provenance = CodeProvenance(
        task_id=initial_cand.task_id,
        model="qwen2.5-coder",
        model_version="1.5b-instruct",
        prompt_hash="dummy_hash",
        source_hash=initial_cand.compute_source_hash(),
        revision=1,
    )

    repaired_cand = ms.repair_code(
        initial_cand,
        error_message="TypeError: add() missing 1 required positional argument: 'b'",
        attempt=1,
    )

    assert repaired_cand.provenance is not None
    assert repaired_cand.provenance.revision == 2
    assert repaired_cand.provenance.parent_revision == 1
    assert "Repaired error" in repaired_cand.provenance.reason_for_revision
