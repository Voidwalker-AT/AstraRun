"""Native Windows Wi-Fi management via wlanapi.dll (Tier A).

Provides safe Wi-Fi scanning, status, connection, and fuzzy SSID resolution with
zero subprocess execution and zero credential exposure.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import difflib
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

from astrarun.capabilities.models import CapabilityErrorCode, CapabilityResult
from astrarun.capabilities.schema import InteractionTier
from astrarun.core.logging import get_logger

logger = get_logger("astrarun.tools.wifi")


# Win32 WLAN API Structures
class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    def to_str(self) -> str:
        d4_1 = "".join(f"{b:02x}" for b in self.Data4[:2])
        d4_2 = "".join(f"{b:02x}" for b in self.Data4[2:])
        return f"{{{self.Data1:08x}-{self.Data2:04x}-{self.Data3:04x}-{d4_1}-{d4_2}}}"


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [
        ("InterfaceGuid", GUID),
        ("strInterfaceDescription", ctypes.c_wchar * 256),
        ("isState", ctypes.c_uint),
    ]


class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [
        ("dwNumberOfItems", ctypes.c_ulong),
        ("dwIndex", ctypes.c_ulong),
        ("InterfaceInfo", WLAN_INTERFACE_INFO * 1),
    ]


class DOT11_SSID(ctypes.Structure):
    _fields_ = [
        ("uSSIDLength", ctypes.c_ulong),
        ("ucSSID", ctypes.c_char * 32),
    ]

    def decode(self) -> str:
        if self.uSSIDLength == 0:
            return ""
        return self.ucSSID[: self.uSSIDLength].decode("utf-8", errors="ignore")


class WLAN_AVAILABLE_NETWORK(ctypes.Structure):
    _fields_ = [
        ("strProfileName", ctypes.c_wchar * 256),
        ("dot11Ssid", DOT11_SSID),
        ("dot11BssType", ctypes.c_uint),
        ("uNumberOfBssids", ctypes.c_ulong),
        ("bNetworkConnectable", ctypes.c_bool),
        ("wlanNotConnectableReason", ctypes.c_ulong),
        ("uNumberOfPhyTypes", ctypes.c_ulong),
        ("dot11PhyTypes", ctypes.c_uint * 8),
        ("bMorePhyTypes", ctypes.c_bool),
        ("wlanSignalQuality", ctypes.c_ulong),
        ("bSecurityEnabled", ctypes.c_bool),
        ("dot11DefaultAuthAlgorithm", ctypes.c_uint),
        ("dot11DefaultCipherAlgorithm", ctypes.c_uint),
        ("dwFlags", ctypes.c_ulong),
        ("dwReserved", ctypes.c_ulong),
    ]


class WLAN_AVAILABLE_NETWORK_LIST(ctypes.Structure):
    _fields_ = [
        ("dwNumberOfItems", ctypes.c_ulong),
        ("dwIndex", ctypes.c_ulong),
        ("Network", WLAN_AVAILABLE_NETWORK * 1),
    ]


class WLAN_CONNECTION_PARAMETERS(ctypes.Structure):
    _fields_ = [
        ("wlanConnectionMode", ctypes.c_uint),
        ("strProfile", ctypes.c_wchar_p),
        ("pDot11Ssid", ctypes.c_void_p),
        ("pDesiredBssidList", ctypes.c_void_p),
        ("dot11BssType", ctypes.c_uint),
        ("dwFlags", ctypes.c_ulong),
    ]


INTERFACE_STATE_MAP = {
    0: "not_ready",
    1: "connected",
    2: "ad_hoc",
    3: "disconnecting",
    4: "disconnected",
    5: "associating",
    6: "discovering",
    7: "authenticating",
}


@dataclass
class WiFiNetwork:
    """Represents a discovered wireless network."""
    ssid: str
    signal_quality: int  # 0 to 100
    security_enabled: bool
    profile_name: str = ""
    connected: bool = False
    interface_desc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ssid": self.ssid,
            "signal_quality": self.signal_quality,
            "security_enabled": self.security_enabled,
            "profile_name": self.profile_name,
            "connected": self.connected,
            "interface_desc": self.interface_desc,
        }


class WiFiResolver:
    """Fuzzy resolution for SSID names."""

    @staticmethod
    def resolve_ssid(query: str, available_networks: list[WiFiNetwork]) -> Optional[WiFiNetwork]:
        """Match query string against available networks using exact, prefix, or fuzzy matching."""
        if not query or not available_networks:
            return None

        clean_query = query.strip().lower()

        # 1. Exact match (case-insensitive)
        for net in available_networks:
            if net.ssid.lower() == clean_query:
                return net

        # 2. Substring match
        for net in available_networks:
            if clean_query in net.ssid.lower():
                return net

        # 3. Fuzzy ratio match
        candidates = [net.ssid for net in available_networks]
        matches = difflib.get_close_matches(query, candidates, n=1, cutoff=0.5)
        if matches:
            best_ssid = matches[0]
            for net in available_networks:
                if net.ssid == best_ssid:
                    return net

        return None


class NativeWiFiClient:
    """Tier A Native Wi-Fi interface using wlanapi.dll."""

    def __init__(self):
        self._available = False
        self._wlan = None
        if sys.platform == "win32":
            try:
                self._wlan = ctypes.windll.wlanapi
                self._available = True
            except Exception as e:
                logger.warning("Failed to load wlanapi.dll: %s", e)

    @property
    def is_available(self) -> bool:
        return self._available

    def _open_handle(self) -> tuple[Optional[ctypes.wintypes.HANDLE], int]:
        if not self._available or not self._wlan:
            return None, -1
        handle = ctypes.wintypes.HANDLE()
        negotiated = ctypes.wintypes.DWORD()
        res = self._wlan.WlanOpenHandle(2, None, ctypes.byref(negotiated), ctypes.byref(handle))
        if res != 0:
            return None, res
        return handle, 0

    def get_networks(self) -> list[WiFiNetwork]:
        """Scan and return available wireless networks."""
        handle, err = self._open_handle()
        if not handle:
            return []

        networks: list[WiFiNetwork] = []
        p_interfaces = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()

        try:
            res = self._wlan.WlanEnumInterfaces(handle, None, ctypes.byref(p_interfaces))
            if res != 0 or not p_interfaces:
                return []

            num_interfaces = p_interfaces.contents.dwNumberOfItems
            for i in range(num_interfaces):
                offset = i * ctypes.sizeof(WLAN_INTERFACE_INFO)
                base = ctypes.addressof(p_interfaces.contents.InterfaceInfo)
                info = ctypes.cast(base + offset, ctypes.POINTER(WLAN_INTERFACE_INFO)).contents
                desc = info.strInterfaceDescription
                is_connected = (info.isState == 1)

                p_net_list = ctypes.POINTER(WLAN_AVAILABLE_NETWORK_LIST)()
                net_res = self._wlan.WlanGetAvailableNetworkList(
                    handle,
                    ctypes.byref(info.InterfaceGuid),
                    2,  # WLAN_AVAILABLE_NETWORK_INCLUDE_ALL_MANUAL_HIDDEN_PROFILES
                    None,
                    ctypes.byref(p_net_list),
                )

                if net_res == 0 and p_net_list:
                    try:
                        num_nets = p_net_list.contents.dwNumberOfItems
                        for j in range(num_nets):
                            net_offset = j * ctypes.sizeof(WLAN_AVAILABLE_NETWORK)
                            net_base = ctypes.addressof(p_net_list.contents.Network)
                            raw_net = ctypes.cast(net_base + net_offset, ctypes.POINTER(WLAN_AVAILABLE_NETWORK)).contents
                            ssid_str = raw_net.dot11Ssid.decode()
                            if not ssid_str:
                                continue

                            # Check if currently connected to this network
                            net_connected = is_connected and (raw_net.dwFlags & 1 != 0)

                            networks.append(
                                WiFiNetwork(
                                    ssid=ssid_str,
                                    signal_quality=int(raw_net.wlanSignalQuality),
                                    security_enabled=bool(raw_net.bSecurityEnabled),
                                    profile_name=str(raw_net.strProfileName),
                                    connected=net_connected,
                                    interface_desc=desc,
                                )
                            )
                    finally:
                        self._wlan.WlanFreeMemory(p_net_list)
        finally:
            if p_interfaces:
                self._wlan.WlanFreeMemory(p_interfaces)
            self._wlan.WlanCloseHandle(handle, None)

        return networks

    def get_status(self) -> dict[str, Any]:
        """Retrieve Wi-Fi adapter state and active connection details."""
        handle, err = self._open_handle()
        if not handle:
            return {"available": False, "reason": "WLAN service unavailable"}

        status: dict[str, Any] = {"available": True, "interfaces": []}
        p_interfaces = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()

        try:
            res = self._wlan.WlanEnumInterfaces(handle, None, ctypes.byref(p_interfaces))
            if res == 0 and p_interfaces:
                num_interfaces = p_interfaces.contents.dwNumberOfItems
                for i in range(num_interfaces):
                    offset = i * ctypes.sizeof(WLAN_INTERFACE_INFO)
                    base = ctypes.addressof(p_interfaces.contents.InterfaceInfo)
                    info = ctypes.cast(base + offset, ctypes.POINTER(WLAN_INTERFACE_INFO)).contents
                    guid_str = info.InterfaceGuid.to_str()
                    state_str = INTERFACE_STATE_MAP.get(info.isState, f"unknown_{info.isState}")
                    status["interfaces"].append({
                        "guid": guid_str,
                        "description": info.strInterfaceDescription,
                        "state": state_str,
                        "is_connected": info.isState == 1,
                    })
        finally:
            if p_interfaces:
                self._wlan.WlanFreeMemory(p_interfaces)
            self._wlan.WlanCloseHandle(handle, None)

        return status

    def connect_profile(self, profile_name: str) -> bool:
        """Connect to a pre-configured Wi-Fi profile."""
        handle, err = self._open_handle()
        if not handle:
            return False

        p_interfaces = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()
        success = False

        try:
            res = self._wlan.WlanEnumInterfaces(handle, None, ctypes.byref(p_interfaces))
            if res == 0 and p_interfaces and p_interfaces.contents.dwNumberOfItems > 0:
                guid = p_interfaces.contents.InterfaceInfo[0].InterfaceGuid

                conn_params = WLAN_CONNECTION_PARAMETERS()
                conn_params.wlanConnectionMode = 0  # wlan_connection_mode_profile
                conn_params.strProfile = profile_name
                conn_params.pDot11Ssid = None
                conn_params.pDesiredBssidList = None
                conn_params.dot11BssType = 1  # dot11_BSS_type_infrastructure
                conn_params.dwFlags = 0

                conn_res = self._wlan.WlanConnect(
                    handle,
                    ctypes.byref(guid),
                    ctypes.byref(conn_params),
                    None,
                )
                success = (conn_res == 0)
        finally:
            if p_interfaces:
                self._wlan.WlanFreeMemory(p_interfaces)
            self._wlan.WlanCloseHandle(handle, None)

        return success

    def disconnect(self) -> bool:
        """Disconnect active Wi-Fi connection."""
        handle, err = self._open_handle()
        if not handle:
            return False

        p_interfaces = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()
        success = False

        try:
            res = self._wlan.WlanEnumInterfaces(handle, None, ctypes.byref(p_interfaces))
            if res == 0 and p_interfaces and p_interfaces.contents.dwNumberOfItems > 0:
                guid = p_interfaces.contents.InterfaceInfo[0].InterfaceGuid
                dis_res = self._wlan.WlanDisconnect(handle, ctypes.byref(guid), None)
                success = (dis_res == 0)
        finally:
            if p_interfaces:
                self._wlan.WlanFreeMemory(p_interfaces)
            self._wlan.WlanCloseHandle(handle, None)

        return success


# Global client instance
_wifi_client = NativeWiFiClient()


def wifi_scan() -> CapabilityResult:
    """Scan and list available Wi-Fi networks (Tier A)."""
    if not _wifi_client.is_available:
        return CapabilityResult.fail(
            capability="wifi_scan",
            message="Native Wi-Fi API is not available on this platform.",
            error_code=CapabilityErrorCode.UNAVAILABLE,
        )

    try:
        networks = _wifi_client.get_networks()
        # Sort by signal quality descending
        networks.sort(key=lambda n: n.signal_quality, reverse=True)
        net_dicts = [n.to_dict() for n in networks]

        # De-duplicate by SSID keeping strongest signal
        seen_ssids = set()
        deduped = []
        for n in net_dicts:
            if n["ssid"] not in seen_ssids:
                seen_ssids.add(n["ssid"])
                deduped.append(n)

        msg = f"Discovered {len(deduped)} wireless networks."
        return CapabilityResult.ok(
            capability="wifi_scan",
            message=msg,
            data={"networks": deduped, "count": len(deduped), "tier": InteractionTier.TIER_A_NATIVE.value},
        )
    except Exception as exc:
        logger.error("Failed to scan Wi-Fi networks: %s", exc, exc_info=True)
        return CapabilityResult.fail(
            capability="wifi_scan",
            message=f"Error scanning Wi-Fi: {exc}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )


def wifi_status() -> CapabilityResult:
    """Query Wi-Fi adapter and active connection state (Tier A)."""
    if not _wifi_client.is_available:
        return CapabilityResult.fail(
            capability="wifi_status",
            message="Native Wi-Fi API is not available on this platform.",
            error_code=CapabilityErrorCode.UNAVAILABLE,
        )

    try:
        status = _wifi_client.get_status()
        networks = _wifi_client.get_networks()
        active_net = next((n for n in networks if n.connected), None)

        data = {
            "status": status,
            "connected": active_net is not None,
            "active_network": active_net.to_dict() if active_net else None,
            "tier": InteractionTier.TIER_A_NATIVE.value,
        }

        if active_net:
            msg = f"Connected to Wi-Fi '{active_net.ssid}' ({active_net.signal_quality}% signal)."
        else:
            msg = "Wi-Fi is enabled but not connected to any network."

        return CapabilityResult.ok(
            capability="wifi_status",
            message=msg,
            data=data,
        )
    except Exception as exc:
        logger.error("Failed to query Wi-Fi status: %s", exc, exc_info=True)
        return CapabilityResult.fail(
            capability="wifi_status",
            message=f"Error querying Wi-Fi status: {exc}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )


def wifi_connect(ssid: str) -> CapabilityResult:
    """Connect to a Wi-Fi network by SSID or profile name using fuzzy resolution (Tier A)."""
    if not _wifi_client.is_available:
        return CapabilityResult.fail(
            capability="wifi_connect",
            message="Native Wi-Fi API is not available on this platform.",
            error_code=CapabilityErrorCode.UNAVAILABLE,
        )

    if not ssid or not ssid.strip():
        return CapabilityResult.fail(
            capability="wifi_connect",
            message="SSID cannot be empty.",
            error_code=CapabilityErrorCode.INVALID_ARGUMENT,
        )

    try:
        networks = _wifi_client.get_networks()
        matched = WiFiResolver.resolve_ssid(ssid, networks)

        if not matched:
            return CapabilityResult.fail(
                capability="wifi_connect",
                message=f"Wi-Fi network '{ssid}' not found in available scan.",
                error_code=CapabilityErrorCode.NOT_FOUND,
            )

        target_profile = matched.profile_name if matched.profile_name else matched.ssid
        success = _wifi_client.connect_profile(target_profile)

        if success:
            return CapabilityResult.ok(
                capability="wifi_connect",
                message=f"Connection request dispatched for '{matched.ssid}'.",
                data={"ssid": matched.ssid, "profile": target_profile, "tier": InteractionTier.TIER_A_NATIVE.value},
            )
        else:
            return CapabilityResult.fail(
                capability="wifi_connect",
                message=f"Failed to initiate connection to '{matched.ssid}'. Ensure profile is configured.",
                error_code=CapabilityErrorCode.OS_ERROR,
            )
    except Exception as exc:
        logger.error("Failed to connect Wi-Fi: %s", exc, exc_info=True)
        return CapabilityResult.fail(
            capability="wifi_connect",
            message=f"Error connecting to Wi-Fi: {exc}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )


def wifi_disconnect() -> CapabilityResult:
    """Disconnect currently active Wi-Fi connection (Tier A)."""
    if not _wifi_client.is_available:
        return CapabilityResult.fail(
            capability="wifi_disconnect",
            message="Native Wi-Fi API is not available on this platform.",
            error_code=CapabilityErrorCode.UNAVAILABLE,
        )

    try:
        success = _wifi_client.disconnect()
        if success:
            return CapabilityResult.ok(
                capability="wifi_disconnect",
                message="Wi-Fi disconnected successfully.",
                data={"tier": InteractionTier.TIER_A_NATIVE.value},
            )
        else:
            return CapabilityResult.fail(
                capability="wifi_disconnect",
                message="Failed to disconnect Wi-Fi or no active connection.",
                error_code=CapabilityErrorCode.OS_ERROR,
            )
    except Exception as exc:
        logger.error("Failed to disconnect Wi-Fi: %s", exc, exc_info=True)
        return CapabilityResult.fail(
            capability="wifi_disconnect",
            message=f"Error disconnecting Wi-Fi: {exc}",
            error_code=CapabilityErrorCode.OS_ERROR,
        )
