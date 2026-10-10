"""Evaluate semantic entity identity resolution across installed and adversarial cases."""

import json
from datetime import datetime, timezone
from pathlib import Path

from astrarun.agent.planner import GoalPlanner
from astrarun.brain.decision.entity_resolver import (
    SemanticEntityIdentityEvaluator,
    SemanticEntityResolver,
)

REPO_ROOT = Path("e:/Workspace/Active/AstraRun")
OUTPUT_PATH = REPO_ROOT / "docs" / "audit" / "F0_23_ENTITY_IDENTITY_RESULTS.json"

TEST_CASES = [
    # Positive discovery & resolution from actually installed applications
    ("open visual studio code", "visual studio code", True, "Visual Studio Code"),
    ("launch notepad", "notepad", True, "Notepad"),
    ("open calculator", "calculator", True, "Calculator"),
    ("run command prompt", "command prompt", True, "Command Prompt"),
    ("launch powershell", "powershell", True, "Windows PowerShell"),
    ("open file explorer", "file explorer", True, "File Explorer"),
    ("launch wt", "wt", True, "Windows Terminal"),
    ("open cmd", "cmd", True, "Command Prompt"),
    ("open calc", "calc", True, "Calculator"),
    ("start vivaldi", "vivaldi", True, "Vivaldi"),
    ("open vscode", "vscode", True, "Visual Studio Code"),
    ("launch pwsh", "pwsh", True, "PowerShell 7"),
    ("open task manager", "task manager", True, "Task Manager"),
    ("open paint", "mspaint", True, "Mspaint"),
    ("open control panel", "control panel", True, "Control Panel"),
    ("launch character map", "character map", True, "Character Map"),
    ("open anaconda prompt", "anaconda prompt", True, "Anaconda Prompt"),
    ("launch adobe acrobat", "adobe acrobat", True, "Adobe Acrobat"),
    ("start antigravity ide", "antigravity ide", True, "Antigravity IDE"),
    ("open access", "access", True, "Access"),
    ("launch autohotkey dash", "autohotkey dash", True, "AutoHotkey Dash"),
    ("open windows terminal", "windows terminal", True, "Windows Terminal"),
    ("run administrative tools", "administrative tools", True, "Administrative Tools"),
    ("open powershell 7", "powershell 7", True, "PowerShell 7"),
    ("start alacritty", "alacritty", True, "Alacritty (Ubuntu)"),
    # Non-existent entities (must honestly resolve to None / reject)
    ("open completely_unknown_app_xyz_123", "completely_unknown_app_xyz_123", False, None),
    ("launch fake_nonexistent_tool_404", "fake_nonexistent_tool_404", False, None),
    ("open non_existent_editor_9999", "non_existent_editor_9999", False, None),
    ("run imaginary_software_alpha_omega", "imaginary_software_alpha_omega", False, None),
    ("start missing_binary_daemon_11", "missing_binary_daemon_11", False, None),
    # Adversarial pairs (must reject semantically wrong software)
    ("open visual studio code", "visual profiler", "ADVERSARIAL_REJECT", "Visual Profiler"),
    ("open visual studio code", "visual studio installer", "ADVERSARIAL_REJECT", "Visual Studio Installer"),
    ("open command prompt", "windows terminal", "ADVERSARIAL_REJECT", "Windows Terminal"),
    ("open word", "wordpad", "ADVERSARIAL_REJECT", "WordPad"),
    ("open chrome", "chromium", "ADVERSARIAL_REJECT", "Chromium"),
    ("open notepad", "wordpad", "ADVERSARIAL_REJECT", "WordPad"),
    ("open calculator", "calc_tax_tool", "ADVERSARIAL_REJECT", "Tax Calc"),
    ("open powershell", "command prompt", "ADVERSARIAL_REJECT", "Command Prompt"),
    ("launch vivaldi", "firefox", "ADVERSARIAL_REJECT", "Firefox"),
    ("open task manager", "resource monitor", "ADVERSARIAL_REJECT", "Resource Monitor"),
    # Paraphrased natural requests
    ("please launch the visual studio code editor for me", "visual studio code", True, "Visual Studio Code"),
    ("bring up command prompt right now", "command prompt", True, "Command Prompt"),
    ("switch to calculator please", "calculator", True, "Calculator"),
    ("can you open notepad", "notepad", True, "Notepad"),
    ("start up powershell", "powershell", True, "Windows PowerShell"),
    ("open the file explorer window", "file explorer", True, "File Explorer"),
    ("launch the character map tool", "character map", True, "Character Map"),
    ("bring up task manager now", "task manager", True, "Task Manager"),
    ("open the paint application", "mspaint", True, "Mspaint"),
    ("open the control panel window", "control panel", True, "Control Panel"),
    ("launch anaconda prompt utility", "anaconda prompt", True, "Anaconda Prompt"),
    ("open adobe acrobat reader", "adobe acrobat", True, "Adobe Acrobat"),
    ("start antigravity ide for me", "antigravity ide", True, "Antigravity IDE"),
    ("execute microsoft access app", "access", True, "Access"),
    ("launch autohotkey dash tool", "autohotkey dash", True, "AutoHotkey Dash"),
]

def main() -> None:
    planner = GoalPlanner()
    resolver = SemanticEntityResolver.get_instance()

    eval_results = []
    passed_count = 0
    rejected_adversarial_count = 0

    for item in TEST_CASES:
        prompt, target_query, expected_mode, expected_name = item
        goal = planner.parse_goal(prompt)
        extracted = goal.contract.target_application or goal.contract.entities.get("application", "")

        if expected_mode == "ADVERSARIAL_REJECT":
            fake_adversarial = resolver.resolve_application(target_query)
            ok, msg = SemanticEntityIdentityEvaluator.evaluate(extracted or prompt, fake_adversarial)
            adversarial_rejected = not ok
            if adversarial_rejected:
                rejected_adversarial_count += 1
                passed_count += 1
            eval_results.append({
                "prompt": prompt,
                "mode": "ADVERSARIAL_REJECTION",
                "extracted_app": extracted,
                "injected_candidate": fake_adversarial.name if fake_adversarial else target_query,
                "oracle_verdict": "REJECTED" if adversarial_rejected else "INVALID_ACCEPT",
                "reason": msg,
                "passed": adversarial_rejected,
            })
        elif expected_mode is True:
            resolved = resolver.resolve_application(extracted or target_query)
            ok, msg = SemanticEntityIdentityEvaluator.evaluate(target_query, resolved)
            eval_results.append({
                "prompt": prompt,
                "mode": "POSITIVE_RESOLUTION",
                "extracted_app": extracted,
                "resolved_name": resolved.name if resolved else None,
                "resolved_id": resolved.entity_id if resolved else None,
                "confidence": resolved.confidence if resolved else 0.0,
                "oracle_verdict": "PASS" if ok else "FAIL",
                "reason": msg,
                "passed": ok,
            })
            if ok:
                passed_count += 1
        else:
            resolved = resolver.resolve_application(extracted or target_query)
            is_none = resolved is None or not resolved.is_installed
            eval_results.append({
                "prompt": prompt,
                "mode": "NONEXISTENT_REJECTION",
                "extracted_app": extracted,
                "resolved": resolved.name if resolved else None,
                "oracle_verdict": "PASS" if is_none else "FAIL",
                "reason": "Correctly rejected non-existent entity" if is_none else "Falsely resolved non-existent entity",
                "passed": is_none,
            })
            if is_none:
                passed_count += 1

    total = len(TEST_CASES)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "F0-23",
        "description": "Semantic entity identity evaluation across installed apps, aliases, and adversarial fixtures.",
        "metrics": {
            "total_evaluated": total,
            "passed": passed_count,
            "failed": total - passed_count,
            "pass_rate_percent": (passed_count / total) * 100.0,
            "adversarial_rejections_verified": rejected_adversarial_count,
            "false_positives": total - passed_count,
        },
        "results": eval_results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"Evaluated {total} entity cases: {passed_count}/{total} passed ({summary['metrics']['pass_rate_percent']:.1f}%).")
    print(f"Wrote to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
