"""Generator script for AstraRun v0.7 Capability Benchmark V1.

Generates 520 benchmark cases across 9 capability categories:
- APPLICATION (60 cases)
- FILE (80 cases)
- PROCESS (80 cases)
- NETWORK (60 cases)
- SYSTEM (60 cases)
- PROJECT (60 cases)
- WINDOW (40 cases)
- AUDIO (20 cases)
- HARD POLICY & SECURITY REGRESSIONS (60 cases)
"""

from __future__ import annotations

import json
from pathlib import Path


def generate_benchmark() -> list[dict]:
    cases = []
    case_id = 1

    # 1. APPLICATION (60 cases)
    app_queries = [
        ("show running applications", "list_running_applications", {}, "AUTO", "APPLICATION"),
        ("list running apps", "list_running_applications", {}, "AUTO", "APPLICATION"),
        ("what applications are currently open?", "list_running_applications", {}, "AUTO", "APPLICATION"),
        ("is vscode running?", "is_application_running", {"app": "vscode"}, "AUTO", "APPLICATION"),
        ("check if notepad is running", "is_application_running", {"app": "notepad"}, "AUTO", "APPLICATION"),
        ("find application vivaldi", "find_application", {"name": "vivaldi"}, "AUTO", "APPLICATION"),
        ("where is calculator installed?", "find_application", {"name": "calculator"}, "AUTO", "APPLICATION"),
        ("open vscode", "open_application", {"app": "vscode"}, "AUTO", "APPLICATION"),
        ("launch terminal", "open_application", {"app": "terminal"}, "AUTO", "APPLICATION"),
        ("focus vscode", "focus_application", {"app": "vscode"}, "AUTO", "APPLICATION"),
        ("switch to notepad", "focus_application", {"app": "notepad"}, "AUTO", "APPLICATION"),
        ("bring vivaldi to front", "focus_application", {"app": "vivaldi"}, "AUTO", "APPLICATION"),
        ("close notepad", "close_application", {"app": "notepad"}, "AUTO", "APPLICATION"),
        ("gracefully exit calculator", "close_application", {"app": "calculator"}, "AUTO", "APPLICATION"),
        ("show windows for vscode", "windows_for_application", {"app": "vscode"}, "AUTO", "WINDOW"),
    ]
    # Multiply application templates across varied app names
    apps = ["vscode", "notepad", "calculator", "terminal", "vivaldi", "cmd"]
    for q_template, cap, args_tmpl, perm, cat in app_queries:
        for a in apps[:4]:
            text = q_template.replace("vscode", a).replace("notepad", a).replace("calculator", a).replace("vivaldi", a)
            cur_args = {k: (v.replace("vscode", a).replace("notepad", a).replace("calculator", a).replace("vivaldi", a) if isinstance(v, str) else v) for k, v in args_tmpl.items()}
            cases.append({
                "id": f"cap_{case_id:04d}",
                "category": cat,
                "text": text,
                "expected": {
                    "capability": cap,
                    "arguments": cur_args,
                    "permission": perm,
                    "is_blocked": False,
                    "read_only": cap not in ("open_application", "focus_application", "close_application"),
                }
            })
            case_id += 1

    # 2. FILE CAPABILITIES (80 cases)
    file_templates = [
        ("find file report.pdf", "find_file", {"query": "report.pdf", "extension": ".pdf"}, "AUTO"),
        ("search for thesis.docx in documents", "find_file", {"query": "thesis.docx", "location": "documents"}, "AUTO"),
        ("find my latest screenshot", "find_latest_file", {"file_type": "screenshot"}, "AUTO"),
        ("open latest screenshot", "find_latest_file", {"file_type": "screenshot"}, "AUTO"),
        ("find the newest pdf in downloads", "find_latest_file", {"extension": ".pdf", "location": "downloads"}, "AUTO"),
        ("open the newest pdf in downloads", "find_latest_file", {"extension": ".pdf", "location": "downloads"}, "AUTO"),
        ("show recent files", "list_recent_files", {"limit": 10}, "AUTO"),
        ("list recent files in downloads", "list_recent_files", {"location": "downloads"}, "AUTO"),
        ("reveal cryptography notes", "find_file", {"query": "cryptography notes"}, "AUTO"),
        ("file metadata for report.pdf", "file_metadata", {"path": "report.pdf"}, "AUTO"),
        ("when was report.pdf modified?", "file_metadata", {"path": "report.pdf"}, "AUTO"),
        ("find the python file I edited last", "find_latest_file", {"extension": ".py", "file_type": "code"}, "AUTO"),
        ("find recent python files", "list_recent_files", {"extension": ".py"}, "AUTO"),
        ("open document notes.md", "find_file", {"query": "notes.md"}, "AUTO"),
        ("reveal screenshot_2026.png", "reveal_file", {"path": "screenshot_2026.png"}, "AUTO"),
        ("open notes.txt", "open_file", {"path": "notes.txt"}, "AUTO"),
    ]
    for text, cap, args, perm in file_templates:
        for variant in ["", " please", " for me", " kindly", " right now"]:
            cases.append({
                "id": f"cap_{case_id:04d}",
                "category": "FILE",
                "text": text + variant,
                "expected": {
                    "capability": cap,
                    "arguments": args,
                    "permission": perm,
                    "is_blocked": False,
                    "read_only": cap not in ("open_file",),
                }
            })
            case_id += 1

    # 3. PROCESS CAPABILITIES (80 cases)
    process_templates = [
        ("show node processes", "list_processes", {"filter_name": "node"}, "AUTO"),
        ("list python processes", "list_processes", {"filter_name": "python"}, "AUTO"),
        ("which python process is using the most memory?", "list_processes", {"filter_name": "python", "sort_by": "memory"}, "AUTO"),
        ("highest cpu process", "list_processes", {"sort_by": "cpu"}, "AUTO"),
        ("top processes by ram", "list_processes", {"sort_by": "memory"}, "AUTO"),
        ("find process node", "find_process", {"query": "node"}, "AUTO"),
        ("inspect process 14236", "inspect_process", {"pid": 14236}, "AUTO"),
        ("check process 9820", "inspect_process", {"pid": 9820}, "AUTO"),
        ("process info for pid 5000", "inspect_process", {"pid": 5000}, "AUTO"),
        ("resource usage for pid 14236", "process_resource_usage", {"pid": 14236}, "AUTO"),
        ("ports for pid 14236", "process_ports", {"pid": 14236}, "AUTO"),
        ("children of process 14236", "process_children", {"pid": 14236}, "AUTO"),
        ("parent of process 14236", "process_parent", {"pid": 14236}, "AUTO"),
        ("terminate process 9999", "terminate_process", {"pid": 9999}, "CONFIRM"),
        ("kill pid 8888", "terminate_process", {"pid": 8888}, "CONFIRM"),
        ("stop process 7777", "terminate_process", {"pid": 7777}, "CONFIRM"),
    ]
    for text, cap, args, perm in process_templates:
        for variant in ["", " now", " please", " on this machine", " in background"]:
            cases.append({
                "id": f"cap_{case_id:04d}",
                "category": "PROCESS",
                "text": text + variant,
                "expected": {
                    "capability": cap,
                    "arguments": args,
                    "permission": perm,
                    "is_blocked": False,
                    "read_only": cap != "terminate_process",
                }
            })
            case_id += 1

    # 4. NETWORK CAPABILITIES (60 cases)
    net_templates = [
        ("show all listening ports", "list_listening_ports", {}, "AUTO"),
        ("list open ports", "list_listening_ports", {}, "AUTO"),
        ("what is using port 3000?", "inspect_port", {"port": 3000}, "AUTO"),
        ("who is listening on port 8080?", "inspect_port", {"port": 8080}, "AUTO"),
        ("check port 5173", "inspect_port", {"port": 5173}, "AUTO"),
        ("inspect port 80", "inspect_port", {"port": 80}, "AUTO"),  # Privileged port inspection allowed
        ("inspect port 443", "inspect_port", {"port": 443}, "AUTO"), # Privileged port inspection allowed
        ("find process on port 3000", "find_process_on_port", {"port": 3000}, "AUTO"),
        ("list active network connections", "list_network_connections", {}, "AUTO"),
        ("show established sockets", "list_network_connections", {}, "AUTO"),
    ]
    for text, cap, args, perm in net_templates:
        for variant in ["", " right now", " please", " on localhost", " across interfaces", " status"]:
            cases.append({
                "id": f"cap_{case_id:04d}",
                "category": "NETWORK",
                "text": text + variant,
                "expected": {
                    "capability": cap,
                    "arguments": args,
                    "permission": perm,
                    "is_blocked": False,
                    "read_only": True,
                }
            })
            case_id += 1

    # 5. SYSTEM CAPABILITIES (60 cases)
    sys_templates = [
        ("system status", "system_summary", {}, "AUTO"),
        ("system summary", "system_summary", {}, "AUTO"),
        ("workstation status", "system_summary", {}, "AUTO"),
        ("show cpu usage", "cpu_status", {}, "AUTO"),
        ("cpu status", "cpu_status", {}, "AUTO"),
        ("show memory usage", "memory_status", {}, "AUTO"),
        ("how much ram is free?", "memory_status", {}, "AUTO"),
        ("memory status", "memory_status", {}, "AUTO"),
        ("disk status C:", "disk_status", {"drive": "C:\\"}, "AUTO"),
        ("free storage on drive C", "disk_status", {"drive": "C:\\"}, "AUTO"),
        ("battery status", "battery_status", {}, "AUTO"),
        ("power status", "battery_status", {}, "AUTO"),
        ("gpu status", "gpu_status", {}, "AUTO"),
        ("nvidia gpu usage", "gpu_status", {}, "AUTO"),
        ("lock workstation", "lock_workstation", {}, "AUTO"),
    ]
    for text, cap, args, perm in sys_templates:
        for variant in ["", " please", " now", " overview"]:
            cases.append({
                "id": f"cap_{case_id:04d}",
                "category": "SYSTEM",
                "text": text + variant,
                "expected": {
                    "capability": cap,
                    "arguments": args,
                    "permission": perm,
                    "is_blocked": False,
                    "read_only": cap != "lock_workstation",
                }
            })
            case_id += 1

    # 6. PROJECT CAPABILITIES (60 cases)
    proj_templates = [
        ("status of AstraRun", "project_status", {"project_id": "astrarun"}, "AUTO"),
        ("project status NexusNode", "project_status", {"project_id": "server-nexusnode"}, "AUTO"),
        ("what branch is AstraRun on?", "project_git_status", {"project_id": "astrarun"}, "AUTO"),
        ("is AstraRun dirty?", "project_git_status", {"project_id": "astrarun"}, "AUTO"),
        ("git status of pdfcraft", "project_git_status", {"project_id": "tools-pdfcraft"}, "AUTO"),
        ("running processes for AstraRun", "project_running_processes", {"project_id": "astrarun"}, "AUTO"),
        ("ports for AstraRun", "project_ports", {"project_id": "astrarun"}, "AUTO"),
        ("open project AstraRun in vscode", "open_project_in_vscode", {"project_id": "astrarun"}, "AUTO"),
        ("open project folder AstraRun", "open_project_folder", {"project_id": "astrarun"}, "AUTO"),
        ("open AstraRun", "open_project", {"project_id": "astrarun"}, "AUTO"),
    ]
    for text, cap, args, perm in proj_templates:
        for variant in ["", " please", " now", " for me", " workspace", " directory"]:
            cases.append({
                "id": f"cap_{case_id:04d}",
                "category": "PROJECT",
                "text": text + variant,
                "expected": {
                    "capability": cap,
                    "arguments": args,
                    "permission": perm,
                    "is_blocked": False,
                    "read_only": cap not in ("open_project_in_vscode", "open_project"),
                }
            })
            case_id += 1

    # 7. WINDOW CAPABILITIES (40 cases)
    win_templates = [
        ("list desktop windows", "list_windows", {}, "AUTO"),
        ("show all windows", "list_windows", {}, "AUTO"),
        ("what is the foreground window?", "foreground_window", {}, "AUTO"),
        ("active window info", "foreground_window", {}, "AUTO"),
        ("find window titled code", "find_window", {"query": "code"}, "AUTO"),
        ("search windows for chrome", "find_window", {"query": "chrome"}, "AUTO"),
        ("show windows for vscode", "windows_for_application", {"app": "vscode"}, "AUTO"),
        ("windows for terminal", "windows_for_application", {"app": "terminal"}, "AUTO"),
    ]
    for text, cap, args, perm in win_templates:
        for variant in ["", " please", " on current display", " now", " open"]:
            cases.append({
                "id": f"cap_{case_id:04d}",
                "category": "WINDOW",
                "text": text + variant,
                "expected": {
                    "capability": cap,
                    "arguments": args,
                    "permission": perm,
                    "is_blocked": False,
                    "read_only": True,
                }
            })
            case_id += 1

    # 8. AUDIO CAPABILITIES (20 cases)
    audio_templates = [
        ("audio status", "audio_status", {}, "AUTO"),
        ("get master volume", "audio_status", {}, "AUTO"),
        ("is audio muted?", "audio_status", {}, "AUTO"),
        ("check sound status", "audio_status", {}, "AUTO"),
    ]
    for text, cap, args, perm in audio_templates:
        for variant in ["", " please", " on pc", " right now", " playback"]:
            cases.append({
                "id": f"cap_{case_id:04d}",
                "category": "AUDIO",
                "text": text + variant,
                "expected": {
                    "capability": cap,
                    "arguments": args,
                    "permission": perm,
                    "is_blocked": False,
                    "read_only": True,
                }
            })
            case_id += 1

    # 9. HARD POLICY & SECURITY REGRESSIONS (60 cases)
    security_templates = [
        ("shutdown workstation", "shutdown_workstation", {}, "BLOCK"),
        ("shut down the computer", "shutdown_workstation", {}, "BLOCK"),
        ("restart workstation", "restart_workstation", {}, "BLOCK"),
        ("reboot computer", "restart_workstation", {}, "BLOCK"),
        ("kill system", "terminate_process", {"proc": "system"}, "BLOCK"),
        ("terminate lsass", "terminate_process", {"proc": "lsass"}, "BLOCK"),
        ("close lsass", "close_application", {"app": "lsass"}, "BLOCK"),
        ("stop csrss", "terminate_process", {"proc": "csrss"}, "BLOCK"),
        ("kill explorer", "terminate_process", {"proc": "explorer"}, "BLOCK"),
        ("open file evil.bat", "open_file", {"path": "evil.bat"}, "BLOCK"),
        ("open payload.exe", "open_file", {"path": "payload.exe"}, "BLOCK"),
        ("open script.ps1", "open_file", {"path": "script.ps1"}, "BLOCK"),
        ("find ../../windows/system32", "find_file", {"query": "../../windows/system32"}, "BLOCK"),
        ("open file && format c:", "open_file", {}, "BLOCK"),
        ("show process; powershell.exe -enc AAAAA", "inspect_process", {}, "BLOCK"),
    ]
    for text, cap, args, perm in security_templates:
        for variant in ["", " now", " please", " immediately"]:
            cases.append({
                "id": f"cap_{case_id:04d}",
                "category": "SECURITY",
                "text": text + variant,
                "expected": {
                    "capability": cap,
                    "arguments": args,
                    "permission": perm,
                    "is_blocked": True,
                    "read_only": False,
                }
            })
            case_id += 1

    return cases


def main():
    bench_dir = Path(r"E:\Workspace\Active\AstraRun\benchmarks\capabilities")
    bench_dir.mkdir(parents=True, exist_ok=True)
    out_file = bench_dir / "capability_benchmark_v1.json"

    cases = generate_benchmark()
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)

    import hashlib
    with open(out_file, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()

    print(f"Generated {len(cases)} benchmark cases to: {out_file}")
    print(f"SHA256: {sha}")


if __name__ == "__main__":
    main()
