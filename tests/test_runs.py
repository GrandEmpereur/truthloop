import json
from pathlib import Path

import pytest

from conftest import RunBuilder
from helpers import sample_answer, sample_question
from truthloop.contracts.repair_plan import RepairPlan
from truthloop.contracts.verdict import COMPONENT_NAMES, Component, Provenance, Verdict
from truthloop.runs import RunDir, RunError, TraceRow, canonical_json, inputs_sha256


def _verdict(iteration: int) -> Verdict:
    return Verdict(
        question_id="q-001",
        iteration=iteration,
        score=0.0,
        decision="invalid",
        threshold=90.0,
        components={
            name: Component(value=None, weight=0.2, applicable=False) for name in COMPONENT_NAMES
        },
        repair_plan=RepairPlan(),
        provenance=Provenance(
            harness_version="0.1.0",
            inputs_sha256="0" * 64,
            config_sha256="0" * 64,
            knowledge_source="files:x",
            knowledge_fingerprint="0" * 64,
            generated_at="2026-09-08T19:40:12+00:00",
        ),
    )


def test_canonical_json_and_inputs_hash() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'
    assert canonical_json({"é": "ü"}) == '{"é":"ü"}'
    same = inputs_sha256([{"a": 1}, None, {"b": 2}])
    assert same == inputs_sha256([{"a": 1}, None, {"b": 2}])
    assert same != inputs_sha256([{"b": 2}, None, {"a": 1}])
    assert inputs_sha256([{"a": 1}, None]) != inputs_sha256([None, {"a": 1}])
    assert len(same) == 64


def test_run_dir_iterations_and_question(make_run: RunBuilder) -> None:
    run_dir = make_run(sample_question(), sample_answer(), None, None, iteration=1)
    make_run(None, sample_answer(iteration=3), None, None, iteration=3)
    run = RunDir(run_dir)
    assert run.iterations() == [1, 3]
    assert run.latest_iteration() == 3
    assert run.iteration_path(3).name == "iter-03"
    question, raw = run.load_question()
    assert question.id == "q-001"
    assert isinstance(raw, dict)


def test_run_dir_errors(tmp_path: Path, make_run: RunBuilder) -> None:
    with pytest.raises(RunError, match=r"question\.json"):
        RunDir(tmp_path / "missing").load_question()
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RunError, match="itération"):
        RunDir(empty).latest_iteration()
    run_dir = make_run(sample_question(text=""), None, None, None)
    with pytest.raises(RunError, match=r"question\.text"):
        RunDir(run_dir).load_question()


def test_question_json_with_invalid_encoding_is_illisible(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "question.json").write_bytes(b"\xff\xfe{")
    with pytest.raises(RunError, match="illisible"):
        RunDir(run_dir).load_question()


def test_trace_append_and_read(make_run: RunBuilder) -> None:
    run = RunDir(make_run(sample_question(), None, None, None))
    run.append_trace(
        {"ts": "t1", "iteration": 1, "event": "verify", "score": 10.0, "decision": "repair"}
    )
    run.append_trace(
        {"ts": "t2", "iteration": 2, "event": "verify", "score": 95.0, "decision": "release"}
    )
    rows = run.read_trace()
    assert [r["iteration"] for r in rows] == [1, 2]
    assert (run.path / "trace.jsonl").read_text(encoding="utf-8").count("\n") == 2
    assert (
        json.loads((run.path / "trace.jsonl").read_text(encoding="utf-8").splitlines()[0])[
            "decision"
        ]
        == "repair"
    )


def test_iteration_dirs_are_strict(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    for name in ("iter-01", "iter-1", "iter-00", "iter-abc", "iter-03"):
        (run_dir / name).mkdir(parents=True)
    assert RunDir(run_dir).iterations() == [1, 3]
    # "iter-001" is not the canonical name for 1 ("iter-01"), so it is ignored, not an error.
    (run_dir / "iter-001").mkdir()
    assert RunDir(run_dir).iterations() == [1, 3]


def test_verdict_round_trip_and_errors(make_run: RunBuilder) -> None:
    run = RunDir(make_run(sample_question(), None, None, None))
    assert run.load_verdict(1) is None
    verdict = _verdict(1)
    path = run.write_verdict(verdict)
    assert path == run.verdict_path(1)
    assert not path.with_name(path.name + ".tmp").exists()
    assert run.load_verdict(1) == verdict
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RunError, match="illisible"):
        run.load_verdict(1)
    path.write_text('{"schema_version": 1}', encoding="utf-8")
    with pytest.raises(RunError, match="invalide"):
        run.load_verdict(1)


def test_run_dir_history(make_run: RunBuilder) -> None:
    run = RunDir(make_run(sample_question(), None, None, None, iteration=1))
    run.write_verdict(_verdict(1))
    (run.path / "iter-02").mkdir()
    rows = run.history()
    assert rows == [
        TraceRow(iteration=1, score=0.0, decision="invalid", open_findings=0, resolved_findings=0),
        TraceRow(
            iteration=2,
            score=None,
            decision=None,
            open_findings=0,
            resolved_findings=0,
        ),
    ]


def test_trace_errors(make_run: RunBuilder) -> None:
    run = RunDir(make_run(sample_question(), None, None, None))
    run.trace_path.write_text('{"a": 1}\n\nnot json\n', encoding="utf-8")
    with pytest.raises(RunError, match="ligne 3"):
        run.read_trace()
    run.trace_path.write_text("[1, 2]\n", encoding="utf-8")
    with pytest.raises(RunError, match="objet JSON attendu"):
        run.read_trace()
