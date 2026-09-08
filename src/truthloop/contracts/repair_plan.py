"""repair_plan contract embedded in verdict.json (spec §7)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from truthloop.contracts.common import ComponentName, EntityType, SchemaVersion, StrictModel

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
    kind: ActionKind = Field(description="Category of repair the orchestrator agent should run.")
    priority: int = Field(
        ge=1, description="Execution order among the plan's actions; 1 = do first."
    )
    expected_gain: float = Field(
        ge=0.0, description="Estimated verdict score increase, in score points, if completed."
    )
    instruction: str = Field(
        description="Natural-language instruction telling the agent exactly what to do."
    )
    entities: list[RepairEntity] = Field(
        default_factory=list,
        description="Knowledge-graph entities this action concerns, with depth/path when known.",
    )
    queries: RetrievalQueries | None = Field(
        default=None, description="Suggested graph and RAG queries to retrieve the entities."
    )
    claim_ids: list[str] = Field(
        default_factory=list,
        description="Ids of the answer.json claims this action should fix or verify.",
    )
    component: ComponentName | None = Field(
        default=None, description="Score component this action would improve, when it targets one."
    )
    errors: list[ContractError] = Field(
        default_factory=list,
        description="Contract validation errors to fix (present only for kind='fix_contract').",
    )


class RepairPlan(StrictModel):
    schema_version: SchemaVersion = 1
    actions: list[RepairAction] = Field(
        default_factory=list,
        description="Prioritized repair actions, ordered highest priority first.",
    )
    summary_for_agent: str = Field(
        default="",
        description="Short natural-language summary of the plan for the orchestrator agent.",
    )
