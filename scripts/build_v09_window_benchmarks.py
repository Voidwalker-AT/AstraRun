"""Build script generating deterministic AstraRun v0.9 Window Benchmark V1.

Generates 330 structured test cases across 9 core evaluation categories:
1. Direct Window Resolution (50 cases)
2. Pronoun & Origin Window Resolution (50 cases)
3. Conversational Context Recall (30 cases)
4. Ambiguity Gating & Exact Title Match (40 cases)
5. Multi-Monitor Natural Language Resolution (40 cases)
6. Desktop Layout Tiling Geometry (40 cases)
7. Coordinate Clamping & Overflow Safety (25 cases)
8. Window Restore Undo Stack & TTL (25 cases)
9. Self-Protection & System Window Policy (30 cases)
"""

from __future__ import annotations

import json
from pathlib import Path


def generate_window_cases() -> list[dict]:
    cases: list[dict] = []
    case_idx = 1

    # Mock window pool for resolution testing
    window_pool = [
        {"hwnd": 1001, "title": "AstraRun - Workstation Assistant", "pid": 500, "app_id": "astrarun.exe", "bounds": [100, 100, 800, 600], "state": "normal", "visible": True},
        {"hwnd": 1002, "title": "Visual Studio Code - AstraRun Workspace", "pid": 1100, "app_id": "code.exe", "bounds": [0, 0, 1920, 1080], "state": "maximized", "visible": True},
        {"hwnd": 1003, "title": "Google Chrome - GitHub Pull Requests", "pid": 1200, "app_id": "chrome.exe", "bounds": [50, 50, 1200, 900], "state": "normal", "visible": True},
        {"hwnd": 1004, "title": "Spotify Free", "pid": 1300, "app_id": "spotify.exe", "bounds": [200, 200, 1000, 700], "state": "normal", "visible": True},
        {"hwnd": 1005, "title": "Windows Terminal - pwsh", "pid": 1400, "app_id": "windowsterminal.exe", "bounds": [100, 100, 900, 600], "state": "normal", "visible": True},
        {"hwnd": 1006, "title": "Slack - General", "pid": 1500, "app_id": "slack.exe", "bounds": [300, 150, 1100, 800], "state": "normal", "visible": True},
        {"hwnd": 1007, "title": "Calculator", "pid": 1600, "app_id": "calc.exe", "bounds": [400, 300, 400, 500], "state": "normal", "visible": True},
        {"hwnd": 1008, "title": "Notepad - notes.txt", "pid": 1700, "app_id": "notepad.exe", "bounds": [150, 150, 700, 500], "state": "normal", "visible": True},
        {"hwnd": 1009, "title": "Vivaldi - Internal Dashboard", "pid": 1800, "app_id": "vivaldi.exe", "bounds": [0, 0, 1920, 1032], "state": "normal", "visible": True},
        {"hwnd": 1010, "title": "Docker Desktop", "pid": 1900, "app_id": "docker.exe", "bounds": [250, 200, 950, 650], "state": "normal", "visible": True},
    ]

    # Category 1: Direct Window Resolution (50 cases)
    # Queries mapping to unique windows via app_id or title
    direct_queries = [
        ("code", 1002, "Visual Studio Code - AstraRun Workspace"),
        ("vscode", 1002, "Visual Studio Code - AstraRun Workspace"),
        ("visual studio code", 1002, "Visual Studio Code - AstraRun Workspace"),
        ("chrome", 1003, "Google Chrome - GitHub Pull Requests"),
        ("google chrome", 1003, "Google Chrome - GitHub Pull Requests"),
        ("github pull requests", 1003, "Google Chrome - GitHub Pull Requests"),
        ("spotify", 1004, "Spotify Free"),
        ("terminal", 1005, "Windows Terminal - pwsh"),
        ("pwsh", 1005, "Windows Terminal - pwsh"),
        ("powershell", 1005, "Windows Terminal - pwsh"),
        ("slack", 1006, "Slack - General"),
        ("slack general", 1006, "Slack - General"),
        ("calculator", 1007, "Calculator"),
        ("calc", 1007, "Calculator"),
        ("notepad", 1008, "Notepad - notes.txt"),
        ("notes.txt", 1008, "Notepad - notes.txt"),
        ("vivaldi", 1009, "Vivaldi - Internal Dashboard"),
        ("internal dashboard", 1009, "Vivaldi - Internal Dashboard"),
        ("docker", 1010, "Docker Desktop"),
        ("docker desktop", 1010, "Docker Desktop"),
        # Variations with prefix/suffix
        ("focus code", 1002, "Visual Studio Code - AstraRun Workspace"),
        ("window spotify", 1004, "Spotify Free"),
        ("app calculator", 1007, "Calculator"),
        ("the notepad window", 1008, "Notepad - notes.txt"),
        ("the slack window", 1006, "Slack - General"),
    ]
    # Replicate variations up to 50
    for q, exp_hwnd, exp_title in direct_queries:
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "direct_resolution",
            "query": q,
            "mock_pool": window_pool,
            "expected_status": "RESOLVED",
            "expected_hwnd": exp_hwnd,
            "expected_title": exp_title,
        })
        case_idx += 1
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "direct_resolution",
            "query": f"find {q}",
            "mock_pool": window_pool,
            "expected_status": "RESOLVED",
            "expected_hwnd": exp_hwnd,
            "expected_title": exp_title,
        })
        case_idx += 1

    # Category 2: Pronoun & Origin Window Resolution (50 cases)
    pronoun_terms = [
        "this", "this window", "current", "current window", "active",
        "active window", "foreground", "foreground window", "origin", "it"
    ]
    origin_targets = [
        {"hwnd": 2001, "title": "Sublime Text - Project", "pid": 2100, "app_id": "sublime.exe", "bounds": [50, 50, 800, 600], "state": "normal", "visible": True},
        {"hwnd": 2002, "title": "PyCharm - AstraRun", "pid": 2200, "app_id": "pycharm.exe", "bounds": [0, 0, 1920, 1080], "state": "maximized", "visible": True},
        {"hwnd": 2003, "title": "Firefox - Documentation", "pid": 2300, "app_id": "firefox.exe", "bounds": [100, 100, 1200, 800], "state": "normal", "visible": True},
        {"hwnd": 2004, "title": "Obsidian - Notes", "pid": 2400, "app_id": "obsidian.exe", "bounds": [200, 100, 900, 700], "state": "normal", "visible": True},
        {"hwnd": 2005, "title": "Postman - API Tests", "pid": 2500, "app_id": "postman.exe", "bounds": [150, 150, 1000, 750], "state": "normal", "visible": True},
    ]
    for origin in origin_targets:
        for p in pronoun_terms:
            cases.append({
                "id": f"wb_{case_idx:03d}",
                "category": "pronoun_origin",
                "query": p,
                "origin_window": origin,
                "mock_pool": window_pool,
                "expected_status": "RESOLVED",
                "expected_hwnd": origin["hwnd"],
                "expected_title": origin["title"],
            })
            case_idx += 1

    # Category 3: Conversational Context Recall (30 cases)
    context_windows = [
        {"hwnd": 3001, "title": "GitKraken - astrarun", "pid": 3100, "app_id": "gitkraken.exe", "bounds": [100, 100, 1000, 700], "state": "normal", "visible": True},
        {"hwnd": 3002, "title": "Windows Explorer - C:\\Workspace", "pid": 3200, "app_id": "explorer.exe", "bounds": [50, 50, 900, 600], "state": "normal", "visible": True},
        {"hwnd": 3003, "title": "Edge - Azure Portal", "pid": 3300, "app_id": "msedge.exe", "bounds": [0, 0, 1920, 1080], "state": "maximized", "visible": True},
    ]
    context_queries = ["that", "that window"]
    for c_win in context_windows:
        for q in context_queries:
            # Context present (24 cases across variations)
            for prefix in ["", "snap ", "minimize ", "focus "]:
                cases.append({
                    "id": f"wb_{case_idx:03d}",
                    "category": "context_recall",
                    "query": f"{prefix}{q}".strip(),
                    "context_window": c_win,
                    "mock_pool": window_pool,
                    "expected_status": "RESOLVED",
                    "expected_hwnd": c_win["hwnd"],
                    "expected_title": c_win["title"],
                })
                case_idx += 1
    # 6 cases with NO context window available -> NOT_FOUND
    for q in ["that", "that window", "snap that", "minimize that", "focus that", "that window please"]:
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "context_recall",
            "query": q,
            "context_window": None,
            "mock_pool": window_pool,
            "expected_status": "NOT_FOUND",
            "expected_hwnd": None,
            "expected_title": None,
        })
        case_idx += 1

    # Category 4: Ambiguity Gating & Exact Title Match (40 cases)
    # Pool with multiple matching windows
    ambiguous_pool = [
        {"hwnd": 4001, "title": "Google Chrome - Tab 1", "pid": 4100, "app_id": "chrome.exe", "bounds": [10, 10, 800, 600], "state": "normal", "visible": True},
        {"hwnd": 4002, "title": "Google Chrome - Tab 2", "pid": 4100, "app_id": "chrome.exe", "bounds": [20, 20, 800, 600], "state": "normal", "visible": True},
        {"hwnd": 4003, "title": "Visual Studio Code - Workspace A", "pid": 4200, "app_id": "code.exe", "bounds": [0, 0, 1000, 800], "state": "normal", "visible": True},
        {"hwnd": 4004, "title": "Visual Studio Code - Workspace B", "pid": 4300, "app_id": "code.exe", "bounds": [50, 50, 1000, 800], "state": "normal", "visible": True},
        {"hwnd": 4005, "title": "Windows Terminal - Tab 1", "pid": 4400, "app_id": "windowsterminal.exe", "bounds": [100, 100, 800, 500], "state": "normal", "visible": True},
        {"hwnd": 4006, "title": "Windows Terminal - Tab 2", "pid": 4401, "app_id": "windowsterminal.exe", "bounds": [120, 120, 800, 500], "state": "normal", "visible": True},
        {"hwnd": 4007, "title": "Slack - Team 1", "pid": 4500, "app_id": "slack.exe", "bounds": [10, 10, 900, 700], "state": "normal", "visible": True},
        {"hwnd": 4008, "title": "Slack - Team 2", "pid": 4501, "app_id": "slack.exe", "bounds": [20, 20, 900, 700], "state": "normal", "visible": True},
    ]
    # Ambiguous queries (20 cases)
    ambig_queries = [
        "chrome", "google chrome", "code", "vscode", "visual studio code",
        "terminal", "slack", "browser"
    ]
    for i in range(20):
        q = ambig_queries[i % len(ambig_queries)]
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "ambiguity_gating",
            "query": q,
            "mock_pool": ambiguous_pool,
            "expected_status": "AMBIGUOUS",
            "min_candidates": 2,
        })
        case_idx += 1

    # Exact Title breaks ambiguity (20 cases)
    exact_break_queries = [
        ("Google Chrome - Tab 1", 4001),
        ("Google Chrome - Tab 2", 4002),
        ("Visual Studio Code - Workspace A", 4003),
        ("Visual Studio Code - Workspace B", 4004),
        ("Windows Terminal - Tab 1", 4005),
        ("Windows Terminal - Tab 2", 4006),
        ("Slack - Team 1", 4007),
        ("Slack - Team 2", 4008),
    ]
    for i in range(20):
        title_q, expected_h = exact_break_queries[i % len(exact_break_queries)]
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "ambiguity_gating",
            "query": title_q,
            "mock_pool": ambiguous_pool,
            "expected_status": "RESOLVED",
            "expected_hwnd": expected_h,
            "expected_title": title_q,
        })
        case_idx += 1

    # Category 5: Multi-Monitor Natural Language Resolution (40 cases)
    # 2-monitor simulated setup: Monitor 1 (primary, 1920x1032), Monitor 2 (secondary, right, 1920x1032 at x=1920)
    monitor_queries = [
        (1, 1, True),
        (2, 2, False),
        ("1", 1, True),
        ("2", 2, False),
        ("monitor 1", 1, True),
        ("monitor 2", 2, False),
        ("screen 1", 1, True),
        ("screen 2", 2, False),
        ("display 1", 1, True),
        ("display 2", 2, False),
        ("primary", 1, True),
        ("primary monitor", 1, True),
        ("main", 1, True),
        ("main monitor", 1, True),
        ("default", 1, True),
        ("secondary", 2, False),
        ("secondary monitor", 2, False),
        ("second", 2, False),
        ("second monitor", 2, False),
        ("left", 1, True),
        ("left monitor", 1, True),
        ("leftmost", 1, True),
        ("right", 2, False),
        ("right monitor", 2, False),
        ("rightmost", 2, False),
        ("other", 2, False),  # current = 1 -> other = 2
        ("next", 2, False),
        ("alternate", 2, False),
        ("other monitor", 2, False),
        ("the other monitor", 2, False),
        # Out-of-bounds index clamping (e.g. monitor 3 or 99 on dual-monitor setup clamps safely to monitor 2)
        (3, 2, False),
        (4, 2, False),
        (99, 2, False),
        ("monitor 3", 2, False),
        ("screen 4", 2, False),
        ("display 5", 2, False),
        # Current = 2 -> other = 1
        ("other", 1, True),
        ("next", 1, True),
        ("alternate", 1, True),
        ("other monitor", 1, True),
    ]
    for idx, (spec, exp_id, exp_primary) in enumerate(monitor_queries):
        cur_id = 2 if idx >= 36 else 1
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "monitor_resolution",
            "spec": spec,
            "current_monitor_id": cur_id,
            "expected_monitor_id": exp_id,
            "expected_is_primary": exp_primary,
        })
        case_idx += 1

    # Category 6: Desktop Layout Tiling Geometry (40 cases)
    # Work area: (0, 0, 1920, 1032)
    # Half w: 960, half h: 516, 2/3 w: 1280, 1/3 w: 640
    layout_specs = [
        ("left", (0, 0, 960, 1032)),
        ("left_half", (0, 0, 960, 1032)),
        ("snap_left", (0, 0, 960, 1032)),
        ("right", (960, 0, 960, 1032)),
        ("right_half", (960, 0, 960, 1032)),
        ("snap_right", (960, 0, 960, 1032)),
        ("top", (0, 0, 1920, 516)),
        ("top_half", (0, 0, 1920, 516)),
        ("bottom", (0, 516, 1920, 516)),
        ("bottom_half", (0, 516, 1920, 516)),
        ("top_left", (0, 0, 960, 516)),
        ("top_right", (960, 0, 960, 516)),
        ("bottom_left", (0, 516, 960, 516)),
        ("bottom_right", (960, 516, 960, 516)),
        ("two_thirds", (0, 0, 1280, 1032)),
        ("left_two_thirds", (0, 0, 1280, 1032)),
        ("one_third", (1280, 0, 640, 1032)),
        ("right_one_third", (1280, 0, 640, 1032)),
        ("full", (0, 0, 1920, 1032)),
        ("maximize", (0, 0, 1920, 1032)),
    ]
    # Primary monitor (0, 0, 1920, 1032) - 20 cases
    for spec, exp_rect in layout_specs:
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "tiling_layout",
            "layout_spec": spec,
            "work_area": [0, 0, 1920, 1032],
            "expected_bounds": list(exp_rect),
        })
        case_idx += 1

    # Secondary monitor shifted (1920, 0, 1920, 1032) - 20 cases
    for spec, exp_rect in layout_specs:
        shifted = (exp_rect[0] + 1920, exp_rect[1], exp_rect[2], exp_rect[3])
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "tiling_layout",
            "layout_spec": spec,
            "work_area": [1920, 0, 1920, 1032],
            "expected_bounds": list(shifted),
        })
        case_idx += 1

    # Category 7: Coordinate Clamping & Overflow Safety (25 cases)
    clamp_inputs = [
        # (x, y, w, h) -> expected (cx, cy, cw, ch)
        (0, 0, 800, 600, (0, 0, 800, 600)),
        (100, 200, 50, 50, (100, 200, 150, 100)),        # Minimum w/h enforcement
        (-100, -200, 0, 0, (-100, -200, 150, 100)),       # Zero w/h clamp
        (-999999, 0, 800, 600, (-50000, 0, 800, 600)),   # Negative overflow clamp
        (999999, 999999, 800, 600, (50000, 50000, 800, 600)), # Positive overflow clamp
        (500, 500, -500, -300, (500, 500, 150, 100)),    # Negative width/height clamp
        (0, 0, 1920, 1080, (0, 0, 1920, 1080)),
        (10, 10, 149, 99, (10, 10, 150, 100)),           # Just below minimum
        (10, 10, 150, 100, (10, 10, 150, 100)),          # Exactly at minimum
        (10, 10, 151, 101, (10, 10, 151, 101)),          # Just above minimum
    ]
    for i in range(25):
        raw = clamp_inputs[i % len(clamp_inputs)]
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "geometry_clamping",
            "input_bounds": [raw[0], raw[1], raw[2], raw[3]],
            "expected_bounds": list(raw[4]),
        })
        case_idx += 1

    # Category 8: Window Restore Undo Stack & TTL (25 cases)
    undo_operations = [
        {"action": "push_peek", "snapshots": [{"hwnd": 501, "title": "App 1", "bounds": [0, 0, 500, 500], "state": "normal"}], "expected_peek_hwnd": 501},
        {"action": "push_pop", "snapshots": [{"hwnd": 502, "title": "App 2", "bounds": [10, 10, 500, 500], "state": "normal"}], "expected_pop_hwnd": 502},
        {"action": "lifo_order", "snapshots": [
            {"hwnd": 503, "title": "App 3", "bounds": [0, 0, 100, 100], "state": "normal"},
            {"hwnd": 504, "title": "App 4", "bounds": [0, 0, 200, 200], "state": "normal"},
        ], "expected_first_pop_hwnd": 504, "expected_second_pop_hwnd": 503},
        {"action": "empty_pop", "snapshots": [], "expected_pop": None},
        {"action": "bounded_depth", "count": 25, "max_depth": 20, "expected_len": 20},
        {"action": "ttl_expiry", "age_seconds": 650.0, "expected_len_after_prune": 0},
    ]
    for i in range(25):
        op = undo_operations[i % len(undo_operations)]
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "undo_stack",
            "operation": op,
        })
        case_idx += 1

    # Category 9: Self-Protection & System Window Policy (30 cases)
    policy_scenarios = [
        # Invalid / Null HWND
        {"hwnd": 0, "expected_allowed": False, "reason": "invalid_null_hwnd"},
        {"hwnd": -1, "expected_allowed": False, "reason": "negative_hwnd"},
        {"hwnd": -999, "expected_allowed": False, "reason": "negative_hwnd"},
        # AstraRun self-window protection
        {"hwnd": 9001, "is_astrarun": True, "expected_allowed": False, "reason": "astrarun_self_protection"},
        {"hwnd": 9002, "is_astrarun": True, "expected_allowed": False, "reason": "astrarun_self_protection"},
        # Protected system classes
        {"hwnd": 9101, "class_name": "Progman", "expected_allowed": False, "reason": "protected_progman"},
        {"hwnd": 9102, "class_name": "WorkerW", "expected_allowed": False, "reason": "protected_workerw"},
        {"hwnd": 9103, "class_name": "Shell_TrayWnd", "expected_allowed": False, "reason": "protected_primary_taskbar"},
        {"hwnd": 9104, "class_name": "Shell_SecondaryTrayWnd", "expected_allowed": False, "reason": "protected_secondary_taskbar"},
        # TOCTOU PID mismatch
        {"hwnd": 9201, "expected_pid": 1111, "actual_pid": 2222, "expected_allowed": False, "reason": "toctou_pid_mismatch"},
        {"hwnd": 9202, "expected_pid": 3333, "actual_pid": 4444, "expected_allowed": False, "reason": "toctou_pid_mismatch"},
        # Legitimate user window
        {"hwnd": 9301, "class_name": "CabinetWClass", "expected_allowed": True, "reason": "normal_explorer_window"},
        {"hwnd": 9302, "class_name": "Chrome_WidgetWin_1", "expected_allowed": True, "reason": "normal_chrome_window"},
        {"hwnd": 9303, "class_name": "Notepad", "expected_allowed": True, "reason": "normal_notepad_window"},
        {"hwnd": 9304, "expected_pid": 5555, "actual_pid": 5555, "expected_allowed": True, "reason": "pid_matched"},
    ]
    for i in range(30):
        scen = policy_scenarios[i % len(policy_scenarios)]
        cases.append({
            "id": f"wb_{case_idx:03d}",
            "category": "safety_policy",
            "scenario": scen,
            "expected_allowed": scen["expected_allowed"],
        })
        case_idx += 1

    return cases


def main():
    cases = generate_window_cases()
    out_dir = Path("benchmarks/windows")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "window_benchmark_v1.json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)

    print(f"[OK] Generated {len(cases)} deterministic window benchmark cases to {out_path}")


if __name__ == "__main__":
    main()
