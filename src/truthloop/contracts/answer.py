"""answer.json contract and cross-reference rules (spec §4.0, §4.2)."""

from __future__ import annotations

from typing import Final, Self

from pydantic import Field, field_validator, model_validator

from truthloop.contracts.common import (
    EntityRef,
    EntityType,
    Predicate,
    SchemaVersion,
    StrictModel,
    normalize_id,
)

RELATION_OBJECT_TYPE: Final[dict[Predicate, EntityType]] = {
    "calls": "program",
    "called_by": "program",
    "reads": "table",
    "writes": "table",
}


def _normalize_all(values: list[str]) -> list[str]:
    normalized = [normalize_id(v) for v in values]
    if any(not v for v in normalized):
        raise ValueError("entity id is empty after normalization")
    return normalized


class Relation(StrictModel):
    subject: str = Field(min_length=1)
    predicate: Predicate
    object: str = Field(min_length=1)

    @field_validator("subject", "object")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return _normalize_all([value])[0]


class Claim(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    entities: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    relation: Relation | None = None
    confidence_self: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("entities")
    @classmethod
    def _normalize(cls, value: list[str]) -> list[str]:
        return _normalize_all(value)


class Abstention(StrictModel):
    text: str = Field(min_length=1)
    entities: list[str] = Field(default_factory=list)

    @field_validator("entities")
    @classmethod
    def _normalize(cls, value: list[str]) -> list[str]:
        return _normalize_all(value)


class Answer(StrictModel):
    schema_version: SchemaVersion = 1
    question_id: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    producer: str = Field(min_length=1)
    entities: list[EntityRef] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    abstentions: list[Abstention] = Field(default_factory=list)
    final_text: str = ""

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        self.entities = _dedupe(self.entities)
        declared: dict[str, set[EntityType]] = {}
        for entity in self.entities:
            declared.setdefault(entity.id, set()).add(entity.type)
        claim_ids: set[str] = set()
        for claim in self.claims:
            if claim.id in claim_ids:
                raise ValueError(f"duplicate claim id {claim.id!r}")
            claim_ids.add(claim.id)
            _check_declared(claim.entities, declared, f"claim {claim.id!r}")
            if claim.relation is not None:
                _check_relation(claim.relation, declared, claim.id)
        for abstention in self.abstentions:
            _check_declared(abstention.entities, declared, "abstention")
        return self

    def entities_of_type(self, entity_type: EntityType) -> set[EntityRef]:
        return {e for e in self.entities if e.type == entity_type}


def _dedupe(entities: list[EntityRef]) -> list[EntityRef]:
    seen: set[EntityRef] = set()
    unique: list[EntityRef] = []
    for entity in entities:
        if entity not in seen:
            seen.add(entity)
            unique.append(entity)
    return unique


def _check_declared(ids: list[str], declared: dict[str, set[EntityType]], owner: str) -> None:
    for entity_id in ids:
        if entity_id not in declared:
            raise ValueError(f"{owner} references entity {entity_id!r} not declared in entities")


def _check_relation(
    relation: Relation, declared: dict[str, set[EntityType]], claim_id: str
) -> None:
    if "program" not in declared.get(relation.subject, set()):
        raise ValueError(
            f"claim {claim_id!r}: relation subject {relation.subject!r} must be a declared program"
        )
    expected = RELATION_OBJECT_TYPE[relation.predicate]
    if expected not in declared.get(relation.object, set()):
        raise ValueError(
            f"claim {claim_id!r}: relation object {relation.object!r} must be a declared {expected}"
        )
