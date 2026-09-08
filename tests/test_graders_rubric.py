import pytest

from conftest import ContextBuilder
from helpers import sample_answer, sample_judge
from truthloop.graders.rubric import grade_rubric


def test_missing_judge(make_ctx: ContextBuilder) -> None:
    faith, rel = grade_rubric(make_ctx(no_judge=True))
    assert (faith.component, faith.value, faith.cap) == ("faithfulness", None, "missing_judge")
    assert [f.code for f in faith.findings] == ["JUDGE_MISSING"]
    assert (rel.component, rel.value) == ("relevance_completeness", None)


def test_sample_judge(make_ctx: ContextBuilder) -> None:
    faith, rel = grade_rubric(make_ctx())
    assert faith.value == 1.0
    assert faith.findings == ()
    assert rel.value == pytest.approx(0.8)


def test_verdict_mapping_and_incomplete(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        claims=[
            {"id": f"c{i}", "text": "t", "entities": [], "citations": ["ev-1"]} for i in range(1, 6)
        ]
    )
    judge = sample_judge(
        claims=[
            {"id": "c1", "verdict": "supported"},
            {"id": "c2", "verdict": "partially"},
            {"id": "c3", "verdict": "unsupported"},
            {"id": "c4", "verdict": "contradicted"},
        ]
    )
    faith, _ = grade_rubric(make_ctx(answer=answer, judge=judge))
    assert faith.value == pytest.approx(1.5 / 5)
    assert [(f.code, f.severity, f.claim_id) for f in faith.findings] == [
        ("JUDGE_PARTIAL", "info", "c2"),
        ("JUDGE_UNSUPPORTED", "major", "c3"),
        ("CONTRADICTED_BY_EVIDENCE", "critical", "c4"),
        ("JUDGE_INCOMPLETE", "major", "c5"),
    ]
    assert faith.cap == "contradiction"


def test_no_claims_gives_not_applicable_faithfulness(make_ctx: ContextBuilder) -> None:
    faith, rel = grade_rubric(
        make_ctx(answer=sample_answer(claims=[]), judge=sample_judge(claims=[]))
    )
    assert faith.value is None
    assert faith.findings == ()
    assert rel.value == pytest.approx(0.8)
