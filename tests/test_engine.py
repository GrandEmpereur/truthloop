from datetime import UTC, datetime

import pytest

from conftest import FIXTURES, RunBuilder
from helpers import (
    files_config,
    release_answer,
    sample_answer,
    sample_evidence,
    sample_judge,
    sample_question,
)
from truthloop.config import Config
from truthloop.engine import EXIT_CODES, evaluate
from truthloop.knowledge.graph import InMemoryGraph
from truthloop.runs import RunDir, RunError

NOW = datetime(2026, 9, 8, 19, 40, 12, tzinfo=UTC)


@pytest.fixture
def config() -> Config:
    return Config.model_validate(files_config(FIXTURES / "graph.json"))


def test_sample_run_is_repair(make_run: RunBuilder, config: Config, graph: InMemoryGraph) -> None:
    run = RunDir(
        make_run(sample_question(), sample_answer(), sample_evidence(), sample_judge(notes="n"))
    )
    verdict = evaluate(run, config, graph, now=NOW)
    assert verdict.decision == "repair"
    assert verdict.score == 69.3  # round(69.25, 1); confirmed by direct measurement
    assert verdict.threshold == 90.0
    assert verdict.components["context_recall"].value == 0.5
    assert verdict.declared_gaps == ["Profondeur 2 non explorée."]
    assert [a.kind for a in verdict.repair_plan.actions] == [
        "retrieve_entities",
        "retrieve_entities",
    ]
    assert verdict.provenance.generated_at == "2026-09-08T19:40:12+00:00"
    assert verdict.provenance.knowledge_source.startswith("files:")
    assert run.verdict_path(1).is_file()
    assert run.read_trace()[0]["decision"] == "repair"
    assert EXIT_CODES[verdict.decision] == 2


def test_release_run(make_run: RunBuilder, config: Config, graph: InMemoryGraph) -> None:
    judge = sample_judge(relevance=0.9, completeness=0.9)
    run = RunDir(make_run(sample_question(), release_answer(), sample_evidence(), judge))
    verdict = evaluate(run, config, graph, now=NOW)
    assert verdict.decision == "release"
    assert verdict.score == pytest.approx(99.0)
    assert verdict.repair_plan.actions == []
    assert EXIT_CODES["release"] == 0


def test_invalid_bundle(make_run: RunBuilder, config: Config, graph: InMemoryGraph) -> None:
    run = RunDir(make_run(sample_question(), None, sample_evidence(), None))
    verdict = evaluate(run, config, graph, now=NOW)
    assert (verdict.decision, verdict.score) == ("invalid", 0.0)
    assert all(not c.applicable for c in verdict.components.values())
    [action] = verdict.repair_plan.actions
    assert action.kind == "fix_contract"
    assert action.errors[0].loc == "answer"
    assert EXIT_CODES["invalid"] == 4


def test_missing_judge_caps_and_plans_run_judge(
    make_run: RunBuilder, config: Config, graph: InMemoryGraph
) -> None:
    judge = None
    run = RunDir(make_run(sample_question(), release_answer(), sample_evidence(), judge))
    verdict = evaluate(run, config, graph, now=NOW)
    assert [c.name for c in verdict.caps_applied] == ["missing_judge"]
    assert verdict.score == 85.0
    assert any(a.kind == "run_judge" for a in verdict.repair_plan.actions)


def test_escalate_at_max_iterations(
    make_run: RunBuilder, config: Config, graph: InMemoryGraph
) -> None:
    run_dir = make_run(
        sample_question(),
        sample_answer(iteration=3),
        sample_evidence(iteration=3),
        sample_judge(iteration=3),
        iteration=3,
    )
    verdict = evaluate(RunDir(run_dir), config, graph, now=NOW)
    assert verdict.decision == "escalate"
    assert len(verdict.repair_plan.actions) >= 1
    assert EXIT_CODES["escalate"] == 3


def test_verdict_is_deterministic(
    make_run: RunBuilder, config: Config, graph: InMemoryGraph
) -> None:
    run = RunDir(make_run(sample_question(), sample_answer(), sample_evidence(), sample_judge()))
    other_now = datetime(2026, 9, 9, 8, 0, 0, tzinfo=UTC)
    first = evaluate(run, config, graph, now=NOW)
    second = evaluate(run, config, graph, now=other_now)
    assert first.model_dump(exclude={"provenance": {"generated_at"}}) == second.model_dump(
        exclude={"provenance": {"generated_at"}}
    )


def test_explicit_iteration_and_missing_iteration(
    make_run: RunBuilder, config: Config, graph: InMemoryGraph
) -> None:
    run = RunDir(make_run(sample_question(), sample_answer(), sample_evidence(), sample_judge()))
    assert evaluate(run, config, graph, iteration=1, now=NOW).iteration == 1
    with pytest.raises(RunError, match="itération 2"):
        evaluate(run, config, graph, iteration=2, now=NOW)


def test_iteration_below_one_is_rejected(
    make_run: RunBuilder, config: Config, graph: InMemoryGraph
) -> None:
    run = RunDir(make_run(sample_question(), sample_answer(), sample_evidence(), sample_judge()))
    with pytest.raises(RunError, match="invalide"):
        evaluate(run, config, graph, iteration=0, now=NOW)


def test_mojibake_blocks_release_without_lowering_the_score(
    make_run: RunBuilder, config: Config, graph: InMemoryGraph
) -> None:
    judge = sample_judge(relevance=0.9, completeness=0.9)
    answer = {**release_answer(), "final_text": "RÃ©ponse publiÃ©e avec un double encodage."}
    run = RunDir(make_run(sample_question(), answer, sample_evidence(), judge))
    verdict = evaluate(run, config, graph, now=NOW)
    assert verdict.decision == "repair"
    assert verdict.score == pytest.approx(99.0)
    assert verdict.caps_applied == []
    assert [f.code for f in verdict.findings] == ["MOJIBAKE"]
    assert verdict.repair_plan.actions[0].kind == "improve_answer"
