"""Section 3: ExecutionBroker Coverage, Dry-Run, and Revision Binding Tests for AstraRun C2.2.

Verifies:
- Dry-run simulation produces SIMULATED verdict with zero side effects.
- Confirmation token revalidation cryptographically binds task_id and plan_revision (N cannot authorize N+1).
- Runtime broker instrumentation detects whether dispatch is within active broker scope.
"""

from astrarun.security.action_gate import ActionGate, ConfirmationToken
from astrarun.security.execution_broker import (
    ActionCategory,
    ActionProposal,
    ExecutionBroker,
    is_broker_dispatch_active,
)
from astrarun.security.models import (
    ActionGateVerdict,
    ActionRequest,
    CapabilityOperationKind,
    CapabilitySecurityMetadata,
    Operation,
    RiskLevel,
)


def test_dry_run_simulation_zero_side_effects():
    broker = ExecutionBroker()
    proposal = ActionProposal(
        category=ActionCategory.ACT,
        capability_id="save_text_file",
        parameters={"path": r"C:\fake\test.txt", "text": "simulated content"},
        dry_run=True,
        task_id="task_sim_01",
        plan_revision=1,
    )

    result = broker.execute(proposal)
    assert result.success
    assert result.verdict == "ALLOW"
    assert result.execution_state == "SIMULATED"
    assert result.data.get("simulated") is True
    assert "SIMULATED" in result.message


def test_confirmation_revision_binding_step_n_plus_1():
    gate = ActionGate.get_instance()
    
    # 1. Create a confirmation token bound to plan_revision=1
    token_str = "tok_rev_test_12345"
    token_obj = ConfirmationToken(
        token=token_str,
        tool="save_text_file",
        arguments={"path": "report.txt", "text": "revision 1 data"},
        entity_id="report.txt",
        task_id="task_binding_01",
        plan_revision=1,
    )
    gate._active_tokens[token_str] = token_obj

    # 2. Revalidation with matching revision=1 must succeed
    valid, msg = gate.revalidate_confirmation(
        token_str=token_str,
        tool_name="save_text_file",
        arguments={"path": "report.txt", "text": "revision 1 data"},
        task_id="task_binding_01",
        plan_revision=1,
    )
    assert valid, f"Expected valid token: {msg}"

    # Re-insert token for next test (it is not popped on success unless executed)
    gate._active_tokens[token_str] = token_obj

    # 3. Revalidation with altered revision=2 (step N+1) must be REJECTED!
    valid_rev2, msg_rev2 = gate.revalidate_confirmation(
        token_str=token_str,
        tool_name="save_text_file",
        arguments={"path": "report.txt", "text": "revision 1 data"},
        task_id="task_binding_01",
        plan_revision=2,
    )
    assert not valid_rev2
    assert "plan_revision mismatch" in msg_rev2

    # Clean up
    gate._active_tokens.pop(token_str, None)


def test_broker_runtime_dispatch_scope():
    assert not is_broker_dispatch_active(), "Should not be active outside broker dispatch"

    broker = ExecutionBroker()
    dispatched_in_scope = False

    def dummy_handler(**kwargs):
        nonlocal dispatched_in_scope
        dispatched_in_scope = is_broker_dispatch_active()
        return {"ok": True}

    proposal = ActionProposal(
        category=ActionCategory.ACT,
        capability_id="open_folder",
        parameters={"folder_path": "."},
        task_id="task_scope_01",
    )

    res = broker.execute(proposal, executor_override=dummy_handler)
    assert res.success
    assert dispatched_in_scope, "Handler must execute inside active BrokerDispatchScope"
    assert not is_broker_dispatch_active(), "Scope must exit cleanly after dispatch"
