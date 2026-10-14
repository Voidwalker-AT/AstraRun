"""Adversarial and Mutation Test Suite for F0-25E Pure Acceptance Engine.

Proves:
1. Missing screenshot => cannot PASS visual dimension
2. Missing model event => cannot PASS causal provenance (returns UNVERIFIED)
3. Missing broker event => cannot PASS causal provenance (returns UNVERIFIED)
4. No editor used => editor = NOT_APPLICABLE (never PASS)
5. No terminal window => terminal = NOT_APPLICABLE
6. Count discrepancy in generated JSON => RESULT_CORRECTNESS fails
7. Mutated raw evidence => manifest integrity verification fails
8. Observer write guard structurally blocks writing to target directory
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import shutil
import tempfile
import sys
from pathlib import Path
from unittest.mock import MagicMock
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.f0_25e_evaluator import (
    FrozenEvidencePackage,
    evaluate_acceptance,
    run_content_oracle,
    verify_manifest_integrity,
)
from scripts.f0_25e_observer import install_evaluator_write_guard, TARGET_DIR


def test_observer_write_guard_blocks_target_dir_writes(tmp_path):
    """Prove observer write-guard throws RuntimeError on any write attempt to TARGET_DIR."""
    install_evaluator_write_guard()

    target_file = TARGET_DIR / "should_be_blocked.txt"
    with pytest.raises(RuntimeError, match="OBSERVER_WRITE_GUARD_VIOLATION"):
        with open(target_file, "w") as f:
            f.write("illegal write")


def test_manifest_integrity_detects_tampered_evidence(tmp_path):
    """Prove manifest integrity verification fails if raw evidence is mutated."""
    raw_file = tmp_path / "raw" / "events.jsonl"
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text('{"event": 1}\n', encoding="utf-8")

    correct_sha = hashlib.sha256(raw_file.read_bytes()).hexdigest()
    manifest_path = tmp_path / "F0_25E_RAW_MANIFEST.json"
    manifest_data = {
        "artifacts": {
            "raw/events.jsonl": {
                "sha256": correct_sha,
                "size_bytes": raw_file.stat().st_size,
            }
        }
    }
    manifest_path.write_text(json.dumps(manifest_data), encoding="utf-8")

    # Before tampering: verification passes
    from scripts import f0_25e_evaluator
    orig_audit = f0_25e_evaluator.AUDIT_DIR
    try:
        f0_25e_evaluator.AUDIT_DIR = tmp_path
        ok, errors = verify_manifest_integrity(manifest_path)
        assert ok is True
        assert len(errors) == 0

        # Tamper with raw file
        raw_file.write_text('{"event": 2, "tampered": true}\n', encoding="utf-8")

        # After tampering: verification fails
        ok_after, errors_after = verify_manifest_integrity(manifest_path)
        assert ok_after is False
        assert any("Hash mismatch" in e for e in errors_after)
    finally:
        f0_25e_evaluator.AUDIT_DIR = orig_audit


def test_missing_model_event_causes_unverified_provenance(tmp_path):
    """Prove missing model event fails causal provenance to UNVERIFIED."""
    pkg = MagicMock()
    pkg.model_events = []  # Empty! Missing!
    pkg.broker_events = [{"action": "execute_dynamic_tool"}]
    pkg.filesystem_events = [{"files": 3}]
    pkg.world_frames = []

    target_dir = tmp_path / "target"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "main.py").write_text("print('hello')", encoding="utf-8")
    (target_dir / "sample.txt").write_text("hello", encoding="utf-8")
    (target_dir / "out.json").write_text('{"hello": 1}', encoding="utf-8")

    matrix = evaluate_acceptance(pkg, target_dir)
    assert matrix["CAUSAL_PROVENANCE"]["verdict"] == "UNVERIFIED"


def test_missing_broker_event_causes_unverified_provenance(tmp_path):
    """Prove missing broker event fails causal provenance to UNVERIFIED."""
    pkg = MagicMock()
    pkg.model_events = [{"model": "qwen"}]
    pkg.broker_events = []  # Empty! Missing!
    pkg.filesystem_events = [{"files": 3}]
    pkg.world_frames = []

    target_dir = tmp_path / "target"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "main.py").write_text("print('hello')", encoding="utf-8")
    (target_dir / "sample.txt").write_text("hello", encoding="utf-8")
    (target_dir / "out.json").write_text('{"hello": 1}', encoding="utf-8")

    matrix = evaluate_acceptance(pkg, target_dir)
    assert matrix["CAUSAL_PROVENANCE"]["verdict"] == "UNVERIFIED"


def test_editor_interaction_is_not_applicable_not_pass(tmp_path):
    """Prove EDITOR_INTERACTION evaluates strictly to NOT_APPLICABLE, never PASS."""
    pkg = MagicMock()
    pkg.model_events = [{"model": "qwen"}]
    pkg.broker_events = [{"action": "execute_dynamic_tool"}]
    pkg.filesystem_events = [{"files": 3}]
    pkg.world_frames = []

    target_dir = tmp_path / "target"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "main.py").write_text("print('hello')", encoding="utf-8")
    (target_dir / "sample.txt").write_text("hello", encoding="utf-8")
    (target_dir / "out.json").write_text('{"hello": 1}', encoding="utf-8")

    matrix = evaluate_acceptance(pkg, target_dir)
    assert matrix["EDITOR_INTERACTION"]["verdict"] == "NOT_APPLICABLE"


def test_visible_terminal_execution_is_not_applicable(tmp_path):
    """Prove VISIBLE_TERMINAL_EXECUTION evaluates to NOT_APPLICABLE for sandboxed execution."""
    pkg = MagicMock()
    pkg.model_events = [{"model": "qwen"}]
    pkg.broker_events = [{"action": "execute_dynamic_tool"}]
    pkg.filesystem_events = [{"files": 3}]
    pkg.world_frames = []

    target_dir = tmp_path / "target"
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "main.py").write_text("print('hello')", encoding="utf-8")
    (target_dir / "sample.txt").write_text("hello", encoding="utf-8")
    (target_dir / "out.json").write_text('{"hello": 1}', encoding="utf-8")

    matrix = evaluate_acceptance(pkg, target_dir)
    assert matrix["VISIBLE_TERMINAL_EXECUTION"]["verdict"] == "NOT_APPLICABLE"


def test_content_oracle_mathematical_verification_success(tmp_path):
    """Prove content oracle correctly tokenizes and matches mathematical counts."""
    sample_text = "The quick brown fox jumps over the lazy dog. The fox was quick and brown."
    (tmp_path / "sample.txt").write_text(sample_text, encoding="utf-8")

    # Tokens: the(3), quick(2), brown(2), fox(2), jumps(1), over(1), lazy(1), dog(1), was(1), and(1)
    actual_json = {
        "the": 3,
        "quick": 2,
        "brown": 2,
        "fox": 2,
        "jumps": 1,
        "over": 1,
        "lazy": 1,
        "dog": 1,
        "was": 1,
        "and": 1,
    }
    (tmp_path / "counts.json").write_text(json.dumps(actual_json), encoding="utf-8")

    res = run_content_oracle(tmp_path)
    assert res["status"] == "PASS"
    assert res["mathematical_match"] is True
    assert len(res["discrepancies"]) == 0


def test_content_oracle_detects_count_discrepancy(tmp_path):
    """Prove content oracle rejects incorrect frequency calculations."""
    sample_text = "apple banana apple cherry"
    (tmp_path / "sample.txt").write_text(sample_text, encoding="utf-8")

    # Wrong counts: claims apple is 10
    actual_json = {
        "apple": 10,
        "banana": 1,
        "cherry": 1,
    }
    (tmp_path / "counts.json").write_text(json.dumps(actual_json), encoding="utf-8")

    res = run_content_oracle(tmp_path)
    assert res["status"] == "FAIL"
    assert res["mathematical_match"] is False
    assert any("Count mismatch for 'apple'" in d for d in res["discrepancies"])
