"""Script to generate dataset_dev.json and dataset_holdout.json for AstraRun v0.11.1 Agent Generality Benchmark.

Ensures at least 200 dev goals and 100 held-out compositional goals with complete ground truth annotations.
"""

from __future__ import annotations

import json
import os
from typing import Any


def generate_dev_dataset() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    # 1. Applications (25 goals)
    apps = ["notepad", "calc", "code", "terminal", "vivaldi", "explorer"]
    for i, app in enumerate(apps):
        cases.append({
            "id": f"DEV-APP-{i*4+1:03d}",
            "prompt": f"open application {app}",
            "category": "application",
            "expected_capabilities": ["open_application"],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })
        cases.append({
            "id": f"DEV-APP-{i*4+2:03d}",
            "prompt": f"is {app} running",
            "category": "application",
            "expected_capabilities": ["is_application_running"],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })
        cases.append({
            "id": f"DEV-APP-{i*4+3:03d}",
            "prompt": f"focus application {app}",
            "category": "application",
            "expected_capabilities": ["focus_application"],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })
        cases.append({
            "id": f"DEV-APP-{i*4+4:03d}",
            "prompt": f"find application {app}",
            "category": "application",
            "expected_capabilities": ["find_application"],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })
    cases.append({
        "id": "DEV-APP-025",
        "prompt": "list all running applications",
        "category": "application",
        "expected_capabilities": ["list_running_applications"],
        "expected_plan_length": 1,
        "requires_dataflow": False,
        "is_negated": False,
        "negated_capabilities": [],
        "should_succeed": True,
    })

    # 2. Windows Management (25 goals)
    win_ops = [
        ("list windows", "list_windows"),
        ("show foreground window", "foreground_window"),
        ("find window Code", "find_window"),
        ("minimize window", "minimize_window"),
        ("maximize window", "maximize_window"),
        ("restore window", "restore_window"),
        ("snap window left", "snap_window_left"),
        ("snap window right", "snap_window_right"),
        ("undo window layout", "undo_window_layout"),
        ("arrange desktop", "arrange_desktop"),
        ("focus window", "focus_window"),
        ("list windows on desktop", "list_windows"),
        ("get active window", "foreground_window"),
        ("minimize active window", "minimize_window"),
        ("maximize active window", "maximize_window"),
        ("restore current window", "restore_window"),
        ("snap current window left", "snap_window_left"),
        ("snap current window right", "snap_window_right"),
        ("show open windows", "list_windows"),
        ("search for window Terminal", "find_window"),
        ("find window Notepad", "find_window"),
        ("undo window arrangement", "undo_window_layout"),
        ("tile desktop windows", "arrange_desktop"),
        ("focus current window", "focus_window"),
        ("list all windows", "list_windows"),
    ]
    for i, (prompt, cap) in enumerate(win_ops):
        cases.append({
            "id": f"DEV-WIN-{i+1:03d}",
            "prompt": prompt,
            "category": "window",
            "expected_capabilities": [cap],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })

    # 3. Files & Directories (25 goals)
    file_ops = [
        ("find file readme.md", "find_file"),
        ("find latest file in Downloads", "find_latest_file"),
        ("list recent files", "list_recent_files"),
        ("open file notes.txt", "open_file"),
        ("reveal file project.json", "reveal_file"),
        ("get file metadata report.pdf", "file_metadata"),
        ("search for file budget.xlsx", "find_file"),
        ("locate latest file in Documents", "find_latest_file"),
        ("show recent files", "list_recent_files"),
        ("open file config.toml", "open_file"),
        ("reveal file data.csv", "reveal_file"),
        ("check file metadata summary.docx", "file_metadata"),
        ("find file error.log", "find_file"),
        ("find latest file in Desktop", "find_latest_file"),
        ("list recently modified files", "list_recent_files"),
        ("open file script.py", "open_file"),
        ("reveal file document.pdf", "reveal_file"),
        ("inspect file metadata test.py", "file_metadata"),
        ("find file license.txt", "find_file"),
        ("find latest file in Temp", "find_latest_file"),
        ("show recent modified files", "list_recent_files"),
        ("open file workspace.json", "open_file"),
        ("reveal file archive.zip", "reveal_file"),
        ("get file metadata image.png", "file_metadata"),
        ("search file backlog.md", "find_file"),
    ]
    for i, (prompt, cap) in enumerate(file_ops):
        cases.append({
            "id": f"DEV-FIL-{i+1:03d}",
            "prompt": prompt,
            "category": "file",
            "expected_capabilities": [cap],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })

    # 4. Processes & Ports (25 goals)
    proc_ops = [
        ("list running processes", "list_processes"),
        ("find process python", "find_process"),
        ("inspect process 1024", "inspect_process"),
        ("check process resource usage 1024", "process_resource_usage"),
        ("show process ports 1024", "process_ports"),
        ("show process children 1024", "process_children"),
        ("show process parent 1024", "process_parent"),
        ("list listening ports", "list_listening_ports"),
        ("inspect port 8080", "inspect_port"),
        ("find process on port 3000", "find_process_on_port"),
        ("list network connections", "list_network_connections"),
        ("show active processes", "list_processes"),
        ("find process node", "find_process"),
        ("inspect process 2048", "inspect_process"),
        ("get process resource usage 2048", "process_resource_usage"),
        ("inspect listening port 5000", "inspect_port"),
        ("find process using port 8000", "find_process_on_port"),
        ("list open network connections", "list_network_connections"),
        ("list all system processes", "list_processes"),
        ("find process code", "find_process"),
        ("inspect process 4096", "inspect_process"),
        ("check process cpu usage 4096", "process_resource_usage"),
        ("list all listening ports", "list_listening_ports"),
        ("inspect port 443", "inspect_port"),
        ("find process on port 80", "find_process_on_port"),
    ]
    for i, (prompt, cap) in enumerate(proc_ops):
        cases.append({
            "id": f"DEV-PRC-{i+1:03d}",
            "prompt": prompt,
            "category": "process",
            "expected_capabilities": [cap],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })

    # 5. Wi-Fi & Network (25 goals)
    wifi_ops = [
        ("scan wifi networks", "wifi_scan"),
        ("scan available wifi", "wifi_scan"),
        ("check wifi status", "wifi_status"),
        ("show wifi connection status", "wifi_status"),
        ("connect to wifi OfficeNet", "wifi_connect"),
        ("disconnect wifi", "wifi_disconnect"),
        ("disconnect from wifi", "wifi_disconnect"),
        ("scan nearby wifi networks", "wifi_scan"),
        ("show current wifi status", "wifi_status"),
        ("connect to wifi HomeGuest", "wifi_connect"),
        ("disconnect current wifi", "wifi_disconnect"),
        ("list wifi networks", "wifi_scan"),
        ("get wifi status", "wifi_status"),
        ("connect to wifi LabNetwork", "wifi_connect"),
        ("disconnect wireless network", "wifi_disconnect"),
        ("search wifi access points", "wifi_scan"),
        ("view wifi status", "wifi_status"),
        ("connect to wifi AstraSecure", "wifi_connect"),
        ("disconnect from current wireless", "wifi_disconnect"),
        ("scan wireless networks", "wifi_scan"),
        ("display wifi connection info", "wifi_status"),
        ("connect to wifi VisitorNet", "wifi_connect"),
        ("turn off wifi connection", "wifi_disconnect"),
        ("scan for wifi SSIDs", "wifi_scan"),
        ("check wireless connection status", "wifi_status"),
    ]
    for i, (prompt, cap) in enumerate(wifi_ops):
        cases.append({
            "id": f"DEV-NET-{i+1:03d}",
            "prompt": prompt,
            "category": "network",
            "expected_capabilities": [cap],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })

    # 6. System Diagnostics & Hardware (25 goals)
    sys_ops = [
        ("run a battery report and save it in Downloads as astra-battery.html", "generate_battery_report"),
        ("generate battery report to Downloads as astra-report.html", "generate_battery_report"),
        ("show system summary", "system_summary"),
        ("check cpu status", "cpu_status"),
        ("check memory status", "memory_status"),
        ("check disk status", "disk_status"),
        ("check battery status", "battery_status"),
        ("check gpu status", "gpu_status"),
        ("check audio status", "audio_status"),
        ("lock workstation", "lock_workstation"),
        ("display system diagnostics summary", "system_summary"),
        ("show cpu usage status", "cpu_status"),
        ("show memory usage status", "memory_status"),
        ("show disk storage status", "disk_status"),
        ("show battery charge status", "battery_status"),
        ("show gpu status info", "gpu_status"),
        ("show audio volume status", "audio_status"),
        ("lock the screen", "lock_workstation"),
        ("get workstation system summary", "system_summary"),
        ("get cpu performance status", "cpu_status"),
        ("get ram memory status", "memory_status"),
        ("get drive disk status", "disk_status"),
        ("get power battery status", "battery_status"),
        ("get graphics gpu status", "gpu_status"),
        ("get sound audio status", "audio_status"),
    ]
    for i, (prompt, cap) in enumerate(sys_ops):
        cases.append({
            "id": f"DEV-SYS-{i+1:03d}",
            "prompt": prompt,
            "category": "system",
            "expected_capabilities": [cap],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })

    # 7. UI & Interaction (25 goals)
    ui_ops = [
        ("inspect window ui", "inspect_window_ui"),
        ("get clipboard content", "get_clipboard_content"),
        ("read clipboard content", "get_clipboard_content"),
        ("show clipboard content", "get_clipboard_content"),
        ("inspect ui elements in window", "inspect_window_ui"),
        ("fetch clipboard text", "get_clipboard_content"),
        ("inspect window controls", "inspect_window_ui"),
        ("view clipboard content", "get_clipboard_content"),
        ("check clipboard content", "get_clipboard_content"),
        ("analyze window ui controls", "inspect_window_ui"),
        ("inspect window accessibility elements", "inspect_window_ui"),
        ("get current clipboard text", "get_clipboard_content"),
        ("inspect controls in active window", "inspect_window_ui"),
        ("retrieve clipboard content", "get_clipboard_content"),
        ("inspect window tree", "inspect_window_ui"),
        ("read current clipboard", "get_clipboard_content"),
        ("inspect window widgets", "inspect_window_ui"),
        ("get text from clipboard", "get_clipboard_content"),
        ("examine window ui components", "inspect_window_ui"),
        ("extract clipboard content", "get_clipboard_content"),
        ("inspect window ui elements and controls", "inspect_window_ui"),
        ("read text stored in clipboard", "get_clipboard_content"),
        ("inspect active window structure", "inspect_window_ui"),
        ("show current text in clipboard", "get_clipboard_content"),
        ("inspect window interactive elements", "inspect_window_ui"),
    ]
    for i, (prompt, cap) in enumerate(ui_ops):
        cases.append({
            "id": f"DEV-UI-{i+1:03d}",
            "prompt": prompt,
            "category": "ui",
            "expected_capabilities": [cap],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })

    # 8. Multi-Step Compositions (20 goals)
    multi_ops = [
        ("scan wifi and check wifi status", ["wifi_scan", "wifi_status"]),
        ("check cpu status and check memory status", ["cpu_status", "memory_status"]),
        ("check disk status and check battery status", ["disk_status", "battery_status"]),
        ("show system summary and check gpu status", ["system_summary", "gpu_status"]),
        ("list windows and show foreground window", ["list_windows", "foreground_window"]),
        ("list running applications and list running processes", ["list_running_applications", "list_processes"]),
        ("check memory status and check cpu status", ["memory_status", "cpu_status"]),
        ("scan available wifi and show wifi status", ["wifi_scan", "wifi_status"]),
        ("show cpu status and show memory status and check disk status", ["cpu_status", "memory_status", "disk_status"]),
        ("list listening ports and list network connections", ["list_listening_ports", "list_network_connections"]),
        ("check battery status and run a battery report and save it in Downloads as astra-battery.html", ["battery_status", "generate_battery_report"]),
        ("get clipboard content and show system summary", ["get_clipboard_content", "system_summary"]),
        ("list recent files and find latest file in Downloads", ["list_recent_files", "find_latest_file"]),
        ("check audio status and check gpu status", ["audio_status", "gpu_status"]),
        ("list open windows and inspect window ui", ["list_windows", "inspect_window_ui"]),
        ("check wifi status and list network connections", ["wifi_status", "list_network_connections"]),
        ("show foreground window and minimize window", ["foreground_window", "minimize_window"]),
        ("show system summary and list processes", ["system_summary", "list_processes"]),
        ("check cpu status and check gpu status", ["cpu_status", "gpu_status"]),
        ("list running applications and show foreground window", ["list_running_applications", "foreground_window"]),
    ]
    for i, (prompt, caps) in enumerate(multi_ops):
        cases.append({
            "id": f"DEV-MLT-{i+1:03d}",
            "prompt": prompt,
            "category": "multi_step",
            "expected_capabilities": caps,
            "expected_plan_length": len(caps),
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": True,
        })

    # 9. Negations & Exclusions (15 goals)
    neg_ops = [
        ("scan wifi networks but do not connect", ["wifi_scan"], ["wifi_connect"]),
        ("check wifi status but don't disconnect", ["wifi_status"], ["wifi_disconnect"]),
        ("list processes but do not terminate any process", ["list_processes"], ["terminate_process"]),
        ("show foreground window but don't close it", ["foreground_window"], ["close_window"]),
        ("show system summary but don't lock workstation", ["system_summary"], ["lock_workstation"]),
        ("scan available wifi but never disconnect", ["wifi_scan"], ["wifi_disconnect"]),
        ("find file readme.md but do not delete it", ["find_file"], []),
        ("list running applications but don't close application", ["list_running_applications"], ["close_application"]),
        ("check cpu status but don't shutdown workstation", ["cpu_status"], ["shutdown_workstation"]),
        ("check memory status without restarting workstation", ["memory_status"], ["restart_workstation"]),
        ("list windows but don't minimize window", ["list_windows"], ["minimize_window"]),
        ("check disk status but don't lock the screen", ["disk_status"], ["lock_workstation"]),
        ("inspect process 1024 without terminating it", ["inspect_process"], ["terminate_process"]),
        ("get clipboard content but do not clear it", ["get_clipboard_content"], []),
        ("scan wifi SSIDs without connecting to any network", ["wifi_scan"], ["wifi_connect"]),
    ]
    for i, (prompt, caps, neg_caps) in enumerate(neg_ops):
        cases.append({
            "id": f"DEV-NEG-{i+1:03d}",
            "prompt": prompt,
            "category": "negation",
            "expected_capabilities": caps,
            "expected_plan_length": len(caps),
            "requires_dataflow": False,
            "is_negated": True,
            "negated_capabilities": neg_caps,
            "should_succeed": True,
        })

    # 10. Unsupported / Hallucination Traps (10 goals)
    trap_ops = [
        "teleport to moon and launch space shuttle",
        "brew a cup of hot espresso coffee",
        "convert lead into gold metal using alchemy",
        "time travel to the year 1999",
        "summon virtual weather cloud indoors",
        "bake a chocolate cake in kitchen",
        "fly airplane across the ocean",
        "perform brain surgery simulation",
        "summon magical dragon on desktop",
        "predict next week lottery numbers",
    ]
    for i, prompt in enumerate(trap_ops):
        cases.append({
            "id": f"DEV-TRP-{i+1:03d}",
            "prompt": prompt,
            "category": "unsupported",
            "expected_capabilities": [],
            "expected_plan_length": 0,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "should_succeed": False,
        })

    return cases


def generate_holdout_dataset() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    # 1. Novel Runtime Plug-Ins (Single-Step) (20 goals)
    # Using plug-in tools registered at runtime: reverse_text, word_count, hash_text, format_json
    plugins = [
        ("reverse text", "reverse hello world", "reverse_text"),
        ("reverse text", "reverse the string AstraRunAgent", "reverse_text"),
        ("reverse text", "reverse word workstation", "reverse_text"),
        ("reverse text", "reverse text 123456789", "reverse_text"),
        ("reverse text", "reverse input string composition", "reverse_text"),
        ("word count", "count words in quick brown fox jumps over lazy dog", "word_count"),
        ("word count", "count words in this sample paragraph text", "word_count"),
        ("word count", "count words in hello world astra", "word_count"),
        ("word count", "count words in autonomous workstation runtime", "word_count"),
        ("word count", "count words in machine state verification", "word_count"),
        ("calculate hash", "calculate sha256 hash of password123", "hash_text"),
        ("calculate hash", "calculate hash of secret payload token", "hash_text"),
        ("calculate hash", "compute sha256 hash for verification test", "hash_text"),
        ("calculate hash", "calculate hash of data integrity block", "hash_text"),
        ("calculate hash", "compute hash for message payload", "hash_text"),
        ("format json", "format json string {name: astra, version: 0.11}", "format_json"),
        ("format json", "format json payload {status: ok, code: 200}", "format_json"),
        ("format json", "beautify json {tasks: [1, 2, 3]}", "format_json"),
        ("format json", "format json data {agent: autonomous, platform: windows}", "format_json"),
        ("format json", "beautify json string {id: test, valid: true}", "format_json"),
    ]
    for i, (cat, prompt, cap) in enumerate(plugins):
        cases.append({
            "id": f"HLD-PLG-{i+1:03d}",
            "prompt": prompt,
            "category": f"plugin_{cat.replace(' ', '_')}",
            "expected_capabilities": [cap],
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "is_plugin": True,
            "should_succeed": True,
        })

    # 2. Novel Compositional Dataflow Pipelines (2-step and 3-step chained) (30 goals)
    dataflow_scenarios = [
        # reverse_text -> save_text_file
        ("reverse text hello and save text file to output.txt", ["reverse_text", "save_text_file"], True),
        ("reverse text astra and save text file to rev.txt", ["reverse_text", "save_text_file"], True),
        ("reverse text workstation and save text file to ws.txt", ["reverse_text", "save_text_file"], True),
        ("reverse text autonomy and save text file to auto.txt", ["reverse_text", "save_text_file"], True),
        ("reverse text dynamic and save text file to dyn.txt", ["reverse_text", "save_text_file"], True),
        # word_count -> save_text_file
        ("count words in test sentence and save text file to count.txt", ["word_count", "save_text_file"], True),
        ("count words in quick brown fox and save text file to wc.txt", ["word_count", "save_text_file"], True),
        ("count words in system metrics summary and save text file to stats.txt", ["word_count", "save_text_file"], True),
        ("count words in diagnostic log and save text file to log_count.txt", ["word_count", "save_text_file"], True),
        ("count words in astra prompt and save text file to prompt_wc.txt", ["word_count", "save_text_file"], True),
        # hash_text -> save_text_file
        ("calculate hash of payload and save text file to hash.txt", ["hash_text", "save_text_file"], True),
        ("calculate hash of checksum and save text file to sha.txt", ["hash_text", "save_text_file"], True),
        ("compute hash for secure string and save text file to digest.txt", ["hash_text", "save_text_file"], True),
        ("calculate hash of release package and save text file to release.sha", ["hash_text", "save_text_file"], True),
        ("compute hash for build artifact and save text file to artifact.sha", ["hash_text", "save_text_file"], True),
        # tool_alpha -> tool_beta -> tool_gamma 3-step pipeline
        ("run tool alpha with input test and run tool beta and run tool gamma", ["tool_alpha", "tool_beta", "tool_gamma"], True),
        ("execute tool alpha with raw data then execute tool beta then execute tool gamma", ["tool_alpha", "tool_beta", "tool_gamma"], True),
        ("start tool alpha pipeline then run tool beta and run tool gamma", ["tool_alpha", "tool_beta", "tool_gamma"], True),
        ("process tool alpha with config then execute tool beta and run tool gamma", ["tool_alpha", "tool_beta", "tool_gamma"], True),
        ("run tool alpha then tool beta then tool gamma", ["tool_alpha", "tool_beta", "tool_gamma"], True),
        # reverse -> hash -> save
        ("reverse text secret and calculate hash and save text file to secure.txt", ["reverse_text", "hash_text", "save_text_file"], True),
        ("reverse text token and compute hash and save text file to token.hash", ["reverse_text", "hash_text", "save_text_file"], True),
        ("reverse text credential and calculate hash and save text file to cred.sha", ["reverse_text", "hash_text", "save_text_file"], True),
        ("reverse text signature and compute hash and save text file to sig.sha", ["reverse_text", "hash_text", "save_text_file"], True),
        ("reverse text header and calculate hash and save text file to head.sha", ["reverse_text", "hash_text", "save_text_file"], True),
        # format_json -> save_text_file
        ("format json string {status: ok} and save text file to status.json", ["format_json", "save_text_file"], True),
        ("format json payload {version: 1} and save text file to meta.json", ["format_json", "save_text_file"], True),
        ("beautify json {count: 42} and save text file to result.json", ["format_json", "save_text_file"], True),
        ("format json data {healthy: true} and save text file to health.json", ["format_json", "save_text_file"], True),
        ("beautify json string {items: []} and save text file to empty.json", ["format_json", "save_text_file"], True),
    ]
    for i, (prompt, caps, df) in enumerate(dataflow_scenarios):
        cases.append({
            "id": f"HLD-DFL-{i+1:03d}",
            "prompt": prompt,
            "category": "heldout_dataflow",
            "expected_capabilities": caps,
            "expected_plan_length": len(caps),
            "requires_dataflow": df,
            "is_negated": False,
            "negated_capabilities": [],
            "is_plugin": True,
            "should_succeed": True,
        })

    # 3. Parallel Independent DAG Branches Aggregated downstream (15 goals)
    parallel_scenarios = [
        ("collect cpu metrics and collect memory metrics and summarize system", ["cpu_metrics", "memory_metrics", "system_summary_aggregator"]),
        ("fetch cpu stats and fetch memory stats and compile performance summary", ["cpu_metrics", "memory_metrics", "system_summary_aggregator"]),
        ("gather cpu utilization and gather ram utilization and generate diagnostics summary", ["cpu_metrics", "memory_metrics", "system_summary_aggregator"]),
        ("read cpu data and read memory data and aggregate workstation metrics", ["cpu_metrics", "memory_metrics", "system_summary_aggregator"]),
        ("query cpu usage and query memory usage and create health overview", ["cpu_metrics", "memory_metrics", "system_summary_aggregator"]),
        ("collect branch alpha data and collect branch beta data and merge branches", ["branch_alpha", "branch_beta", "branch_merger"]),
        ("run branch alpha and run branch beta and combine results", ["branch_alpha", "branch_beta", "branch_merger"]),
        ("execute stream one and execute stream two and join streams", ["branch_alpha", "branch_beta", "branch_merger"]),
        ("query feed left and query feed right and consolidate feeds", ["branch_alpha", "branch_beta", "branch_merger"]),
        ("process chunk A and process chunk B and assemble chunks", ["branch_alpha", "branch_beta", "branch_merger"]),
        ("sample sensor 1 and sample sensor 2 and reconcile sensors", ["branch_alpha", "branch_beta", "branch_merger"]),
        ("measure channel X and measure channel Y and compare channels", ["branch_alpha", "branch_beta", "branch_merger"]),
        ("evaluate policy A and evaluate policy B and fuse policies", ["branch_alpha", "branch_beta", "branch_merger"]),
        ("inspect node north and inspect node south and report topology", ["branch_alpha", "branch_beta", "branch_merger"]),
        ("scan partition 1 and scan partition 2 and audit storage", ["branch_alpha", "branch_beta", "branch_merger"]),
    ]
    for i, (prompt, caps) in enumerate(parallel_scenarios):
        cases.append({
            "id": f"HLD-PAR-{i+1:03d}",
            "prompt": prompt,
            "category": "heldout_parallel_dag",
            "expected_capabilities": caps,
            "expected_plan_length": len(caps),
            "requires_dataflow": True,
            "is_parallel_dag": True,
            "is_negated": False,
            "negated_capabilities": [],
            "is_plugin": True,
            "should_succeed": True,
        })

    # 4. Complex Novel Negations & Selective Filtering (15 goals)
    neg_scenarios = [
        ("reverse text test string but do not save text file", ["reverse_text"], ["save_text_file"]),
        ("calculate hash of payload but don't save text file", ["hash_text"], ["save_text_file"]),
        ("count words in document but never save text file", ["word_count"], ["save_text_file"]),
        ("format json string {a: 1} without saving text file", ["format_json"], ["save_text_file"]),
        ("execute tool alpha but do not run tool beta", ["tool_alpha"], ["tool_beta"]),
        ("run tool alpha but skip tool gamma", ["tool_alpha"], ["tool_gamma"]),
        ("collect cpu metrics without collecting memory metrics", ["cpu_metrics"], ["memory_metrics"]),
        ("run branch alpha but do not run branch beta", ["branch_alpha"], ["branch_beta"]),
        ("compute hash for secret data but never write to disk", ["hash_text"], ["save_text_file"]),
        ("reverse text payload without writing output file", ["reverse_text"], ["save_text_file"]),
        ("format json without publishing to disk", ["format_json"], ["save_text_file"]),
        ("count words in paragraph but do not save results", ["word_count"], ["save_text_file"]),
        ("execute tool alpha with params but do not execute tool gamma", ["tool_alpha"], ["tool_gamma"]),
        ("collect cpu stats but do not gather ram utilization", ["cpu_metrics"], ["memory_metrics"]),
        ("run stream one but never start stream two", ["branch_alpha"], ["branch_beta"]),
    ]
    for i, (prompt, caps, negs) in enumerate(neg_scenarios):
        cases.append({
            "id": f"HLD-NEG-{i+1:03d}",
            "prompt": prompt,
            "category": "heldout_negation",
            "expected_capabilities": caps,
            "expected_plan_length": len(caps),
            "requires_dataflow": False,
            "is_negated": True,
            "negated_capabilities": negs,
            "is_plugin": True,
            "should_succeed": True,
        })

    # 5. Adversarial / Malformed DAG Rejection & Quality Gate Safety (10 goals)
    adv_scenarios = [
        ("adversarial_cycle_2_node", "cyclic dependency a -> b -> a", ["step_a", "step_b"], "cycle"),
        ("adversarial_cycle_3_node", "cyclic dependency a -> b -> c -> a", ["step_a", "step_b", "step_c"], "cycle"),
        ("adversarial_dangling_ref", "output reference pointing to non-existent step", ["step_x"], "dangling_ref"),
        ("adversarial_dangling_field", "output reference pointing to missing field", ["step_y"], "dangling_field"),
        ("adversarial_blocked_tool", "request to execute ToolRisk.BLOCKED capability", ["dangerous_nuke"], "blocked_tool"),
        ("adversarial_missing_arg", "capability invoked with missing mandatory arguments", ["needs_key"], "missing_arg"),
        ("adversarial_self_loop", "step depending on itself a -> a", ["step_z"], "cycle"),
        ("adversarial_deadlock_condition", "conflicting mutual conditions causing deadlock", ["step_c1", "step_c2"], "deadlock"),
        ("adversarial_unknown_cap", "plan step referencing completely unregistered capability", ["nonexistent_magic"], "unknown_capability"),
        ("adversarial_unvalidated_replan", "replan injection attempting to bypass validator", ["unvalidated_step"], "unvalidated_replan"),
    ]
    for i, (adv_type, prompt, caps, expected_failure) in enumerate(adv_scenarios):
        cases.append({
            "id": f"HLD-ADV-{i+1:03d}",
            "prompt": prompt,
            "category": "heldout_adversarial_safety",
            "expected_capabilities": caps,
            "expected_plan_length": 0,
            "requires_dataflow": False,
            "is_negated": False,
            "negated_capabilities": [],
            "is_adversarial": True,
            "adversarial_type": expected_failure,
            "should_succeed": False,
        })

    # 6. Dynamic Replanning & Fallback Resilience (10 goals)
    replan_scenarios = [
        ("attempt primary failing service and fallback to secondary backup service", ["primary_action"], ["fallback_action"]),
        ("try high speed network download and fallback to standard http download on failure", ["primary_action"], ["fallback_action"]),
        ("connect via fast channel and fallback to safe resilient channel", ["primary_action"], ["fallback_action"]),
        ("retrieve from memory cache and fallback to persistent disk storage", ["primary_action"], ["fallback_action"]),
        ("execute optimized accelerator and fallback to cpu emulation", ["primary_action"], ["fallback_action"]),
        ("send via low latency socket and fallback to poll queue", ["primary_action"], ["fallback_action"]),
        ("query local mirror and fallback to upstream canonical repo", ["primary_action"], ["fallback_action"]),
        ("allocate contiguous buffer and fallback to segmented buffer pool", ["primary_action"], ["fallback_action"]),
        ("acquire high priority lock and fallback to queued worker thread", ["primary_action"], ["fallback_action"]),
        ("execute primary action and replan to fallback action if primary fails", ["primary_action"], ["fallback_action"]),
    ]
    for i, (prompt, prim, fall) in enumerate(replan_scenarios):
        cases.append({
            "id": f"HLD-RPL-{i+1:03d}",
            "prompt": prompt,
            "category": "heldout_replan_resilience",
            "expected_capabilities": prim,
            "fallback_capabilities": fall,
            "expected_plan_length": 1,
            "requires_dataflow": False,
            "is_replan": True,
            "is_negated": False,
            "negated_capabilities": [],
            "is_plugin": True,
            "should_succeed": True,
        })

    return cases


def main():
    os.makedirs("benchmarks/agent_generality", exist_ok=True)

    dev_cases = generate_dev_dataset()
    holdout_cases = generate_holdout_dataset()

    dev_path = "benchmarks/agent_generality/dataset_dev.json"
    holdout_path = "benchmarks/agent_generality/dataset_holdout.json"

    with open(dev_path, "w", encoding="utf-8") as f:
        json.dump(dev_cases, f, indent=2)

    with open(holdout_path, "w", encoding="utf-8") as f:
        json.dump(holdout_cases, f, indent=2)

    print(f"Generated {len(dev_cases)} dev cases -> {dev_path}")
    print(f"Generated {len(holdout_cases)} holdout cases -> {holdout_path}")
    print(f"Total benchmark cases: {len(dev_cases) + len(holdout_cases)}")


if __name__ == "__main__":
    main()
