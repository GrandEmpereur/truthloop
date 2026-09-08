"""Types shared by all graders (spec §6)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from truthloop.contracts.answer import Answer
from truthloop.contracts.common import CapName, ComponentName
from truthloop.contracts.evidence import Evidence
from truthloop.contracts.judge import Judge
from truthloop.contracts.question import Question
from truthloop.contracts.verdict import Finding
from truthloop.knowledge import KnowledgeSource


@dataclass(frozen=True)
class GraderContext:
    question: Question
    answer: Answer
    evidence: Evidence
    judge: Judge | None
    knowledge: KnowledgeSource


@dataclass(frozen=True)
class GraderResult:
    """One component value (or a gate-only result when ``component`` is None)."""

    component: ComponentName | None
    value: float | None
    findings: tuple[Finding, ...] = ()
    # ``cap`` names a key of ``scoring.caps``; ``scoring.aggregate`` resolves it to a value.
    cap: CapName | None = None
    expected_size: int | None = None


Grader = Callable[[GraderContext], list[GraderResult]]
