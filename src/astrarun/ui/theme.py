"""AstraRun 1.0 Unified Design System and Theme Tokens.

Provides canonical color tokens, typography scales, spacing, border radii,
and standardized Qt stylesheets for the dark, technical, restrained desktop UI.

Visual system character:
  - Dominant surfaces: Near-black (#0c0d10), Elevated Charcoal (#141519), Graphite (#1c1e24)
  - Neutral low-contrast borders: #282a32, #383b46
  - Text hierarchy: High-legibility near-white (#f0f2f5), neutral gray (#9ea3ae), muted (#606470)
  - Accent signal: Restrained cool Astra periwinkle/blue (#5b8cf7)
  - Status signals: Semantic muted tones (Success: #38b26e, Warning: #d99b38, Danger: #d64545)
"""

from __future__ import annotations

from typing import Optional


# =============================================================================
# COLOR TOKENS
# =============================================================================

# Background & Surface Hierarchy
BG_APP = "#0c0d10"             # Foundational dark canvas (near-black)
SURFACE = "#141519"            # Elevated dark charcoal (windows, overlays)
SURFACE_RAISED = "#1c1e24"     # Secondary elevated surface (cards, panels, sections)
SURFACE_HOVER = "#24262f"      # Hover state for interactive items
SURFACE_PRESSED = "#181920"    # Pressed/Active state for interactive items
SURFACE_INPUT = "#101115"      # Input background (subtle indentation)

# Borders & Separators
BORDER_SUBTLE = "#1e2026"      # Very quiet divider
BORDER = "#282a32"             # Standard structural border
BORDER_STRONG = "#383b46"      # Focused, active, or prominent border

# Text & Content
TEXT_PRIMARY = "#f0f2f5"       # High-contrast primary reading text
TEXT_SECONDARY = "#9ea3ae"     # Subtitle, metadata, descriptive labels
TEXT_MUTED = "#606470"         # Timestamps, minor hints, inactive states
TEXT_DISABLED = "#3e414c"      # Disabled labels and controls

# Primary Brand / Accent (Cool restrained Astra periwinkle-blue)
ACCENT = "#5b8cf7"             # Accent signal and focus indicators
ACCENT_HOVER = "#6d99f8"       # Accent interactive hover
ACCENT_PRESSED = "#4a7ae8"     # Accent active press
ACCENT_SUBTLE = "#162036"      # Accent container / badge background
ACCENT_BORDER = "#2a3d66"      # Accent badge / outline border

# Status Signals
SUCCESS = "#38b26e"            # Muted green (Completed, Healthy, Approved)
SUCCESS_BG = "#12251c"
SUCCESS_BORDER = "#1f4a31"

WARNING = "#d99b38"            # Muted amber (Paused, Pending review, Medium risk)
WARNING_BG = "#292012"
WARNING_BORDER = "#523c1b"

DANGER = "#d64545"             # Muted red (Failed, High risk, Cancel, Terminate)
DANGER_BG = "#2a1416"
DANGER_BORDER = "#5c2024"

ATTENTION = "#8270db"          # Muted violet (Needs user action, Clarification)
ATTENTION_BG = "#1d192e"
ATTENTION_BORDER = "#392f60"

# Category Badge Colors
CATEGORY_COLORS = {
    "APP": (ACCENT, ACCENT_SUBTLE, ACCENT_BORDER),
    "FOLDER": (WARNING, WARNING_BG, WARNING_BORDER),
    "WEB": (SUCCESS, SUCCESS_BG, SUCCESS_BORDER),
    "COMMAND": (ATTENTION, ATTENTION_BG, ATTENTION_BORDER),
    "SKILL": (ACCENT, ACCENT_SUBTLE, ACCENT_BORDER),
    "TASK": (TEXT_SECONDARY, SURFACE_RAISED, BORDER),
}


# =============================================================================
# TYPOGRAPHY & SPACING TOKENS
# =============================================================================

FONT_FAMILY = "'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif"
FONT_MONO = "'Cascadia Code', 'Consolas', 'Segoe UI Mono', monospace"

FONT_SIZE_TITLE_LG = "16px"
FONT_SIZE_TITLE = "14px"
FONT_SIZE_BODY = "13px"
FONT_SIZE_CAPTION = "11px"
FONT_SIZE_SMALL = "10px"

# Radii
RADIUS_SM = 4
RADIUS_MD = 8
RADIUS_LG = 12
RADIUS_ROUND = 999

# Spacing
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 20
SPACE_2XL = 24


# =============================================================================
# REUSABLE QT STYLESHEET SNIPPETS
# =============================================================================

def get_button_style(
    variant: str = "secondary",
    size: str = "md",
    font_weight: str = "500",
) -> str:
    """Generate consistent Qt stylesheet for standard button variants.
    
    Variants:
      - 'primary': Bold accent button for primary affirmative workflow steps
      - 'secondary': Charcoal raised button with quiet border for default actions
      - 'ghost': Borderless transparent button for subtle tools / dismiss
      - 'danger': Explicit warning/red button for destructive / irreversible actions
      - 'subtle': Quiet outline button for small auxiliary actions
    """
    padding = {
        "sm": "2px 8px",
        "md": "5px 12px",
        "lg": "8px 16px",
    }.get(size, "5px 12px")

    font_size = {
        "sm": FONT_SIZE_CAPTION,
        "md": FONT_SIZE_BODY,
        "lg": FONT_SIZE_TITLE,
    }.get(size, FONT_SIZE_BODY)

    radius = RADIUS_SM if size == "sm" else RADIUS_MD

    if variant == "primary":
        return f"""
            QPushButton {{
                background-color: {ACCENT};
                color: #ffffff;
                border: 1px solid {ACCENT};
                border-radius: {radius}px;
                padding: {padding};
                font-family: {FONT_FAMILY};
                font-size: {font_size};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {ACCENT_HOVER};
                border-color: {ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {ACCENT_PRESSED};
                border-color: {ACCENT_PRESSED};
            }}
            QPushButton:disabled {{
                background-color: {SURFACE_RAISED};
                color: {TEXT_DISABLED};
                border-color: {BORDER};
            }}
        """
    elif variant == "danger":
        return f"""
            QPushButton {{
                background-color: {DANGER};
                color: #ffffff;
                border: 1px solid {DANGER};
                border-radius: {radius}px;
                padding: {padding};
                font-family: {FONT_FAMILY};
                font-size: {font_size};
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #e35555;
                border-color: #e35555;
            }}
            QPushButton:pressed {{
                background-color: #b83333;
                border-color: #b83333;
            }}
            QPushButton:disabled {{
                background-color: {SURFACE_RAISED};
                color: {TEXT_DISABLED};
                border-color: {BORDER};
            }}
        """
    elif variant == "ghost":
        return f"""
            QPushButton {{
                background-color: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                border-radius: {radius}px;
                padding: {padding};
                font-family: {FONT_FAMILY};
                font-size: {font_size};
                font-weight: {font_weight};
            }}
            QPushButton:hover {{
                background-color: {SURFACE_HOVER};
                color: {TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {SURFACE_PRESSED};
                color: {TEXT_PRIMARY};
            }}
            QPushButton:disabled {{
                color: {TEXT_DISABLED};
            }}
        """
    elif variant == "subtle":
        return f"""
            QPushButton {{
                background-color: {SURFACE_RAISED};
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: {radius}px;
                padding: {padding};
                font-family: {FONT_FAMILY};
                font-size: {font_size};
                font-weight: {font_weight};
            }}
            QPushButton:hover {{
                background-color: {SURFACE_HOVER};
                border-color: {BORDER};
                color: {TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background-color: {SURFACE_PRESSED};
            }}
            QPushButton:disabled {{
                color: {TEXT_DISABLED};
                border-color: {BORDER_SUBTLE};
            }}
        """
    else:  # "secondary" default
        return f"""
            QPushButton {{
                background-color: {SURFACE_RAISED};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: {radius}px;
                padding: {padding};
                font-family: {FONT_FAMILY};
                font-size: {font_size};
                font-weight: {font_weight};
            }}
            QPushButton:hover {{
                background-color: {SURFACE_HOVER};
                border-color: {BORDER_STRONG};
            }}
            QPushButton:pressed {{
                background-color: {SURFACE_PRESSED};
                border-color: {BORDER};
            }}
            QPushButton:disabled {{
                background-color: {SURFACE};
                color: {TEXT_DISABLED};
                border-color: {BORDER_SUBTLE};
            }}
        """


def get_badge_style(color: str, bg_color: str, border_color: Optional[str] = None) -> str:
    """Return styling for discrete status and category badges."""
    b_col = border_color or f"{color}33"
    return f"""
        color: {color};
        background-color: {bg_color};
        border: 1px solid {b_col};
        border-radius: 4px;
        padding: 2px 6px;
        font-family: {FONT_FAMILY};
        font-size: {FONT_SIZE_SMALL};
        font-weight: 600;
    """


SCROLLBAR_STYLE = f"""
    QScrollBar:vertical {{
        width: 6px;
        background-color: transparent;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {BORDER};
        min-height: 24px;
        border-radius: 3px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {BORDER_STRONG};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}
"""
