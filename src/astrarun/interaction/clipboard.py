"""Privacy-preserving clipboard interaction utilities."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from typing import Optional, Tuple

from astrarun.capabilities.models import CapabilityErrorCode
from astrarun.core.logging import get_logger
from astrarun.interaction.policy import is_simulated_interaction_validation

logger = get_logger("astrarun.interaction.clipboard")

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

_SIMULATED_CLIPBOARD: str = "AstraRun simulated clipboard content"


def _setup_clipboard_prototypes():
    """Configure Win32 kernel32 and user32 function pointer types for 64-bit compatibility."""
    if sys.platform != "win32":
        return

    kernel32 = ctypes.windll.kernel32
    user32 = ctypes.windll.user32

    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [ctypes.wintypes.UINT, ctypes.c_size_t]

    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]

    kernel32.GlobalUnlock.restype = ctypes.wintypes.BOOL
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]

    kernel32.GlobalFree.restype = ctypes.c_void_p
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]

    user32.GetClipboardData.restype = ctypes.c_void_p
    user32.GetClipboardData.argtypes = [ctypes.wintypes.UINT]

    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [ctypes.wintypes.UINT, ctypes.c_void_p]


def get_clipboard_text() -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """
    Safely retrieve text content from the system clipboard.
    Returns (success, text, error_code).
    """
    global _SIMULATED_CLIPBOARD
    if sys.platform != "win32" or is_simulated_interaction_validation():
        return True, _SIMULATED_CLIPBOARD, None

    _setup_clipboard_prototypes()
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    if not user32.OpenClipboard(None):
        return False, "Unable to open Windows clipboard.", CapabilityErrorCode.OS_ERROR

    try:
        h_clip_mem = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_clip_mem:
            return True, "", None  # Clipboard is empty or contains non-text data

        p_clip_mem = kernel32.GlobalLock(h_clip_mem)
        if not p_clip_mem:
            return False, "Failed to lock clipboard memory.", CapabilityErrorCode.OS_ERROR

        try:
            text = ctypes.c_wchar_p(p_clip_mem).value or ""
            return True, text, None
        finally:
            kernel32.GlobalUnlock(h_clip_mem)
    finally:
        user32.CloseClipboard()


def set_clipboard_text(text: str) -> Tuple[bool, str, Optional[CapabilityErrorCode]]:
    """
    Safely write text content to the system clipboard.
    Returns (success, message, error_code).
    """
    global _SIMULATED_CLIPBOARD
    if sys.platform != "win32" or is_simulated_interaction_validation():
        _SIMULATED_CLIPBOARD = text
        return True, "Clipboard updated (simulated).", None

    _setup_clipboard_prototypes()
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    if not user32.OpenClipboard(None):
        return False, "Unable to open Windows clipboard.", CapabilityErrorCode.OS_ERROR

    try:
        if not user32.EmptyClipboard():
            return False, "Unable to clear Windows clipboard.", CapabilityErrorCode.OS_ERROR

        buf = ctypes.create_unicode_buffer(text)
        nbytes = ctypes.sizeof(buf)
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, nbytes)
        if not h_mem:
            return False, "Failed to allocate global memory for clipboard.", CapabilityErrorCode.OS_ERROR

        p_mem = kernel32.GlobalLock(h_mem)
        if not p_mem:
            kernel32.GlobalFree(h_mem)
            return False, "Failed to lock global memory for clipboard.", CapabilityErrorCode.OS_ERROR

        try:
            ctypes.memmove(p_mem, ctypes.addressof(buf), nbytes)
        finally:
            kernel32.GlobalUnlock(h_mem)

        if not user32.SetClipboardData(CF_UNICODETEXT, h_mem):
            kernel32.GlobalFree(h_mem)
            return False, "SetClipboardData failed.", CapabilityErrorCode.OS_ERROR

        return True, "Clipboard updated successfully.", None
    finally:
        user32.CloseClipboard()
