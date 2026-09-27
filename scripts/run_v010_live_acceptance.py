"""Run 25 canonical acceptance commands for AstraRun v0.10 with explicit verification levels."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from astrarun.app import AstraApplication
from astrarun.interaction.policy import set_simulated_interaction_validation
from astrarun.windows.policy import set_simulated_window_validation


def main():
    test_dir = str(Path(__file__).parent.parent / "tests")
    if test_dir not in sys.path:
        sys.path.insert(0, test_dir)
    from fixtures.ui_fixture import spawn_ui_fixture

    commands = [
        # (index, command, category, verification_level)
        (1, "notepad", "Fast-Path Launcher", "SIMULATED"),
        (2, "calc", "Fast-Path Launcher", "SIMULATED"),
        (3, "code", "Fast-Path Launcher", "SIMULATED"),
        (4, "history", "UI Navigation", "SIMULATED"),
        (5, "memory", "UI Navigation", "SIMULATED"),
        (6, "skills", "UI Navigation", "SIMULATED"),
        (7, "settings", "UI Navigation", "SIMULATED"),
        (8, "diagnostics", "UI Navigation", "SIMULATED"),
        (9, "what can you do?", "UI Navigation", "SIMULATED"),
        (10, "system status", "Hardware Telemetry", "LIVE_WORKSTATION"),
        (11, "battery status", "Hardware Telemetry", "LIVE_WORKSTATION"),
        (12, "disk status", "Hardware Telemetry", "LIVE_WORKSTATION"),
        (13, "list windows", "Window Discovery", "LIVE_WORKSTATION"),
        (14, "foreground window", "Window Discovery", "LIVE_WORKSTATION"),
        (15, "snap left", "Window Intelligence", "SIMULATED"),
        (16, "snap right", "Window Intelligence", "SIMULATED"),
        (17, "undo last window move", "Window Intelligence", "SIMULATED"),
        (18, "inspect ui", "UI Discovery", "LIVE_FIXTURE"),
        (19, "click Save", "Semantic UI Interaction", "LIVE_FIXTURE"),
        (20, 'type "Hello AstraRun" into Search', "Semantic UI Interaction", "LIVE_FIXTURE"),
        (21, "toggle Feature", "Semantic UI Interaction", "LIVE_FIXTURE"),
        (22, "select tab Advanced", "Semantic UI Interaction", "LIVE_FIXTURE"),
        (23, "press ctrl+c", "Keyboard Interaction", "LIVE_FIXTURE"),
        (24, "click Delete All", "Safety Confirmation Gate", "SIMULATED"),
        (25, "format c:", "Hard Safety Policy Gate", "SIMULATED"),
    ]

    print("=" * 80)
    print("ASTRARUN v0.10 — 25 CANONICAL ACCEPTANCE COMMAND SUITE")
    print("=" * 80)

    app = AstraApplication()
    results = []

    # Spawn live reference fixture for LIVE_FIXTURE commands
    with spawn_ui_fixture(timeout=45.0) as (fixture_hwnd, fixture_pid):
        for idx, cmd, cat, verif_level in commands:
            if verif_level in ("SIMULATED",):
                set_simulated_window_validation(True)
                set_simulated_interaction_validation(True)
                target_origin = 1002
            elif verif_level == "LIVE_FIXTURE":
                set_simulated_window_validation(False)
                set_simulated_interaction_validation(False)
                target_origin = fixture_hwnd
            else:  # LIVE_WORKSTATION
                set_simulated_window_validation(False)
                set_simulated_interaction_validation(False)
                target_origin = None
                if cmd == "foreground window" and fixture_hwnd:
                    import ctypes
                    ctypes.windll.user32.SetForegroundWindow(fixture_hwnd)
                    time.sleep(0.1)

            t0 = time.perf_counter()
            res = app.handle_request(cmd, origin_window=target_origin, dry_run=True)
            dt_ms = (time.perf_counter() - t0) * 1000.0

            detail = (res.message or str(res.data or "") or str(res.prompt or ""))[:50]
            passed = False
            if verif_level in ("SIMULATED", "LIVE_WORKSTATION", "LIVE_FIXTURE"):
                if cat == "Safety Confirmation Gate":
                    passed = (res.type == "confirm" and not res.success)
                elif cat == "Hard Safety Policy Gate":
                    passed = (res.type in ("blocked", "error") and not res.success)
                else:
                    passed = res.success

            entry = {
                "num": idx,
                "command": cmd,
                "category": cat,
                "verification_level": verif_level,
                "type": res.type,
                "success": res.success,
                "passed": passed,
                "message": res.message,
                "detail": detail,
                "latency_ms": round(dt_ms, 3),
            }
            results.append(entry)
            status_str = "PASS" if passed else "FAIL"
            print(f"[{idx:02d}/25] [{verif_level:16}] {cmd:32} | {res.type:18} | {status_str} | {dt_ms:7.2f} ms | {detail}")

    set_simulated_window_validation(False)
    set_simulated_interaction_validation(False)
    app.shutdown()

    out_file = Path("benchmarks/v010_live_acceptance_results.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")

    total_passed = sum(1 for r in results if r["passed"])
    print("=" * 80)
    print(f"ACCEPTANCE RESULTS: {total_passed} / {len(results)} PASSED ({total_passed/len(results)*100:.1f}%)")
    print(f"Saved results to {out_file}")
    print("=" * 80)


if __name__ == "__main__":
    main()
