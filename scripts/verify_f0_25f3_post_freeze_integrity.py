"""Verify that 100% of files listed in F0_25F3_SOURCE_FREEZE.json remain byte-identical post-acceptance."""

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def compute_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def verify_post_freeze():
    freeze_path = REPO_ROOT / "docs" / "audit" / "F0_25F3_SOURCE_FREEZE.json"
    if not freeze_path.exists():
        print(f"Error: {freeze_path} does not exist.")
        sys.exit(1)

    freeze_data = json.loads(freeze_path.read_text(encoding="utf-8"))
    source_hashes = freeze_data.get("source_hashes", {})

    total = len(source_hashes)
    matched = 0
    mismatches = []
    missing = []

    for rel_path, meta in source_hashes.items():
        full_path = REPO_ROOT / rel_path
        if not full_path.exists():
            missing.append(rel_path)
            continue
        current_sha = compute_sha256(full_path)
        expected_sha = meta["sha256"]
        if current_sha == expected_sha:
            matched += 1
        else:
            mismatches.append({
                "path": rel_path,
                "expected_sha": expected_sha,
                "current_sha": current_sha,
            })

    report = {
        "benchmark": "POST_FREEZE_INTEGRITY_VERIFICATION",
        "phase": "F0-25F.3",
        "total_frozen_files": total,
        "matched_files": matched,
        "mismatches": mismatches,
        "missing_files": missing,
        "integrity_verified": (matched == total and len(mismatches) == 0 and len(missing) == 0),
        "integrity_rate_pct": (matched / total * 100.0) if total else 0.0,
    }

    out_file = REPO_ROOT / "docs" / "audit" / "F0_25F3_POST_FREEZE_INTEGRITY.json"
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Integrity check: {matched}/{total} matched ({report['integrity_rate_pct']:.2f}%)")
    if mismatches:
        print(f"FAILED: {len(mismatches)} files modified after freeze!")
        for m in mismatches[:5]:
            print(f"  {m['path']}")
        sys.exit(1)
    if missing:
        print(f"FAILED: {len(missing)} files missing after freeze!")
        sys.exit(1)

    print("SUCCESS: 0 post-freeze modifications detected. Integrity verified.")
    return True

if __name__ == "__main__":
    verify_post_freeze()
