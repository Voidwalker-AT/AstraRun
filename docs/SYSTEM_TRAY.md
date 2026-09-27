# SYSTEM_TRAY.md — System Tray Integration & Notification Area Controls

> **Milestone**: AstraRun v0.9 (Daily Driver Integration & Window Intelligence)  
> **Status**: APPROVED  
> **Subsystem**: `src/astrarun/ui/tray.py`  
> **Target Audience**: Desktop UI Engineers, Windows UX Designers  
> **Last Updated**: 2026-09-27  

---

## 1. Overview & Resident UX Philosophy

A true daily driver utility must never demand constant taskbar real estate or require a permanent console window. AstraRun v0.9 integrates with the Windows Notification Area (System Tray) via PySide6's `QSystemTrayIcon`:
- **Unobtrusive Ambient Presence**: AstraRun lives quietly in the tray, waiting for `Alt+Space` or tray icon interactions.
- **Custom Native Painting**: Rather than bundling static raster assets that blur or pixelate under Windows DPI scaling, the AstraRun icon is rendered programmatically using `QPainter` with Catppuccin Mocha themed palette colors (`#cba6f7` Mauve and `#11111b` Crust).
- **Fast-Action Context Menu**: Right-clicking the tray icon exposes direct entry points into all platform views and diagnostics.

---

## 2. Programmatic Icon Rendering

To maintain razor-sharp rendering across 100%, 125%, 150%, and 200% Windows display scaling, `_create_default_icon()` dynamically draws the icon onto a 64x64 high-DPI `QPixmap`:

```python
def _create_default_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Background circle (Dark Crust: #181825)
    bg_color = QColor("#181825")
    painter.setBrush(QBrush(bg_color))
    painter.setPen(QPen(QColor("#cba6f7"), 3))
    painter.drawEllipse(4, 4, 56, 56)

    # Stylized AstraRun "A" Glyph (Catppuccin Mauve: #cba6f7)
    pen = QPen(QColor("#cba6f7"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.drawLine(32, 16, 20, 48)  # Left leg
    painter.drawLine(32, 16, 44, 48)  # Right leg
    painter.drawLine(24, 38, 40, 38)  # Crossbar

    painter.end()
    return QIcon(pixmap)
```

---

## 3. Tray Context Menu Architecture

Right-clicking the tray icon reveals a structured `QMenu`:

```text
┌─────────────────────────────────────────┐
│ AstraRun v0.9                           │ (Bold Header)
├─────────────────────────────────────────┤
│ 🚀 Open Launcher (Alt+Space)            │ -> Toggles Launcher Overlay
├─────────────────────────────────────────┤
│ 📜 Task History & Timeline...          │ -> Opens HistoryDialog
│ 🧠 Learned Memory & Aliases...         │ -> Opens MemoryDialog
│ ⚡ Mined Skills & Workflows...          │ -> Opens SkillReviewDialog
│ 🛠️ System Diagnostics...              │ -> Opens DiagnosticsDialog
│ ⚙️ Settings & Preferences...           │ -> Opens SettingsDialog
├─────────────────────────────────────────┤
│ ❌ Exit AstraRun                        │ -> Graceful Application Shutdown
└─────────────────────────────────────────┘
```

---

## 4. Activation Events & Tray Notifications

1. **Left-Click / Double-Click**:
   - Clicking or double-clicking the tray icon immediately triggers `launcher.toggle_visibility()`, positioning the launcher centered on the active screen.
2. **System Balloon Messages (`showMessage`)**:
   - Used sparingly for critical asynchronous events:
     - Learning Engine discovered and approved a new skill pattern.
     - Long-running background task completed or failed.
     - Hotkey registration conflicts detected upon startup.
