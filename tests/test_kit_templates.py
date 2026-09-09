import json
import re
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
from truthloop.integration.installer import _RETRIEVERS_TOKEN, render
from truthloop.knowledge.factory import open_knowledge
from truthloop.runs import RunDir

FIXTURE_GRAPH = Path(__file__).parent / "fixtures" / "graph.json"

SUBS = {"TRUTHLOOP_PROJECT": "/abs/truthloop", "MAX_ITERATIONS": "3"}

JSON_BLOCK = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


def kit_path(relative: str) -> Path:
    root = resources.files("truthloop.integration.copilot")
    with resources.as_file(root / relative) as path:
        return Path(path)


def frontmatter(text: str) -> dict[str, object]:
    assert text.startswith("---\n"), "frontmatter attendu"
    _, block, _ = text.split("---\n", 2)
    data = yaml.safe_load(block)
    assert isinstance(data, dict)
    return data


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


def test_orchestrator_template_before_and_after_substitution() -> None:
    raw = kit_path("agents/truthloop-orchestrator.agent.md").read_text(encoding="utf-8")
    meta = frontmatter(raw)
    assert meta["name"] == "truthloop-orchestrator"
    assert meta["tools"] == ["agent", "runCommands", "read", "edit", "search"]
    assert meta["agents"] == ["truthloop-judge", "{{RETRIEVER_AGENTS}}"]
    handoffs = meta["handoffs"]
    assert isinstance(handoffs, list)
    assert handoffs[0]["label"] == "Escalader à un humain"
    rendered = render(raw, SUBS, ["rag-agent", "graph-agent"])
    assert frontmatter(rendered)["agents"] == ["truthloop-judge", "rag-agent", "graph-agent"]
    assert "{{" not in rendered
    assert "Au plus 3 itérations" in rendered
    for kind in (
        "retrieve_entities",
        "verify_claim",
        "write_claims",
        "improve_answer",
        "run_judge",
        "fix_question",
        "fix_contract",
    ):
        assert kind in rendered
    assert "truthloop-contract.instructions.md" in rendered
    assert "Consigne à copier" in rendered
    assert "n'interroge jamais directement la base de connaissance" in rendered


def test_judge_template() -> None:
    raw = kit_path("agents/truthloop-judge.agent.md").read_text(encoding="utf-8")
    meta = frontmatter(raw)
    assert meta["name"] == "truthloop-judge"
    assert meta["user-invocable"] is False
    assert meta["tools"] == ["runCommands", "read", "edit"]
    rendered = render(raw, SUBS, [])
    assert "{{" not in rendered
    assert 'uv run --project "/abs/truthloop" truthloop verify' in rendered
    assert "judge.json" in rendered
    for verdict in ("supported", "partially", "unsupported", "contradicted"):
        assert verdict in rendered
    assert "decision: error" in rendered
    for prefix in ("score:", "decision:", "verdict:", "summary:"):
        assert prefix in rendered


def test_contract_examples_are_valid() -> None:
    raw = kit_path("instructions/truthloop-contract.instructions.md").read_text(encoding="utf-8")
    assert frontmatter(raw)["description"]
    assert "Consigne à copier" in raw
    assert "raw_target" in raw  # graph chunk context recommendation
    blocks = [json.loads(b) for b in JSON_BLOCK.findall(raw)]
    assert len(blocks) == 3, "fragment, answer.json, evidence.json"
    fragment, answer, evidence = blocks
    assert set(fragment) == {"entities", "claims", "chunks", "abstentions"}
    Answer.model_validate(
        {
            "schema_version": 1,
            "question_id": "q",
            "iteration": 1,
            "producer": "truthloop-orchestrator",
            "entities": fragment["entities"],
            "claims": fragment["claims"],
            "abstentions": fragment["abstentions"],
            "final_text": "x",
        }
    )
    Evidence.model_validate(
        {"schema_version": 1, "question_id": "q", "iteration": 1, "chunks": fragment["chunks"]}
    )
    parsed_answer = Answer.model_validate(answer)
    parsed_evidence = Evidence.model_validate(evidence)
    chunk_ids = set(parsed_evidence.chunk_by_id())
    assert all(set(c.citations) <= chunk_ids for c in parsed_answer.claims)
    assert "{{" not in render(raw, SUBS, [])


def test_install_prompt_and_acceptance() -> None:
    prompt = kit_path("prompts/truthloop-install.prompt.md").read_text(encoding="utf-8")
    meta = frontmatter(prompt)
    assert meta["name"] == "truthloop-install"
    assert meta["tools"] == ["read", "edit", "search", "runCommands"]
    assert _RETRIEVERS_TOKEN in prompt
    rendered = render(prompt, SUBS, [])
    assert "'{{RETRIEVER_AGENTS}}'" in rendered  # the token Copilot must look for, left verbatim
    assert "{{" not in rendered.replace("'{{RETRIEVER_AGENTS}}'", "")
    assert ".github/truthloop/smoke/truthloop.yaml" in rendered
    assert "--version" in rendered
    assert "expert de domaine" in rendered
    assert "retriever graphe" in rendered
    acceptance = render(kit_path("ACCEPTANCE.md").read_text(encoding="utf-8"), SUBS, [])
    assert "{{" not in acceptance
    assert acceptance.count("- [ ]") >= 6
