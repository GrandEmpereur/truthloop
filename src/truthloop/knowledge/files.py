"""File backend: graph.json or one CSV per relation → InMemoryGraph (spec §5.2)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Final

from pydantic import Field, ValidationError

from truthloop.contracts.common import StrictModel
from truthloop.knowledge.graph import GraphRows, InMemoryGraph, KnowledgeError

_CSV_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "programs": ("id", "name"),
    "tables": ("id", "name"),
    "calls": ("caller_id", "callee_id"),
    "program_tables": ("program_id", "table_id", "access"),
    "docs": ("id", "title", "source"),
}


class _Program(StrictModel):
    id: str
    name: str = ""
    kind: str | None = None
    folder: str | None = None


class _Table(StrictModel):
    id: str
    name: str = ""


class _Call(StrictModel):
    caller_id: str
    callee_id: str
    call_type: str | None = None


class _ProgramTable(StrictModel):
    program_id: str
    table_id: str
    access: str


class _Doc(StrictModel):
    id: str
    title: str = ""
    source: str = ""
    version: str | None = None


class _GraphFile(StrictModel):
    programs: list[_Program]
    tables: list[_Table]
    calls: list[_Call]
    program_tables: list[_ProgramTable]
    docs: list[_Doc] = Field(default_factory=list)


def load_files(path: Path) -> InMemoryGraph:
    json_path = path if path.is_file() else path / "graph.json"
    if json_path.is_file():
        return _from_json(json_path)
    if path.is_dir():
        return _from_csv(path)
    raise KnowledgeError(f"source fichiers introuvable : {path}")


def _from_json(path: Path) -> InMemoryGraph:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise KnowledgeError(f"{path.name} illisible : {exc}") from exc
    try:
        parsed = _GraphFile.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise KnowledgeError(f"{path.name} invalide : {exc}") from exc
    rows = GraphRows(
        programs=tuple((p.id, p.name) for p in parsed.programs),
        tables=tuple((t.id, t.name) for t in parsed.tables),
        calls=tuple((c.caller_id, c.callee_id) for c in parsed.calls),
        program_tables=tuple(
            (pt.program_id, pt.table_id, pt.access) for pt in parsed.program_tables
        ),
        docs=tuple((d.id, d.title, d.source) for d in parsed.docs),
    )
    return InMemoryGraph(rows, hashlib.sha256(text.encode("utf-8")).hexdigest())


def _from_csv(directory: Path) -> InMemoryGraph:
    digest = hashlib.sha256()
    loaded: dict[str, tuple[tuple[str, ...], ...]] = {}
    for name, columns in _CSV_COLUMNS.items():
        csv_path = directory / f"{name}.csv"
        if not csv_path.is_file():
            if name == "docs":
                loaded[name] = ()
                continue
            raise KnowledgeError(f"{name}.csv manquant dans {directory}")
        # BOM-tolerant read; Path.read_text() also normalizes CRLF to "\n", so the digest is
        # a "logical" fingerprint (byte-identical content hashes the same regardless of BOM
        # or line-ending style).
        try:
            text = csv_path.read_text(encoding="utf-8-sig")
        except (OSError, ValueError) as exc:
            raise KnowledgeError(f"{csv_path.name} illisible : {exc}") from exc
        digest.update(name.encode("utf-8"))
        digest.update(text.encode("utf-8"))
        reader = csv.DictReader(io.StringIO(text), restval="")
        missing = set(columns) - set(reader.fieldnames or [])
        if missing:
            raise KnowledgeError(f"{name}.csv : colonnes manquantes {sorted(missing)}")
        loaded[name] = tuple(tuple(row[col] for col in columns) for row in reader)
    rows = GraphRows(
        programs=tuple((r[0], r[1]) for r in loaded["programs"]),
        tables=tuple((r[0], r[1]) for r in loaded["tables"]),
        calls=tuple((r[0], r[1]) for r in loaded["calls"]),
        program_tables=tuple((r[0], r[1], r[2]) for r in loaded["program_tables"]),
        docs=tuple((r[0], r[1], r[2]) for r in loaded["docs"]),
    )
    return InMemoryGraph(rows, digest.hexdigest())
