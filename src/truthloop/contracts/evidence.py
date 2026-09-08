"""evidence.json contract (spec §4.3)."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from truthloop.contracts.common import SchemaVersion, StrictModel


class Chunk(StrictModel):
    id: str = Field(min_length=1, description="Unique identifier, referenced by claims.citations.")
    source: str = Field(
        min_length=1, description="Where this chunk was retrieved from (e.g. graph:calls)."
    )
    text: str = Field(description="Retrieved text a claim can cite as supporting evidence.")
    score: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Retriever's relevance score for this chunk, 0 to 1.",
    )


class Evidence(StrictModel):
    schema_version: SchemaVersion = 1
    question_id: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    chunks: list[Chunk] = Field(
        default_factory=list, description="Retrieved chunks available for claims to cite."
    )

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
