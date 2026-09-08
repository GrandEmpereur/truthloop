import sqlite3
from pathlib import Path

import pytest

from truthloop.contracts.common import EntityRef
from truthloop.knowledge import KnowledgeError
from truthloop.knowledge.sqlite import DEFAULT_QUERIES, load_sqlite


def test_load_sqlite_with_default_queries(sqlite_path: Path) -> None:
    graph = load_sqlite(sqlite_path, {})
    valid = EntityRef(type="program", id="prg_ord_valid")
    assert {e.id for e in graph.neighbors(valid, "callers", 1)} == {
        "prg_ord_save",
        "prg_ord_notify",
    }
    assert graph.has_docs()
    assert len(graph.fingerprint()) == 64


def test_load_sqlite_with_overridden_queries(sqlite_path: Path) -> None:
    conn = sqlite3.connect(sqlite_path)
    with conn:
        conn.executescript(
            """
            CREATE TABLE xpa_programs (prog_id TEXT, prog_name TEXT);
            INSERT INTO xpa_programs SELECT id, name FROM programs;
            DROP TABLE programs;
            DROP TABLE docs;
            """
        )
    conn.close()
    graph = load_sqlite(
        sqlite_path, {"programs": "SELECT prog_id AS id, prog_name AS name FROM xpa_programs"}
    )
    assert graph.resolve("PRG_ORD_VALID", "program") is not None
    assert graph.has_docs() is False


def test_missing_file_and_bad_query_raise(sqlite_path: Path, tmp_path: Path) -> None:
    with pytest.raises(KnowledgeError, match="introuvable"):
        load_sqlite(tmp_path / "nope.db", {})
    with pytest.raises(KnowledgeError, match="calls"):
        load_sqlite(sqlite_path, {"calls": "SELECT caller_id FROM calls"})
    with pytest.raises(KnowledgeError, match="programs"):
        load_sqlite(sqlite_path, {"programs": "SELECT * FROM does_not_exist"})


def test_default_queries_cover_logical_schema() -> None:
    assert set(DEFAULT_QUERIES) == {"programs", "tables", "calls", "program_tables", "docs"}
