"""Generate requirements-release.lock for AstraRun 1.0."""

import importlib.metadata
import platform
import time
from pathlib import Path


def main():
    header = f"""# AstraRun 1.0 Release Candidate Locked Dependencies
# Target Platform: Windows 11 / x86_64
# Python Version: {platform.python_version()} ({platform.python_implementation()})
# CUDA Runtime Bundled: PyTorch 2.4.0 / cu121 (Hardware: NVIDIA RTX 2050 Laptop GPU)
# Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
# Policy: Strict lockfile for release reproducibility. Do NOT modify without verification.

"""
    dists = sorted(
        list(importlib.metadata.distributions()),
        key=lambda d: d.metadata.get("Name", "").lower(),
    )

    lines = []
    seen = set()
    for dist in dists:
        name = dist.metadata.get("Name")
        if not name or name.lower() in seen or name.lower() == "astrarun":
            continue
        seen.add(name.lower())
        ver = dist.metadata.get("Version", "unknown")
        lines.append(f"{name}=={ver}")

    content = header + "\n".join(lines) + "\n"
    out_file = Path("requirements-release.lock")
    out_file.write_text(content, encoding="utf-8")
    print(f"Locked {len(lines)} dependencies to {out_file}")


if __name__ == "__main__":
    main()
