"""Coverage (context_recall) and TableCoverage (table_recall) graders (spec §6)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from truthloop.contracts.common import EntityRef
from truthloop.contracts.question import Question
from truthloop.contracts.verdict import Finding
from truthloop.graders.base import GraderContext, GraderResult
from truthloop.knowledge import KnowledgeSource


@dataclass(frozen=True)
class ExpectedProgram:
    depth: int
    via: str


def _by_id(entity: EntityRef) -> str:
    return entity.id


def expected_programs(
    question: Question, knowledge: KnowledgeSource
) -> dict[EntityRef, ExpectedProgram] | None:
    """E with the depth/pivot each program was first reached from; None if a pivot is unknown."""
    if any(knowledge.resolve(p.id, p.type) is None for p in question.pivot_entities):
        return None
    pivot_programs = question.pivot_programs
    expected: dict[EntityRef, ExpectedProgram] = {}

    def record(program: EntityRef, depth: int, via: str) -> None:
        if program in pivot_programs:
            return
        current = expected.get(program)
        if current is None or depth < current.depth:
            expected[program] = ExpectedProgram(depth=depth, via=via)

    for pivot in sorted(pivot_programs, key=_by_id):
        _expand(knowledge, question, pivot, question.depth, 0, pivot.id, record)
    for table in sorted(question.pivot_tables, key=_by_id):
        for program in sorted(knowledge.programs_of([table]), key=_by_id):
            record(program, 1, table.id)
            _expand(knowledge, question, program, question.depth - 1, 1, table.id, record)
    return expected


def _expand(
    knowledge: KnowledgeSource,
    question: Question,
    start: EntityRef,
    depth: int,
    base_depth: int,
    via: str,
    record: Callable[[EntityRef, int, str], None],
) -> None:
    reached: set[EntityRef] = set()
    for hop in range(1, depth + 1):
        layer = knowledge.neighbors(start, question.direction, hop) - reached
        for program in sorted(layer, key=_by_id):
            record(program, base_depth + hop, via)
        reached |= layer


_NOT_APPLICABLE = (
    GraderResult(component="context_recall", value=None),
    GraderResult(component="table_recall", value=None),
)


def grade_coverage(ctx: GraderContext) -> list[GraderResult]:
    question = ctx.question
    if not question.pivot_entities:
        return list(_NOT_APPLICABLE)
    expected = expected_programs(question, ctx.knowledge)
    if not expected:
        return list(_NOT_APPLICABLE)
    pivot_programs = question.pivot_programs
    cited = ctx.answer.entities_of_type("program") - pivot_programs
    expected_set = set(expected)
    findings: list[Finding] = []
    for program in sorted(expected_set - cited, key=_by_id):
        info = expected[program]
        findings.append(
            Finding(
                code="MISSING_ENTITY",
                severity="major",
                entity=program,
                depth=info.depth,
                via=info.via,
                detail=f"Programme attendu à la profondeur {info.depth} via {info.via}, non cité.",
            )
        )
    for program in sorted(cited - expected_set, key=_by_id):
        if ctx.knowledge.resolve(program.id, "program") is not None:
            findings.append(
                Finding(
                    code="EXTRA_ENTITY",
                    severity="info",
                    entity=program,
                    detail="Programme cité hors du périmètre attendu.",
                )
            )
    recall = len(expected_set & cited) / len(expected_set)
    coverage = GraderResult(
        component="context_recall",
        value=recall,
        findings=tuple(findings),
        expected_size=len(expected_set),
    )
    return [coverage, _grade_tables(ctx, expected_set | pivot_programs)]


def _grade_tables(ctx: GraderContext, scope: set[EntityRef]) -> GraderResult:
    pivot_tables = ctx.question.pivot_tables
    expected_tables = ctx.knowledge.tables_of(scope) - pivot_tables
    if not expected_tables:
        return GraderResult(component="table_recall", value=None)
    cited_tables = ctx.answer.entities_of_type("table") - pivot_tables
    findings: list[Finding] = []
    for table in sorted(expected_tables - cited_tables, key=_by_id):
        users = sorted(ctx.knowledge.programs_of([table]) & scope, key=_by_id)
        # table came from tables_of(scope), so it has at least one program in scope: users is never empty
        via = users[0].id
        findings.append(
            Finding(
                code="MISSING_TABLE",
                severity="major",
                entity=table,
                via=via,
                detail=f"Table référencée par {via}, non citée.",
            )
        )
    recall = len(expected_tables & cited_tables) / len(expected_tables)
    return GraderResult(
        component="table_recall",
        value=recall,
        findings=tuple(findings),
        expected_size=len(expected_tables),
    )
