"""CitationValidity: every cited program/table must exist in the graph (spec §6)."""

from __future__ import annotations

from truthloop.contracts.common import EntityRef
from truthloop.contracts.verdict import Finding
from truthloop.graders.base import GraderContext, GraderResult


def grade_citations(ctx: GraderContext) -> list[GraderResult]:
    findings: list[Finding] = []
    unknown_pivots: set[EntityRef] = set()
    for pivot in ctx.question.pivot_entities:
        if ctx.knowledge.resolve(pivot.id, pivot.type) is None:
            unknown_pivots.add(pivot)
            findings.append(
                Finding(
                    code="UNKNOWN_PIVOT",
                    severity="critical",
                    entity=pivot,
                    detail=f"Pivot {pivot.id} ({pivot.type}) inconnu du graphe : corriger question.json.",
                )
            )
    check_docs = ctx.knowledge.has_docs()
    for entity in ctx.answer.entities:
        if entity in unknown_pivots:
            continue
        if entity.type in ("doc", "release") and not check_docs:
            continue
        if ctx.knowledge.resolve(entity.id, entity.type) is None:
            findings.append(
                Finding(
                    code="UNKNOWN_ENTITY",
                    severity="critical",
                    entity=entity,
                    detail=f"Entité {entity.id} ({entity.type}) inconnue du graphe.",
                )
            )
    return [
        GraderResult(
            component=None,
            value=None,
            findings=tuple(findings),
            cap="unknown_entity" if findings else None,
        )
    ]
