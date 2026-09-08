from pathlib import Path

from conftest import RunBuilder
from helpers import sample_answer, sample_evidence, sample_judge, sample_question
from truthloop.contracts.bundle import load_iteration
from truthloop.contracts.question import Question


def _question() -> Question:
    return Question.model_validate(sample_question())


def test_load_iteration_happy_path(make_run: RunBuilder) -> None:
    run_dir = make_run(sample_question(), sample_answer(), sample_evidence(), sample_judge())
    loaded = load_iteration(_question(), run_dir / "iter-01", 1)
    assert loaded.errors == []
    assert loaded.bundle is not None
    assert loaded.bundle.judge is not None
    assert set(loaded.raw) == {"answer", "evidence", "judge"}


def test_missing_judge_is_not_an_error(make_run: RunBuilder) -> None:
    run_dir = make_run(sample_question(), sample_answer(), sample_evidence(), None)
    loaded = load_iteration(_question(), run_dir / "iter-01", 1)
    assert loaded.errors == []
    assert loaded.bundle is not None
    assert loaded.bundle.judge is None
    assert "judge" not in loaded.raw


def test_missing_answer_and_invalid_json_are_reported(make_run: RunBuilder) -> None:
    run_dir = make_run(sample_question(), None, sample_evidence(), None)
    (run_dir / "iter-01" / "evidence.json").write_text("{not json", encoding="utf-8")
    loaded = load_iteration(_question(), run_dir / "iter-01", 1)
    assert loaded.bundle is None
    locs = [e.loc for e in loaded.errors]
    assert "answer" in locs
    assert "evidence" in locs


def test_schema_errors_carry_pydantic_location(make_run: RunBuilder) -> None:
    run_dir = make_run(sample_question(), sample_answer(iteration="1"), sample_evidence(), None)
    loaded = load_iteration(_question(), run_dir / "iter-01", 1)
    assert loaded.bundle is None
    assert loaded.errors[0].loc == "answer.iteration"


def test_cross_checks(make_run: RunBuilder) -> None:
    judge = sample_judge(claims=[{"id": "c9", "verdict": "supported"}], question_id="other")
    run_dir = make_run(sample_question(), sample_answer(), sample_evidence(iteration=2), judge)
    loaded = load_iteration(_question(), run_dir / "iter-01", 1)
    assert loaded.bundle is None
    locs = {e.loc for e in loaded.errors}
    assert {"evidence.iteration", "judge.question_id", "judge.claims.0.id"} <= locs


def test_directory_without_files(tmp_path: Path) -> None:
    loaded = load_iteration(_question(), tmp_path / "iter-01", 1)
    assert loaded.bundle is None
    assert [e.loc for e in loaded.errors] == ["answer", "evidence"]


def test_non_object_json_is_a_contract_error(make_run: RunBuilder) -> None:
    run_dir = make_run(sample_question(), sample_answer(), sample_evidence(), None)
    (run_dir / "iter-01" / "judge.json").write_text("null", encoding="utf-8")
    loaded = load_iteration(_question(), run_dir / "iter-01", 1)
    assert loaded.bundle is None
    assert [e.loc for e in loaded.errors] == ["judge"]
    assert loaded.errors[0].msg == "objet JSON attendu"


def test_undecodable_file_is_a_contract_error(make_run: RunBuilder) -> None:
    run_dir = make_run(sample_question(), sample_answer(), sample_evidence(), None)
    (run_dir / "iter-01" / "answer.json").write_bytes(b"\xff\xfe{")
    loaded = load_iteration(_question(), run_dir / "iter-01", 1)
    assert loaded.bundle is None
    assert loaded.errors[0].loc == "answer"
    assert loaded.errors[0].msg.startswith("JSON invalide")
