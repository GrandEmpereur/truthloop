"""question.json contract (spec §4.1)."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from truthloop.contracts.common import Direction, EntityRef, Intent, SchemaVersion, StrictModel


class Question(StrictModel):
    schema_version: SchemaVersion = 1
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    intent: Intent
    pivot_entities: list[EntityRef] = Field(default_factory=list)
    direction: Direction = "both"
    depth: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="after")
    def _pivots_are_programs_or_tables(self) -> Self:
        for pivot in self.pivot_entities:
            if pivot.type not in ("program", "table"):
                raise ValueError(f"pivot {pivot.id!r} must be a program or a table")
        return self

    @property
    def pivot_programs(self) -> set[EntityRef]:
        return {p for p in self.pivot_entities if p.type == "program"}

    @property
    def pivot_tables(self) -> set[EntityRef]:
        return {p for p in self.pivot_entities if p.type == "table"}
