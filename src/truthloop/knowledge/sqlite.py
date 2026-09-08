"""SQLite backend: configurable SQL → logical rows → InMemoryGraph (spec §5.1)."""

from __future__ import annotations

import hashlib
import sqlite3
import urllib.parse
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from truthloop.knowledge.graph import GraphRows, InMemoryGraph, KnowledgeError

DEFAULT_QUERIES: Final[dict[str, str]] = {
    "programs": "SELECT id, name FROM programs",
    "tables": "SELECT id, name FROM tables",
    "calls": "SELECT caller_id, callee_id FROM calls",
    "program_tables": "SELECT program_id, table_id, access FROM program_tables",
    "docs": "SELECT id, title, source FROM docs",
}
_WIDTHS: Final[dict[str, int]] = {
    "programs": 2,
    "tables": 2,
    "calls": 2,
    "program_tables": 3,
    "docs": 3,
}


def load_sqlite(path: Path, queries: Mapping[str, str]) -> InMemoryGraph:
    if not path.is_file():
        raise KnowledgeError(f"base SQLite introuvable : {path}")
    merged = {**DEFAULT_QUERIES, **queries}
    # ``Path.as_uri()`` treats a literal ``?`` or ``#`` in the path as the start of the query
    # string or fragment, silently truncating it; percent-encode the path ourselves instead.
    uri = "file:" + urllib.parse.quote(str(path.resolve())) + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise KnowledgeError(f"ouverture impossible de {path} : {exc}") from exc
    try:
        programs = _rows(conn, "programs", merged["programs"])
        tables = _rows(conn, "tables", merged["tables"])
        calls = _rows(conn, "calls", merged["calls"])
        program_tables = _rows(conn, "program_tables", merged["program_tables"])
        docs = _rows(conn, "docs", merged["docs"], optional=True)
    finally:
        conn.close()
    stat = path.stat()
    fingerprint = hashlib.sha256(f"{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()
    return InMemoryGraph(
        GraphRows(
            programs=tuple((r[0], r[1]) for r in programs),
            tables=tuple((r[0], r[1]) for r in tables),
            calls=tuple((r[0], r[1]) for r in calls),
            program_tables=tuple((r[0], r[1], r[2]) for r in program_tables),
            docs=tuple((r[0], r[1], r[2]) for r in docs),
        ),
        fingerprint,
    )


def _rows(
    conn: sqlite3.Connection, name: str, sql: str, *, optional: bool = False
) -> tuple[tuple[str, ...], ...]:
    """Run one logical-schema query; ``optional`` relations (docs) vanish when their table is absent."""
    try:
        cursor = conn.execute(sql)
        fetched = cursor.fetchall()
    except sqlite3.OperationalError as exc:
        # Textual check on purpose: sqlite3 exposes no error code for a missing table.
        if optional and "no such table" in str(exc):
            return ()
        raise KnowledgeError(f"requête {name} en erreur : {exc}") from exc
    except sqlite3.Error as exc:
        raise KnowledgeError(f"requête {name} en erreur : {exc}") from exc
    width = _WIDTHS[name]
    actual = len(cursor.description or ())
    if actual != width:
        raise KnowledgeError(f"requête {name} : {width} colonnes attendues, {actual} obtenues")
    return tuple(tuple("" if value is None else str(value) for value in row) for row in fetched)
