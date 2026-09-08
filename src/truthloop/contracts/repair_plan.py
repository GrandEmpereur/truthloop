"""repair_plan contract embedded in verdict.json (spec §7)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from truthloop.contracts.common import EntityType, SchemaVersion, StrictModel

ActionKind = Literal[
    "retrieve_entities",
    "verify_claim",
    "write_claims",
    "improve_answer",
    "fix_question",
    "run_judge",
    "fix_contract",
]


class RepairEntity(StrictModel):
    type: EntityType
    id: str = Field(min_length=1)
    depth: int | None = None
    via: str | None = None


class RetrievalQueries(StrictModel):
    graph: str
    rag: str


class ContractError(StrictModel):
    loc: str
    msg: str


class RepairAction(StrictModel):
    id: str = Field(min_length=1)
    kind: ActionKind
    priority: int = Field(ge=1)
    expected_gain: float = Field(ge=0.0)
    instruction: str
    entities: list[RepairEntity] = Field(default_factory=list)
    queries: RetrievalQueries | None = None
    claim_ids: list[str] = Field(default_factory=list)
    component: str | None = None
    errors: list[ContractError] = Field(default_factory=list)


class RepairPlan(StrictModel):
    schema_version: SchemaVersion = 1
    actions: list[RepairAction] = Field(default_factory=list)
    summary_for_agent: str = ""
