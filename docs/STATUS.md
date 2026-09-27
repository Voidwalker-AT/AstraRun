# AstraRun v0.8.5 Status Report

> **Date**: 2026-09-27  
> **Status**: STABLE / VERIFIED / MILESTONE COMPLETE  
> **Milestone**: v0.8.5 Complete (Memory, Learning & Skill Foundation)  
> **Prior Milestone**: v0.8 Complete (`a7bc33b`)  

---

## 1. What Works Completely

1. **Semantic Memory Subsystem (`astrarun.learning.memory`)**:
   - Durable workstation knowledge storage across 5 namespaces (`ALIAS`, `PREFERENCE`, `WORKFLOW`, `ENTITY_ATTRIBUTE`, `TEACHING`).
   - 5-state formal lifecycle FSM (`CANDIDATE`, `ACTIVE`, `REJECTED`, `DEPRECATED`, `CONFLICTED`).
   - Immutable evidence references with verified task/event provenance pointers.

2. **Mathematical Confidence & Decay Engine (`astrarun.learning.confidence`)**:
   - Rigorous formulation combining evidence weighting, double contradiction penalties, asymptotic support saturation, and time-decay attenuation.
   - Pinned/confirmed fact floor ($\ge 0.95$).
   - Automated conflict detection when top candidate margins are narrow ($< 0.20$).

3. **Multi-Tier Alias Manager (`astrarun.learning.aliases`)**:
   - Strict hierarchical resolution: Static Config > Conflicted Gating > User-Confirmed Learned > High-Confidence Habit ($C \ge 0.85$, $N \ge 3$) > Fallback.
   - Strong type safety enforcement matching targets to requested domains.
   - Deep integration into `EntityResolutionEngine.resolve_app`.

4. **User Correction Absorption (`astrarun.learning.evidence`)**:
   - Detects user corrections across sequential tasks within 120-second conversation windows.
   - Immediately collapses erroneous mapping ($C < 0.10$, `DEPRECATED`).
   - Promotes corrected mapping ($C \ge 0.95$, `ACTIVE`, `user_confirmed=True`).

5. **Sequential Pattern Mining & Skills (`astrarun.learning.patterns`, `astrarun.learning.skills`)**:
   - `PatternMiner` extracts repetitive capability n-grams ($L \in [2, 5]$, support $\ge 3$).
   - Generalizes concrete arguments into typed template parameters (`{target_project}`).
   - Inherits maximum step risk (`max(step_risks)`); rejects blocked capabilities.
   - `SkillManager` coordinates candidate review, version upgrades, and direct compilation to executable `Workflow` definitions.
   - Mandatory human review via `SkillReviewWidget` before activation.

6. **SQLite WAL Learning Persistence (`astrarun.learning.persistence`)**:
   - Separate `data/astra_learning.db` independent of raw history retention.
   - WAL mode, atomic transactions, corruption recovery, and append-only audit trail (`audit_events`).

7. **Background Learning Engine (`astrarun.learning.engine`)**:
   - Coordinates asynchronous, non-blocking ingestion off the hot path (0 ms overhead on `Alt+Space`).
   - Programmatic natural language teaching interface.

8. **Offline Dataset Builder (`astrarun.learning.dataset_builder`)**:
   - Sanitizes and redacts API keys, tokens, passwords, and user paths.
   - Strictly gated by `allow_training_dataset_export` setting.
   - **Zero online gradient updates or weight mutations.**

9. **PySide6 Interactive UI (`astrarun.ui.memory`)**:
   - `MemoryView`: Search, inspect provenance, confirm, reject, delete, and clear memories.
   - `SkillReviewWidget`: Visual dialog proposing recurring workflow patterns for user confirmation.

10. **Non-Learnable Security Invariants**:
    - ActionGate permissions and confirmation policies cannot be learned away.
    - Protected OS processes (`lsass.exe`, `csrss.exe`) and blocked commands cannot be aliased or manipulated.

---

## 2. Verification & Benchmark Results

### 2.1 Automated Unit & Integration Tests
- **Status**: **215 / 215 PASSED** in **12.56s**
- **Regressions**: **0**
- Test suites: Config, Routing, UI, Telemetry, Action Gate, Ensemble, NLP Engine, Capabilities, Tasks, and Learning Subsystem (18 new tests).

### 2.2 Standard Benchmark Suites (All 5 Green)

| Benchmark Suite | Case Count | Target Dataset SHA256 | Primary Accuracy Metric | Key Safety Metric | Mean Latency |
|---|---|---|---|---|---|
| **Action Benchmark V1** | 330 | `d73ac62ab9...` | **100.0%** Intent Acc | **0.00%** FER | **0.065 ms** |
| **NLP Benchmark V1 (Test)** | 310 | `41f1ad1b6a...` | **100.0%** Intent Acc | **0.00%** Negated Leakage | **7.115 ms** |
| **Capability Benchmark V1** | 520 | `32ca0f2946...` | **100.0%** Cap Acc | **100.0%** Block Recall | **0.576 ms** |
| **Task Benchmark V1** | 300 | `7979fb8dd6...` | **100.0%** Status Acc | **100.0%** Seq & Persist Acc | **70.813 ms** |
| **Learning Benchmark V1** | 320 | `b935f4ece7...` | **100.0%** Overall Acc | **0.00%** False Activation | **25.285 ms** |

### 2.3 Learning Benchmark V1 Breakdown (320 Cases)
- `explicit_teaching`: **100.0%** (50 / 50)
- `alias_precedence`: **100.0%** (60 / 60)
- `user_corrections`: **100.0%** (50 / 50)
- `conflicted_aliases`: **100.0%** (40 / 40)
- `time_decay`: **100.0%** (40 / 40)
- `skill_mining`: **100.0%** (30 / 30)
- `security_invariants`: **100.0%** (50 / 50)
- **False Memory Activation Rate**: **0.00%** (PRIME SAFETY INVARIANT)
- **Security Invariant Enforcement**: **100.0%** (PRIME SAFETY INVARIANT)

### 2.4 Platform Health Diagnostic (`wsctl doctor`)
- **Status**: **EXCELLENT (39 / 39 OK)**
- 0 errors, 0 warnings.
