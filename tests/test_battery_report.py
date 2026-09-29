"""Unit tests for SystemUtilityAdapter and PowerCfgAdapter (Tier B)."""

import os
import tempfile
from pathlib import Path
import pytest

from astrarun.agent.models import PlanStep
from astrarun.agent.verifier import StepVerifier
from astrarun.capabilities.schema import VerifierStrategy
from astrarun.tools.system_adapter import PowerCfgAdapter, SystemUtilityAdapter


class TestSystemUtilityAdapter:
    """Tests for base SystemUtilityAdapter security and validation."""

    def test_blocks_shell_characters(self):
        adapter = PowerCfgAdapter()
        with pytest.raises(ValueError, match="Prohibited shell character detected"):
            adapter.run_validated(["/test; rm -rf /"])

        with pytest.raises(ValueError, match="Prohibited shell character detected"):
            adapter.run_validated(["/test & calc.exe"])

        with pytest.raises(ValueError, match="Prohibited shell character detected"):
            adapter.run_validated(["/test | dir"])

    def test_downloads_directory_resolution(self):
        downloads = PowerCfgAdapter.get_downloads_directory()
        assert isinstance(downloads, Path)
        assert downloads.exists() or downloads.parent.exists()


class TestPowerCfgBatteryReport:
    """Tests for PowerCfgAdapter battery report generation and verification."""

    def test_generate_battery_report_custom_temp_path(self):
        adapter = PowerCfgAdapter()
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = Path(tmpdir) / "test-battery.html"
            res = adapter.generate_battery_report(str(target_file))

            # On real battery hardware (or laptops), this creates the file
            if res.success:
                assert target_file.exists()
                assert target_file.stat().st_size > 0
                assert res.data["output_file"] == str(target_file)
                assert res.data["file_size_bytes"] > 0
                assert res.data["format"] == "html"
                assert res.data["tier"] == "TIER_B_STRUCTURED_CLI"

                # Verify with StepVerifier
                verifier = StepVerifier()
                step = PlanStep(
                    step_id="test_step",
                    capability_id="generate_battery_report",
                    verifier_strategy=VerifierStrategy.FILE_NON_EMPTY,
                    verifier_params={"path": str(target_file)},
                )
                ver_res = verifier.verify(step, res)
                assert ver_res.verified is True
            else:
                # If virtualized / desktop without battery, must fail gracefully with UNAVAILABLE
                assert res.error_code is not None

    def test_normalize_bare_filename_to_downloads(self):
        adapter = PowerCfgAdapter()
        downloads = adapter.get_downloads_directory()
        expected = downloads / "astra-unit-test.html"

        # Cleanup if previously existed
        if expected.exists():
            try:
                expected.unlink()
            except Exception:
                pass

        try:
            res = adapter.generate_battery_report("astra-unit-test.html")
            if res.success:
                assert expected.exists()
                assert expected.stat().st_size > 0
                assert Path(res.data["output_file"]) == expected
        finally:
            if expected.exists():
                try:
                    expected.unlink()
                except Exception:
                    pass
