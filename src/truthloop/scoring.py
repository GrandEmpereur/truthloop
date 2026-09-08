"""Aggregation with caps and the release decision (spec §6.1, §6.2)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from truthloop.contracts.verdict import COMPONENT_NAMES, CapApplied, Component, Decision, Finding
from truthloop.graders.base import GraderResult


@dataclass(frozen=True)
class ScoreBreakdown:
    raw: float
    score: float
    components: dict[str, Component]
    caps_applied: list[CapApplied]


def aggregate(
    results: Sequence[GraderResult], weights: Mapping[str, float], caps: Mapping[str, int]
) -> ScoreBreakdown:
    components = {
        name: Component(value=None, weight=weights[name], applicable=False)
        for name in COMPONENT_NAMES
    }
    for result in results:
        if result.component is not None:
            components[result.component] = Component(
                value=result.value,
                weight=weights[result.component],
                applicable=result.value is not None,
            )
    numerator = sum(
        c.weight * c.value for c in components.values() if c.applicable and c.value is not None
    )
    denominator = sum(c.weight for c in components.values() if c.applicable)
    raw = min(100.0, max(0.0, 100.0 * numerator / denominator)) if denominator > 0 else 0.0
    cap_names = sorted({result.cap for result in results if result.cap is not None})
    caps_applied = [CapApplied(name=name, value=caps[name]) for name in cap_names]
    score = min([raw, *(float(cap.value) for cap in caps_applied)])
    return ScoreBreakdown(raw=raw, score=score, components=components, caps_applied=caps_applied)


def decide(
    score: float,
    findings: Sequence[Finding],
    *,
    coverage_applicable: bool,
    iteration: int,
    max_iterations: int,
    release_threshold: float,
    release_threshold_no_reference: float,
) -> tuple[Decision, float]:
    threshold = release_threshold if coverage_applicable else release_threshold_no_reference
    has_critical = any(finding.severity == "critical" for finding in findings)
    if score >= threshold and not has_critical:
        return "release", threshold
    if iteration < max_iterations:
        return "repair", threshold
    return "escalate", threshold
