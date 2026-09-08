"""judge.json contract, filled by the Copilot judge agent (spec §4.4)."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from truthloop.contracts.common import SchemaVersion, StrictModel

ClaimVerdict = Literal["supported", "partially", "unsupported", "contradicted"]


class JudgedClaim(StrictModel):
    id: str = Field(
        min_length=1, description="Id of the claim being judged; must exist in answer.json."
    )
    verdict: ClaimVerdict = Field(
        description="The judge's assessment of how well this claim holds up."
    )
    rationale: str = Field(default="", description="The judge's short explanation for the verdict.")


class Judge(StrictModel):
    schema_version: SchemaVersion = 1
    question_id: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    judge_model: str = Field(
        default="", description="Identifier of the model or agent that judged."
    )
    claims: list[JudgedClaim] = Field(
        default_factory=list, description="Per-claim verdicts covering answer.json's claims."
    )
    relevance: float = Field(
        ge=0.0, le=1.0, description="How relevant the answer is to the question, 0 to 1."
    )
    completeness: float = Field(
        ge=0.0, le=1.0, description="How completely the answer covers the question, 0 to 1."
    )
    notes: str = Field(
        default="", description="Free-form notes from the judge about the answer overall."
    )

    @model_validator(mode="after")
    def _unique_claim_ids(self) -> Self:
        seen: set[str] = set()
        for claim in self.claims:
            if claim.id in seen:
                raise ValueError(f"duplicate judged claim id {claim.id!r}")
            seen.add(claim.id)
        return self

    def verdict_by_claim(self) -> dict[str, ClaimVerdict]:
        return {claim.id: claim.verdict for claim in self.claims}
