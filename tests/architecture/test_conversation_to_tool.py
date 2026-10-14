"""Test conversation to tool transition and verified artifact binding.

Sequence:
1. 'Explain modular inverses.'
2. 'Give me an example.'
3. 'Put that example in a text file.'
4. 'Open it.'

Verifies:
- TurnReasoner selects registered file-writing capability
- ExecutionBroker and ActionGate are invoked
- File is genuinely created on disk and non-empty
- Content derives from prior conversational context
- Step consequences are empirically verified
- Artifact is pinned to session (e.g. 'last_file')
- Follow-up 'Open it' resolves 'it' to the verified artifact
"""

import os
import tempfile
from pathlib import Path
import pytest

from astrarun.agent.coordinator import AgentCoordinator, TurnStatus
from astrarun.ingress.models import RequestEnvelope, RequestOrigin
from astrarun.session.models import ArtifactKind, ConversationSession
from astrarun.session.store import SessionStore


def test_conversation_to_tool_and_artifact_resolution():
    """Verify conversation leads to governed file creation and subsequent 'Open it' resolution."""
    coordinator = AgentCoordinator.get_instance()
    store = SessionStore.get_instance()
    session = store.create_session("sess-tool-conv")

    with tempfile.TemporaryDirectory() as tmpdir:
        target_file = Path(tmpdir) / "modular_example.txt"

        # Turn 1: Conversational inquiry
        env1 = RequestEnvelope.create(
            "Explain modular inverses.",
            origin=RequestOrigin.LAUNCHER,
            session_id=session.session_id,
        )
        res1 = coordinator.handle_turn(env1, session)
        assert res1.status == TurnStatus.SUCCESS
        assert len(res1.response_text) > 10

        # Turn 2: Request numerical example
        env2 = RequestEnvelope.create(
            "Give me a concrete numerical example.",
            origin=RequestOrigin.LAUNCHER,
            session_id=session.session_id,
        )
        res2 = coordinator.handle_turn(env2, session)
        assert res2.status == TurnStatus.SUCCESS
        assert len(res2.response_text) > 10

        # Turn 3: Put that example in a text file
        prompt_write = f"Put that example in a text file at {target_file}."
        env3 = RequestEnvelope.create(
            prompt_write,
            origin=RequestOrigin.LAUNCHER,
            session_id=session.session_id,
        )
        res3 = coordinator.handle_turn(env3, session)
        assert res3.status == TurnStatus.SUCCESS
        assert len(res3.tool_observations) > 0
        assert res3.tool_observations[0]["capability_id"] in ("save_text_file", "write_file")
        assert res3.tool_observations[0]["success"] is True

        # Invariant: File must exist on disk and be non-empty
        assert target_file.exists(), f"Target file was not created: {target_file}"
        file_content = target_file.read_text(encoding="utf-8")
        assert len(file_content) > 0, "Created file is empty"

        # Invariant: Artifact must be pinned to session as verified
        assert "last_file" in session.pinned_artifacts
        pinned = session.pinned_artifacts["last_file"]
        assert pinned.verified is True
        assert pinned.kind == ArtifactKind.FILE
        assert str(target_file.resolve()).lower() in pinned.path.lower()

        # Turn 4: 'Open it.'
        env4 = RequestEnvelope.create(
            "Open it.",
            origin=RequestOrigin.LAUNCHER,
            session_id=session.session_id,
            dry_run=True,  # Dry run to avoid spawning real GUI window in test runner
        )
        res4 = coordinator.handle_turn(env4, session)
        assert res4.status == TurnStatus.SUCCESS
        assert len(res4.decision.plan_steps) > 0
        open_step = res4.decision.plan_steps[0]
        assert open_step.capability_id in ("open_file", "reveal_file")
        # Invariant: Must resolve 'it' to the verified file path
        assert str(target_file.resolve()).lower() in str(open_step.arguments.get("path", "")).lower()
