"""question.json contract (spec §4.1)."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from truthloop.contracts.common import (
    Direction,
    EntityRef,
    Intent,
    SchemaVersion,
    StrictModel,
    normalize_id,
)


class PivotRef(StrictModel):
    """A normalized reference to the program or table a traversal starts from."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    type: Literal["program", "table"] = Field(
        description="Kind of the pivot entity: only programs and tables can be traversal starts."
    )
    id: str = Field(min_length=1, description="Normalized identifier of the pivot entity.")

    @field_validator("id")
    @classmethod
    def _normalize(cls, value: str) -> str:
        normalized = normalize_id(value)
        if not normalized:
            raise ValueError("entity id is empty after normalization")
        return normalized

    def as_entity(self) -> EntityRef:
        """Widen to the generic ``EntityRef`` expected by findings and knowledge lookups."""
        return EntityRef(type=self.type, id=self.id)


class Question(StrictModel):
    schema_version: SchemaVersion = 1
    id: str = Field(min_length=1, description="Unique identifier of the question within a run.")
    text: str = Field(min_length=1, description="Natural-language question the agent must answer.")
    intent: Intent = Field(description="Task category the question belongs to.")
    pivot_entities: list[PivotRef] = Field(
        default_factory=list,
        description="Programs or tables the graph traversal starts from.",
    )
    direction: Direction = Field(
        default="both", description="Call-graph edges to follow from the pivots when traversing."
    )
    depth: int = Field(
        default=1, ge=1, le=5, description="Maximum number of hops to traverse from each pivot."
    )

    @property
    def pivot_programs(self) -> set[EntityRef]:
        return {p.as_entity() for p in self.pivot_entities if p.type == "program"}

    @property
    def pivot_tables(self) -> set[EntityRef]:
        return {p.as_entity() for p in self.pivot_entities if p.type == "table"}
