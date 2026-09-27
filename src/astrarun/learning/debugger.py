"""CLI Diagnostic & Inspection Tool for AstraRun Learning Foundation.

Allows offline inspection, provenance verification, conflict auditing, and skill review
without starting the UI or executing any actions.

Usage:
    python -m astrarun.learning.debugger list
    python -m astrarun.learning.debugger inspect <id>
    python -m astrarun.learning.debugger conflicts
    python -m astrarun.learning.debugger skills
    python -m astrarun.learning.debugger audit
    python -m astrarun.learning.debugger stats
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from astrarun.learning.models import MemoryNamespace, MemoryStatus, SkillStatus
from astrarun.learning.persistence import LearningPersistence


def cmd_list(persistence: LearningPersistence, args: argparse.Namespace) -> None:
    ns = MemoryNamespace(args.namespace) if args.namespace else None
    st = MemoryStatus(args.status) if args.status else None
    memories = persistence.find_memories(namespace=ns, status=st)

    print(f"\nFound {len(memories)} semantic memories:")
    print(f"{'ID':<10} {'NS':<10} {'KEY':<20} {'VALUE':<25} {'STATUS':<12} {'CONF':<8} {'SUP':<5} {'CONT':<5}")
    print("-" * 100)
    for m in memories:
        print(f"{m.id[:8]:<10} {m.namespace.value:<10} {m.key:<20} {str(m.value)[:24]:<25} {m.status.value:<12} {m.confidence:<8.2f} {m.support_count:<5} {m.contradiction_count:<5}")
    print()


def cmd_inspect(persistence: LearningPersistence, args: argparse.Namespace) -> None:
    mem = persistence.get_memory(args.memory_id)
    if not mem:
        # Search by prefix
        all_m = persistence.find_memories()
        for m in all_m:
            if m.id.startswith(args.memory_id):
                mem = m
                break

    if not mem:
        print(f"Memory with ID '{args.memory_id}' not found.")
        return

    print("\n" + "=" * 60)
    print(f"Memory ID:        {mem.id}")
    print(f"Namespace:        {mem.namespace.value}")
    print(f"Key:              {mem.key}")
    print(f"Value:            {mem.value}")
    print(f"Target Type:      {mem.target_type}")
    print(f"Status:           {mem.status.value}")
    print(f"Confidence:       {mem.confidence:.4f}")
    print(f"Support Count:    {mem.support_count}")
    print(f"Contradictions:   {mem.contradiction_count}")
    print(f"User Confirmed:   {mem.user_confirmed}")
    print(f"Pinned:           {mem.pinned}")
    print(f"Created:          {mem.created_at}")
    print(f"Last Used:        {mem.last_used_at}")
    print("-" * 60)
    print(f"Evidence References ({len(mem.evidence_refs)}):")
    for idx, ref in enumerate(mem.evidence_refs, 1):
        print(f"  [{idx}] Type: {ref.evidence_type.value} | Weight: {ref.weight} | Task: {ref.task_id[:8]} | Event: {ref.event_id or 'none'}")
        if ref.details:
            print(f"      Details: {ref.details}")
    print("=" * 60 + "\n")


def cmd_conflicts(persistence: LearningPersistence, args: argparse.Namespace) -> None:
    conflicted = persistence.find_memories(status=MemoryStatus.CONFLICTED)
    print(f"\nFound {len(conflicted)} conflicted memories:")
    print(f"{'ID':<10} {'KEY':<20} {'VALUE':<25} {'CONF':<8} {'SUP':<5} {'CONT':<5}")
    print("-" * 75)
    for m in conflicted:
        print(f"{m.id[:8]:<10} {m.key:<20} {str(m.value)[:24]:<25} {m.confidence:<8.2f} {m.support_count:<5} {m.contradiction_count:<5}")
    print()


def cmd_skills(persistence: LearningPersistence, args: argparse.Namespace) -> None:
    skills = persistence.list_skills()
    print(f"\nFound {len(skills)} skills:")
    print(f"{'ID':<10} {'NAME':<25} {'STATUS':<15} {'STEPS':<8} {'CONF':<8} {'SUP':<5}")
    print("-" * 75)
    for s in skills:
        print(f"{s.id[:8]:<10} {s.name:<25} {s.status.value:<15} {len(s.steps):<8} {s.confidence:<8.2f} {s.support_count:<5}")
    print()


def cmd_audit(persistence: LearningPersistence, args: argparse.Namespace) -> None:
    events = persistence.list_audit_events(limit=args.limit)
    print(f"\nShowing last {len(events)} audit events:")
    print(f"{'ID':<10} {'ACTION':<20} {'ENTITY':<10} {'TARGET ID':<15} {'DETAILS'}")
    print("-" * 80)
    for ev in events:
        print(f"{ev.id[:8]:<10} {ev.action.value:<20} {ev.entity_type:<10} {ev.entity_id[:12]:<15} {ev.details}")
    print()


def cmd_stats(persistence: LearningPersistence, args: argparse.Namespace) -> None:
    all_mem = persistence.find_memories()
    active_cnt = sum(1 for m in all_mem if m.status == MemoryStatus.ACTIVE)
    candidate_cnt = sum(1 for m in all_mem if m.status == MemoryStatus.CANDIDATE)
    conflicted_cnt = sum(1 for m in all_mem if m.status == MemoryStatus.CONFLICTED)
    deprecated_cnt = sum(1 for m in all_mem if m.status == MemoryStatus.DEPRECATED)
    rejected_cnt = sum(1 for m in all_mem if m.status == MemoryStatus.REJECTED)

    skills = persistence.list_skills()
    active_skills = sum(1 for s in skills if s.status == SkillStatus.ACTIVE)
    pending_skills = sum(1 for s in skills if s.status == SkillStatus.PENDING_REVIEW)

    print("\n" + "=" * 40)
    print("      ASTRARUN LEARNING STATS")
    print("=" * 40)
    print(f"Total Semantic Memories: {len(all_mem)}")
    print(f"  - Active:              {active_cnt}")
    print(f"  - Candidate:           {candidate_cnt}")
    print(f"  - Conflicted:          {conflicted_cnt}")
    print(f"  - Deprecated:          {deprecated_cnt}")
    print(f"  - Rejected:            {rejected_cnt}")
    print("-" * 40)
    print(f"Total Skills:            {len(skills)}")
    print(f"  - Active:              {active_skills}")
    print(f"  - Pending Review:      {pending_skills}")
    print("=" * 40 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="AstraRun Learning Diagnostic Tool")
    parser.add_argument("--db", default="data/astra_learning.db", help="Path to learning database")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = subparsers.add_parser("list", help="List semantic memories")
    p_list.add_argument("--namespace", choices=[n.value for n in MemoryNamespace], default=None)
    p_list.add_argument("--status", choices=[s.value for s in MemoryStatus], default=None)

    # inspect
    p_inspect = subparsers.add_parser("inspect", help="Inspect a specific memory by ID")
    p_inspect.add_argument("memory_id", help="Memory ID or prefix")

    # conflicts
    subparsers.add_parser("conflicts", help="List conflicted memories")

    # skills
    subparsers.add_parser("skills", help="List skills")

    # audit
    p_audit = subparsers.add_parser("audit", help="List audit events")
    p_audit.add_argument("--limit", type=int, default=20)

    # stats
    subparsers.add_parser("stats", help="Summary statistics")

    args = parser.parse_args()
    persistence = LearningPersistence(db_path=args.db)

    handlers = {
        "list": cmd_list,
        "inspect": cmd_inspect,
        "conflicts": cmd_conflicts,
        "skills": cmd_skills,
        "audit": cmd_audit,
        "stats": cmd_stats,
    }

    handlers[args.command](persistence, args)


if __name__ == "__main__":
    main()
