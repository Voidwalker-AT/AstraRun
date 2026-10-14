"""Adversarial mutation tests for F0-25 acceptance evaluator.

Verifies that f0_25e_evaluator.py is mechanically incapable of giving false PASSes:
1. Zero launcher pixels -> ASTRA_LAUNCHER_UI is FAIL.
2. Zero progress frames -> PROGRESS_UI is FAIL (never default PARTIAL).
3. Disk files exist but zero presentation events/windows -> OUTPUT_PRESENTATION is FAIL.
4. Unrequested terminal window present -> VISIBLE_TERMINAL_EXECUTION is FAIL.
5. Leaked unmanaged PID in final frame -> RESOURCE_RESTORATION is FAIL.
6. Any PARTIAL or FAIL dimension -> overall verdict cannot be PASS.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from PIL import Image

from scripts.f0_25e_evaluator import (
    FrozenEvidencePackage,
    evaluate_acceptance,
    generate_resource_delta_report,
    write_final_markdown_report,
)


def create_mock_package(tmp_path: Path, world_frames=None, events=None, screenshots=None):
    raw_dir = tmp_path / "raw"
    sc_dir = raw_dir / "screenshots"
    sc_dir.mkdir(parents=True, exist_ok=True)

    pkg = MagicMock(spec=FrozenEvidencePackage)
    pkg.audit_dir = tmp_path
    pkg.raw_dir = raw_dir
    pkg.screenshots_dir = sc_dir
    pkg.world_frames = world_frames or []
    pkg.events = events or []
    pkg.model_events = []
    pkg.broker_events = []
    pkg.filesystem_events = []

    # Create dummy white screenshot if not provided
    if not screenshots:
        white_img = Image.new("RGB", (1920, 1080), color=(255, 255, 255))
        white_img.save(sc_dir / "frame_0000.png")
    else:
        for idx, img in enumerate(screenshots):
            img.save(sc_dir / f"frame_{idx:04d}.png")

    return pkg


def test_evaluator_fails_launcher_ui_when_zero_dark_pixels(tmp_path: Path):
    """Mutant 1: World frames claim launcher window, but screenshots are pure white."""
    world_frames = [
        {"astra_windows": [{"title": "AstraRun", "topmost": True}]},
    ]
    pkg = create_mock_package(tmp_path, world_frames=world_frames)

    with patch("scripts.f0_25e_evaluator.RAW_DIR", tmp_path / "raw"):
        matrix = evaluate_acceptance(pkg, tmp_path / "target")

    # Pure white screenshot -> no dark pixels -> ASTRA_LAUNCHER_UI MUST be FAIL
    assert matrix["ASTRA_LAUNCHER_UI"]["verdict"] == "FAIL"


def test_evaluator_fails_progress_ui_when_zero_frames(tmp_path: Path):
    """Mutant 2: Zero HUD frames and zero launcher frames must yield FAIL, not PARTIAL."""
    world_frames = [
        {"astra_windows": []},
    ]
    pkg = create_mock_package(tmp_path, world_frames=world_frames)

    with patch("scripts.f0_25e_evaluator.RAW_DIR", tmp_path / "raw"):
        matrix = evaluate_acceptance(pkg, tmp_path / "target")

    assert matrix["PROGRESS_UI"]["verdict"] == "FAIL"


def test_evaluator_fails_output_presentation_when_unpresented(tmp_path: Path):
    """Mutant 3: Deliverables exist on disk, but zero presentation events/windows."""
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / "app.py").write_text("print(1)")
    (target_dir / "output.json").write_text('{"a": 1}')
    (target_dir / "sample.txt").write_text("sample")

    world_frames = [{"astra_windows": []}]
    events = [{"event_type": "GOAL_COMPLETED"}]
    pkg = create_mock_package(tmp_path, world_frames=world_frames, events=events)

    with patch("scripts.f0_25e_evaluator.RAW_DIR", tmp_path / "raw"):
        matrix = evaluate_acceptance(pkg, target_dir)

    # Deliverables on disk alone must NOT PASS output presentation
    assert matrix["OUTPUT_PRESENTATION"]["verdict"] == "FAIL"


def test_evaluator_fails_visible_terminal_when_unrequested_terminal_appears(tmp_path: Path):
    """Mutant 4: An unrequested terminal window is present -> must be FAIL, not PASS."""
    world_frames = [
        {"astra_windows": [{"title": "Windows PowerShell", "pid": 4567}]},
    ]
    pkg = create_mock_package(tmp_path, world_frames=world_frames)

    with patch("scripts.f0_25e_evaluator.RAW_DIR", tmp_path / "raw"):
        matrix = evaluate_acceptance(pkg, tmp_path / "target")

    assert matrix["VISIBLE_TERMINAL_EXECUTION"]["verdict"] == "FAIL"


def test_evaluator_fails_resource_restoration_when_unmanaged_pid_leaks(tmp_path: Path):
    """Mutant 5: A leaked PID remains in final world frame -> RESOURCE_RESTORATION must FAIL."""
    world_frames = [
        {"running_pids": [100, 200], "astra_windows": []},
        {"running_pids": [100, 200, 999], "astra_windows": []},  # PID 999 leaked!
    ]
    pkg = create_mock_package(tmp_path, world_frames=world_frames)

    with patch("scripts.f0_25e_evaluator.RAW_DIR", tmp_path / "raw"):
        matrix = evaluate_acceptance(pkg, tmp_path / "target")

    assert matrix["RESOURCE_RESTORATION"]["verdict"] == "FAIL"
    assert 999 in matrix["RESOURCE_RESTORATION"]["evidence"]["unmanaged_new_pids"]


def test_evaluator_overall_verdict_cannot_pass_with_partial_or_fail(tmp_path: Path):
    """Mutant 6: Any dimension returning PARTIAL or FAIL must prevent suggested PASS."""
    matrix_with_partial = {
        "DIM_1": {"verdict": "PASS", "predicate": ""},
        "DIM_2": {"verdict": "PARTIAL", "predicate": ""},
    }
    with patch("scripts.f0_25e_evaluator.AUDIT_DIR", tmp_path):
        out_report = write_final_markdown_report(matrix_with_partial, {}, {}, {}, {})
        content = out_report.read_text(encoding="utf-8")
        assert "- **Suggested Verdict**: **PARTIAL**" in content
        assert "- **Suggested Verdict**: **PASS**" not in content

    matrix_with_fail = {
        "DIM_1": {"verdict": "PASS", "predicate": ""},
        "DIM_2": {"verdict": "FAIL", "predicate": ""},
    }
    with patch("scripts.f0_25e_evaluator.AUDIT_DIR", tmp_path):
        out_report = write_final_markdown_report(matrix_with_fail, {}, {}, {}, {})
        content = out_report.read_text(encoding="utf-8")
        assert "- **Suggested Verdict**: **FAIL**" in content
        assert "- **Suggested Verdict**: **PASS**" not in content
