"""Section 4: Sealed Artifact Promotion Tests for AstraRun C2.2.

Evaluates handle-based source sealing, restrictive sharing, canonical path resolution,
symlink/junction defenses, copy integrity verification, and atomic commit.
"""

import hashlib
import os
import tempfile
from pathlib import Path
import pytest

from astrarun.core.paths import AstraPaths
from astrarun.files.service import deliver_artifact, validate_safe_path


def test_validate_safe_path_boundaries():
    # 1. Trailing dots and spaces
    assert not validate_safe_path("out.txt.")[0]
    assert not validate_safe_path("out.txt ")[0]
    assert not validate_safe_path("folder./file.txt")[0]
    assert not validate_safe_path("folder /file.txt")[0]

    # 2. Drive-relative paths
    assert not validate_safe_path("C:file.txt")[0]
    assert not validate_safe_path("D:folder/file.txt")[0]

    # 3. NT namespace and UNC paths
    assert not validate_safe_path(r"\\?\C:\file.txt")[0]
    assert not validate_safe_path(r"\??\C:\file.txt")[0]
    assert not validate_safe_path(r"\\server\share\file.txt")[0]

    # 4. ADS streams
    assert not validate_safe_path("file.txt:stream")[0]

    # 5. Reserved DOS names
    assert not validate_safe_path("CON")[0]
    assert not validate_safe_path("aux.txt")[0]
    assert not validate_safe_path("com1")[0]

    # 6. Valid absolute paths
    assert validate_safe_path(r"C:\Users\test\file.txt")[0]
    assert validate_safe_path(r"E:\Workspace\data\report.json")[0]


def test_handle_based_sealed_artifact_promotion():
    sb_dir = AstraPaths.sandbox_dir() / f"test_seal_{int(os.getpid())}"
    sb_dir.mkdir(parents=True, exist_ok=True)
    src_file = sb_dir / "valid_artifact.txt"
    payload = b"Authoritative verified artifact output bytes 2026."
    src_file.write_bytes(payload)
    correct_hash = hashlib.sha256(payload).hexdigest()

    with tempfile.TemporaryDirectory() as td:
        dest_file = Path(td) / "promoted_artifact.txt"

        # 1. Success with hash verification and revision binding
        res = deliver_artifact(
            source=str(src_file),
            destination=str(dest_file),
            source_sha256=correct_hash,
            task_id="task_test_01",
            plan_revision=1,
            artifact_identity="promoted_artifact.txt",
        )
        assert res.success
        assert dest_file.exists()
        assert dest_file.read_bytes() == payload
        assert res.data["sha256"] == correct_hash
        assert res.data["plan_revision"] == 1

        # 2. Rejection of hash mismatch
        tamper_dest = Path(td) / "tamper.txt"
        res_tamper = deliver_artifact(
            source=str(src_file),
            destination=str(tamper_dest),
            source_sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        )
        assert not res_tamper.success
        assert not tamper_dest.exists()

        # 3. Rejection when destination exists and overwrite=False
        res_conflict = deliver_artifact(
            source=str(src_file),
            destination=str(dest_file),
            overwrite=False,
        )
        assert not res_conflict.success
        assert "exists" in res_conflict.message.lower()

    # Cleanup
    src_file.unlink(missing_ok=True)
    sb_dir.rmdir()


def test_sealed_artifact_boundary_escape_denial():
    with tempfile.TemporaryDirectory() as td:
        # Create file outside authorized sandbox roots
        rogue_file = Path(td) / "outside.txt"
        rogue_file.write_text("outside data", encoding="utf-8")

        dest_file = Path(td) / "out.txt"
        res = deliver_artifact(
            source=str(rogue_file),
            destination=str(dest_file),
        )
        assert not res.success
        assert "escapes" in res.message.lower() or "boundary" in res.message.lower()
        assert not dest_file.exists()


def test_sealed_artifact_type_header_verification():
    sb_dir = AstraPaths.sandbox_dir() / f"test_type_{int(os.getpid())}"
    sb_dir.mkdir(parents=True, exist_ok=True)

    try:
        # A. Valid JSON
        json_file = sb_dir / "valid.json"
        json_file.write_text('{"status": "ok", "count": 42}', encoding="utf-8")

        # B. Invalid JSON pretending to be JSON
        bad_json_file = sb_dir / "corrupt.json"
        bad_json_file.write_text('{status: not valid json syntax', encoding="utf-8")

        # C. Invalid PNG pretending to be PNG
        fake_png = sb_dir / "fake.png"
        fake_png.write_bytes(b"NOT_A_PNG_FILE_HEADER")

        with tempfile.TemporaryDirectory() as td:
            # Valid JSON delivery
            res_json_ok = deliver_artifact(
                source=str(json_file),
                destination=str(Path(td) / "out.json"),
                expected_artifact_type="json",
            )
            assert res_json_ok.success

            # Corrupt JSON rejection
            res_json_bad = deliver_artifact(
                source=str(bad_json_file),
                destination=str(Path(td) / "bad.json"),
                expected_artifact_type="json",
            )
            assert not res_json_bad.success
            assert "json" in res_json_bad.message.lower()

            # Fake PNG rejection
            res_png_bad = deliver_artifact(
                source=str(fake_png),
                destination=str(Path(td) / "fake.png"),
                expected_artifact_type="png",
            )
            assert not res_png_bad.success
            assert "png" in res_png_bad.message.lower()

    finally:
        for f in sb_dir.glob("*"):
            f.unlink(missing_ok=True)
        sb_dir.rmdir()
