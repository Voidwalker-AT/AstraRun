"""Unit tests for Native Wi-Fi management and WiFiResolver (Tier A)."""

import pytest

from astrarun.agent.models import PlanStep
from astrarun.agent.verifier import StepVerifier
from astrarun.capabilities.schema import VerifierStrategy
from astrarun.tools.wifi import (
    NativeWiFiClient,
    WiFiNetwork,
    WiFiResolver,
    wifi_connect,
    wifi_disconnect,
    wifi_scan,
    wifi_status,
)


class TestWiFiResolver:
    """Tests for fuzzy SSID matching."""

    @pytest.fixture
    def sample_networks(self):
        return [
            WiFiNetwork(ssid="Corporate_5G", signal_quality=95, security_enabled=True),
            WiFiNetwork(ssid="Guest_Network", signal_quality=60, security_enabled=False),
            WiFiNetwork(ssid="Home_WiFi_2.4G", signal_quality=80, security_enabled=True),
        ]

    def test_exact_match_case_insensitive(self, sample_networks):
        res = WiFiResolver.resolve_ssid("corporate_5g", sample_networks)
        assert res is not None
        assert res.ssid == "Corporate_5G"

    def test_substring_match(self, sample_networks):
        res = WiFiResolver.resolve_ssid("Guest", sample_networks)
        assert res is not None
        assert res.ssid == "Guest_Network"

    def test_fuzzy_match(self, sample_networks):
        # Typo: "Hom_WiFi" instead of "Home_WiFi_2.4G"
        res = WiFiResolver.resolve_ssid("Hom_WiFi", sample_networks)
        assert res is not None
        assert res.ssid == "Home_WiFi_2.4G"

    def test_no_match_returns_none(self, sample_networks):
        res = WiFiResolver.resolve_ssid("CompletelyUnrelatedSSID_XYZ", sample_networks)
        assert res is None


class TestNativeWiFiExecution:
    """Tests for native Wi-Fi capabilities."""

    def test_wifi_status(self):
        res = wifi_status()
        assert res.capability == "wifi_status"
        # If running on Windows host with Wi-Fi, it should succeed
        if res.success:
            assert "status" in res.data
            assert "connected" in res.data
            assert res.data["tier"] == "TIER_A_NATIVE"

    def test_wifi_scan(self):
        res = wifi_scan()
        assert res.capability == "wifi_scan"
        if res.success:
            assert "networks" in res.data
            assert "count" in res.data
            assert res.data["tier"] == "TIER_A_NATIVE"

    def test_wifi_connect_empty_ssid_fails(self):
        res = wifi_connect("")
        assert not res.success
        assert "empty" in res.message.lower()

    def test_verifier_network_ssid(self):
        verifier = StepVerifier()
        status_res = wifi_status()

        if status_res.success and status_res.data.get("connected"):
            current_ssid = status_res.data["active_network"]["ssid"]
            step = PlanStep(
                step_id="wifi_step",
                capability_id="wifi_connect",
                arguments={"ssid": current_ssid},
                verifier_strategy=VerifierStrategy.NETWORK_SSID,
                verifier_params={"ssid": current_ssid},
            )
            ver = verifier.verify(step, status_res)
            assert ver.verified is True
