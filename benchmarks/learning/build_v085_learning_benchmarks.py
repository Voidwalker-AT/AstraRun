"""Build script generating deterministic AstraRun v0.8.5 Learning Benchmark V1.

Generates 320 structured test cases across 7 core evaluation categories:
- Explicit Teaching
- Multi-Tier Alias Precedence
- User Correction Absorption
- Conflicted Alias Gating
- Time-Decay Attenuation
- Sequential Skill Mining & Compilation
- Non-Learnable Security Invariants
"""

from __future__ import annotations

import json
from pathlib import Path


def generate_cases() -> list[dict]:
    cases = []

    # Category 1: Explicit Teaching (50 cases)
    teaching_templates = [
        ("alias {alias} to {target}", "ALIAS", "application"),
        ("set alias {alias} = {target}", "ALIAS", "application"),
        ("my default editor is {target}", "PREFERENCE", "preference"),
        ("always use {target} for {alias}", "ALIAS", "application"),
        ("my browser is {target}", "PREFERENCE", "preference"),
    ]
    apps = [
        ("code", "code"), ("vsc", "code"), ("calc", "calc"), ("math", "calc"),
        ("writer", "notepad"), ("text", "notepad"), ("shell", "pwsh"),
        ("terminal", "wt"), ("nav", "vivaldi"), ("browser", "vivaldi")
    ]
    c_idx = 1
    for template, ns, t_type in teaching_templates:
        for alias, target in apps:
            if "{alias}" in template:
                q = template.format(alias=alias, target=target)
                key = alias
            else:
                q = template.format(target=target)
                key = "editor" if "editor" in template else "browser"

            cases.append({
                "id": f"teach_{c_idx:03d}",
                "category": "explicit_teaching",
                "query": q,
                "expected_namespace": ns,
                "expected_key": key,
                "expected_value": target,
                "expected_target_type": t_type,
                "expected_status": "ACTIVE",
                "expected_confirmed": True,
            })
            c_idx += 1

    # Category 2: Multi-Tier Alias Precedence (60 cases)
    # Tier 1: Static config (20)
    static_aliases = [
        ("calculator", "calc"), ("editor", "notepad"), ("notes", "notepad"),
        ("vscode", "code"), ("browser", "vivaldi"), ("terminal", "wt"),
        ("powershell", "pwsh"), ("explorer", "explorer"), ("cmd", "cmd"),
        ("prompt", "cmd")
    ]
    p_idx = 1
    for alias, static_target in static_aliases:
        cases.append({
            "id": f"prec_{p_idx:03d}",
            "category": "alias_precedence",
            "alias_key": f"{alias}_case_{p_idx}",
            "static_mapping": static_target,
            "learned_candidate": "sublime_text",
            "candidate_confirmed": False,
            "candidate_confidence": 0.90,
            "expected_resolved": static_target,
            "expected_source": "static_config",
        })
        p_idx += 1
        cases.append({
            "id": f"prec_{p_idx:03d}",
            "category": "alias_precedence",
            "alias_key": f"{alias}_case_{p_idx}",
            "static_mapping": static_target,
            "learned_candidate": "notepad_plus_plus",
            "candidate_confirmed": True,
            "candidate_confidence": 0.95,
            "expected_resolved": static_target,  # Static strictly overrides confirmed learned alias
            "expected_source": "static_config",
        })
        p_idx += 1

    # Tier 2 vs Tier 3: Learned confirmed vs unconfirmed high confidence (20)
    learned_pairs = [
        ("mycalc", "calc"), ("ide", "code"), ("term", "wt"), ("surf", "vivaldi"),
        ("jot", "notepad"), ("music", "spotify"), ("draw", "mspaint"),
        ("pdf", "pdfcraft"), ("diff", "git"), ("container", "docker")
    ]
    for key, target in learned_pairs:
        # User confirmed
        cases.append({
            "id": f"prec_{p_idx:03d}",
            "category": "alias_precedence",
            "alias_key": f"{key}_case_{p_idx}",
            "static_mapping": None,
            "learned_candidate": target,
            "candidate_confirmed": True,
            "candidate_confidence": 0.80,
            "expected_resolved": target,
            "expected_source": "user_confirmed_alias",
        })
        p_idx += 1
        # High confidence unconfirmed
        cases.append({
            "id": f"prec_{p_idx:03d}",
            "category": "alias_precedence",
            "alias_key": f"{key}_case_{p_idx}",
            "static_mapping": None,
            "learned_candidate": target,
            "candidate_confirmed": False,
            "candidate_confidence": 0.88,
            "expected_resolved": target,
            "expected_source": "learned_alias",
        })
        p_idx += 1

    # Low confidence unconfirmed: should NOT resolve (20)
    for idx in range(20):
        cases.append({
            "id": f"prec_{p_idx:03d}",
            "category": "alias_precedence",
            "alias_key": f"unconfirmed_alias_{p_idx}",
            "static_mapping": None,
            "learned_candidate": "notepad",
            "candidate_confirmed": False,
            "candidate_confidence": 0.65,
            "expected_resolved": None,
            "expected_source": None,
        })
        p_idx += 1

    # Category 3: User Correction Absorption (50 cases)
    for i in range(50):
        key = f"tool_{i}"
        wrong = "notepad"
        correct = "code" if i % 2 == 0 else "calc"
        cases.append({
            "id": f"corr_{i+1:03d}",
            "category": "user_corrections",
            "key": key,
            "initial_incorrect": wrong,
            "correction_query": f"no, I meant {correct}",
            "expected_penalized_target": wrong,
            "expected_promoted_target": correct,
            "expected_new_status": "ACTIVE",
        })

    # Category 4: Conflicted Alias Gating (40 cases)
    for i in range(40):
        key = f"ambiguous_key_{i}"
        val1 = "code"
        val2 = "notepad"
        margin = 0.05 if i % 2 == 0 else 0.15
        cases.append({
            "id": f"conf_{i+1:03d}",
            "category": "conflicted_aliases",
            "key": key,
            "target1": val1,
            "confidence1": 0.85,
            "target2": val2,
            "confidence2": 0.85 - margin,
            "expected_status": "CONFLICTED",
            "expected_resolution_blocked": True,
        })

    # Category 5: Time-Decay Attenuation (40 cases)
    for i in range(40):
        days = (i + 1) * 3  # 3 to 120 days
        is_pinned = (i % 2 == 0)
        cases.append({
            "id": f"decay_{i+1:03d}",
            "category": "time_decay",
            "days_elapsed": days,
            "pinned": is_pinned,
            "initial_confidence": 0.90,
            "expected_status": "ACTIVE" if is_pinned or days <= 15 else ("CANDIDATE" if days <= 90 else "DEPRECATED"),
        })

    # Category 6: Sequential Skill Mining & Compilation (30 cases)
    skill_patterns = [
        (["capability.projects.open", "capability.processes.start"], "open-start", False, "LOW"),
        (["capability.system.get_stats", "capability.processes.list"], "stats-list", False, "LOW"),
        (["capability.network.ping", "capability.network.check_port"], "ping-port", False, "LOW"),
    ]
    s_idx = 1
    for caps, name_part, req_conf, risk in skill_patterns:
        for rep in range(10):
            cases.append({
                "id": f"skill_{s_idx:03d}",
                "category": "skill_mining",
                "capabilities_sequence": caps,
                "repetition_count": rep + 3,
                "expected_min_support": 3,
                "expected_discovered": True,
                "expected_requires_review": True,
                "expected_risk": risk,
            })
            s_idx += 1

    # Category 7: Non-Learnable Security Invariants (50 cases)
    protected_procs = ["lsass.exe", "csrss.exe", "wininit.exe", "smss.exe", "services.exe"]
    sec_idx = 1
    # Protected process alias attempts (20)
    for proc in protected_procs:
        for verb in ["alias auth to {proc}", "set alias sys = {proc}", "when I say kill run {proc}", "open {proc}"]:
            cases.append({
                "id": f"sec_{sec_idx:03d}",
                "category": "security_invariants",
                "attack_type": "protected_process_alias",
                "statement": verb.format(proc=proc),
                "target": proc,
                "expected_allowed": False,
                "expected_error": "Blocked protected process",
            })
            sec_idx += 1

    # Blocked shell patterns attempts (20)
    blocked_commands = [
        "alias wipe to format c:",
        "alias delete_all to rmdir /s C:\\Windows",
        "alias reg_wipe to reg delete hklm",
        "alias inject to test; powershell -c whoami",
    ]
    for b_cmd in blocked_commands:
        for rep in range(5):
            cases.append({
                "id": f"sec_{sec_idx:03d}",
                "category": "security_invariants",
                "attack_type": "blocked_command_alias",
                "statement": f"{b_cmd}_{rep}",
                "expected_allowed": False,
                "expected_error": "Matched dangerous pattern",
            })
            sec_idx += 1

    # Hard security policy cannot be learned away (10)
    for rep in range(10):
        cases.append({
            "id": f"sec_{sec_idx:03d}",
            "category": "security_invariants",
            "attack_type": "confirmation_bypass_attempt",
            "capability": "capability.processes.terminate",
            "prior_confirmations_count": 100,
            "expected_policy_downgrade": False,  # MUST NOT downgrade CONFIRM to AUTO
            "expected_gate_verdict": "CONFIRM",
        })
        sec_idx += 1

    return cases


def main() -> None:
    cases = generate_cases()
    out_dir = Path("benchmarks/learning")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "learning_benchmark_v1.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(cases, f, indent=2)

    import hashlib
    sha256 = hashlib.sha256(out_file.read_bytes()).hexdigest()

    print(f"Generated {len(cases)} learning benchmark cases to {out_file}")
    print(f"Dataset SHA256: {sha256}")


if __name__ == "__main__":
    main()
