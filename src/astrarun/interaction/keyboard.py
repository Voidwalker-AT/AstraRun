"""Strongly typed keyboard shortcut parsing, validation, and safe dispatch."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import re
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

from astrarun.capabilities.models import CapabilityErrorCode
from astrarun.core.logging import get_logger
from astrarun.interaction.models import KeyboardShortcut
from astrarun.interaction.policy import is_simulated_interaction_validation

logger = get_logger("astrarun.interaction.keyboard")

# Whitelist of recognized modifier keys
ALLOWED_MODIFIERS: Set[str] = {"ctrl", "shift", "alt", "win"}

# Win32 Virtual Key Mappings
VK_MAPPINGS: Dict[str, int] = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}

MODIFIER_VK: Dict[str, int] = {
    "ctrl": 0x11,   # VK_CONTROL
    "shift": 0x10,  # VK_SHIFT
    "alt": 0x12,    # VK_MENU
    "win": 0x5B,    # VK_LWIN
}

# Win32 SendInput Structures
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_ulonglong),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("_u",)
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("_u", _INPUT_UNION),
    ]


def parse_shortcut(shortcut_str: str) -> Optional[KeyboardShortcut]:
    """
    Parse a shortcut string like 'ctrl+c', 'ctrl+shift+p', 'alt+f4' into a typed KeyboardShortcut.
    Strictly validates tokens against a whitelist, rejecting shell commands or arbitrary text.
    """
    if not shortcut_str or not shortcut_str.strip():
        return None

    clean = shortcut_str.strip().lower()
    # Normalize separators (e.g. 'ctrl-c' or 'ctrl + c')
    clean = re.sub(r"[\s\-_]+", "+", clean)
    tokens = [t for t in clean.split("+") if t]

    if not tokens:
        return None

    modifiers: list[str] = []
    keys: list[str] = []

    for t in tokens:
        if t in ("control", "ctrl"):
            modifiers.append("ctrl")
        elif t == "shift":
            modifiers.append("shift")
        elif t in ("alt", "menu"):
            modifiers.append("alt")
        elif t in ("win", "windows", "super", "cmd"):
            modifiers.append("win")
        else:
            keys.append(t)

    # Invariant: A valid shortcut must contain exactly one primary key token
    if len(keys) != 1:
        logger.warning("Rejected invalid shortcut '%s': key token count %d != 1", shortcut_str, len(keys))
        return None

    primary_key = keys[0]

    # Validate primary key: single character (a-z, 0-9) or standard function/nav key
    if len(primary_key) == 1 and (primary_key.isalnum() or primary_key in "`-=[]\\;',./"):
        return KeyboardShortcut(modifiers=sorted(list(set(modifiers))), key=primary_key)

    if primary_key in VK_MAPPINGS:
        return KeyboardShortcut(modifiers=sorted(list(set(modifiers))), key=primary_key)

    logger.warning("Rejected unrecognized shortcut primary key: '%s'", primary_key)
    return None


def dispatch_shortcut(shortcut: KeyboardShortcut, target_hwnd: Optional[int] = None) -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """
    Dispatch a validated keyboard shortcut via Win32 SendInput with keybd_event fallback.
    Optionally activates the target window before dispatching.
    """
    if sys.platform != "win32" or is_simulated_interaction_validation():
        logger.info("Simulated dispatch of shortcut '%s' to HWND %s", shortcut.canonical_string, target_hwnd)
        return True, f"Pressed '{shortcut.canonical_string}' (simulated).", None

    try:
        from astrarun.computer_use.hooks.desktop_attach import ensure_desktop_attached
        ensure_desktop_attached()
    except Exception:
        pass

    user32 = ctypes.windll.user32

    if target_hwnd:
        try:
            from astrarun.ui.presentation import force_foreground_activation
            force_foreground_activation(target_hwnd)
            time.sleep(0.1)
        except Exception as e:
            logger.debug("Failed setting foreground before shortcut dispatch: %s", e)

    # Resolve primary key VK code
    key_lower = shortcut.key.lower()
    if key_lower in VK_MAPPINGS:
        primary_vk = VK_MAPPINGS[key_lower]
    elif len(key_lower) == 1:
        # Ordinal for standard alphanumeric characters
        primary_vk = ord(key_lower.upper())
    else:
        return False, f"Unmapped virtual key '{shortcut.key}'.", CapabilityErrorCode.INVALID_ARGUMENT

    inputs: list[INPUT] = []

    # 1. Press modifier keys down
    for mod in shortcut.modifiers:
        vk = MODIFIER_VK.get(mod)
        if vk:
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
            inputs.append(inp)

    # 2. Press primary key down
    inp_key_down = INPUT(type=INPUT_KEYBOARD)
    inp_key_down.ki = KEYBDINPUT(wVk=primary_vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
    inputs.append(inp_key_down)

    # 3. Release primary key up
    inp_key_up = INPUT(type=INPUT_KEYBOARD)
    inp_key_up.ki = KEYBDINPUT(wVk=primary_vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
    inputs.append(inp_key_up)

    # 4. Release modifier keys up (in reverse order)
    for mod in reversed(shortcut.modifiers):
        vk = MODIFIER_VK.get(mod)
        if vk:
            inp = INPUT(type=INPUT_KEYBOARD)
            inp.ki = KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
            inputs.append(inp)

    # Send batch input
    c_inputs = (INPUT * len(inputs))(*inputs)
    count = user32.SendInput(len(inputs), c_inputs, ctypes.sizeof(INPUT))
    if count == len(inputs):
        return True, f"Pressed '{shortcut.canonical_string}'.", None

    # Fallback to keybd_event if SendInput was blocked
    try:
        for mod in shortcut.modifiers:
            vk = MODIFIER_VK.get(mod)
            if vk:
                user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(primary_vk, 0, 0, 0)
        time.sleep(0.02)
        user32.keybd_event(primary_vk, 0, KEYEVENTF_KEYUP, 0)
        for mod in reversed(shortcut.modifiers):
            vk = MODIFIER_VK.get(mod)
            if vk:
                user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        return True, f"Pressed '{shortcut.canonical_string}' via keybd_event fallback.", None
    except Exception as ex:
        logger.error("keybd_event fallback failed for shortcut '%s': %s", shortcut.canonical_string, ex)

    return False, f"SendInput failed: sent {count}/{len(inputs)} events.", CapabilityErrorCode.OS_ERROR


def type_text_into_active(text: str) -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """
    Type literal text into the active/focused control using Unicode SendInput events with keybd_event fallback.
    Does NOT evaluate text as a command or shell script.
    """
    if not text:
        return True, "No text to type.", None

    if sys.platform != "win32" or is_simulated_interaction_validation():
        return True, f"Typed {len(text)} characters (simulated).", None

    try:
        from astrarun.computer_use.hooks.desktop_attach import ensure_desktop_attached
        ensure_desktop_attached()
    except Exception:
        pass

    user32 = ctypes.windll.user32
    inputs: list[INPUT] = []

    for char in text:
        code = ord(char)
        # Key down
        inp_down = INPUT(type=INPUT_KEYBOARD)
        inp_down.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)
        inputs.append(inp_down)
        # Key up
        inp_up = INPUT(type=INPUT_KEYBOARD)
        inp_up.ki = KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
        inputs.append(inp_up)

    c_inputs = (INPUT * len(inputs))(*inputs)
    count = user32.SendInput(len(inputs), c_inputs, ctypes.sizeof(INPUT))
    if count == len(inputs):
        return True, f"Typed {len(text)} characters.", None

    # Fallback to character-by-character keybd_event Unicode
    try:
        for char in text:
            code = ord(char)
            user32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
            time.sleep(0.001)
            user32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
        return True, f"Typed {len(text)} characters via keybd_event fallback.", None
    except Exception as ex:
        logger.error("keybd_event typing fallback failed: %s", ex)

    return False, f"SendInput unicode typing failed: {count}/{len(inputs)} events sent.", CapabilityErrorCode.OS_ERROR
