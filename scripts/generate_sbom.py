"""SPDX 2.3 Software Bill of Materials (SBOM) Generator for AstraRun 1.0.

Inspects the Python environment and build outputs to produce a compliant
SPDX 2.3 JSON document listing packages, licenses, dependencies, and SHA-256 hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def generate_spdx_sbom(output_path: Path) -> Dict[str, Any]:
    """Generate SPDX 2.3 JSON document."""
    created_time = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    doc_namespace = f"https://spdx.org/spdxdocs/astrarun-1.0.0-rc.1-{uuid.uuid4().hex[:12]}"

    # Root application package
    root_package = {
        "SPDXID": "SPDXRef-Package-AstraRun",
        "name": "AstraRun",
        "versionInfo": "1.0.0-rc.1",
        "downloadLocation": "https://github.com/astrarun/astrarun",
        "filesAnalyzed": False,
        "supplier": "Organization: AstraRun Engineering Team",
        "originator": "Organization: AstraRun Engineering Team",
        "homepage": "https://github.com/astrarun/astrarun",
        "licenseConcluded": "MIT",
        "licenseDeclared": "MIT",
        "copyrightText": "Copyright 2026 AstraRun Contributors",
        "summary": "Autonomous desktop AI agent for Windows with dual-engine cognition and governed dynamic tooling.",
        "description": "Resident workstation agent featuring dual-engine local LLM inference, sandboxed dynamic tooling, AST verification, and zero console windows.",
    }

    # Inspect build artifacts if present
    checksums = []
    dist_exe = Path("dist/AstraRun/AstraRun.exe")
    if dist_exe.exists():
        checksums.append({
            "algorithm": "SHA256",
            "checksumValue": compute_file_sha256(dist_exe),
        })

    for inst_path in [Path("dist/AstraRun-Setup-1.0.0-rc.1.exe"), Path("Output/AstraRun-Setup-1.0.0-rc.1.exe")]:
        if inst_path.exists():
            checksums.append({
                "algorithm": "SHA256",
                "checksumValue": compute_file_sha256(inst_path),
            })
            break

    if checksums:
        root_package["checksums"] = checksums

    packages: List[Dict[str, Any]] = [root_package]
    relationships: List[Dict[str, Any]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package-AstraRun",
        }
    ]

    # Gather installed runtime dependencies
    try:
        dists = list(importlib.metadata.distributions())
    except Exception:
        dists = []

    # Sort distributions for deterministic reproducible output
    dists.sort(key=lambda d: d.metadata.get("Name", "").lower())

    seen_names = set()
    for dist in dists:
        name = dist.metadata.get("Name")
        if not name or name.lower() in seen_names or name.lower() == "astrarun":
            continue
        seen_names.add(name.lower())

        ver = dist.metadata.get("Version", "unknown")
        lic = dist.metadata.get("License", "NOASSERTION") or "NOASSERTION"
        # Sanitize license string if multiline
        if "\n" in lic or len(lic) > 80:
            lic = "NOASSERTION"

        pkg_id = f"SPDXRef-Package-PyPI-{name.replace('_', '-').replace('.', '-')}"
        pkg = {
            "SPDXID": pkg_id,
            "name": name,
            "versionInfo": ver,
            "downloadLocation": f"https://pypi.org/project/{name}/{ver}/",
            "filesAnalyzed": False,
            "supplier": "Person: Upstream PyPI Contributor",
            "licenseConcluded": lic,
            "licenseDeclared": lic,
            "copyrightText": "NOASSERTION",
        }
        packages.append(pkg)
        relationships.append({
            "spdxElementId": "SPDXRef-Package-AstraRun",
            "relationshipType": "DEPENDS_ON",
            "relatedSpdxElement": pkg_id,
        })

    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "AstraRun-1.0.0-rc.1-SBOM",
        "documentNamespace": doc_namespace,
        "creationInfo": {
            "created": created_time,
            "creators": [
                "Tool: AstraRun-SPDX-Generator-1.0",
                "Organization: AstraRun Engineering Team",
            ],
            "licenseListVersion": "3.20",
        },
        "packages": packages,
        "relationships": relationships,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return document


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SPDX 2.3 SBOM for AstraRun.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/AstraRun-1.0.0-rc.1.spdx.json"),
        help="Target output path for JSON document.",
    )
    args = parser.parse_args()

    doc = generate_spdx_sbom(args.output)
    print(f"SPDX 2.3 SBOM successfully written to: {args.output} ({len(doc['packages'])} packages cataloged)")


if __name__ == "__main__":
    main()
