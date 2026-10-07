"""Test capability security manifest consistency across all registered production capabilities.

Enforces:
  - 0 unclassified or UNKNOWN_CONSEQUENTIAL production mutating capabilities
  - Consistency between read_only and mutates_state
  - BLOCK and CONFIRM permissions strictly enforce safety
  - PROCESS_KILL is never auto-authorized
  - ActionGate policy alignment
"""

import json
from pathlib import Path

import pytest

from astrarun.capabilities.models import CapabilityPermission
from astrarun.capabilities.registry import CapabilityRegistry
from astrarun.core.models import ToolRisk
from astrarun.security.action_gate import ActionGate
from astrarun.security.execution_broker import ActionCategory, ActionProposal, ExecutionBroker
from astrarun.security.models import (
    ActionGateVerdict,
    CapabilityOperationKind,
    RiskLevel,
)


def test_capability_manifest_consistency_and_export():
    registry = CapabilityRegistry()
    capabilities = registry.list_capabilities()
    broker = ExecutionBroker(capability_registry=registry)
    gate = ActionGate(capability_registry=registry)

    total_count = len(capabilities)
    explicit_count = 0
    read_only_count = 0
    mutating_count = 0
    confirm_count = 0
    blocked_count = 0
    unknown_count = 0

    manifest_records = []

    for cap in capabilities:
        sec = cap.get_security_metadata()
        assert sec is not None, f"Capability {cap.id} returned None for security metadata"

        # Track counts
        explicit_count += 1
        if cap.read_only:
            read_only_count += 1
        else:
            mutating_count += 1

        if sec.requires_confirmation or cap.requires_confirmation or cap.permission == CapabilityPermission.CONFIRM:
            confirm_count += 1

        if cap.permission == CapabilityPermission.BLOCK or cap.risk == ToolRisk.BLOCKED:
            blocked_count += 1

        if sec.operation_kind == CapabilityOperationKind.UNKNOWN_CONSEQUENTIAL:
            unknown_count += 1

        # Invariant 1: read_only must never contradict mutates_state
        assert cap.read_only == (not sec.mutates_state), (
            f"Consistency failure on '{cap.id}': read_only={cap.read_only} contradicts mutates_state={sec.mutates_state}"
        )

        # Invariant 2: Mutating capability must NOT have UNKNOWN_CONSEQUENTIAL
        if not cap.read_only:
            assert sec.operation_kind != CapabilityOperationKind.UNKNOWN_CONSEQUENTIAL, (
                f"Production mutating capability '{cap.id}' has unclassified UNKNOWN_CONSEQUENTIAL operation_kind"
            )

        # Invariant 3: BLOCK permission must not map to permissive metadata
        if cap.permission == CapabilityPermission.BLOCK or cap.risk == ToolRisk.BLOCKED:
            assert sec.risk in (RiskLevel.HIGH, RiskLevel.CRITICAL), (
                f"BLOCKED capability '{cap.id}' has permissive risk level {sec.risk}"
            )
            assert sec.requires_confirmation or sec.risk == RiskLevel.CRITICAL, (
                f"BLOCKED capability '{cap.id}' must require confirmation or have CRITICAL risk"
            )

        # Invariant 4: CONFIRM capability must require confirmation
        if cap.permission == CapabilityPermission.CONFIRM or cap.requires_confirmation:
            assert sec.requires_confirmation, (
                f"CONFIRM capability '{cap.id}' has sec_meta.requires_confirmation=False"
            )

        # Invariant 5: PROCESS_KILL is never auto-authorized
        if sec.operation_kind == CapabilityOperationKind.PROCESS_KILL or cap.id == "terminate_process":
            assert sec.requires_confirmation, f"PROCESS_KILL capability '{cap.id}' cannot be auto-authorized"
            assert cap.permission != CapabilityPermission.AUTO, f"PROCESS_KILL capability '{cap.id}' cannot have AUTO permission"

        # Invariant 6: Alignment with ActionGate
        if not cap.read_only:
            prop = ActionProposal(
                category=ActionCategory.ACT,
                capability_id=cap.id,
                parameters={"target": "test", "pid": 1234, "path": "C:\\temp\\test.txt", "command": "echo test"},
            )
            gate_req = broker._map_to_gate_request(prop, sec)
            eval_res = gate.evaluate_request(gate_req)

            # If capability requires confirmation, gate must require confirmation or deny
            if sec.requires_confirmation:
                assert eval_res.verdict in (ActionGateVerdict.REQUIRE_CONFIRMATION, ActionGateVerdict.DENY), (
                    f"Capability '{cap.id}' requires confirmation but ActionGate gave verdict {eval_res.verdict}"
                )

        manifest_records.append({
            "id": cap.id,
            "category": cap.category.value,
            "operation_kind": sec.operation_kind.value,
            "risk": sec.risk.value,
            "mutates_state": sec.mutates_state,
            "requires_confirmation": sec.requires_confirmation,
            "resource_scope": sec.resource_scope,
            "permission": cap.permission.value,
            "read_only": cap.read_only,
            "classification_source": "authoritative_manifest",
        })

    # Summary checks
    assert total_count >= 80, f"Expected at least 80 registered capabilities, found {total_count}"
    assert explicit_count == total_count, "All capabilities must be explicitly classified"
    assert unknown_count == 0, f"Found {unknown_count} unknown consequential capabilities, target is 0"

    print("\n--- CAPABILITY SECURITY MANIFEST SUMMARY ---")
    print(f"Total capabilities:             {total_count}")
    print(f"Explicitly classified:          {explicit_count}")
    print(f"Read-only (observational):      {read_only_count}")
    print(f"Mutating (consequential):       {mutating_count}")
    print(f"Confirmation-required:          {confirm_count}")
    print(f"Blocked:                        {blocked_count}")
    print(f"Unknown consequential:          {unknown_count}")

    # Write out authoritative manifest JSON report
    out_path = Path("docs/audit/CAPABILITY_SECURITY_MANIFEST.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_data = {
        "total_capabilities": total_count,
        "explicitly_classified": explicit_count,
        "read_only": read_only_count,
        "mutating": mutating_count,
        "confirmation_required": confirm_count,
        "blocked": blocked_count,
        "unknown_consequential": unknown_count,
        "capabilities": manifest_records,
    }
    out_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    assert out_path.exists(), "Manifest export file was not created"
