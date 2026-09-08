"""Pick the knowledge backend from the configuration (spec §5, §8.3)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from truthloop.knowledge import KnowledgeSource
from truthloop.knowledge.files import load_files
from truthloop.knowledge.graph import KnowledgeError
from truthloop.knowledge.sqlite import load_sqlite


def open_knowledge(kind: str, path: Path, queries: Mapping[str, str]) -> KnowledgeSource:
    if kind == "sqlite":
        return load_sqlite(path, queries)
    if kind == "files":
        return load_files(path)
    raise KnowledgeError(f"kind de source inconnu : {kind!r}")
