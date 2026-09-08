from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from helpers import sample_answer, sample_evidence, sample_judge, sample_question, write_json
from truthloop.contracts.answer import Answer
from truthloop.contracts.evidence import Evidence
from truthloop.contracts.judge import Judge
from truthloop.contracts.question import Question
from truthloop.graders.base import GraderContext
from truthloop.knowledge.files import load_files
from truthloop.knowledge.graph import InMemoryGraph

FIXTURES = Path(__file__).parent / "fixtures"

RunBuilder = Callable[..., Path]
ContextBuilder = Callable[..., GraderContext]


@pytest.fixture
def graph() -> InMemoryGraph:
    return load_files(FIXTURES / "graph.json")


@pytest.fixture
def sqlite_path(tmp_path: Path) -> Path:
    """Build a SQLite database with the logical schema from tests/fixtures/graph.json."""
    data = json.loads((FIXTURES / "graph.json").read_text(encoding="utf-8"))
    path = tmp_path / "magic.db"
    conn = sqlite3.connect(path)
    with conn:
        conn.executescript(
            """
            CREATE TABLE programs (id TEXT, name TEXT);
            CREATE TABLE tables (id TEXT, name TEXT);
            CREATE TABLE calls (caller_id TEXT, callee_id TEXT);
            CREATE TABLE program_tables (program_id TEXT, table_id TEXT, access TEXT);
            CREATE TABLE docs (id TEXT, title TEXT, source TEXT);
            """
        )
        conn.executemany(
            "INSERT INTO programs VALUES (?, ?)", [(r["id"], r["name"]) for r in data["programs"]]
        )
        conn.executemany(
            "INSERT INTO tables VALUES (?, ?)", [(r["id"], r["name"]) for r in data["tables"]]
        )
        conn.executemany(
            "INSERT INTO calls VALUES (?, ?)",
            [(r["caller_id"], r["callee_id"]) for r in data["calls"]],
        )
        conn.executemany(
            "INSERT INTO program_tables VALUES (?, ?, ?)",
            [(r["program_id"], r["table_id"], r["access"]) for r in data["program_tables"]],
        )
        conn.executemany(
            "INSERT INTO docs VALUES (?, ?, ?)",
            [(r["id"], r["title"], r["source"]) for r in data["docs"]],
        )
    conn.close()
    return path


@pytest.fixture
def make_run(tmp_path: Path) -> RunBuilder:
    """Write a run directory; pass ``None`` to omit a file."""

    def _make(
        question: dict[str, object] | None,
        answer: dict[str, object] | None,
        evidence: dict[str, object] | None,
        judge: dict[str, object] | None,
        *,
        iteration: int = 1,
        run_id: str = "q-001",
    ) -> Path:
        run_dir = tmp_path / "runs" / run_id
        iter_dir = run_dir / f"iter-{iteration:02d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        if question is not None:
            write_json(run_dir / "question.json", question)
        for name, data in (("answer", answer), ("evidence", evidence), ("judge", judge)):
            if data is not None:
                write_json(iter_dir / f"{name}.json", data)
        return run_dir

    return _make


@pytest.fixture
def make_ctx(graph: InMemoryGraph) -> ContextBuilder:
    def _make(
        question: dict[str, object] | None = None,
        answer: dict[str, object] | None = None,
        evidence: dict[str, object] | None = None,
        judge: dict[str, object] | None = None,
        *,
        no_judge: bool = False,
    ) -> GraderContext:
        return GraderContext(
            question=Question.model_validate(question or sample_question()),
            answer=Answer.model_validate(answer or sample_answer()),
            evidence=Evidence.model_validate(evidence or sample_evidence()),
            judge=None if no_judge else Judge.model_validate(judge or sample_judge()),
            knowledge=graph,
        )

    return _make
