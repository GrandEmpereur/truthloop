"""Consistency: a claimed relation must exist in the graph (spec §6, gate-only)."""

from __future__ import annotations

from truthloop.contracts.answer import RELATION_OBJECT_TYPE
from truthloop.contracts.verdict import Finding
from truthloop.graders.base import GraderContext, GraderResult


def grade_consistency(ctx: GraderContext) -> list[GraderResult]:
    findings: list[Finding] = []
    for claim in ctx.answer.claims:
        relation = claim.relation
        if relation is None:
            continue
        subject = ctx.knowledge.resolve(relation.subject, "program")
        obj = ctx.knowledge.resolve(relation.object, RELATION_OBJECT_TYPE[relation.predicate])
        if subject is None or obj is None:
            continue
        if not ctx.knowledge.has_edge(subject, relation.predicate, obj):
            findings.append(
                Finding(
                    code="CONTRADICTED_BY_GRAPH",
                    severity="critical",
                    claim_id=claim.id,
                    detail=f"Le graphe ne contient pas {relation.subject} {relation.predicate} {relation.object}.",
                )
            )
    return [
        GraderResult(
            component=None,
            value=None,
            findings=tuple(findings),
            cap="contradiction" if findings else None,
        )
    ]
