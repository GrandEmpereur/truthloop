import pytest

from conftest import ContextBuilder
from helpers import sample_answer, sample_question
from truthloop.contracts.common import EntityRef
from truthloop.graders.coverage import expected_programs, grade_coverage
from truthloop.knowledge.graph import InMemoryGraph


def _ids(entities: list[dict[str, str]]) -> list[dict[str, object]]:
    return [{"type": e["type"], "id": e["id"]} for e in entities]


def test_sample_recall_and_findings(make_ctx: ContextBuilder) -> None:
    coverage, tables = grade_coverage(make_ctx())
    assert coverage.component == "context_recall"
    assert coverage.value == 0.5
    assert coverage.expected_size == 4
    assert [
        (f.code, f.entity.id if f.entity else None, f.depth, f.via) for f in coverage.findings
    ] == [
        ("MISSING_ENTITY", "prg_cust_load", 1, "prg_ord_valid"),
        ("MISSING_ENTITY", "prg_inv_check", 1, "prg_ord_valid"),
    ]
    assert tables.component == "table_recall"
    assert tables.value == 0.25
    assert tables.expected_size == 4
    assert [(f.code, f.entity.id if f.entity else None, f.via) for f in tables.findings] == [
        ("MISSING_TABLE", "t_customers", "prg_cust_load"),
        ("MISSING_TABLE", "t_order_lines", "prg_ord_save"),
        ("MISSING_TABLE", "t_stock", "prg_inv_check"),
    ]


def test_not_applicable_without_pivot_or_with_unknown_pivot(make_ctx: ContextBuilder) -> None:
    for question in (
        sample_question(pivot_entities=[], intent="architecture"),
        sample_question(pivot_entities=[{"type": "program", "id": "PRG_GHOST"}]),
    ):
        coverage, tables = grade_coverage(make_ctx(question=question))
        assert coverage.value is None
        assert tables.value is None
        assert coverage.findings == ()


def test_extra_known_entity_is_info_and_pivot_is_never_extra(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        entities=_ids(
            [
                {"type": "program", "id": "PRG_ORD_VALID"},
                {"type": "program", "id": "PRG_ORD_SAVE"},
                {"type": "program", "id": "PRG_REPORT"},
            ]
        ),
        claims=[],
        abstentions=[],
    )
    coverage, _ = grade_coverage(make_ctx(answer=answer))
    extras = [f for f in coverage.findings if f.code == "EXTRA_ENTITY"]
    assert [f.entity.id for f in extras if f.entity] == ["prg_report"]
    assert extras[0].severity == "info"
    assert coverage.value == 0.25


def test_depth_attribution_for_callers(make_ctx: ContextBuilder) -> None:
    question = sample_question(direction="callers", depth=2)
    coverage, _ = grade_coverage(make_ctx(question=question))
    missing = {f.entity.id: (f.depth, f.via) for f in coverage.findings if f.entity}
    assert missing == {"prg_main_menu": (2, "prg_ord_valid")}
    assert coverage.value == pytest.approx(2 / 3)


def test_table_pivot(make_ctx: ContextBuilder, graph: InMemoryGraph) -> None:
    question = sample_question(pivot_entities=[{"type": "table", "id": "T_CUSTOMERS"}], depth=2)
    expected = expected_programs(question=make_ctx(question=question).question, knowledge=graph)
    assert expected is not None
    assert {e.id: (info.depth, info.via) for e, info in expected.items()} == {
        "prg_cust_load": (1, "t_customers"),
        "prg_ord_valid": (2, "t_customers"),
    }
    answer = sample_answer(
        entities=_ids(
            [
                {"type": "table", "id": "T_CUSTOMERS"},
                {"type": "program", "id": "PRG_CUST_LOAD"},
                {"type": "program", "id": "PRG_ORD_VALID"},
            ]
        ),
        claims=[],
        abstentions=[],
    )
    coverage, tables = grade_coverage(make_ctx(question=question, answer=answer))
    assert coverage.value == 1.0
    assert tables.value == 0.0
    assert [f.entity.id for f in tables.findings if f.entity] == ["t_orders"]


def test_two_program_pivots_use_smallest_depth(
    make_ctx: ContextBuilder, graph: InMemoryGraph
) -> None:
    question = sample_question(
        pivot_entities=[
            {"type": "program", "id": "PRG_ORD_VALID"},
            {"type": "program", "id": "PRG_MAIN_MENU"},
        ],
        direction="both",
        depth=2,
    )
    expected = expected_programs(question=make_ctx(question=question).question, knowledge=graph)
    assert expected is not None
    assert "prg_ord_valid" not in {e.id for e in expected}
    assert "prg_main_menu" not in {e.id for e in expected}
    assert expected[EntityRef(type="program", id="prg_ord_save")].depth == 1


def test_recall_never_decreases_when_adding_expected_entities(make_ctx: ContextBuilder) -> None:
    cited = [{"type": "program", "id": "PRG_ORD_VALID"}]
    previous = 0.0
    for extra in ("PRG_ORD_SAVE", "PRG_ORD_NOTIFY", "PRG_CUST_LOAD", "PRG_INV_CHECK"):
        cited.append({"type": "program", "id": extra})
        coverage, _ = grade_coverage(
            make_ctx(answer=sample_answer(entities=_ids(cited), claims=[], abstentions=[]))
        )
        assert coverage.value is not None
        assert coverage.value >= previous
        previous = coverage.value
    assert previous == 1.0
    assert EntityRef(type="program", id="prg_ord_valid") not in {
        f.entity for f in coverage.findings if f.entity is not None
    }
