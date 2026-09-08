"""evidence.json contract (spec §4.3)."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from truthloop.contracts.common import SchemaVersion, StrictModel


class Chunk(StrictModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    text: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class Evidence(StrictModel):
    schema_version: SchemaVersion = 1
    question_id: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    chunks: list[Chunk] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_chunk_ids(self) -> Self:
        seen: set[str] = set()
        for chunk in self.chunks:
            if chunk.id in seen:
                raise ValueError(f"duplicate chunk id {chunk.id!r}")
            seen.add(chunk.id)
        return self

    def chunk_by_id(self) -> dict[str, Chunk]:
        return {chunk.id: chunk for chunk in self.chunks}
