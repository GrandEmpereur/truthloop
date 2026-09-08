import pytest

from truthloop.contracts.common import Direction, EntityRef
from truthloop.knowledge import KnowledgeError
from truthloop.knowledge.graph import GraphRows, InMemoryGraph


def prog(entity_id: str) -> EntityRef:
    return EntityRef(type="program", id=entity_id)


def table(entity_id: str) -> EntityRef:
    return EntityRef(type="table", id=entity_id)


def test_resolve_normalizes_and_is_typed(graph: InMemoryGraph) -> None:
    assert graph.resolve("PRG-ORD-VALID", "program") == prog("prg_ord_valid")
    assert graph.resolve("prg_ord_valid", "table") is None
    assert graph.resolve("nope", "program") is None
    assert graph.resolve("rel-2026.1", "doc") == EntityRef(type="doc", id="rel_2026.1")
    assert graph.has_docs() is True


@pytest.mark.parametrize(
    ("direction", "depth", "expected"),
    [
        ("callers", 1, {"prg_ord_save", "prg_ord_notify"}),
        ("callers", 2, {"prg_ord_save", "prg_ord_notify", "prg_main_menu"}),
        ("callees", 1, {"prg_cust_load", "prg_inv_check"}),
        ("both", 1, {"prg_ord_save", "prg_ord_notify", "prg_cust_load", "prg_inv_check"}),
        (
            "both",
            2,
            {
                "prg_ord_save",
                "prg_ord_notify",
                "prg_cust_load",
                "prg_inv_check",
                "prg_main_menu",
                "prg_ord_archive",
            },
        ),
        ("both", 0, set()),
    ],
)
def test_neighbors(
    graph: InMemoryGraph, direction: Direction, depth: int, expected: set[str]
) -> None:
    result = graph.neighbors(prog("prg_ord_valid"), direction, depth)
    assert {e.id for e in result} == expected
    assert all(e.type == "program" for e in result)


def test_neighbors_of_unknown_program_is_empty(graph: InMemoryGraph) -> None:
    assert graph.neighbors(prog("ghost"), "both", 3) == set()


def test_programs_and_tables(graph: InMemoryGraph) -> None:
    assert {e.id for e in graph.programs_of([table("t_orders")])} == {
        "prg_ord_save",
        "prg_ord_valid",
        "prg_ord_archive",
        "prg_report",
    }
    assert {e.id for e in graph.tables_of([prog("prg_ord_save")])} == {"t_orders", "t_order_lines"}
    assert graph.tables_of([prog("prg_main_menu")]) == set()


def test_has_edge_semantics(graph: InMemoryGraph) -> None:
    assert graph.has_edge(prog("prg_ord_save"), "calls", prog("prg_ord_valid"))
    assert graph.has_edge(prog("prg_ord_valid"), "called_by", prog("prg_ord_save"))
    assert not graph.has_edge(prog("prg_ord_valid"), "calls", prog("prg_ord_save"))
    assert graph.has_edge(prog("prg_ord_save"), "writes", table("t_orders"))
    assert not graph.has_edge(prog("prg_ord_save"), "reads", table("t_orders"))
    assert graph.has_edge(prog("prg_inv_check"), "reads", table("t_stock"))
    assert graph.has_edge(prog("prg_inv_check"), "writes", table("t_stock"))


def test_fingerprint_is_stable(graph: InMemoryGraph) -> None:
    assert len(graph.fingerprint()) == 64
    assert graph.fingerprint() == graph.fingerprint()


def test_edges_to_unknown_nodes_fail_closed() -> None:
    rows = GraphRows(programs=(("A", "a"),), tables=(), calls=(("A", "B"),), program_tables=())
    with pytest.raises(KnowledgeError, match="'b'"):
        InMemoryGraph(rows, fingerprint="x")
    rows = GraphRows(
        programs=(("A", "a"),), tables=(("T", "t"),), calls=(), program_tables=(("A", "T", "rw"),)
    )
    with pytest.raises(KnowledgeError, match="access"):
        InMemoryGraph(rows, fingerprint="x")


def test_empty_and_duplicate_ids_fail_closed() -> None:
    with pytest.raises(KnowledgeError, match="vide"):
        InMemoryGraph(
            GraphRows(programs=(("  ", "blank"),), tables=(), calls=(), program_tables=()), "x"
        )
    with pytest.raises(KnowledgeError, match="double"):
        InMemoryGraph(
            GraphRows(
                programs=(("PRG-A", "a"), ("prg_a", "a again")),
                tables=(),
                calls=(),
                program_tables=(),
            ),
            "x",
        )
    with pytest.raises(KnowledgeError, match="vide"):
        InMemoryGraph(
            GraphRows(programs=(("A", "a"),), tables=(), calls=(("A", ""),), program_tables=()), "x"
        )


def test_conflicting_access_rows_merge_to_both() -> None:
    rows = GraphRows(
        programs=(("A", "a"),),
        tables=(("T", "t"),),
        calls=(),
        program_tables=(("A", "T", "read"), ("A", "T", "write")),
    )
    graph = InMemoryGraph(rows, "x")
    assert graph.has_edge(prog("a"), "reads", table("t"))
    assert graph.has_edge(prog("a"), "writes", table("t"))
    reversed_rows = GraphRows(
        programs=rows.programs,
        tables=rows.tables,
        calls=(),
        program_tables=rows.program_tables[::-1],
    )
    assert InMemoryGraph(reversed_rows, "x").has_edge(prog("a"), "reads", table("t"))


def test_tables_of_expected_scope(graph: InMemoryGraph) -> None:
    scope = {
        prog(i)
        for i in (
            "prg_ord_save",
            "prg_ord_notify",
            "prg_cust_load",
            "prg_inv_check",
            "prg_ord_valid",
        )
    }
    assert {t.id for t in graph.tables_of(scope)} == {
        "t_orders",
        "t_order_lines",
        "t_customers",
        "t_stock",
    }
