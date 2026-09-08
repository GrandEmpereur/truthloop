"""EvidenceSupport: every claim must rest on a cited chunk that names one of its entities (spec §6)."""

from __future__ import annotations

import re

from truthloop.contracts.answer import Claim
from truthloop.contracts.common import normalize_id
from truthloop.contracts.evidence import Chunk
from truthloop.contracts.verdict import Finding
from truthloop.graders.base import GraderContext, GraderResult

_TOKEN_SPLIT = re.compile(r"[^\w-]+")


def parts_of(text: str) -> list[str]:
    """Split on non-word characters, normalize, then split ids on ``_``; drop empties."""
    return [
        part
        for token in _TOKEN_SPLIT.split(text)
        for part in normalize_id(token).split("_")
        if part
    ]


def contains_id(text: str, entity_id: str) -> bool:
    """True if the id's parts appear as a contiguous run in the text's parts (spec §6)."""
    return contains_parts(parts_of(text), entity_id)


def contains_parts(text_parts: list[str], entity_id: str) -> bool:
    target = parts_of(entity_id)
    width = len(target)
    if width == 0:
        return False
    return any(text_parts[i : i + width] == target for i in range(len(text_parts) - width + 1))


def grade_evidence(ctx: GraderContext) -> list[GraderResult]:
    claims = ctx.answer.claims
    if not claims:
        if ctx.question.intent == "diagram":
            return [GraderResult(component="evidence_support", value=None)]
        finding = Finding(
            code="NO_CLAIMS",
            severity="major",
            detail="Aucune claim : rédiger des claims citées pour les entités présentes.",
        )
        return [
            GraderResult(
                component="evidence_support", value=None, findings=(finding,), cap="missing_claims"
            )
        ]
    chunks = ctx.evidence.chunk_by_id()
    chunk_parts = {chunk_id: parts_of(chunk.text) for chunk_id, chunk in chunks.items()}
    findings: list[Finding] = []
    supported = 0
    for claim in claims:
        present: list[Chunk] = []
        for citation in claim.citations:
            chunk = chunks.get(citation)
            if chunk is None:
                findings.append(
                    Finding(
                        code="DANGLING_CITATION",
                        severity="major",
                        claim_id=claim.id,
                        detail=f"Citation {citation} introuvable dans evidence.json.",
                    )
                )
            else:
                present.append(chunk)
        present_parts = [chunk_parts[chunk.id] for chunk in present]
        if _is_supported(claim, present_parts):
            supported += 1
        else:
            findings.append(
                Finding(
                    code="UNSUPPORTED_CLAIM",
                    severity="major",
                    claim_id=claim.id,
                    detail="Aucune évidence citée ne mentionne une entité de la claim.",
                )
            )
    return [
        GraderResult(
            component="evidence_support", value=supported / len(claims), findings=tuple(findings)
        )
    ]


def _is_supported(claim: Claim, present_parts: list[list[str]]) -> bool:
    if not present_parts:
        return False
    if not claim.entities:
        return True
    return any(
        contains_parts(parts, entity_id) for parts in present_parts for entity_id in claim.entities
    )
