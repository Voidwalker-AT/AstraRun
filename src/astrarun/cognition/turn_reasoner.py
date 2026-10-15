"""Stateless TurnReasoner for AstraRun 1.0 intelligent spine.

Responsible for:
- Bounded prompt assembly (system role, recent turns, pinned artifacts, compact world state, Top-K schemas)
- Local model invocation via ModelService / ModelClient
- Strict TurnDecision parsing and fail-safe recovery
- Post-tool synthesis grounded in actual tool observations
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from astrarun.cognition.client import ModelClient
from astrarun.cognition.models import InferenceRequest, ModelRole
from astrarun.cognition.service import ModelService
from astrarun.cognition.turn_models import PlanStep, TurnDecision, TurnMode
from astrarun.core.logging import get_logger

if TYPE_CHECKING:
    from astrarun.capabilities.schema import CapabilitySchema
    from astrarun.computer_use.world.summary import WorldStateSummary
    from astrarun.session.models import ConversationSession, PinnedArtifact

logger = get_logger("astrarun.cognition.turn_reasoner")

SYSTEM_PROMPT = """You are Astra, a local-first workstation AI and intelligent OS assistant.
You converse naturally, preserve context across multi-turn dialogs, resolve conversational references ('it', 'that', 'that example') to previously verified artifacts or discussion topics, and choose the appropriate action mode.

MODES:
- DIRECT_ANSWER: For questions, explanations, math, code examples/snippets, summaries, or pure conversation. Provide your response in "assistant_reply".
  CRITICAL: If the user asks for code, explanations, analogies, or answers (e.g. 'explain <concept>', 'give me an example', 'show me code', 'why does that work?'), you MUST use DIRECT_ANSWER with the full text or code in "assistant_reply". Do NOT use tools or execute code for conversational requests!
- TOOL_PLAN: ONLY when the user explicitly requests an operational action on the workstation (e.g. creating/saving a file, launching/opening an application or file, snapping a window, checking battery status).
  CRITICAL: You MUST select capability_id ONLY from the Candidate Capabilities list provided below. NEVER invent, hallucinate, or use IDs not present in Candidate Capabilities (such as 'display_text', 'print', or arbitrary tools). If no suitable capability is listed under Candidate Capabilities, you MUST use DIRECT_ANSWER.
- HYBRID_ACT_AND_ANSWER: When the user explicitly requests both an operational workstation action AND a conversational explanation (e.g., 'Open calculator and explain why 0.1 + 0.2 is weird').
- CLARIFY: When the request is genuinely ambiguous and cannot be safely resolved.
- REFUSE: When the request is harmful or strictly prohibited.

RULES:
1. Grounded Context: When the user asks for an example, code, explanation, or analogy (e.g. 'Give me an example', 'Show me code'), your response MUST be directly about the active topic of the ongoing conversation in the Conversation History. NEVER switch to unrelated topics or output generic placeholders.
2. When the user asks a question, requests an explanation, asks 'why does that work?', asks for a code snippet/example, or asks to make something shorter or summarize, use DIRECT_ANSWER. Put the complete explanation, analogy, or code in "assistant_reply".
3. When the user references prior discussion (e.g. 'put that example in a text file', 'make it shorter', 'why does that work?'), resolve 'that' or 'it' strictly against the Active Topic and Conversation History.
4. For TOOL_PLAN, select capabilities ONLY from the Candidate Capabilities provided below. Map arguments accurately.
5. For file creation ('write_file', 'save_text_file'), provide 'path' and 'content' with the actual resolved text from conversation.
6. Output strictly a single valid JSON object matching the TurnDecision schema. No markdown formatting around the JSON outside ```json fences."""


class TurnReasoner:
    """
    Stateless cognitive reasoner for turn-level decision making and post-tool synthesis.
    
    Invariant: TurnReasoner proposes decisions. It NEVER executes tools, authorizes capabilities,
    mutates the filesystem, or bypasses ExecutionBroker.
    """

    def __init__(
        self,
        model_service: Optional[ModelService] = None,
        model_client: Optional[ModelClient] = None,
        endpoint: Optional[str] = None,
    ) -> None:
        self.model_service = model_service or ModelService.get_instance()
        self.client = model_client or ModelClient()
        self.endpoint = endpoint or self.model_service.deep_endpoint
        self.model_role = ModelRole.TURN_REASONER

    def reason_turn(
        self,
        query: str,
        session: Optional[ConversationSession] = None,
        world_state: Optional[WorldStateSummary] = None,
        candidate_schemas: Optional[List[CapabilitySchema]] = None,
        memory_context: Optional[Any] = None,
    ) -> TurnDecision:
        """
        Produce a strongly typed TurnDecision for the current user query.
        """
        # Ensure model backend is ready
        try:
            self.model_service.ensure_backend(self.model_role)
        except Exception as exc:
            logger.debug("Model backend ensure check: %s", exc)

        messages = self._build_prompt_messages(
            query=query,
            session=session,
            world_state=world_state,
            candidate_schemas=candidate_schemas or [],
            memory_context=memory_context,
        )

        inference_req = InferenceRequest(
            role=self.model_role,
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
        )

        obs = self.client.complete_sync(inference_req, self.endpoint)
        if obs.status == "SUCCESS" and obs.raw_output:
            decision = self._parse_turn_decision(obs.raw_output, query, candidate_schemas)
            decision.metadata["latency_ms"] = obs.latency_ms
            decision.metadata["prompt_tokens"] = obs.prompt_tokens
            decision.metadata["completion_tokens"] = obs.completion_tokens
            # Deterministic mathematical verification of claims
            if decision.assistant_reply:
                from astrarun.cognition.math_verifier import MathClaimVerifier
                repaired, math_audits = MathClaimVerifier.verify_and_repair(decision.assistant_reply)
                if math_audits:
                    decision.assistant_reply = repaired
                    decision.metadata["math_claim_audits"] = [a.__dict__ for a in math_audits]
            return decision

        logger.warning("Inference did not succeed (%s: %s). Falling back.", obs.status, obs.failure_reason)
        return self._safe_fallback_decision(query, obs.raw_output or obs.failure_reason or "Inference unavailable")

    def synthesize_post_tool(
        self,
        query: str,
        decision: TurnDecision,
        tool_observations: List[Dict[str, Any]],
        session: Optional[ConversationSession] = None,
    ) -> str:
        """
        Synthesize a natural, data-grounded assistant response after governed tool execution.
        Fulfills Section 24: Model must reason from actual tool observations, not prior expectations.
        """
        obs_text = json.dumps(tool_observations, indent=2)
        prompt = (
            f"User Request: {query}\n"
            f"Action Taken: {decision.goal_summary or decision.mode.value}\n"
            f"Actual Tool Observations from Workstation:\n{obs_text}\n\n"
            "Provide a concise, direct, and factual response to the user grounded strictly in these tool observations."
        )

        messages = [
            {"role": "system", "content": "You are Astra, a helpful workstation assistant. Answer the user based strictly on the factual tool observations."},
            {"role": "user", "content": prompt},
        ]

        inference_req = InferenceRequest(
            role=self.model_role,
            messages=messages,
            temperature=0.2,
            max_tokens=512,
        )

        obs = self.client.complete_sync(inference_req, self.endpoint)
        if obs.status == "SUCCESS" and obs.raw_output:
            cleaned = obs.raw_output.strip()
            # Strip markdown quotes if model added them
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            return cleaned

        # Fallback summary if synthesis model call failed
        summaries = [o.get("output_summary") or str(o) for o in tool_observations]
        return f"Completed action. Result: {'; '.join(summaries)}"

    def _build_prompt_messages(
        self,
        query: str,
        session: Optional[ConversationSession],
        world_state: Optional[WorldStateSummary],
        candidate_schemas: List[CapabilitySchema],
        memory_context: Optional[Any],
    ) -> List[Dict[str, str]]:
        """Construct the prompt messages for the turn reasoner."""
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

        context_sections: List[str] = []

        # 1. Recent turns & rolling summary from session
        if session:
            if session.active_topic:
                context_sections.append(f"### Active Discussion Topic:\n{session.active_topic}")

            if session.rolling_summary:
                context_sections.append(f"### Previous Conversation Summary:\n{session.rolling_summary}")

            recent_turns = session.get_recent_turns(4)
            if recent_turns:
                turns_repr = []
                for idx, t in enumerate(recent_turns, 1):
                    turn_topic_str = f" (Topic: {t.topic})" if t.topic else ""
                    turns_repr.append(f"Turn {idx} [User]: {t.user_text}")
                    turns_repr.append(f"Turn {idx} [Astra]{turn_topic_str}: {t.assistant_text}")
                    if t.conversational_artifacts:
                        for art in t.conversational_artifacts:
                            preview = (art.content[:90] + "...") if art.content and len(art.content) > 90 else (art.content or "")
                            turns_repr.append(f"Turn {idx} [Artifact: {art.kind.value} '{art.display_name}'] (topic: {art.topic}): {preview}")
                    if t.artifacts:
                        art_descs = [f"{a.kind.value}: {a.display_name} (path: {a.path})" for a in t.artifacts]
                        turns_repr.append(f"Turn {idx} [Workstation Artifacts]: {', '.join(art_descs)}")
                context_sections.append("### Conversation History:\n" + "\n".join(turns_repr))

            # 2. Pinned artifacts
            if session.pinned_artifacts:
                art_lines = []
                for k, a in session.pinned_artifacts.items():
                    art_lines.append(f"- '{k}': {a.kind.value} '{a.display_name}' (verified={a.verified}, path={a.path}, pid={a.pid})")
                context_sections.append("### Verified Pinned Artifacts:\n" + "\n".join(art_lines))

            # 2B. Contextual Grounding Directive for follow-up turns
            if session.active_topic:
                q_lower = query.lower()
                if any(w in q_lower for w in ("shorter", "summarize", "example", "why", "work", "it", "that", "put that", "more")):
                    context_sections.append(
                        f"### Contextual Grounding Directive:\n"
                        f"The user query is a continuation referring directly to the Active Discussion Topic: '{session.active_topic}'.\n"
                        f"Your response MUST remain strictly on the active topic '{session.active_topic}'. Do NOT switch to unrelated topics."
                    )

        # 3. Compact world state
        if world_state and (world_state.foreground_app or world_state.visible_windows):
            context_sections.append(f"### Desktop World State:\n{world_state.to_prompt_str()}")

        # 4. Top-K Candidate capabilities
        if candidate_schemas:
            caps_repr = []
            for s in candidate_schemas:
                params = {p.name: f"{p.type_name} ({p.description})" for p in s.parameters}
                caps_repr.append(f"- ID: {s.id}\n  Description: {s.description}\n  Parameters: {json.dumps(params)}")
            context_sections.append("### Candidate Capabilities (Top-K available for TOOL_PLAN):\n" + "\n".join(caps_repr))
        else:
            context_sections.append("### Candidate Capabilities:\nNone available. No workstation tools match this request. You MUST choose mode: DIRECT_ANSWER.")

        # 5. Schema and template guidance (Neutral format templates without domain-specific few-shot priming)
        context_sections.append(
"""### Output Format Examples:

Example 1: Question, explanation, or code snippet (DIRECT_ANSWER):
{
  "mode": "DIRECT_ANSWER",
  "assistant_reply": "<Complete direct explanation, answer, or code addressing the user's specific request and active topic>",
  "goal_summary": "<Goal summary>",
  "plan_steps": [],
  "referenced_artifacts": [],
  "confidence": 1.0
}

Example 2: Operational workstation action (TOOL_PLAN):
{
  "mode": "TOOL_PLAN",
  "assistant_reply": "<Brief confirmation of the workstation action>",
  "goal_summary": "<Goal summary>",
  "plan_steps": [
    {
      "step_id": "step-1",
      "capability_id": "<EXACT ID FROM CANDIDATE CAPABILITIES>",
      "arguments": { "<param_name>": "<param_value>" },
      "depends_on": []
    }
  ],
  "referenced_artifacts": [],
  "confidence": 1.0
}

CRITICAL: In 'assistant_reply', provide your complete, detailed response to the user with the actual explanation, math, code, or answer (do not truncate or write placeholder ellipses). Respond ONLY with a single JSON object."""
        )

        # Combine context into the user turn or prompt
        full_user_content = ""
        if context_sections:
            full_user_content = "\n\n".join(context_sections) + f"\n\n### Current User Input:\n{query}"
        else:
            full_user_content = f"### Current User Input:\n{query}"

        messages.append({"role": "user", "content": full_user_content})
        return messages

    def _parse_turn_decision(
        self,
        raw_output: str,
        original_query: str,
        candidate_schemas: Optional[List[CapabilitySchema]] = None,
    ) -> TurnDecision:
        """Parse, validate, and sanitize the model's raw output into a TurnDecision."""
        cleaned = raw_output.strip()

        # Extract JSON block from markdown fences if present
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        # Extract first outermost brace block
        brace_match = re.search(r"(\{[\s\S]*\})", cleaned)
        if brace_match:
            cleaned = brace_match.group(1).strip()

        parsed_decision: Optional[TurnDecision] = None
        # First attempt: direct json.loads with strict=False
        try:
            parsed = json.loads(cleaned, strict=False)
            if isinstance(parsed, dict):
                if "properties" in parsed and isinstance(parsed["properties"], dict):
                    parsed = parsed["properties"]
                if "mode" in parsed:
                    parsed_decision = TurnDecision.from_dict(parsed)
        except Exception:
            # Second attempt: repair unescaped LaTeX/path backslashes
            try:
                repaired = re.sub(r'\\(?![/"\\bfnrtu])', r'\\\\', cleaned)
                parsed = json.loads(repaired, strict=False)
                if isinstance(parsed, dict):
                    if "properties" in parsed and isinstance(parsed["properties"], dict):
                        parsed = parsed["properties"]
                    if "mode" in parsed:
                        parsed_decision = TurnDecision.from_dict(parsed)
            except Exception as exc:
                logger.debug("JSON parse failure on reasoner output: %s", exc)

        # Third attempt: regex extraction of key fields if JSON syntax is truncated/malformed
        if parsed_decision is None:
            reply_match = re.search(r'"assistant_reply"\s*:\s*"((?:\\.|[^"\\])*)"', cleaned)
            if reply_match:
                mode_match = re.search(r'"mode"\s*:\s*"([A-Z_]+)"', cleaned)
                mode_str = mode_match.group(1) if mode_match else TurnMode.DIRECT_ANSWER.value
                try:
                    mode = TurnMode(mode_str)
                except Exception:
                    mode = TurnMode.DIRECT_ANSWER
                try:
                    rep_text = reply_match.group(1).encode().decode("unicode_escape", errors="replace")
                except Exception:
                    rep_text = reply_match.group(1)
                parsed_decision = TurnDecision(
                    mode=mode,
                    assistant_reply=rep_text,
                    goal_summary="Extracted conversational answer",
                    confidence=0.85,
                    model_role=self.model_role.value,
                )

        if parsed_decision is None:
            # If model generated a direct conversational response without JSON wrapping
            if not any(token in raw_output.lower() for token in ["\"plan_steps\"", "\"mode\"", "tool_plan"]):
                return TurnDecision(
                    mode=TurnMode.DIRECT_ANSWER,
                    assistant_reply=raw_output.strip(),
                    goal_summary="Direct conversational answer",
                    confidence=0.85,
                    model_role=self.model_role.value,
                    metadata={"parsed_from_raw_text": True},
                )
            return self._safe_fallback_decision(original_query, raw_output)

        decision = parsed_decision

        PSEUDO_CONVERSATIONAL_CAPABILITIES = {
            "display_text", "show_text", "print", "echo", "say", "speak", "reply", "message", "text_response", "answer", "explain"
        }

        # Normalize DIRECT_ANSWER
        if decision.mode == TurnMode.DIRECT_ANSWER:
            decision.plan_steps = []
        elif decision.mode in (TurnMode.TOOL_PLAN, TurnMode.HYBRID_ACT_AND_ANSWER):
            # Check for pseudo-conversational capabilities
            if decision.plan_steps and all(s.capability_id.lower() in PSEUDO_CONVERSATIONAL_CAPABILITIES for s in decision.plan_steps):
                if not decision.assistant_reply:
                    first_args = decision.plan_steps[0].arguments
                    decision.assistant_reply = str(first_args.get("text") or first_args.get("message") or first_args.get("content") or decision.goal_summary or "Answer provided.")
                decision.mode = TurnMode.DIRECT_ANSWER
                decision.plan_steps = []
            elif not decision.plan_steps and decision.mode == TurnMode.TOOL_PLAN:
                decision.mode = TurnMode.DIRECT_ANSWER

            # If empty candidate schemas were explicitly provided and proposed tools are unregistered
            if candidate_schemas is not None and len(candidate_schemas) == 0 and decision.plan_steps:
                from astrarun.capabilities.manifest import AUTHORITATIVE_CAPABILITY_MANIFEST
                if not any(s.capability_id in AUTHORITATIVE_CAPABILITY_MANIFEST for s in decision.plan_steps):
                    # Recover any code, text, or script embedded in the hallucinated tool arguments
                    for s in decision.plan_steps:
                        code_val = s.arguments.get("code") or s.arguments.get("text") or s.arguments.get("script") or s.arguments.get("content")
                        if code_val and str(code_val) not in (decision.assistant_reply or ""):
                            decision.assistant_reply = f"{decision.assistant_reply or ''}\n\n```python\n{code_val}\n```".strip()
                    decision.mode = TurnMode.DIRECT_ANSWER
                    decision.plan_steps = []

            # If candidate schemas were provided, ensure step capability_id is valid
            if candidate_schemas and decision.plan_steps:
                cand_ids = {s.id for s in candidate_schemas}
                query_lower = original_query.lower()
                for step in decision.plan_steps:
                    if step.capability_id not in cand_ids:
                        # Check if a candidate capability cleanly matches the query
                        matched = False
                        for cand in candidate_schemas:
                            if cand.id in query_lower or any(word in query_lower for word in cand.id.split("_")):
                                step.capability_id = cand.id
                                matched = True
                                break
                        # If only one candidate was available, align to it
                        if not matched and len(candidate_schemas) == 1:
                            step.capability_id = candidate_schemas[0].id

        # Guard against hallucinating physical/hardware state without tool execution
        if decision.mode == TurnMode.DIRECT_ANSWER and candidate_schemas:
            query_lower = original_query.lower()
            if any(b in query_lower for b in ("battery", "plug in", "charge level", "power status")):
                for cand in candidate_schemas:
                    if cand.id in ("battery_status", "generate_battery_report"):
                        decision.mode = TurnMode.TOOL_PLAN
                        decision.goal_summary = "Inspect battery status"
                        decision.plan_steps = [PlanStep(step_id="step-1", capability_id=cand.id)]
                        break

        return decision

    def _safe_fallback_decision(self, query: str, raw_output: str) -> TurnDecision:
        """Safe fail-closed or conversational fallback when model output is unparseable."""
        cleaned = raw_output.strip()
        # If raw_output contains an assistant_reply field, extract it
        ar_match = re.search(r'"assistant_reply"\s*:\s*"((?:\\.|[^"\\])*)"', cleaned)
        if ar_match:
            try:
                cleaned = ar_match.group(1).encode().decode("unicode_escape", errors="replace")
            except Exception:
                cleaned = ar_match.group(1)
        elif "```" in cleaned:
            # Strip code block fences if present
            cleaned = re.sub(r"```(?:json)?\s*([\s\S]*?)\s*```", r"\1", cleaned).strip()

        return TurnDecision(
            mode=TurnMode.DIRECT_ANSWER,
            assistant_reply=cleaned if len(cleaned) < 2000 else cleaned[:2000],
            goal_summary="Fallback conversational answer",
            confidence=0.5,
            model_role=self.model_role.value,
            metadata={"fallback": True, "raw_output": raw_output[:200]},
        )
