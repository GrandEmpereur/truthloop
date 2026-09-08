"""In-memory graph shared by every storage backend (spec §5)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, Literal

from truthloop.contracts.common import Direction, EntityRef, EntityType, Predicate, normalize_id

Access = Literal["read", "write", "both"]
_ACCESSES: frozenset[str] = frozenset({"read", "write", "both"})
_ACCESS_FOR_PREDICATE: Final[dict[str, frozenset[str]]] = {
    "reads": frozenset({"read", "both"}),
    "writes": frozenset({"write", "both"}),
}


class KnowledgeError(Exception):
    """The knowledge source cannot be opened or is inconsistent (exit code 1)."""


@dataclass(frozen=True)
class GraphRows:
    """Rows of the logical schema, as read from SQLite or files (ids not yet normalized)."""

    programs: tuple[tuple[str, str], ...]
    tables: tuple[tuple[str, str], ...]
    calls: tuple[tuple[str, str], ...]
    program_tables: tuple[tuple[str, str, str], ...]
    docs: tuple[tuple[str, str, str], ...] = ()


class InMemoryGraph:
    """Normalized, fail-closed view of the knowledge graph shared by every backend."""

    def __init__(self, rows: GraphRows, fingerprint: str) -> None:
        self._fingerprint = fingerprint
        self._programs = self._index(rows.programs, "programs")
        self._tables = self._index(rows.tables, "tables")
        self._docs = self._index(((i, t) for i, t, _ in rows.docs), "docs")
        self._callees: dict[str, set[str]] = defaultdict(set)
        self._callers: dict[str, set[str]] = defaultdict(set)
        for caller, callee in rows.calls:
            src, dst = normalize_id(caller), normalize_id(callee)
            self._require(src, self._programs, "calls.caller_id")
            self._require(dst, self._programs, "calls.callee_id")
            self._callees[src].add(dst)
            self._callers[dst].add(src)
        self._access: dict[tuple[str, str], str] = {}
        self._program_tables: dict[str, set[str]] = defaultdict(set)
        self._table_programs: dict[str, set[str]] = defaultdict(set)
        for program, table, access in rows.program_tables:
            prog, tbl = normalize_id(program), normalize_id(table)
            self._require(prog, self._programs, "program_tables.program_id")
            self._require(tbl, self._tables, "program_tables.table_id")
            if access not in _ACCESSES:
                raise KnowledgeError(
                    f"program_tables.access invalide pour ({program}, {table}) : {access!r}"
                )
            self._access[(prog, tbl)] = self._merge_access(self._access.get((prog, tbl)), access)
            self._program_tables[prog].add(tbl)
            self._table_programs[tbl].add(prog)

    @staticmethod
    def _index(rows: Iterable[tuple[str, str]], relation: str) -> dict[str, str]:
        index: dict[str, str] = {}
        for raw_id, name in rows:
            entity_id = normalize_id(raw_id)
            if not entity_id:
                raise KnowledgeError(f"{relation}.id vide (valeur brute {raw_id!r})")
            if entity_id in index:
                raise KnowledgeError(f"{relation}.id en double après normalisation : {entity_id!r}")
            index[entity_id] = name
        return index

    @staticmethod
    def _merge_access(current: str | None, new: str) -> str:
        return new if current is None or current == new else "both"

    @staticmethod
    def _require(entity_id: str, known: dict[str, str], column: str) -> None:
        if entity_id not in known:
            raise KnowledgeError(f"{column} référence un id inconnu ou vide : {entity_id!r}")

    def resolve(self, raw_id: str, entity_type: EntityType) -> EntityRef | None:
        entity_id = normalize_id(raw_id)
        known = {
            "program": self._programs,
            "table": self._tables,
            "doc": self._docs,
            "release": self._docs,
        }[entity_type]
        if entity_id in known:
            return EntityRef(type=entity_type, id=entity_id)
        return None

    def neighbors(self, program: EntityRef, direction: Direction, depth: int) -> set[EntityRef]:
        start = program.id
        if start not in self._programs or depth <= 0:
            return set()
        visited = {start}
        frontier = {start}
        found: set[str] = set()
        for _ in range(depth):
            next_frontier: set[str] = set()
            for node in frontier:
                for neighbor in self._adjacent(node, direction):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
                        found.add(neighbor)
            if not next_frontier:
                break
            frontier = next_frontier
        return {EntityRef(type="program", id=i) for i in found}

    def _adjacent(self, node: str, direction: Direction) -> set[str]:
        callers = self._callers.get(node, set())
        callees = self._callees.get(node, set())
        if direction == "callers":
            return callers
        if direction == "callees":
            return callees
        return callers | callees

    def programs_of(self, tables: Iterable[EntityRef]) -> set[EntityRef]:
        return {
            EntityRef(type="program", id=p)
            for t in tables
            for p in self._table_programs.get(t.id, set())
        }

    def tables_of(self, programs: Iterable[EntityRef]) -> set[EntityRef]:
        return {
            EntityRef(type="table", id=t)
            for p in programs
            for t in self._program_tables.get(p.id, set())
        }

    def has_edge(self, subject: EntityRef, predicate: Predicate, obj: EntityRef) -> bool:
        if predicate == "calls":
            return obj.id in self._callees.get(subject.id, set())
        if predicate == "called_by":
            return obj.id in self._callers.get(subject.id, set())
        access = self._access.get((subject.id, obj.id))
        if access is None:
            return False
        return access in _ACCESS_FOR_PREDICATE[predicate]

    def has_docs(self) -> bool:
        return bool(self._docs)

    def fingerprint(self) -> str:
        return self._fingerprint
