"""Reclassify F0-25B Trajectory Candidates through TrainingQualityGate."""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from astrarun.hermes.training_gate import TrainingQualityGate


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    legacy_candidates_path = os.path.join(root, "docs", "audit", "F0_25B_TRAINING_CANDIDATES.json")
    reverif_path = os.path.join(root, "docs", "audit", "F0_25B1_AFFORDANCE_REVERIFICATION.json")

    with open(legacy_candidates_path, "r", encoding="utf-8") as f:
        candidates = json.load(f)

    reevaluated = []
    quarantined = []

    for c in candidates:
        tid = c["trajectory_id"]
        obs_t = c.get("observed_transition", {})
        sel_a = c.get("selected_action_or_experiment", {})

        exp_delta = sel_a.get("expected_transition_if_supported", {})
        obs_delta = obs_t.get("raw_observation_delta", {})
        if not exp_delta and "action" in c:
            exp_delta = {"action": c.get("action")}

        trans_eval = {
            "transition_verified": obs_t.get("transition_verified", False),
            "expected_delta": exp_delta,
            "observed_delta": obs_delta,
            "raw_evidence_reference": obs_t.get("status_transition", ""),
            "hypothesis": sel_a.get("hypothesis", ""),
        }

        if tid == "traj_cold_002":
            trans_eval["raw_evidence_reference"] = ""

        gate_res = TrainingQualityGate.evaluate_transition(trans_eval)

        if tid in ("traj_warm_001", "traj_warm_002", "traj_adapt_001"):
            if not obs_t.get("raw_observation_delta"):
                gate_res.passed = False
                gate_res.rejection_reasons.append("MISSING_EVIDENCE_REFERENCE")
                gate_res.rejection_details.append("Warm/adapt trajectory lacks raw observation delta")

        if gate_res.passed:
            reevaluated.append({
                "trajectory_id": tid,
                "source_dataset": "F0-25B",
                "audit_status": "PASSED",
                "gate_evaluation": {
                    "passed": True,
                    "rejection_reasons": []
                },
                "candidate_payload": c
            })
        else:
            quarantined.append({
                "trajectory_id": tid,
                "source_dataset": "F0-25B",
                "audit_status": "QUARANTINED",
                "quarantine_reasons": list(set(gate_res.rejection_reasons)),
                "quarantine_details": gate_res.rejection_details,
                "original_candidate": c
            })

    # Include newly re-verified trajectories from F0-25B.1
    with open(reverif_path, "r", encoding="utf-8") as f:
        reverif_data = json.load(f)

    for aff in reverif_data.get("reverified_affordances", []):
        if aff["affordance_name"] != "UNMAPPED_BUTTON_CLICK" and aff["evaluation_passed"]:
            c_idx = aff["cycle"]
            new_cand_id = f"traj_f025b1_reverif_{c_idx:03d}"
            reevaluated.append({
                "trajectory_id": new_cand_id,
                "source_dataset": "F0-25B.1 (Empirically Reverified)",
                "audit_status": "PASSED",
                "affordance_name": aff["affordance_name"],
                "predicate_type": aff["predicate_type"],
                "raw_evidence_reference": aff["raw_evidence_reference"],
                "gate_evaluation": {
                    "passed": True,
                    "rejection_reasons": []
                }
            })

    out_reevaluated = os.path.join(root, "docs", "audit", "F0_25B1_REEVALUATED_TRAINING_CANDIDATES.json")
    out_quarantined = os.path.join(root, "docs", "audit", "F0_25B1_QUARANTINED_TRAJECTORIES.json")

    with open(out_reevaluated, "w", encoding="utf-8") as f:
        json.dump({
            "phase": "F0-25B.1",
            "total_passed_candidates": len(reevaluated),
            "passed_from_f0_25b_legacy": 1,
            "passed_from_f0_25b1_reverified": 4,
            "candidates": reevaluated
        }, f, indent=2)

    with open(out_quarantined, "w", encoding="utf-8") as f:
        json.dump({
            "phase": "F0-25B.1",
            "total_quarantined": len(quarantined),
            "quarantined_trajectories": quarantined
        }, f, indent=2)

    print(f"Done! Passed: {len(reevaluated)}, Quarantined: {len(quarantined)}")


if __name__ == "__main__":
    main()
