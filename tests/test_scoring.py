import pytest

from conftest import ContextBuilder
from truthloop.contracts.verdict import COMPONENT_NAMES, Finding
from truthloop.graders import run_graders
from truthloop.graders.base import GraderResult
from truthloop.scoring import aggregate, decide

WEIGHTS = {
    "context_recall": 0.35,
    "table_recall": 0.15,
    "evidence_support": 0.15,
    "faithfulness": 0.25,
    "relevance_completeness": 0.10,
}
CAPS = {"unknown_entity": 50, "contradiction": 70, "missing_judge": 85, "missing_claims": 85}


def _results(**values: float | None) -> list[GraderResult]:
    return [GraderResult(component=name, value=values.get(name)) for name in COMPONENT_NAMES]


def test_spec_example_scores_76_5() -> None:
    results = _results(
        context_recall=0.6,
        table_recall=0.5,
        evidence_support=1.0,
        faithfulness=1.0,
        relevance_completeness=0.8,
    )
    breakdown = aggregate(results, WEIGHTS, CAPS)
    assert breakdown.raw == pytest.approx(76.5)
    assert breakdown.score == pytest.approx(76.5)
    assert breakdown.caps_applied == []
    assert breakdown.components["context_recall"].applicable is True


def test_weights_are_renormalized_over_applicable_components() -> None:
    results = _results(evidence_support=1.0, faithfulness=1.0, relevance_completeness=0.5)
    breakdown = aggregate(results, WEIGHTS, CAPS)
    assert breakdown.raw == pytest.approx(100 * (0.15 + 0.25 + 0.05) / 0.5)
    assert breakdown.components["context_recall"].applicable is False
    assert breakdown.components["context_recall"].weight == 0.35


def test_caps_bound_the_score_and_are_sorted() -> None:
    results = [
        *_results(
            context_recall=1.0,
            table_recall=1.0,
            evidence_support=1.0,
            faithfulness=1.0,
            relevance_completeness=1.0,
        ),
        GraderResult(component=None, value=None, cap="contradiction"),
        GraderResult(component=None, value=None, cap="unknown_entity"),
    ]
    breakdown = aggregate(results, WEIGHTS, CAPS)
    assert breakdown.raw == 100.0
    assert breakdown.score == 50.0
    assert [c.name for c in breakdown.caps_applied] == ["contradiction", "unknown_entity"]


def test_no_applicable_component_gives_zero() -> None:
    assert aggregate(_results(), WEIGHTS, CAPS).raw == 0.0


def test_raw_is_clamped_to_100_despite_float_error() -> None:
    weights = {
        "context_recall": 0.1,
        "table_recall": 0.7,
        "evidence_support": 0.1,
        "faithfulness": 0.05,
        "relevance_completeness": 0.05,
    }
    results = _results(
        context_recall=1.0,
        table_recall=1.0,
        evidence_support=1.0,
        faithfulness=1.0,
        relevance_completeness=1.0,
    )
    breakdown = aggregate(results, weights, CAPS)
    assert breakdown.raw <= 100.0
    assert breakdown.score <= 100.0


def _critical() -> Finding:
    return Finding(code="UNKNOWN_ENTITY", severity="critical", detail="x")


@pytest.mark.parametrize(
    ("score", "findings", "coverage", "iteration", "expected"),
    [
        (90.0, [], True, 1, ("release", 90.0)),
        (89.999, [], True, 1, ("repair", 90.0)),
        (95.0, [_critical()], True, 1, ("repair", 90.0)),
        (94.0, [], False, 1, ("repair", 95.0)),
        (95.0, [], False, 2, ("release", 95.0)),
        (10.0, [], True, 3, ("escalate", 90.0)),
        (10.0, [], True, 4, ("escalate", 90.0)),
    ],
)
def test_decide(
    score: float,
    findings: list[Finding],
    coverage: bool,
    iteration: int,
    expected: tuple[str, float],
) -> None:
    assert (
        decide(
            score,
            findings,
            coverage_applicable=coverage,
            iteration=iteration,
            max_iterations=3,
            release_threshold=90.0,
            release_threshold_no_reference=95.0,
        )
        == expected
    )


def test_run_graders_on_sample(make_ctx: ContextBuilder) -> None:
    results = run_graders(make_ctx())
    components = {r.component: r.value for r in results if r.component}
    assert components == {
        "context_recall": 0.5,
        "table_recall": 0.25,
        "evidence_support": 1.0,
        "faithfulness": 1.0,
        "relevance_completeness": pytest.approx(0.8),
    }
    breakdown = aggregate(results, WEIGHTS, CAPS)
    assert breakdown.raw == pytest.approx(69.25)
