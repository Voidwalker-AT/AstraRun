"""Developer diagnostic CLI to discover and inspect registered capabilities."""

from __future__ import annotations

import argparse
from astrarun.capabilities.models import CapabilityCategory
from astrarun.capabilities.registry import CapabilityRegistry


def main() -> None:
    parser = argparse.ArgumentParser(description="AstraRun Workstation Capability Catalog")
    parser.add_argument("--category", type=str, choices=[c.value for c in CapabilityCategory], help="Filter by category")
    parser.add_argument("--json", action="store_true", help="Output JSON formatted catalog")
    args = parser.parse_args()

    reg = CapabilityRegistry()
    cat_filter = CapabilityCategory(args.category) if args.category else None
    caps = reg.list_capabilities(category=cat_filter)

    if args.json:
        import json
        data = [c.to_dict() for c in caps]
        print(json.dumps(data, indent=2))
        return

    print("=" * 85)
    print("                      ASTRARUN WORKSTATION CAPABILITIES                      ")
    print("=" * 85)
    header = f"{'ID':<28} {'CATEGORY':<14} {'RISK':<8} {'RO':<5} {'PERMISSION':<11} {'HEALTH':<10}"
    print(header)
    print("-" * 85)

    for c in caps:
        ro_str = "YES" if c.read_only else "NO"
        line = f"{c.id:<28} {c.category.value:<14} {c.risk.value:<8} {ro_str:<5} {c.permission.value:<11} {c.health.value:<10}"
        print(line)

    print("=" * 85)
    print(f"Total Registered Capabilities: {len(caps)}\n")


if __name__ == "__main__":
    main()
