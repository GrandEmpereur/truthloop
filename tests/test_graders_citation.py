from conftest import ContextBuilder
from helpers import sample_answer, sample_question
from truthloop.graders.base import GraderContext
from truthloop.graders.citation import grade_citations
from truthloop.knowledge.graph import GraphRows, InMemoryGraph


def test_all_entities_known(make_ctx: ContextBuilder) -> None:
    [result] = grade_citations(make_ctx())
    assert result.component is None
    assert result.value is None
    assert result.findings == ()
    assert result.cap is None


def test_unknown_entity_is_critical_and_caps(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        entities=[
            {"type": "program", "id": "PRG_ORD_VALID"},
            {"type": "program", "id": "PRG_GHOST"},
        ],
        claims=[],
        abstentions=[],
    )
    [result] = grade_citations(make_ctx(answer=answer))
    assert [f.code for f in result.findings] == ["UNKNOWN_ENTITY"]
    assert result.findings[0].severity == "critical"
    assert result.findings[0].entity is not None
    assert result.findings[0].entity.id == "prg_ghost"
    assert result.cap == "unknown_entity"


def test_unknown_pivot_is_reported_once(make_ctx: ContextBuilder) -> None:
    question = sample_question(pivot_entities=[{"type": "program", "id": "PRG_GHOST"}])
    answer = sample_answer(
        entities=[{"type": "program", "id": "PRG_GHOST"}], claims=[], abstentions=[]
    )
    [result] = grade_citations(make_ctx(question=question, answer=answer))
    assert [f.code for f in result.findings] == ["UNKNOWN_PIVOT"]
    assert result.cap == "unknown_entity"


def test_docs_are_checked_only_when_source_has_docs(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        entities=[{"type": "release", "id": "REL-9999"}], claims=[], abstentions=[]
    )
    [with_docs] = grade_citations(make_ctx(answer=answer))
    assert [f.code for f in with_docs.findings] == ["UNKNOWN_ENTITY"]

    ctx = make_ctx(answer=answer)
    bare = InMemoryGraph(
        GraphRows(programs=(("PRG_ORD_VALID", ""),), tables=(), calls=(), program_tables=()), "x"
    )
    without_docs = GraderContext(ctx.question, ctx.answer, ctx.evidence, ctx.judge, bare)
    [result] = grade_citations(without_docs)
    assert result.findings == ()
