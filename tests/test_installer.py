import hashlib
from pathlib import Path

import pytest

from truthloop.config import load_config
from truthloop.integration.installer import (
    InstallError,
    KnowledgeSpec,
    _wired_retrievers,
    install_copilot,
    parse_knowledge,
    project_root,
    render,
)

EXPECTED_FILES = [
    ".github/agents/truthloop-orchestrator.agent.md",
    ".github/agents/truthloop-judge.agent.md",
    ".github/instructions/truthloop-contract.instructions.md",
    ".github/prompts/truthloop-install.prompt.md",
    ".github/truthloop/ACCEPTANCE.md",
    ".github/truthloop/smoke/graph.json",
    ".github/truthloop/smoke/truthloop.yaml",
    ".github/truthloop/schemas/question.schema.json",
    ".github/truthloop/schemas/answer.schema.json",
    ".github/truthloop/schemas/evidence.schema.json",
    ".github/truthloop/schemas/judge.schema.json",
    ".github/truthloop/schemas/verdict.schema.json",
    ".github/truthloop/schemas/repair_plan.schema.json",
    "runs/smoke/question.json",
    "runs/smoke/iter-01/answer.json",
    "runs/smoke/iter-01/evidence.json",
    "runs/smoke/iter-01/judge.json",
    "runs/.gitkeep",
    "truthloop.yaml",
]


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_parse_knowledge() -> None:
    assert parse_knowledge("sqlite:knowledge/magic.db") == KnowledgeSpec(
        kind="sqlite", path="knowledge/magic.db"
    )
    assert parse_knowledge("files:C:/data/graph") == KnowledgeSpec(
        kind="files", path="C:/data/graph"
    )
    for bad in ("neo4j:x", "sqlite", "sqlite:", ":path"):
        with pytest.raises(InstallError):
            parse_knowledge(bad)


def test_render_substitutes_only_known_placeholders() -> None:
    text = "a={{TRUTHLOOP_PROJECT}} b='{{RETRIEVER_AGENTS}}' c={{MAX_ITERATIONS}}"
    out = render(text, {"TRUTHLOOP_PROJECT": "/p", "MAX_ITERATIONS": "3"}, retrievers=[])
    assert out == "a=/p b='{{RETRIEVER_AGENTS}}' c=3"
    out = render(
        text, {"TRUTHLOOP_PROJECT": "/p", "MAX_ITERATIONS": "3"}, retrievers=["rag", "graph"]
    )
    assert out == "a=/p b='rag', 'graph' c=3"


def test_project_root_has_pyproject() -> None:
    assert (project_root() / "pyproject.toml").is_file()
    assert not project_root().as_posix().endswith("/")


def test_install_creates_expected_tree(tmp_path: Path) -> None:
    results = install_copilot(
        tmp_path, parse_knowledge("sqlite:knowledge/magic.db"), ["rag", "graph"], force=False
    )
    written = sorted(str(r.path.relative_to(tmp_path)) for r in results)
    assert written == sorted(EXPECTED_FILES)
    assert all(r.status == "créé" for r in results)
    config = (tmp_path / "truthloop.yaml").read_text(encoding="utf-8")
    assert "kind: sqlite" in config
    assert 'path: "knowledge/magic.db"' in config
    orchestrator = (tmp_path / ".github/agents/truthloop-orchestrator.agent.md").read_text(
        encoding="utf-8"
    )
    assert "'rag', 'graph'" in orchestrator
    assert "{{" not in orchestrator
    for relative in EXPECTED_FILES:
        if relative.endswith((".md", ".yaml")) and not relative.endswith(
            "truthloop-install.prompt.md"
        ):
            assert "{{" not in (tmp_path / relative).read_text(encoding="utf-8"), relative
    assert project_root().as_posix() in orchestrator


def test_install_without_retrievers_keeps_quoted_token(tmp_path: Path) -> None:
    install_copilot(tmp_path, parse_knowledge("files:knowledge"), [], force=False)
    orchestrator = (tmp_path / ".github/agents/truthloop-orchestrator.agent.md").read_text(
        encoding="utf-8"
    )
    assert "'{{RETRIEVER_AGENTS}}'" in orchestrator
    others = [
        p
        for p in tmp_path.rglob("*.md")
        if p.name not in ("truthloop-orchestrator.agent.md", "truthloop-install.prompt.md")
    ]
    assert all("{{" not in p.read_text(encoding="utf-8") for p in others)


def test_install_is_idempotent_and_never_overwrites_config(tmp_path: Path) -> None:
    install_copilot(tmp_path, parse_knowledge("files:knowledge"), ["rag"], force=False)
    first = _tree_digest(tmp_path)
    (tmp_path / "truthloop.yaml").write_text(
        "schema_version: 1\n# edited\n"
        + (tmp_path / "truthloop.yaml").read_text(encoding="utf-8").split("\n", 1)[1],
        encoding="utf-8",
    )
    edited = (tmp_path / "truthloop.yaml").read_text(encoding="utf-8")
    results = install_copilot(tmp_path, None, ["rag"], force=False)
    assert all(r.status == "conservé" for r in results)
    assert (tmp_path / "truthloop.yaml").read_text(encoding="utf-8") == edited
    results = install_copilot(tmp_path, None, ["rag"], force=True)
    statuses = {str(r.path.relative_to(tmp_path)): r.status for r in results}
    assert statuses["truthloop.yaml"] == "conservé"
    assert statuses[".github/agents/truthloop-judge.agent.md"] == "remplacé"
    after_force = _tree_digest(tmp_path)
    install_copilot(tmp_path, None, ["rag"], force=False)
    assert _tree_digest(tmp_path) == after_force
    assert first != after_force  # the edited config changed the tree; nothing else did


def test_install_prompt_keeps_retrievers_token_even_with_retrievers(tmp_path: Path) -> None:
    install_copilot(tmp_path, parse_knowledge("files:knowledge"), ["rag"], force=False)
    prompt = (tmp_path / ".github/prompts/truthloop-install.prompt.md").read_text(encoding="utf-8")
    assert "'{{RETRIEVER_AGENTS}}'" in prompt


def test_force_without_retrievers_keeps_wired_names(tmp_path: Path) -> None:
    install_copilot(tmp_path, parse_knowledge("files:knowledge"), ["rag", "graph"], force=False)
    install_copilot(tmp_path, None, [], force=True)
    orchestrator = (tmp_path / ".github/agents/truthloop-orchestrator.agent.md").read_text(
        encoding="utf-8"
    )
    assert "agents: ['truthloop-judge', 'rag', 'graph']" in orchestrator


def test_force_recreates_smoke_run_residues(tmp_path: Path) -> None:
    install_copilot(tmp_path, parse_knowledge("files:knowledge"), ["rag"], force=False)
    residue = tmp_path / "runs/smoke/iter-01/verdict.json"
    residue.write_text("{}", encoding="utf-8")
    install_copilot(tmp_path, None, ["rag"], force=True)
    assert not residue.exists()
    assert (tmp_path / "runs/smoke/iter-01/answer.json").is_file()


def test_max_iterations_comes_from_kept_config(tmp_path: Path) -> None:
    install_copilot(tmp_path, parse_knowledge("files:knowledge"), ["rag"], force=False)
    config_path = tmp_path / "truthloop.yaml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace("max_iterations: 3", "max_iterations: 5"),
        encoding="utf-8",
    )
    install_copilot(tmp_path, None, ["rag"], force=True)
    orchestrator = (tmp_path / ".github/agents/truthloop-orchestrator.agent.md").read_text(
        encoding="utf-8"
    )
    assert "Au plus 5 itérations" in orchestrator


def test_install_errors(tmp_path: Path) -> None:
    with pytest.raises(InstallError, match="dossier"):
        install_copilot(tmp_path / "missing", parse_knowledge("files:k"), [], force=False)
    with pytest.raises(InstallError, match="knowledge"):
        install_copilot(tmp_path, None, [], force=False)
    (tmp_path / "truthloop.yaml").write_text("knowledge: [broken", encoding="utf-8")
    with pytest.raises(InstallError, match=r"truthloop\.yaml"):
        install_copilot(tmp_path, None, [], force=False)


def test_invalid_knowledge_path_writes_nothing(tmp_path: Path) -> None:
    # A blank path passes parse_knowledge only when built directly; the config validator rejects it.
    with pytest.raises(InstallError, match="invalide"):
        install_copilot(tmp_path, KnowledgeSpec(kind="files", path="   "), [], force=False)
    assert not (tmp_path / "truthloop.yaml").exists()
    assert not (tmp_path / ".github").exists()


def test_knowledge_path_with_special_characters_round_trips(tmp_path: Path) -> None:
    install_copilot(tmp_path, parse_knowledge("files:my path # not a comment"), [], force=False)
    assert load_config(tmp_path / "truthloop.yaml").knowledge.path == "my path # not a comment"


@pytest.mark.parametrize("name", ["a'b", "rag agent", "", "x,y"])
def test_invalid_retriever_names_are_rejected(tmp_path: Path, name: str) -> None:
    with pytest.raises(InstallError, match="retriever"):
        install_copilot(tmp_path, parse_knowledge("files:k"), [name], force=False)
    assert not (tmp_path / "truthloop.yaml").exists()


def test_wired_retrievers_parses_frontmatter_variants(tmp_path: Path) -> None:
    path = tmp_path / "o.agent.md"
    path.write_text(
        "---\nname: x\nagents:  [ 'truthloop-judge' , \"rag\" , 'graph' ]\n---\n"
        "body agents: ['nope']\n",
        encoding="utf-8",
    )
    assert _wired_retrievers(path) == ["rag", "graph"]
    path.write_text(
        "---\nname: x\nagents: ['truthloop-judge', '{{RETRIEVER_AGENTS}}']\n---\n",
        encoding="utf-8",
    )
    assert _wired_retrievers(path) == []
    path.write_text("no frontmatter", encoding="utf-8")
    assert _wired_retrievers(path) == []
