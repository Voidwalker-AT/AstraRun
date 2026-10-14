"""Generates Authoritative Source Freeze for F0-25F.7 Routing Subsystem.

Enforces:
- Records both `whole_file_sha256` and `canonical_content_sha256` (CRLF-normalized).
- Covers all 11 core routing, capability, planning, and recovery source files.
- Frozen state forms the immutable boundary before blind holdout evaluation.

Outputs:
- docs/audit/F0_25F7_ROUTING_SOURCE_FREEZE.json
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path


FROZEN_FILES = [
    "src/astrarun/agent/models.py",
    "src/astrarun/agent/planner.py",
    "src/astrarun/capabilities/manifest.py",
    "src/astrarun/capabilities/registry.py",
    "src/astrarun/capabilities/schema.py",
    "src/astrarun/recovery/engine.py",
    "src/astrarun/recovery/models.py",
    "src/astrarun/routing/context_sufficiency.py",
    "src/astrarun/routing/context_grounding.py",
    "src/astrarun/routing/capability_grounding.py",
    "src/astrarun/routing/learned_router.py",
]


def compute_hashes(path: Path) -> dict:
    raw_bytes = path.read_bytes()
    whole_sha = hashlib.sha256(raw_bytes).hexdigest()
    canonical_bytes = raw_bytes.replace(b"\r\n", b"\n").strip()
    canonical_sha = hashlib.sha256(canonical_bytes).hexdigest()
    return {
        "whole_file_sha256": whole_sha,
        "canonical_content_sha256": canonical_sha,
        "size_bytes": len(raw_bytes),
    }


def freeze_sources():
    out_dict = {
        "phase": "F0-25F.7",
        "stage": "STAGE 10 — ROUTING SOURCE FREEZE",
        "frozen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "policy": "FROZEN — STRICTLY NO MODIFICATIONS PERMITTED AFTER THIS STEP",
        "hash_specification": {
            "whole_file_sha256": "SHA-256 of raw bytes on filesystem",
            "canonical_content_sha256": "SHA-256 of LF-normalized, whitespace-stripped content",
        },
        "files": {},
    }

    for rel_path in FROZEN_FILES:
        p = Path(rel_path)
        assert p.exists(), f"Source file missing: {p}"
        hashes = compute_hashes(p)
        out_dict["files"][rel_path] = hashes
        print(f"Frozen {rel_path}:")
        print(f"  whole:     {hashes['whole_file_sha256']}")
        print(f"  canonical: {hashes['canonical_content_sha256']}")

    freeze_path = Path("docs/audit/F0_25F7_ROUTING_SOURCE_FREEZE.json")
    freeze_path.parent.mkdir(parents=True, exist_ok=True)
    freeze_path.write_text(json.dumps(out_dict, indent=2), encoding="utf-8")
    print(f"\nAuthoritative Source Freeze saved to {freeze_path}")


if __name__ == "__main__":
    freeze_sources()
