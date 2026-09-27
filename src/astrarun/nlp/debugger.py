"""Developer diagnostic tool and CLI for inspecting AstraRun NLP parsing.

Usage:
    python -m astrarun.nlp.debugger "open AstraRun in vscode and inspect port 3000"
    python -m astrarun.nlp.debugger "don't kill node, just inspect it"
"""

from __future__ import annotations

import json
import sys
from astrarun.nlp.engine import NLPEngine
from astrarun.nlp.models import UserRequest
from astrarun.workflows.compiler import WorkflowCompiler
from astrarun.projects import get_project_registry


def inspect_nlp(query: str) -> None:
    """Parse text and print rich formatted diagnostic inspection output."""
    project_registry = get_project_registry()
    engine = NLPEngine(project_registry=project_registry)
    compiler = WorkflowCompiler()

    req = UserRequest(text=query, source="debugger_cli")
    utterance = engine.parse(req)
    escalation = engine.check_reasoning_escalation(utterance)
    proposal = compiler.compile(utterance)

    print("=" * 70)
    print(f"  ASTRARUN NLP DIAGNOSTIC DEBUGGER")
    print("=" * 70)
    print(f"Raw Input:        '{utterance.raw_text}'")
    print(f"Normalized Text:  '{utterance.normalized_text}'")
    print(f"Overall Conf:     {utterance.confidence:.4f}")
    print(f"Ambiguity Score:  {utterance.ambiguity:.4f}")
    print(f"Parser Sources:   {', '.join(utterance.parser_sources)}")
    print(f"Duration:         {utterance.provenance.get('parse_duration_ms', 0.0):.3f} ms")
    print("-" * 70)

    # 1. Clauses
    print(f"\n[CLAUSES] ({len(utterance.clauses)} detected)")
    for c in utterance.clauses:
        neg_str = " [NEGATED]" if c.negated else " [ACTIVE]"
        print(f"  Clause {c.idx}{neg_str}: '{c.text}'")
        print(f"    Action:     {c.action} (intent: {c.intent}, conf: {c.confidence:.2f})")
        if c.entities:
            print(f"    Entities:   {', '.join(f'{e.type.value}:{e.normalized}' for e in c.entities)}")
        if c.constraints:
            print(f"    Constraints:{', '.join(co.type for co in c.constraints)}")
        if c.negation_details:
            print(f"    Negation:   '{c.negation_details.text}' targeting clause {c.negation_details.target_clause_idx}")

    # 2. Ordering Relations
    if utterance.ordering_relations:
        print(f"\n[ORDERING RELATIONS]")
        for frm, rel, to in utterance.ordering_relations:
            print(f"  Clause {frm} --({rel.value})--> Clause {to}")

    # 3. Entities with Spans
    if utterance.entities:
        print(f"\n[EXTRACTED ENTITIES]")
        for e in utterance.entities:
            print(f"  - [{e.start:2d}:{e.end:2d}] {e.type.value:<12} '{e.text}' -> {e.normalized} (source: {e.source})")

    # 4. Directed Relations
    if utterance.relations:
        print(f"\n[SEMANTIC RELATIONS]")
        for r in utterance.relations:
            print(f"  - {r.source_entity} --({r.type.value})--> {r.target_entity} (conf: {r.confidence:.2f})")

    # 5. Temporal Expressions
    if utterance.temporal_expressions:
        print(f"\n[TEMPORAL EXPRESSIONS]")
        for t in utterance.temporal_expressions:
            print(f"  - '{t.text}' -> val: {t.value}, rel: {t.relation}, range: {t.resolved_range}")

    # 6. Contextual References
    if utterance.contextual_references:
        print(f"\n[CONTEXTUAL REFERENCES]")
        for cr in utterance.contextual_references:
            print(f"  - '{cr.text}' -> target: {cr.target_type}, resolved: {cr.resolved_id}, ambig: {cr.ambiguous}")

    # 7. Escalation Check
    if escalation:
        print(f"\n[AI BRIDGE ESCALATION (v0.7)]")
        print(f"  Reason:      {escalation.reason}")
        print(f"  Explanation: {escalation.explanation}")
        print(f"  Unresolved:  {escalation.unresolved_fields}")

    # 8. Workflow Proposal Preview
    print(f"\n[WORKFLOW PROPOSAL]")
    print(f"  Status:       {proposal.status}")
    print(f"  Overall Risk: {proposal.overall_risk.value}")
    print(f"  Requires Conf:{proposal.requires_confirmation}")
    if proposal.blocked_reasons:
        print(f"  Blocked:      {proposal.blocked_reasons}")
    if proposal.unsupported_clauses:
        print(f"  Unsupported:  {proposal.unsupported_clauses}")
    print(f"  Preview:\n{proposal.preview}")
    print("=" * 70 + "\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m astrarun.nlp.debugger '<utterance>'")
        sys.exit(1)
    query = " ".join(sys.argv[1:])
    inspect_nlp(query)


if __name__ == "__main__":
    main()
