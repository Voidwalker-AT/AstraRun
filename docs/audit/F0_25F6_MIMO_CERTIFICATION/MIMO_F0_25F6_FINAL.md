# MIMO F0-25F.6 — Targeted Independent Credibility Certification

**Auditor**: MiMo · **Date**: 2026-10-14 · **Subject**: F0-25F.6 foundations (routing already known FAIL)
**Binary**: `2f422df7…` dist ≡ installed · Routing source freeze 8/8 rehash MATCH · Holdout BURNED

---

Routing 453/500 (90.6%, macro-F1 0.902) **recomputed and confirmed**. Not re-litigated as a release gate.

## Findings that matter for F0-25F.7

| Area | Verdict | Evidence |
|---|---|---|
| Routing benchmark credibility | **PASS** | 500 rows, 453 correct, F1 0.902 from matrix; freeze 01:20 < manifest 01:22 < results 01:23; no post-prediction edits; SHA mismatch is documentation-only |
| Fallback reachability | **PARTIAL** | `IntelligentFallbackEngine` live in `agent/loop.py:113/842` |
| Fallback security | **PASS** | No ActionGate bypass; 20-scenario adversarial suite on production engine |
| Loop control | **PASS** | Fingerprint budgets + A-B-A oscillation → FAIL_CLOSED |
| Physical recovery | **FAIL** | Screenshots show **Antigravity only — no Notepad/window**; pixel attestation false |
| Resource restoration | **PARTIAL** | Zero-leak claim lacks PID-time/screenshot proof |
| Security manifest | **PASS** | **89/45/44/3/2/0** recomputed (report prose “22 capabilities” contradicts) |
| Tool intelligence | **PARTIAL** | JSON 39/40 vs report 38/40 |
| Intelligence benchmark | **PARTIAL** | 38/38 curated; narrow |
| Regression | **PARTIAL** | JUnit honest **999 passed / 2 failed / 14 skipped**; report **misnames the 2 failures** |
| Generic repair | **PASS** | Honest 7/8; REPAIR-02 semantic fail retained |
| Mutations | **PASS** | 12/12 genuine kills |
| Production purity | **PASS** | 0 contamination tokens in src |
| Evidence honesty | **PARTIAL** | Routing FAIL honest; physical screenshots misleading; multiple report-vs-artifact contradictions |

**Dynamic under-routing note**: precision 1.0 / recall **0.588** (33 DYNAMIC→CLARIFICATION on hard math prompts). Opposite failure mode from F0-25F.2 over-routing; remains the primary F0-25F.7 target.

**Decision rationale**: Fallback/security/loop/purity/repair/mutation foundations are credible enough to preserve. Physical-recovery visual evidence and report integrity defects are concrete and must be repaired alongside routing — they do not warrant a full stop.

**F0-25F.7 MUST ALSO REPAIR SPECIFIC FOUNDATION DEFECTS**

Artifacts: `00_FREEZE.json` … `15_ACCEPTANCE_MATRIX.json` under `docs/audit/F0_25F6_MIMO_CERTIFICATION/`.
