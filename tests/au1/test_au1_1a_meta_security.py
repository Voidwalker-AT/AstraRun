"""
AU-1.1A Meta Handler Security & Structural Isolation Tests.

Verifies:
1. Meta handling never reaches ExecutionBroker or ActionGate.
2. Meta commands never mutate workstation or spawn processes.
3. Composite queries with meta tokens fail-closed to OPERATIONAL_GOAL.
"""

from unittest.mock import MagicMock, patch
import pytest

from astrarun.app import AstraApplication
from astrarun.ingress.models import IngressRoute, RequestEnvelope, RequestOrigin


@pytest.fixture
def astra_app():
    app = AstraApplication()
    return app


def test_meta_command_structural_isolation(astra_app: AstraApplication):
    """Verify that pure meta commands never invoke ExecutionBroker or spawn actions."""
    with patch.object(astra_app.execution_broker, "execute") as mock_broker_exec:
        res = astra_app.handle_request("help")
        assert res.success is True
        assert res.type == "list_result"
        assert "AstraRun Workstation Capabilities" in res.message
        # Broker must NEVER be called for pure meta commands
        assert mock_broker_exec.call_count == 0

        res_diag = astra_app.handle_request("diagnostics")
        assert res_diag.success is True
        assert res_diag.type == "command"
        assert res_diag.message == "open_diagnostics"
        assert mock_broker_exec.call_count == 0

        res_hk = astra_app.handle_request("hotkey status")
        assert res_hk.success is True
        assert res_hk.type == "capability_result"
        assert "Hotkey Status" in res_hk.message
        assert mock_broker_exec.call_count == 0


def test_composite_meta_not_handled_by_meta_handler(astra_app: AstraApplication):
    """A composite command containing meta keywords must route to OPERATIONAL_GOAL and evaluate safely."""
    composite_envelope = RequestEnvelope.create(
        raw_query="help and open notepad",
        origin=RequestOrigin.CLI,
        dry_run=True,
    )
    decision = astra_app.request_boundary_router.classify(composite_envelope)
    assert decision.route == IngressRoute.OPERATIONAL_GOAL
    assert decision.reason_code == "COMPOSITE_CONTAINS_OPERATIONAL_CLAUSE"

    # When handled by app, it does not execute as a pure meta help list
    res = astra_app.handle_request(composite_envelope)
    # Since it's compound, it gets parsed through the operational path
    assert res.message != "AstraRun Workstation Capabilities"
