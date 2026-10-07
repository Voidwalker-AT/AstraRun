import sys
import ctypes
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from astrarun.core.models import AppInfo, RoutingContext
from astrarun.hotkeys.manager import HotkeyManager, format_shortcut_name
from astrarun.search.index import SearchIndex
from astrarun.ui.hotkey_conflict import HotkeyConflictDialog
from astrarun.ui.launcher import LauncherWindow
from astrarun.ui.settings import SettingsDialog

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    idx = SearchIndex()
    apps = {
        'intel_gfx_1': AppInfo(key='intel_gfx_1', name='Intel(R) Graphics Software', path=r'C:\Windows\System32\igfx.exe'),
        'intel_gfx_2': AppInfo(key='intel_gfx_2', name='Intel(R) Graphics Software', path=r'C:\Windows\System32\igfx.exe'),
        'calc': AppInfo(key='calc', name='Calculator', path=r'C:\Windows\System32\calc.exe'),
        'notepad': AppInfo(key='notepad', name='Notepad', path=r'C:\Windows\System32\notepad.exe'),
    }
    idx.build_from_sources(apps, {}, {}, {})
    ctx = RoutingContext(apps=apps, search_index=idx)

    launcher = LauncherWindow(context=ctx)
    launcher.show()

    # Test 1: typing 'hi'
    launcher.input_field.setText('hi')
    app.processEvents()
    print("Test 1: typing 'hi' -> suggestions visible:", launcher.suggestions_list.isVisible(), "items:", launcher.suggestions_list.count())
    assert not launcher.suggestions_list.isVisible(), "Suggestions should be hidden for 'hi'"

    # Test 1b: execute 'hi'
    launcher.execute_command()
    app.processEvents()
    print("Test 1b: Enter on 'hi' -> status text:", launcher.status_label.text().encode('ascii', 'replace').decode('ascii'))
    assert "Hi. What do you need?" in launcher.status_label.text(), "Feedback should invite command"

    # Test 2: typing 'calc'
    launcher.input_field.setText('calc')
    app.processEvents()
    print("Test 2: typing 'calc' -> suggestions visible:", launcher.suggestions_list.isVisible(), "items:", launcher.suggestions_list.count())
    assert launcher.suggestions_list.isVisible(), "Suggestions should be visible for 'calc'"
    assert launcher.suggestions_list.count() == 1, "Should have exactly 1 suggestion for 'calc'"
    res_item = launcher.suggestions_list.item(0).data(Qt.ItemDataRole.UserRole)
    print("Top suggestion for 'calc':", res_item.name, "score:", res_item.score)
    assert res_item.name == "Calculator"

    # Test 3: typing 'what gpu do i have'
    launcher.input_field.setText('what gpu do i have')
    app.processEvents()
    print("Test 3: typing 'what gpu do i have' -> suggestions visible:", launcher.suggestions_list.isVisible())
    assert not launcher.suggestions_list.isVisible(), "Suggestions should be hidden for questions"

    # Test 4: typing 'make me a test file'
    launcher.input_field.setText('make me a test file')
    app.processEvents()
    print("Test 4: typing 'make me a test file' -> suggestions visible:", launcher.suggestions_list.isVisible())
    assert not launcher.suggestions_list.isVisible(), "Suggestions should be hidden for goals"

    launcher.close()

    # Test 5: HotkeyManager conflict detection and HotkeyConflictDialog
    print("\n--- Test 5: Hotkey Conflict Detection & Dialog ---")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    # Simulate conflict: claim Alt+Space with external dummy id
    hold_res = user32.RegisterHotKey(None, 888, 0x4001, 0x20)
    print("Simulated external hold on Alt+Space:", hold_res)

    hk_mgr = HotkeyManager(['Alt'], 'Space')
    conflict_detected = []
    hk_mgr.hotkey_conflict.connect(lambda sc, code, msg: conflict_detected.append((sc, code, msg)))

    start_res = hk_mgr.start()
    print("HotkeyManager start result during conflict:", start_res, "is_registered:", hk_mgr.is_registered)
    assert not start_res
    assert not hk_mgr.is_registered
    assert len(conflict_detected) == 1
    assert conflict_detected[0][1] == 1409  # ERROR_HOTKEY_ALREADY_REGISTERED
    print("Conflict detected correctly: code 1409 ('%s')" % conflict_detected[0][2])

    # Show HotkeyConflictDialog
    dlg = HotkeyConflictDialog(hotkey_manager=hk_mgr, failed_shortcut="Alt+Space")
    assert dlg.radio_buttons[0].text().startswith("Ctrl + Space")
    # Release external hold
    user32.UnregisterHotKey(None, 888)

    # Test rebind to Ctrl+Space
    rebind_success, _, _ = hk_mgr.rebind(['Ctrl'], 'Space')
    print("Rebind to Ctrl+Space success:", rebind_success, "current:", hk_mgr.shortcut_name)
    assert rebind_success
    assert hk_mgr.shortcut_name == "Ctrl+Space"
    hk_mgr.stop()
    dlg.close()

    # Test 6: SettingsDialog hotkey controls
    print("\n--- Test 6: SettingsDialog Hotkey Controls & Persistence ---")
    class DummyApp:
        def __init__(self):
            self.settings = {"hotkey": {"modifiers": ["Alt"], "key": "Space"}}
            self.hotkey_manager = HotkeyManager(['Alt'], 'Space')
    dummy_app = DummyApp()
    settings_dlg = SettingsDialog(app_instance=dummy_app)
    # Check that preset combobox contains options
    assert settings_dlg.cbo_hotkey.count() >= 4
    # Switch to Ctrl+Space preset
    settings_dlg.cbo_hotkey.setCurrentIndex(1)
    mods, key = settings_dlg._get_selected_hotkey()
    assert mods == ["Ctrl"] and key == "Space"
    # Test availability
    settings_dlg._on_test_hotkey()
    print("Settings test availability status:", settings_dlg.lbl_hotkey_status.text().encode('ascii', 'replace').decode('ascii'))
    assert "available" in settings_dlg.lbl_hotkey_status.text().lower()
    settings_dlg.close()

    # Test 7: Candidate Deduplication
    print("\n--- Test 7: SearchIndex Application Deduplication ---")
    # Both intel_gfx_1 and intel_gfx_2 should have merged into 1 candidate
    gfx_candidates = [c for c in idx.all_candidates() if "graphics" in c.name.lower()]
    print("Gfx candidates count in index:", len(gfx_candidates))
    assert len(gfx_candidates) == 1
    assert len(gfx_candidates[0].aliases) >= 3

    print("\nALL 7 RC.6 HOTKEY, LAUNCHER, AND DEDUPLICATION TESTS PASSED!")

if __name__ == '__main__':
    main()
