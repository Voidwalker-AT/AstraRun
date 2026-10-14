# F0-25F.6 Intelligent Fallback & Recovery Architecture

> **Phase**: F0-25F.6 — Routing Generalization, Intelligent Fallback, Security & Intelligence Certification  
> **Status**: APPROVED & ACTIVE  
> **Component**: Autonomous Diagnostics, Recovery Hierarchy & Loop Prevention  

---

## 1. Objective & Non-Negotiable Contract

AstraRun does not perform blind `try/except: pass` retries. Every failure becomes structured, immutable evidence with causal provenance.

The operational lifecycle is governed by:
$$\text{UNDERSTAND} \longrightarrow \text{ROUTE} \longrightarrow \text{PLAN} \longrightarrow \text{GOVERN} \longrightarrow \text{ACT} \longrightarrow \text{OBSERVE} \longrightarrow \text{VERIFY}$$
$$\Big\downarrow \text{failure / uncertainty}$$
$$\text{DIAGNOSE} \longrightarrow \text{RECOVER / REPLAN} \longrightarrow \text{VERIFY AGAIN} \longrightarrow \text{COMPLETE OR FAIL HONESTLY}$$

---

## 2. Structured Failure & Recovery Question Schema

Every fallback decision is recorded with cryptographic provenance and must answer eight mandatory questions:

1. **What failed?** (Capability, model, observation, pre/postcondition, or verification oracle)
2. **What evidence proves it failed?** (Exact error code, return status, OS observation, or discrepancy)
3. **Is retry safe?** (Idempotency check, state mutation audit, side-effect analysis)
4. **Has world state changed?** (Desktop state delta, file existence, child process creation)
5. **Is the original goal still valid?** (Goal relevance verification against observed state)
6. **What alternative is available?** (Ranked candidate from the fallback hierarchy)
7. **Why is that alternative preferable?** (Selection rationale, safety and fidelity justification)
8. **What new verification is required?** (Postcondition oracle for the alternative action)

---

## 3. Fallback Hierarchy

### A. Reasoning & Intelligence
$$\text{Preferred Model} \longrightarrow \text{Alternate Configured Model} \longrightarrow \text{Deterministic Local Capability} \longrightarrow \text{Clarification / Fail-Closed}$$

### B. Computer Use & UI Interaction
$$\text{Semantic / UIA Interaction} \longrightarrow \text{Refreshed Observation + Semantic} \longrightarrow \text{Alternate Generic Interaction} \longrightarrow \text{Visual Grounding} \longrightarrow \text{Fail-Closed}$$
- *Invariant*: Coordinate clicking without confirmed target identity is strictly forbidden.

### C. Execution & Planning
$$\text{Known Capability} \longrightarrow \text{Composition DAG} \longrightarrow \text{Governed Dynamic Tool (if permitted)} \longrightarrow \text{External Delegation (if permitted)} \longrightarrow \text{Clarification / Fail-Closed}$$

### D. Empirical Verification
$$\text{Strong Semantic Oracle} \longrightarrow \text{Alternate Independent Observation} \longrightarrow \text{Alternate Evidence Source} \longrightarrow \text{FAIL HONESTLY}$$
- *Invariant*: Verification failure must **never** be converted into assumed success.

---

## 4. Loop Prevention & Bounded Budgets

To prevent infinite recovery cycles ($A \to B \to A \to B$ loops, repeated identical prompts, repeated failed tool calls):
1. **Fingerprint Tracking**: Each attempt computes:
   $$\text{Fingerprint} = \text{SHA256}(\text{FailureCategory} \parallel \text{TargetID} \parallel \text{ActionType} \parallel \text{ErrorDigest})$$
2. **Bounded Retry Budget**:
   - Max 2 retries per unique fingerprint.
   - Max 3 total dynamic replans per task.
3. **Escalation**:
   - When budget is exhausted or an oscillation loop ($A \to B \to A$) is detected, the engine escalates immediately to `CLEANUP_AND_FAIL` or `FAIL_CLOSED`.

---

## 5. Security Invariant Governance

Fallback mechanisms **never** become security bypass vectors:
- **BLOCK remains BLOCK**: If a tool or alternative is blocked by policy, fallback cannot execute it.
- **CONFIRM remains CONFIRM**: Confirmation gates cannot be circumvented by switching tools.
- **Scope Containment**: Fallbacks cannot expand filesystem, process, or network scope beyond authorized boundaries.
- **Zero Self-Certification**: An action cannot verify itself using its own internal return code alone when an independent oracle is required.
