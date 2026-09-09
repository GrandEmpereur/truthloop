import shutil
from importlib import resources
from pathlib import Path

import yaml

from truthloop.config import DEFAULT_CONFIG_YAML, Config, load_config
from truthloop.contracts.answer import Answer
from truthloop.contracts.evidence import Evidence
from truthloop.contracts.judge import Judge
from truthloop.contracts.question import Question
from truthloop.engine import evaluate
from truthloop.knowledge.factory import open_knowledge
from truthloop.runs import RunDir

FIXTURE_GRAPH = Path(__file__).parent / "fixtures" / "graph.json"


def kit_path(relative: str) -> Path:
    root = resources.files("truthloop.integration.copilot")
    with resources.as_file(root / relative) as path:
        return Path(path)


def test_smoke_graph_is_the_phase1_fixture() -> None:
    assert kit_path("smoke/graph.json").read_text(encoding="utf-8") == FIXTURE_GRAPH.read_text(
        encoding="utf-8"
    )


def test_smoke_config_uses_default_scoring() -> None:
    config = load_config(kit_path("smoke/truthloop.yaml"))
    assert config.knowledge.kind == "files"
    assert config.knowledge.path == "graph.json"
    default = Config.model_validate(yaml.safe_load(DEFAULT_CONFIG_YAML))
    assert config.scoring == default.scoring
    assert config.loop == default.loop


def test_smoke_run_files_are_valid_contracts() -> None:
    run = kit_path("smoke/run")
    Question.model_validate_json((run / "question.json").read_text(encoding="utf-8"))
    Answer.model_validate_json((run / "iter-01" / "answer.json").read_text(encoding="utf-8"))
    Evidence.model_validate_json((run / "iter-01" / "evidence.json").read_text(encoding="utf-8"))
    Judge.model_validate_json((run / "iter-01" / "judge.json").read_text(encoding="utf-8"))


def test_smoke_run_evaluates_to_repair_with_two_actions(tmp_path: Path) -> None:
    shutil.copytree(kit_path("smoke/run"), tmp_path / "smoke")
    config_path = kit_path("smoke/truthloop.yaml")
    config = load_config(config_path)
    knowledge = open_knowledge(
        config.knowledge.kind, config_path.parent / config.knowledge.path, config.knowledge.queries
    )
    verdict = evaluate(RunDir(tmp_path / "smoke"), config, knowledge)
    assert verdict.decision == "repair"
    assert verdict.score == 69.3
    assert [a.kind for a in verdict.repair_plan.actions] == [
        "retrieve_entities",
        "retrieve_entities",
    ]
