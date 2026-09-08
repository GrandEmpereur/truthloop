import pytest
from pydantic import ValidationError

from truthloop.contracts.evidence import Evidence
from truthloop.contracts.judge import Judge


def _evidence(chunks: list[dict[str, object]]) -> dict[str, object]:
    return {"schema_version": 1, "question_id": "q", "iteration": 1, "chunks": chunks}


def test_evidence_indexes_chunks_by_id() -> None:
    ev = Evidence.model_validate(
        _evidence(
            [
                {"id": "ev-1", "source": "graph:calls", "text": "A -> B", "score": 0.9},
                {"id": "ev-2", "source": "docs/x.md", "text": "…"},
            ]
        )
    )
    assert set(ev.chunk_by_id()) == {"ev-1", "ev-2"}
    assert ev.chunk_by_id()["ev-2"].score is None


def test_evidence_rejects_duplicate_ids_and_bad_score() -> None:
    with pytest.raises(ValidationError):
        Evidence.model_validate(
            _evidence(
                [
                    {"id": "ev-1", "source": "s", "text": "t"},
                    {"id": "ev-1", "source": "s", "text": "t"},
                ]
            )
        )
    with pytest.raises(ValidationError):
        Evidence.model_validate(
            _evidence([{"id": "ev-1", "source": "s", "text": "t", "score": 1.5}])
        )


def _judge(claims: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "question_id": "q",
        "iteration": 1,
        "claims": claims,
        "relevance": 0.9,
        "completeness": 0.7,
    }


def test_judge_maps_verdicts() -> None:
    judge = Judge.model_validate(
        _judge(
            [
                {"id": "c1", "verdict": "supported", "rationale": "ok"},
                {"id": "c2", "verdict": "partially"},
            ]
        )
    )
    assert judge.verdict_by_claim() == {"c1": "supported", "c2": "partially"}
    assert judge.judge_model == ""
    assert judge.notes == ""


def test_judge_rejects_duplicate_claim_and_bad_verdict() -> None:
    with pytest.raises(ValidationError):
        Judge.model_validate(
            _judge([{"id": "c1", "verdict": "supported"}, {"id": "c1", "verdict": "supported"}])
        )
    with pytest.raises(ValidationError):
        Judge.model_validate(_judge([{"id": "c1", "verdict": "maybe"}]))
