"""Rubric adapter: turns judge.json into faithfulness and relevance_completeness (spec §6)."""

from __future__ import annotations

from typing import assert_never

from truthloop.contracts.verdict import Finding, FindingCode, Severity
from truthloop.graders.base import GraderContext, GraderResult


def grade_rubric(ctx: GraderContext) -> list[GraderResult]:
    judge = ctx.judge
    if judge is None:
        finding = Finding(
            code="JUDGE_MISSING",
            severity="major",
            detail="judge.json absent : aucune revue sémantique.",
        )
        return [
            GraderResult(
                component="faithfulness", value=None, findings=(finding,), cap="missing_judge"
            ),
            GraderResult(component="relevance_completeness", value=None),
        ]
    verdicts = judge.verdict_by_claim()
    findings: list[Finding] = []
    points = 0.0
    contradicted = False
    for claim in ctx.answer.claims:
        verdict = verdicts.get(claim.id)
        if verdict is None:
            findings.append(
                _finding("JUDGE_INCOMPLETE", "major", claim.id, "Claim non jugée : la faire juger.")
            )
        elif verdict == "supported":
            points += 1.0
        elif verdict == "partially":
            points += 0.5
            findings.append(
                _finding(
                    "JUDGE_PARTIAL",
                    "info",
                    claim.id,
                    "Claim partiellement supportée : la préciser.",
                )
            )
        elif verdict == "unsupported":
            findings.append(
                _finding(
                    "JUDGE_UNSUPPORTED", "major", claim.id, "Le juge ne trouve pas de support."
                )
            )
        elif verdict == "contradicted":
            contradicted = True
            findings.append(
                _finding(
                    "CONTRADICTED_BY_EVIDENCE",
                    "critical",
                    claim.id,
                    "Le juge estime la claim contredite.",
                )
            )
        else:
            assert_never(verdict)
    faithfulness = points / len(ctx.answer.claims) if ctx.answer.claims else None
    relevance = (judge.relevance + judge.completeness) / 2
    return [
        GraderResult(
            component="faithfulness",
            value=faithfulness,
            findings=tuple(findings),
            cap="contradiction" if contradicted else None,
        ),
        GraderResult(component="relevance_completeness", value=relevance),
    ]


def _finding(code: FindingCode, severity: Severity, claim_id: str, detail: str) -> Finding:
    return Finding(code=code, severity=severity, claim_id=claim_id, detail=detail)
