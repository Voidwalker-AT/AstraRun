"""Centralized Motion Tokens and Animation Controller for AstraRun v0.11 UI."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from typing import Optional

from PySide6.QtCore import QEasingCurve


class MotionTokens:
    """Design tokens governing animation durations, curves, and accessibility compliance."""

    # Standard animation durations (milliseconds)
    ENTER_DURATION_MS: int = 200
    EXIT_DURATION_MS: int = 150
    EXPAND_DURATION_MS: int = 220
    COLLAPSE_DURATION_MS: int = 180
    STEP_TRANSITION_MS: int = 120
    PULSE_DURATION_MS: int = 800

    # Motion curves
    EASING_ENTER: QEasingCurve.Type = QEasingCurve.Type.OutCubic
    EASING_EXIT: QEasingCurve.Type = QEasingCurve.Type.InCubic
    EASING_EXPAND: QEasingCurve.Type = QEasingCurve.Type.OutQuad
    EASING_COLLAPSE: QEasingCurve.Type = QEasingCurve.Type.InOutQuad

    @staticmethod
    def is_reduced_motion_enabled() -> bool:
        """
        Check if the user has disabled animations in Windows accessibility settings
        via SPI_GETCLIENTAREAANIMATION.
        """
        if sys.platform != "win32":
            return False

        try:
            SPI_GETCLIENTAREAANIMATION = 0x1042
            b_anim = ctypes.wintypes.BOOL()
            res = ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(b_anim), 0
            )
            if res:
                # If animation is NOT enabled, reduced motion is requested
                return not bool(b_anim.value)
        except Exception:
            pass

        return False

    @classmethod
    def get_enter_duration(cls, force_reduced: Optional[bool] = None) -> int:
        if force_reduced or cls.is_reduced_motion_enabled():
            return 0
        return cls.ENTER_DURATION_MS

    @classmethod
    def get_exit_duration(cls, force_reduced: Optional[bool] = None) -> int:
        if force_reduced or cls.is_reduced_motion_enabled():
            return 0
        return cls.EXIT_DURATION_MS

    @classmethod
    def get_expand_duration(cls, force_reduced: Optional[bool] = None) -> int:
        if force_reduced or cls.is_reduced_motion_enabled():
            return 0
        return cls.EXPAND_DURATION_MS

    @classmethod
    def get_step_duration(cls, force_reduced: Optional[bool] = None) -> int:
        if force_reduced or cls.is_reduced_motion_enabled():
            return 0
        return cls.STEP_TRANSITION_MS
