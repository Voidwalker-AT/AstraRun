---
name: wifi_reconnect
description: Scan, connect to a specified Wi-Fi SSID, and verify internet connectivity.
version: 1.0.0
author: AstraRun Procedural Engine
tags: [network, wifi, connectivity, diagnostics]
inputs: [ssid, target_host, timeout_seconds]
platforms: [windows]
---

# Wi-Fi Reconnect & Verification Skill

## Overview
Automates scanning, connecting to a wireless access point, and verifying end-to-end IP connectivity.

## When to Use
- When the host loses Wi-Fi connection or drops offline.
- When instructed to connect to a specific Wi-Fi SSID.
- To diagnose wireless network link status.

## Required Parameters
- `ssid` (string): The target Wi-Fi network SSID (e.g. 'campus-guest').
- `target_host` (string, optional): Ping verification host (default: '8.8.8.8').
- `timeout_seconds` (integer, optional): Connection timeout in seconds (default: 15).

## Procedure
1. Load arguments from `args.json`.
2. Verify adapter state.
3. Initiate association with target SSID.
4. Verify ping reachability to `target_host`.
5. Return JSON execution artifact.
