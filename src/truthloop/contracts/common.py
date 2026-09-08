"""Shared building blocks for every truthloop contract (spec §4.0)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EntityType = Literal["program", "table", "doc", "release"]
Direction = Literal["callers", "callees", "both"]
Predicate = Literal["calls", "called_by", "reads", "writes"]
Intent = Literal["impact_analysis", "architecture", "feature", "diagram"]
SchemaVersion = Literal[1]

_SEPARATORS = re.compile(r"[-_\s]+")


def normalize_id(raw: str) -> str:
    """Canonical id: trimmed, casefolded, separators collapsed to ``_``."""
    return _SEPARATORS.sub("_", raw.strip().casefold())


class StrictModel(BaseModel):
    """Base for every contract: no coercion, no unknown fields."""

    model_config = ConfigDict(extra="forbid", strict=True)


class EntityRef(StrictModel):
    """A typed, normalized reference to a knowledge-graph entity."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    type: EntityType
    id: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def _normalize(cls, value: str) -> str:
        normalized = normalize_id(value)
        if not normalized:
            raise ValueError("entity id is empty after normalization")
        return normalized
