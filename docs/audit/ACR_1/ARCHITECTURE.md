# ACR-1 — Rebuilt Central Intelligence Spine Architecture

> **Component**: AstraRun Central Cognitive Architecture (ACR-1)  
> **Repository**: [https://github.com/Voidwalker-AT/AstraRun](https://github.com/Voidwalker-AT/AstraRun)  
> **Development Branch**: `dev/au-1`  
> **Review Authority**: Gemini 4 Argon Architecture Blueprint & MiMo Forensics  
> **Status**: VERIFIED & CERTIFIED  

---

## 1. Executive Architectural Summary

ACR-1 transitions AstraRun from a collection of fragmented, regex-heavy dispatchers and isolated workflow scripts into a unified, resident Windows OS-AI assistant capable of:
1. Multi-turn natural conversation with robust contextual continuity and pronoun resolution ("it", "that", "that example").
2. Dynamic, governed tool planning through the sole authoritative execution choke-point (`ExecutionBroker` + `ActionGate`).
3. Empirical consequence observation via compact desktop state adapters (`WorldStateSummary` and `DesktopObserver`).
4. Post-tool grounded response synthesis (reasoning from actual tool observations rather than prior hallucinations).
5. Affirmative artifact verification and session pinning (`PinnedArtifact` with verified path and process identity).

---

## 2. Ingress & Execution Pipeline Flow

```
                      [ User Input / Voice / Launcher ]
                                      │
                                      ▼
                             [ RequestEnvelope ]
                                      │
                                      ▼
                       [ AstraApplication.handle_request ]
                                      │
                                      ▼
                         [ RequestBoundaryRouter ]
                                ┌─────┴───────────────────────┐
                                │                             │
                     PRODUCT_META_COMMAND              OPERATIONAL_GOAL
                                │                             │
                        [ Meta Handler ]              [ Routing Seam ]
                                                       ┌──────┴──────────────────────┐
                                                       │                             │
                                              [ AgentCoordinator ]          [ Legacy Fallback ]
                                                       │                    (Emits LEGACY_FALLBACK_USED)
                                                       │                             │
                                                       │                    [ Inline Legacy Engine ]
                                                       │
                                      ┌────────────────┴────────────────────────┐
                                      ▼                                         ▼
                            [ DesktopObserver ]                     [ SingleStepFastTrack ]
                       (Produce WorldStateSummary)                    (Match clean single-step)
                                      │                                         │
                                      ▼                                         │
                        [ CapabilitySemanticIndex ]                             │
                        (Top-K=6 Candidate Schemas)                             │
                                      │                                         │
                                      ▼                                         │
                               [ TurnReasoner ]                                 │
                         (Local LLM Inference on 8089)                          │
                                      │                                         │
                                      └────────────────┬────────────────────────┘
                                                       │
                                                       ▼
                                                [ TurnDecision ]
                                      ┌────────────────┼────────────────────────┐
                                      │                │                        │
                                DIRECT_ANSWER      TOOL_PLAN           HYBRID_ACT_AND_ANSWER
                                      │                │                        │
                                      │                ▼                        ▼
                                      │       [ ExecutionBroker ] ◄─────────────┘
                                      │                │
                                      │                ▼
                                      │          [ ActionGate ]
                                      │                │
                                      │         [ Native Tool ]
                                      │                │
                                      │                ▼
                                      │       [ StepVerifier & Pin ]
                                      │                │
                                      │                ▼
                                      │     [ Post-Tool Synthesis ]
                                      │                │
                                      └────────────────┼────────────────────────┘
                                                       ▼
                                            [ TurnResult / Commit ]
                                                       │
                                                       ▼
                                          [ AssistantCard in UI ]
```

---

## 3. Core Subsystem Implementations

### 3.1 Session Layer (`src/astrarun/session/`)
- **`models.py`**:
  - `ConversationSession`: Chronological turns list, rolling summary, verified pinned artifacts dictionary, active flags.
  - `TurnRecord`: Strongly typed immutable record of turn execution, tool calls, tool observations, verified status, and latency.
  - `PinnedArtifact`: Tracks verified artifacts (`ArtifactKind.FILE`, `APPLICATION`, `WINDOW`, `CODE`, `TOOL_RESULT`). Enforces the affirmative verification invariant: unverified artifacts cannot be pinned or resolved across turns.
- **`events.py`**:
  - Strongly typed, OpenHands-style append-only event stream (`UserTurnEvent`, `WorldObservationEvent`, `ReasoningDecisionEvent`, `ToolCallEvent`, `ToolObservationEvent`, `VerificationEvent`, `RecoveryEvent`, `AssistantResponseEvent`, `TurnCompletedEvent`). No raw CoT or private model tokens are persisted.
- **`store.py`**:
  - `SessionStore`: Thread-safe session persistence, session isolation, and bounded context extraction (last 4 turns + rolling summary + pinned artifacts).

### 3.2 Cognition & Turn Reasoning (`src/astrarun/cognition/`)
- **`turn_models.py`**:
  - `TurnMode`: Strongly typed modes (`DIRECT_ANSWER`, `TOOL_PLAN`, `HYBRID_ACT_AND_ANSWER`, `CLARIFY`, `REFUSE`).
  - `PlanStep`: Discrete executable tool proposal with step ID, capability ID, arguments, and dependencies.
  - `TurnDecision`: Authoritative output from reasoner or fast-track.
- **`turn_reasoner.py`**:
  - Stateless turn reasoner with bounded prompt assembly (system instructions, conversation history, pinned artifacts, compact world state, Top-6 candidate schemas).
  - Resilient multi-stage parsing: direct JSON parse -> unescaped LaTeX math (`\(`, `\cdot`, `\pmod`) repair -> regex field extraction -> conversational fallback.
  - Pseudo-tool normalization: converts conversational pseudo-tools (`display_text`, `print`, `echo`) into `DIRECT_ANSWER`.
  - Physical state protection: intercepts attempts to guess real-time physical/hardware metrics (battery percentage, hardware state) and forces tool execution through `ExecutionBroker`.
  - Post-tool grounded synthesis: reasons strictly from actual workstation observations (`tool_observations`).

### 3.3 Fast Track & Adaptive Retrieval (`src/astrarun/agent/`)
- **`fast_track.py`**:
  - `SingleStepFastTrack`: High-speed deterministic path for unambiguous single-step requests (pure math, clean calculator launch, battery query, window snapping). Produces standard `TurnDecision` objects without bypassing coordinator or broker. Strictly rejects conversational references ("it", "that", "earlier", "shorter").
- **`indexer.py`**:
  - `CapabilitySemanticIndex`: Multi-factor semantic retrieval (exact ID, token overlap, domain tags, verb matching) ranking top-K=6 capabilities. Includes guards preventing dynamic tool compilation from matching conversational code requests.
- **`coordinator.py`**:
  - `AgentCoordinator`: Central execution spine state machine orchestrating the complete turn lifecycle (INGESTED -> OBSERVED -> FAST_TRACK_OR_REASON -> DECIDED -> EXECUTING -> VERIFYING -> SYNTHESIZING -> COMPLETING -> COMMITTED).

### 3.4 Governance & Execution Authority (`src/astrarun/security/`)
- **`execution_broker.py` & `action_gate.py`**:
  - The model is **never** the execution authority.
  - All operations pass through `ExecutionBroker.execute()`.
  - Unregistered capabilities are BLOCKED fail-closed.
  - High-risk operations pause for explicit user confirmation tokens (`PAUSED_CONFIRMATION`).

### 3.5 Desktop State Adapter (`src/astrarun/computer_use/world/`)
- **`summary.py`**:
  - `WorldStateSummary` & `WorldStateAdapter`: Compact snapshot of active foreground window title, PID, process name, total visible windows, active modal dialogs, and task resources without prompt token bloating.

### 3.6 Interactive Presentation Layer (`src/astrarun/ui/`)
- **`launcher.py` & `cards.py`**:
  - `LauncherWindow` preserves `self.session_id` across turns, enabling multi-turn conversation.
  - `AssistantCard` displays conversational answers and verified tool consequence badges (`Action Verified`).

---

## 4. Verification & Testing Evidence

1. **Architecture Test Suite**: 23 passed / 0 failed in `tests/architecture/`.
2. **Whole-Repository Test Suite**: 1,067 passed / 0 failed / 14 skipped in `tests/`.
3. **Physical Interactive Demos**: 6-turn Cryptography multi-turn sequence and Hybrid Calculator demo executed with real screenshots captured in `docs/audit/ACR_1/screenshots/`.
4. **Process Leak Cleanliness**: Zero lingering PIDs verified post-test.
