"""AstraRun 1.0 Non-Self-Modifiable Trust Kernel Boundary.

Binding Principle:
AstraRun is an ADAPTIVE workstation agent. Adaptation (planning, model routing,
tool selection, recovery, generated scripts, procedural skills, retrieval,
visual strategy, browser workflows) occurs ABOVE a stable trust boundary.

The following components remain authoritative and NON-SELF-MODIFIABLE during
normal autonomous operation:
- ActionGate
- SecretBroker
- SandboxManager policy
- NetworkBroker policy
- ResourceGovernor
- Audit/Event Ledger
- Capability permission model
- Update verification
- User authorization boundaries

Astra may reason about these policies. It may NOT rewrite, hot-patch, or
bypass them autonomously. Any modification to the trust kernel requires
explicit human authorization via normal developer workflows.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

from astrarun.core.logging import get_logger

logger = get_logger("astrarun.security.trust_kernel")


# Protected component names
TRUST_KERNEL_COMPONENTS: List[str] = [
    "ActionGate",
    "SecretBroker",
    "SandboxManager",
    "NetworkBroker",
    "ResourceGovernor",
    "TaskLedger",
    "CapabilityRegistry",
    "UpdateVerifier",
    "TrustKernel",
]

# Protected source path patterns
PROTECTED_KERNEL_PATTERNS: List[str] = [
    r"astrarun/security",
    r"astrarun/sandbox",
    r"astrarun/network/broker",
    r"astrarun/tasks/ledger",
    r"astrarun/capabilities/registry",
    r"astrarun/core/hardware",
]


class TrustKernelViolationError(PermissionError):
    """Raised when an autonomous agent attempts to modify its own trust kernel."""
    pass


def is_trust_kernel_path(target_path: str | Path) -> bool:
    """Return True if path references a protected Trust Kernel source file."""
    norm = str(Path(target_path).resolve()).replace("\\", "/").lower()
    for pat in PROTECTED_KERNEL_PATTERNS:
        if pat.lower() in norm:
            return True
    return False


def validate_kernel_mutation_request(
    target: str | Path,
    is_autonomous_agent: bool = True,
    has_explicit_human_approval: bool = False,
) -> Tuple[bool, str]:
    """
    Validate whether a modification request against a target file or module is permitted.
    
    Returns:
        (is_allowed, explanation_message)
    """
    if not is_trust_kernel_path(target):
        return True, "Target is outside the Trust Kernel boundary."

    if is_autonomous_agent and not has_explicit_human_approval:
        msg = (
            f"Autonomous mutation of AstraRun Trust Kernel component '{target}' "
            "is strictly prohibited by system governance. Hot-patching security "
            "kernel requires explicit human approval via interactive ActionGate."
        )
        logger.error("SECURITY VIOLATION: %s", msg)
        return False, msg

    return True, "Human authorized developer modification of kernel component."
