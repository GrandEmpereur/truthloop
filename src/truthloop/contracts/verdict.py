"""verdict.json contract (spec §4.5)."""

from __future__ import annotations

from typing import Final, Literal, Self, get_args

from pydantic import Field, model_validator

from truthloop.contracts.common import CapName, ComponentName, EntityRef, SchemaVersion, StrictModel
from truthloop.contracts.repair_plan import RepairPlan

Severity = Literal["critical", "major", "info"]
Decision = Literal["release", "repair", "escalate", "invalid"]
FindingCode = Literal[
    "UNKNOWN_ENTITY",
    "UNKNOWN_PIVOT",
    "MISSING_ENTITY",
    "EXTRA_ENTITY",
    "MISSING_TABLE",
    "UNSUPPORTED_CLAIM",
    "DANGLING_CITATION",
    "NO_CLAIMS",
    "CONTRADICTED_BY_GRAPH",
    "CONTRADICTED_BY_EVIDENCE",
    "JUDGE_MISSING",
    "JUDGE_INCOMPLETE",
    "JUDGE_UNSUPPORTED",
    "JUDGE_PARTIAL",
    "MOJIBAKE",
]

# Derived from the Literal aliases (rather than duplicated as string tuples) so the two
# representations can never drift apart.
COMPONENT_NAMES: Final[tuple[str, ...]] = get_args(ComponentName)
CAP_NAMES: Final[tuple[str, ...]] = get_args(CapName)


class Finding(StrictModel):
    code: FindingCode
    severity: Severity
    detail: str
    entity: EntityRef | None = None
    claim_id: str | None = None
    depth: int | None = None
    via: str | None = None


class Component(StrictModel):
    value: float | None
    weight: float = Field(ge=0.0)
    applicable: bool


class CapApplied(StrictModel):
    name: CapName
    value: int = Field(ge=0, le=100)


class Provenance(StrictModel):
    harness_version: str
    inputs_sha256: str
    config_sha256: str
    knowledge_source: str
    knowledge_fingerprint: str
    generated_at: str


class Verdict(StrictModel):
    schema_version: SchemaVersion = 1
    question_id: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    score: float = Field(ge=0.0, le=100.0)
    decision: Decision
    threshold: float = Field(ge=0.0, le=100.0)
    components: dict[str, Component]
    caps_applied: list[CapApplied] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    declared_gaps: list[str] = Field(default_factory=list)
    repair_plan: RepairPlan
    provenance: Provenance

    @model_validator(mode="after")
    def _components_are_complete(self) -> Self:
        if set(self.components) != set(COMPONENT_NAMES):
            raise ValueError(f"components doit contenir exactement {sorted(COMPONENT_NAMES)}")
        return self


def finding_target(finding: Finding) -> str:
    """The claim or entity a finding is about, for display and diffing (spec §8.2)."""
    return finding.claim_id or (finding.entity.id if finding.entity is not None else "")
