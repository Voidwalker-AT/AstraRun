# AI Bridge Boundary Specification (AstraRun v0.6)

> **Status**: ARCHITECTURAL SPECIFICATION & PROTOCOL  
> **Package**: `astrarun.ai_bridge`  
> **Last Verified**: 2026-09-27  

---

## 1. Overview & Architectural Boundaries

As AstraRun evolves from an intelligent launcher toward a controlled workstation orchestration platform, it must maintain strict insulation against external model vulnerabilities, prompt injection, and unverified execution.

**AstraRun v0.6 introduces the AI Bridge boundary protocol.**

### Strict Platform Invariants
1. **Zero Direct Cloud Model API Calls Inside AstraRun**: No OpenAI, Anthropic, Google GenAI, or remote cloud REST client libraries are imported or invoked inside the AstraRun process.
2. **Zero Shell Execution Authority for External Models**: Model suggestions are never piped into PowerShell, `cmd.exe`, or arbitrary subprocesses.
3. **Reasoning Provider as External Advisor**: External reasoning engines (such as AI Bridge or local sidecars) act strictly as advisory services.
4. **Mandatory Pipeline Re-Entry**: Any workstation command proposed or suggested by an external model must enter the front of the AstraRun deterministic safety chain:
   $$\text{External Model Proposal} \longrightarrow \mathbf{EntityResolutionEngine} \longrightarrow \mathbf{ActionGate} \longrightarrow \mathbf{ConfirmationCard} \longrightarrow \mathbf{Registered Tool} \longrightarrow \mathbf{OS}$$

---

## 2. Interface Protocol (`astrarun.ai_bridge.interface`)

```python
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

@dataclass
class ReasoningRequest:
    """Request payload sent to an external reasoning provider."""
    prompt: str
    system_instruction: str = ""
    context_data: dict[str, Any] = field(default_factory=dict)
    temperature: float = 0.2
    max_tokens: int = 512
    session_id: str = ""

@dataclass
class ReasoningResult:
    """Standardized response from a reasoning provider."""
    content: str
    model_name: str
    provider: str
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    raw_response: dict[str, Any] = field(default_factory=dict)

@runtime_checkable
class ReasoningProvider(Protocol):
    """
    Protocol defining the reasoning gateway contract.
    Implemented by external AI Bridge or local mock adapters outside AstraRun.
    """
    def is_available(self) -> bool:
        """Check whether the reasoning service is online and ready."""
        ...

    def ask(self, request: ReasoningRequest) -> ReasoningResult:
        """Submit a reasoning request synchronously."""
        ...

    async def ask_async(self, request: ReasoningRequest) -> ReasoningResult:
        """Submit a reasoning request asynchronously."""
        ...
```

---

## 3. Sandboxing & Quarantine Rules

When external reasoning providers are queried:
- **Telemetry Redaction**: Requests pass through AstraRun's telemetry scrubber (`redact_sensitive_text()`) before transmission to strip API keys, Windows user paths, and sensitive tokens.
- **Quarantined Output**: Responses are treated as untrusted text. They are never evaluated as code, executed as shell strings, or granted default execution privileges.
- **Fail-Open to Deterministic Baseline**: If the reasoning provider is offline, unreachable, or returns an error, AstraRun seamlessly falls back to local deterministic and fuzzy search without disrupting launcher availability.
