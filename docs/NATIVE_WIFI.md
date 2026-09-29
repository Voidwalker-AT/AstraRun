# Native Wi-Fi Capabilities (Tier A)

> **Module**: `astrarun.tools.wifi`  
> **Status**: APPROVED & VERIFIED  
> **Platform**: Windows 11 x64 (Native Wi-Fi API / `wlanapi.dll`)  

---

## 1. Overview

AstraRun v0.11 provides direct integration with the Windows Native Wi-Fi API (`wlanapi.dll`), eliminating fragile subprocess execution of `netsh wlan` or PowerShell scripts.

---

## 2. Capabilities Exposed

| Capability ID | Category | Tier | Description |
| :--- | :--- | :--- | :--- |
| `wifi_scan` | `NETWORK` | `TIER_A_NATIVE` | Scans and lists available 802.11 networks with signal quality |
| `wifi_status` | `NETWORK` | `TIER_A_NATIVE` | Returns active adapter state, connected SSID, and signal quality |
| `wifi_connect` | `NETWORK` | `TIER_A_NATIVE` | Connects to a network profile using fuzzy SSID resolution |
| `wifi_disconnect`| `NETWORK` | `TIER_A_NATIVE` | Disconnects the active Wi-Fi connection |

---

## 3. Security & Invariants

1. **Zero Child Processes**:
   - All calls execute in-process via `ctypes` bindings to `wlanapi.dll` (`WlanOpenHandle`, `WlanEnumInterfaces`, `WlanGetAvailableNetworkList`, `WlanConnect`).
2. **Zero Credential Exposure**:
   - Connections utilize existing Windows profiles configured on the machine. Passwords/keys are never accepted as arguments or recorded in telemetry logs.
3. **Fuzzy SSID Resolution (`WiFiResolver`)**:
   - Supports exact, substring, and difflib fuzzy matching for spoken or mistyped network names.
