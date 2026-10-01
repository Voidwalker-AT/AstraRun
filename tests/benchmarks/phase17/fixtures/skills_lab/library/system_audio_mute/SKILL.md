---
name: system_audio_mute
description: Toggle or set master audio output volume and mute state via CoreAudio.
version: 1.0.0
author: AstraRun Engine
tags: [audio, volume, sound, media]
inputs: [action, volume_level, device_endpoint]
platforms: [windows]
---

# Master Audio Volume & Mute Management Skill

## Overview
Inspects, sets, or toggles master audio endpoint mute state and scalar volume levels using native Windows CoreAudio interfaces.

## When to Use
- When the user asks to mute, unmute, or adjust system audio volume.
- When entering a meeting or focus mode requiring audio silence.
- When checking current speaker output levels.

## Required Parameters
- `action` (string): Action to execute: 'mute', 'unmute', 'toggle', or 'set_volume'.
- `volume_level` (integer, optional): Target volume scalar from 0 to 100 (required if action is 'set_volume').
- `device_endpoint` (string, optional): Specific audio output device name or 'default' (default: 'default').

## Procedure
1. Initialize Windows CoreAudio MMDeviceEnumerator COM endpoint.
2. Query default audio render device (`eRender`, `eMultimedia`).
3. Activate `IAudioEndpointVolume` interface.
4. Execute requested action:
   - If `mute`: call `SetMute(TRUE)`.
   - If `unmute`: call `SetMute(FALSE)`.
   - If `toggle`: query `GetMute()` and invert state.
   - If `set_volume`: convert 0-100 scalar to float range [0.0, 1.0] and call `SetMasterVolumeLevelScalar`.
5. Read back applied state to verify action.
6. Return structured JSON payload with active mute state and volume scalar.

## Verification Steps
- Read back master volume level to confirm target value within 1% tolerance.
- Confirm mute flag reflects commanded state.

