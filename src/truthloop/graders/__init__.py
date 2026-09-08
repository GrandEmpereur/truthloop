"""Deterministic graders (spec §6). Order matters for finding order in the verdict."""

from __future__ import annotations

from typing import Final

from truthloop.graders.base import Grader, GraderContext, GraderResult
from truthloop.graders.citation import grade_citations
from truthloop.graders.consistency import grade_consistency
from truthloop.graders.coverage import grade_coverage
from truthloop.graders.evidence import grade_evidence
from truthloop.graders.rubric import grade_rubric

ALL_GRADERS: Final[tuple[Grader, ...]] = (
    grade_citations,
    grade_coverage,
    grade_evidence,
    grade_consistency,
    grade_rubric,
)


def run_graders(ctx: GraderContext) -> list[GraderResult]:
    return [result for grader in ALL_GRADERS for result in grader(ctx)]


__all__ = ["ALL_GRADERS", "GraderContext", "GraderResult", "run_graders"]
