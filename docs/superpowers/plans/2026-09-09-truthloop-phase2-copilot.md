# truthloop phase 2 (intégration Copilot) — Plan d'implémentation

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer le kit Copilot (agents orchestrateur et juge, contrat des retrievers, prompt d'installation, graphe de fumée, checklist) et la commande `truthloop install-copilot` qui l'installe dans le dépôt Magic.

**Architecture:** Le kit est un sous-paquet de ressources `truthloop.integration.copilot` (fichiers Markdown, JSON, YAML). Le module `truthloop.integration.installer` copie ces ressources dans un dépôt cible en substituant des placeholders `{{NOM}}`, écrit `truthloop.yaml` et les schémas, et rend compte fichier par fichier. La CLI expose `install-copilot`. Les gabarits d'agents sont testés mécaniquement (frontmatter YAML, exemples JSON valides, run de fumée évalué) ; leur comportement est couvert par la checklist d'acceptation manuelle.

**Tech Stack:** Python 3.11, uv, pydantic 2.13, PyYAML 6, Rich 15, pytest 9, ruff 0.16, mypy strict (plugin pydantic). Spec : `docs/superpowers/specs/2026-09-09-truthloop-phase2-copilot-design.md` (§ cités). Phase 1 livrée (branche `feat/truthloop-phase1`, 160 tests).

**Règles de travail** (identiques à la phase 1) :
- TDD : test rouge, implémentation, test vert, puis `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`.
- Tests isolés avec `--no-cov` ; suite complète en fin de chunk.
- **Commits** uniquement aux points de contrôle, après accord de l'utilisateur (déjà donné pour un commit par chunk validé).
- Prose utilisateur (agents, contrat, messages CLI) en français ; code et identifiants en anglais.
- La première ligne `# src/…` / `# tests/…` d'un bloc de code est un marqueur de fichier, à ne pas recopier. Les blocs de gabarits Markdown commencent par un marqueur `<!-- fichier : … -->` à ne pas recopier non plus.
- Environnement : `chflags -R nohidden .venv` avant les commandes (voir README « Dépannage »).

---

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `src/truthloop/integration/__init__.py` | Paquet (docstring). |
| `src/truthloop/integration/copilot/__init__.py` | Marque le dossier de ressources comme paquet pour `importlib.resources`. |
| `src/truthloop/integration/copilot/agents/truthloop-orchestrator.agent.md` | Gabarit orchestrateur (§5). |
| `src/truthloop/integration/copilot/agents/truthloop-judge.agent.md` | Gabarit juge (§6). |
| `src/truthloop/integration/copilot/instructions/truthloop-contract.instructions.md` | Contrat des retrievers (§7). |
| `src/truthloop/integration/copilot/prompts/truthloop-install.prompt.md` | Prompt de câblage (§8). |
| `src/truthloop/integration/copilot/ACCEPTANCE.md` | Checklist d'acceptation (§10). |
| `src/truthloop/integration/copilot/smoke/graph.json` | Copie du graphe de fixture. |
| `src/truthloop/integration/copilot/smoke/truthloop.yaml` | Config de fumée (`kind: files`, `path: graph.json`). |
| `src/truthloop/integration/copilot/smoke/run/question.json`, `run/iter-01/{answer,evidence,judge}.json` | Run de fumée (échantillons de phase 1). |
| `src/truthloop/integration/installer.py` | `KnowledgeSpec`, `parse_knowledge`, `InstallError`, `InstallResult`, `project_root`, `render`, `install_copilot` (§9). |
| `src/truthloop/cli.py` (modifier) | Sous-commande `install-copilot`. |
| `tests/test_installer.py` | Installateur : arbre, statuts, config conservée, `--force`, idempotence, placeholders, run de fumée. |
| `tests/test_kit_templates.py` | Frontmatters YAML, exemples JSON du contrat, config de fumée. |
| `tests/test_cli.py` (modifier) | `install-copilot` via `main`. |
| `README.md` (modifier) | Section « Phase 2 » remplacée par le mode d'emploi. |

Substitutions (§4) : `{{TRUTHLOOP_PROJECT}}` (chemin absolu POSIX sans `/` final), `{{MAX_ITERATIONS}}`, et le token quoté `'{{RETRIEVER_AGENTS}}'` remplacé par `'a', 'b'` seulement si `--retrievers` est fourni.

---

## Chunk 1 : ressources du kit et installateur

### Task 1 : Paquet de ressources et run de fumée

**Files:**
- Create: `src/truthloop/integration/__init__.py`
- Create: `src/truthloop/integration/copilot/__init__.py`
- Create: `src/truthloop/integration/copilot/smoke/graph.json`
- Create: `src/truthloop/integration/copilot/smoke/truthloop.yaml`
- Create: `src/truthloop/integration/copilot/smoke/run/question.json`
- Create: `src/truthloop/integration/copilot/smoke/run/iter-01/answer.json`
- Create: `src/truthloop/integration/copilot/smoke/run/iter-01/evidence.json`
- Create: `src/truthloop/integration/copilot/smoke/run/iter-01/judge.json`
- Create: `tests/test_kit_templates.py` (première partie)

- [ ] **Step 1 : Test rouge**

```python
# tests/test_kit_templates.py
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
    assert kit_path("smoke/graph.json").read_text(encoding="utf-8") == FIXTURE_GRAPH.read_text(encoding="utf-8")


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
    knowledge = open_knowledge(config.knowledge.kind, config_path.parent / config.knowledge.path, config.knowledge.queries)
    verdict = evaluate(RunDir(tmp_path / "smoke"), config, knowledge)
    assert verdict.decision == "repair"
    assert verdict.score == 69.3
    assert [a.kind for a in verdict.repair_plan.actions] == ["retrieve_entities", "retrieve_entities"]
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_kit_templates.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.integration'`

- [ ] **Step 3 : Implémenter**

`src/truthloop/integration/__init__.py` :

```python
# src/truthloop/integration/__init__.py
"""Integration kits shipped with truthloop (phase 2: GitHub Copilot agents)."""
```

`src/truthloop/integration/copilot/__init__.py` :

```python
# src/truthloop/integration/copilot/__init__.py
"""Resource package: templates and smoke assets installed by ``truthloop install-copilot``."""
```

`smoke/graph.json` : copie exacte de `tests/fixtures/graph.json` (`cp tests/fixtures/graph.json src/truthloop/integration/copilot/smoke/graph.json`).

`smoke/truthloop.yaml` :

```yaml
schema_version: 1
knowledge:
  kind: files
  path: graph.json
  queries: {}
scoring:
  weights:
    context_recall: 0.35
    table_recall: 0.15
    evidence_support: 0.15
    faithfulness: 0.25
    relevance_completeness: 0.10
  caps:
    unknown_entity: 50
    contradiction: 70
    missing_judge: 85
    missing_claims: 85
  release_threshold: 90
  release_threshold_no_reference: 95
loop:
  max_iterations: 3
paths:
  runs: runs
  golden: golden
  reports: reports
```

`smoke/run/question.json` :

```json
{
  "schema_version": 1,
  "id": "q-001",
  "text": "Quels programmes et tables sont impactés si je modifie PRG_ORD_VALID ?",
  "intent": "impact_analysis",
  "pivot_entities": [{"type": "program", "id": "PRG_ORD_VALID"}],
  "direction": "both",
  "depth": 1
}
```

`smoke/run/iter-01/answer.json` :

```json
{
  "schema_version": 1,
  "question_id": "q-001",
  "iteration": 1,
  "producer": "truthloop-orchestrator",
  "entities": [
    {"type": "program", "id": "PRG_ORD_VALID"},
    {"type": "program", "id": "PRG_ORD_SAVE"},
    {"type": "program", "id": "PRG_ORD_NOTIFY"},
    {"type": "table", "id": "T_ORDERS"}
  ],
  "claims": [
    {
      "id": "c1",
      "text": "PRG_ORD_SAVE appelle PRG_ORD_VALID.",
      "entities": ["PRG_ORD_SAVE", "PRG_ORD_VALID"],
      "citations": ["ev-1"],
      "relation": {"subject": "PRG_ORD_SAVE", "predicate": "calls", "object": "PRG_ORD_VALID"},
      "confidence_self": 0.8
    },
    {
      "id": "c2",
      "text": "PRG_ORD_NOTIFY appelle PRG_ORD_VALID.",
      "entities": ["PRG_ORD_NOTIFY", "PRG_ORD_VALID"],
      "citations": ["ev-2"]
    }
  ],
  "abstentions": [{"text": "Profondeur 2 non explorée.", "entities": ["PRG_ORD_VALID"]}],
  "final_text": "PRG_ORD_VALID est appelé par PRG_ORD_SAVE et PRG_ORD_NOTIFY."
}
```

`smoke/run/iter-01/evidence.json` :

```json
{
  "schema_version": 1,
  "question_id": "q-001",
  "iteration": 1,
  "chunks": [
    {"id": "ev-1", "source": "graph:calls", "text": "PRG_ORD_SAVE -> PRG_ORD_VALID (call)", "score": 0.9},
    {"id": "ev-2", "source": "graph:calls", "text": "PRG_ORD_NOTIFY calls PRG-ORD-VALID", "score": 0.8}
  ]
}
```

`smoke/run/iter-01/judge.json` :

```json
{
  "schema_version": 1,
  "question_id": "q-001",
  "iteration": 1,
  "judge_model": "copilot-chat",
  "claims": [
    {"id": "c1", "verdict": "supported", "rationale": "ev-1 montre l'appel explicite."},
    {"id": "c2", "verdict": "supported", "rationale": "ev-2 montre l'appel explicite."}
  ],
  "relevance": 0.9,
  "completeness": 0.7,
  "notes": ""
}
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_kit_templates.py --no-cov -q`
Expected: `4 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 2 : Installateur

**Files:**
- Create: `src/truthloop/integration/installer.py`
- Create: `tests/test_installer.py`

Prérequis : les gabarits de la Task 4 à 7 n'existent pas encore. Pour que l'installateur soit testable dès maintenant, l'installateur ne connaît que la **liste** des ressources ; les tests de cette tâche créent les gabarits manquants ? Non : pour rester simple, les fichiers gabarits sont créés **vides avec leur frontmatter minimal** dans cette tâche (Step 3, « gabarits provisoires »), puis remplacés par leur contenu réel dans le chunk 2. Les tests de contenu (frontmatter, exemples) arrivent au chunk 2.

- [ ] **Step 1 : Test rouge**

```python
# tests/test_installer.py
import hashlib
from pathlib import Path

import pytest

from truthloop.integration.installer import (
    InstallError,
    KnowledgeSpec,
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
    assert parse_knowledge("sqlite:knowledge/magic.db") == KnowledgeSpec(kind="sqlite", path="knowledge/magic.db")
    assert parse_knowledge("files:C:/data/graph") == KnowledgeSpec(kind="files", path="C:/data/graph")
    for bad in ("neo4j:x", "sqlite", "sqlite:", ":path"):
        with pytest.raises(InstallError):
            parse_knowledge(bad)


def test_render_substitutes_only_known_placeholders() -> None:
    text = "a={{TRUTHLOOP_PROJECT}} b='{{RETRIEVER_AGENTS}}' c={{MAX_ITERATIONS}}"
    out = render(text, {"TRUTHLOOP_PROJECT": "/p", "MAX_ITERATIONS": "3"}, retrievers=[])
    assert out == "a=/p b='{{RETRIEVER_AGENTS}}' c=3"
    out = render(text, {"TRUTHLOOP_PROJECT": "/p", "MAX_ITERATIONS": "3"}, retrievers=["rag", "graph"])
    assert out == "a=/p b='rag', 'graph' c=3"


def test_project_root_has_pyproject() -> None:
    assert (project_root() / "pyproject.toml").is_file()
    assert not project_root().as_posix().endswith("/")


def test_install_creates_expected_tree(tmp_path: Path) -> None:
    results = install_copilot(tmp_path, parse_knowledge("sqlite:knowledge/magic.db"), ["rag", "graph"], force=False)
    written = sorted(str(r.path.relative_to(tmp_path)) for r in results)
    assert written == sorted(EXPECTED_FILES)
    assert all(r.status == "créé" for r in results)
    config = (tmp_path / "truthloop.yaml").read_text(encoding="utf-8")
    assert "kind: sqlite" in config
    assert "path: knowledge/magic.db" in config
    orchestrator = (tmp_path / ".github/agents/truthloop-orchestrator.agent.md").read_text(encoding="utf-8")
    assert "'rag', 'graph'" in orchestrator
    assert "{{" not in orchestrator
    for relative in EXPECTED_FILES:
        if relative.endswith((".md", ".yaml")) and not relative.endswith("truthloop-install.prompt.md"):
            assert "{{" not in (tmp_path / relative).read_text(encoding="utf-8"), relative
    assert project_root().as_posix() in orchestrator


def test_install_without_retrievers_keeps_quoted_token(tmp_path: Path) -> None:
    install_copilot(tmp_path, parse_knowledge("files:knowledge"), [], force=False)
    orchestrator = (tmp_path / ".github/agents/truthloop-orchestrator.agent.md").read_text(encoding="utf-8")
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
    (tmp_path / "truthloop.yaml").write_text("schema_version: 1\n# edited\n" + (tmp_path / "truthloop.yaml").read_text(encoding="utf-8").split("\n", 1)[1], encoding="utf-8")
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
    orchestrator = (tmp_path / ".github/agents/truthloop-orchestrator.agent.md").read_text(encoding="utf-8")
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
    config_path.write_text(config_path.read_text(encoding="utf-8").replace("max_iterations: 3", "max_iterations: 5"), encoding="utf-8")
    install_copilot(tmp_path, None, ["rag"], force=True)
    orchestrator = (tmp_path / ".github/agents/truthloop-orchestrator.agent.md").read_text(encoding="utf-8")
    assert "Au plus 5 itérations" in orchestrator


def test_install_errors(tmp_path: Path) -> None:
    with pytest.raises(InstallError, match="dossier"):
        install_copilot(tmp_path / "missing", parse_knowledge("files:k"), [], force=False)
    with pytest.raises(InstallError, match="knowledge"):
        install_copilot(tmp_path, None, [], force=False)
    (tmp_path / "truthloop.yaml").write_text("knowledge: [broken", encoding="utf-8")
    with pytest.raises(InstallError, match=r"truthloop\.yaml"):
        install_copilot(tmp_path, None, [], force=False)
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_installer.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.integration.installer'`

- [ ] **Step 3 : Gabarits provisoires**

Créer les cinq fichiers Markdown du kit avec un contenu minimal (remplacés au chunk 2) :

`src/truthloop/integration/copilot/agents/truthloop-orchestrator.agent.md` :

```markdown
<!-- fichier : agents/truthloop-orchestrator.agent.md (provisoire) -->
---
name: truthloop-orchestrator
description: Provisoire.
tools: ['agent', 'runCommands', 'read', 'edit', 'search']
agents: ['truthloop-judge', '{{RETRIEVER_AGENTS}}']
---
Provisoire. Harness : {{TRUTHLOOP_PROJECT}}. Au plus {{MAX_ITERATIONS}} itérations.
```

`agents/truthloop-judge.agent.md` :

```markdown
<!-- fichier : agents/truthloop-judge.agent.md (provisoire) -->
---
name: truthloop-judge
description: Provisoire.
user-invocable: false
tools: ['runCommands', 'read', 'edit']
---
Provisoire. Harness : {{TRUTHLOOP_PROJECT}}.
```

`instructions/truthloop-contract.instructions.md` et `ACCEPTANCE.md` : une ligne `Provisoire. Harness : {{TRUTHLOOP_PROJECT}}.`. `prompts/truthloop-install.prompt.md` : frontmatter `name: truthloop-install` / `tools: ['read', 'edit', 'search', 'runCommands']` puis la ligne `Provisoire. Harness : {{TRUTHLOOP_PROJECT}}. Remplacer le token '{{RETRIEVER_AGENTS}}'.` (le token quoté doit être présent dès maintenant : les tests de l'installateur en dépendent).

- [ ] **Step 4 : Implémenter l'installateur**

```python
# src/truthloop/integration/installer.py
"""Install the Copilot kit into a target repository (spec phase 2 §4, §9)."""

from __future__ import annotations

import re
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Final, Literal

from truthloop.config import DEFAULT_CONFIG_YAML, ConfigError, load_config
from truthloop.contracts.schemas import export_schemas

KnowledgeKind = Literal["sqlite", "files"]
Status = Literal["créé", "conservé", "remplacé"]

_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
_RETRIEVERS_TOKEN: Final = "'{{RETRIEVER_AGENTS}}'"
_KIT: Final = "truthloop.integration.copilot"

# (resource path inside the kit, destination relative to the target, substitute placeholders?)
_TEMPLATES: Final[tuple[tuple[str, str, bool], ...]] = (
    ("agents/truthloop-orchestrator.agent.md", ".github/agents/truthloop-orchestrator.agent.md", True),
    ("agents/truthloop-judge.agent.md", ".github/agents/truthloop-judge.agent.md", True),
    ("instructions/truthloop-contract.instructions.md", ".github/instructions/truthloop-contract.instructions.md", True),
    ("prompts/truthloop-install.prompt.md", ".github/prompts/truthloop-install.prompt.md", True),
    ("ACCEPTANCE.md", ".github/truthloop/ACCEPTANCE.md", True),
    ("smoke/graph.json", ".github/truthloop/smoke/graph.json", False),
    ("smoke/truthloop.yaml", ".github/truthloop/smoke/truthloop.yaml", False),
    ("smoke/run/question.json", "runs/smoke/question.json", False),
    ("smoke/run/iter-01/answer.json", "runs/smoke/iter-01/answer.json", False),
    ("smoke/run/iter-01/evidence.json", "runs/smoke/iter-01/evidence.json", False),
    ("smoke/run/iter-01/judge.json", "runs/smoke/iter-01/judge.json", False),
)


class InstallError(Exception):
    """Installation impossible (exit code 1)."""


@dataclass(frozen=True)
class KnowledgeSpec:
    kind: KnowledgeKind
    path: str


@dataclass(frozen=True)
class InstallResult:
    path: Path
    status: Status


def parse_knowledge(spec: str) -> KnowledgeSpec:
    kind, separator, path = spec.partition(":")
    if not separator or not path.strip():
        raise InstallError("--knowledge attend la forme kind:chemin (ex. sqlite:knowledge/magic.db)")
    if kind not in ("sqlite", "files"):
        raise InstallError(f"--knowledge : kind inconnu {kind!r} (attendu sqlite ou files)")
    return KnowledgeSpec(kind="sqlite" if kind == "sqlite" else "files", path=path.strip())


def project_root() -> Path:
    """The truthloop checkout (``pyproject.toml`` directory), used for ``uv run --project``."""
    root = Path(__file__).resolve().parents[3]
    if not (root / "pyproject.toml").is_file():
        raise InstallError(
            "truthloop doit être lancé depuis son dépôt (uv run --project <dépôt truthloop>) pour installer le kit"
        )
    return root


def render(text: str, values: Mapping[str, str], retrievers: Sequence[str]) -> str:
    if retrievers:
        text = text.replace(_RETRIEVERS_TOKEN, ", ".join(f"'{name}'" for name in retrievers))
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def install_copilot(
    target: Path, knowledge: KnowledgeSpec | None, retrievers: Sequence[str], *, force: bool
) -> list[InstallResult]:
    if not target.is_dir():
        raise InstallError(f"--target doit être un dossier existant : {target}")
    results: list[InstallResult] = []
    config_path = target / "truthloop.yaml"
    results.append(_write_config(config_path, knowledge))
    try:
        max_iterations = load_config(config_path).loop.max_iterations
    except ConfigError as exc:
        raise InstallError(f"truthloop.yaml invalide dans {target} : {exc}") from exc
    values = {"TRUTHLOOP_PROJECT": project_root().as_posix().rstrip("/"), "MAX_ITERATIONS": str(max_iterations)}
    if not retrievers:
        retrievers = _wired_retrievers(target / ".github" / "agents" / "truthloop-orchestrator.agent.md")
    if force:
        shutil.rmtree(target / "runs" / "smoke", ignore_errors=True)
    kit = resources.files(_KIT)
    for resource, destination, substitute in _TEMPLATES:
        content = (kit / resource).read_text(encoding="utf-8")
        if substitute:
            # The install prompt must keep the retrievers token verbatim: it tells Copilot what to replace.
            content = render(content, values, [] if resource.startswith("prompts/") else retrievers)
        results.append(_write(target / destination, content, force))
    results.extend(_write_schemas(target / ".github" / "truthloop" / "schemas", force))
    results.append(_write(target / "runs" / ".gitkeep", "", force))
    return results


_AGENTS_LINE = re.compile(r"^agents: \[(.*)\]$", re.MULTILINE)


def _wired_retrievers(orchestrator_path: Path) -> list[str]:
    """Retriever names already wired in an installed orchestrator (kept across ``--force``)."""
    if not orchestrator_path.is_file():
        return []
    match = _AGENTS_LINE.search(orchestrator_path.read_text(encoding="utf-8"))
    if match is None:
        return []
    names = [item.strip().strip("'") for item in match.group(1).split(",")]
    return [name for name in names if name and name != "truthloop-judge" and not name.startswith("{{")]


def _write_config(config_path: Path, knowledge: KnowledgeSpec | None) -> InstallResult:
    if config_path.exists():
        return InstallResult(config_path, "conservé")
    if knowledge is None:
        raise InstallError("--knowledge est requis quand truthloop.yaml n'existe pas encore")
    content = DEFAULT_CONFIG_YAML.replace("  kind: sqlite\n", f"  kind: {knowledge.kind}\n", 1).replace(
        "  path: knowledge/magic.db\n", f"  path: {knowledge.path}\n", 1
    )
    config_path.write_text(content, encoding="utf-8")
    return InstallResult(config_path, "créé")


def _write(path: Path, content: str, force: bool) -> InstallResult:
    exists = path.exists()
    if exists and not force:
        return InstallResult(path, "conservé")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return InstallResult(path, "remplacé" if exists else "créé")


def _write_schemas(out_dir: Path, force: bool) -> list[InstallResult]:
    staging = out_dir.parent / ".schemas.tmp"
    shutil.rmtree(staging, ignore_errors=True)
    written = export_schemas(staging)
    results = [_write(out_dir / path.name, path.read_text(encoding="utf-8"), force) for path in written]
    shutil.rmtree(staging, ignore_errors=True)
    return results
```

Note : `export_schemas` écrit directement des fichiers ; on passe par un dossier de transit pour appliquer la règle `créé` / `conservé` / `remplacé` uniformément.

- [ ] **Step 5 : Vérifier le succès**

Run: `uv run pytest tests/test_installer.py --no-cov -q`
Expected: `11 passed`

- [ ] **Step 6 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur. Si mypy se plaint de `resources.files(...) / resource` (type `Traversable`), utiliser `kit.joinpath(resource).read_text(encoding="utf-8")`.

### Task 3 : Sous-commande `install-copilot`

**Files:**
- Modify: `src/truthloop/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1 : Test rouge** (ajouter à `tests/test_cli.py`)

```python
def test_install_copilot_command(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "magic"
    target.mkdir()
    code = main(["install-copilot", "--target", str(target), "--knowledge", "files:knowledge", "--retrievers", "rag,graph"])
    assert code == 0
    out = capsys.readouterr().out
    assert "créé : " in out
    assert "/truthloop-install" in out
    assert (target / ".github/agents/truthloop-orchestrator.agent.md").is_file()
    assert main(["install-copilot", "--target", str(target)]) == 0
    assert "conservé : " in capsys.readouterr().out
    assert main(["install-copilot", "--target", str(tmp_path / "nope"), "--knowledge", "files:k"]) == 1
    assert "dossier" in capsys.readouterr().err
    assert main(["install-copilot", "--target", str(target), "--knowledge", "neo4j:k", "--force"]) == 1
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_cli.py::test_install_copilot_command --no-cov -q`
Expected: FAIL (argparse : `invalid choice: 'install-copilot'`, `SystemExit` code 1)

- [ ] **Step 3 : Implémenter**

Dans `cli.py` : importer `InstallError, install_copilot, parse_knowledge` depuis `truthloop.integration.installer` ; ajouter `InstallError` au tuple d'exceptions de `main` ; dans `build_parser` :

```python
    install = subparsers.add_parser("install-copilot", help="installe le kit Copilot dans un dépôt cible")
    install.add_argument("--target", type=Path, required=True)
    install.add_argument("--knowledge", default=None, help="kind:chemin, ex. sqlite:knowledge/magic.db")
    install.add_argument("--retrievers", default="", help="noms des agents retrievers, séparés par des virgules")
    install.add_argument("--force", action="store_true")
    install.set_defaults(handler=cmd_install_copilot)
```

et le handler :

```python
def cmd_install_copilot(args: argparse.Namespace, console: Console) -> int:
    knowledge = parse_knowledge(args.knowledge) if args.knowledge else None
    retrievers = [name.strip() for name in str(args.retrievers).split(",") if name.strip()]
    results = install_copilot(args.target, knowledge, retrievers, force=args.force)
    for result in results:
        console.print(f"{result.status} : {result.path}", markup=False)
    console.print("Étapes suivantes : ouvrir le dépôt cible dans VS Code, lancer le prompt /truthloop-install,", markup=False)
    console.print("puis dérouler .github/truthloop/ACCEPTANCE.md.", markup=False)
    return 0
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_cli.py --no-cov -q`
Expected: `7 passed`

- [ ] **Step 5 : Suite complète et lint**

Run: `uv run ruff format src tests && uv run pytest -q && uv run ruff check src tests && uv run mypy`
Expected: tous les tests passent (160 + 4 + 11 + 1 = 176), couverture ≥ 85 %, aucune erreur.

- [ ] **Step 6 : Point de contrôle**

Commit du chunk (accord déjà donné) : `✨ feat(truthloop): copilot kit resources and install-copilot command`.

### Écarts appliqués après la revue qualité du chunk 1

- `installer.py` : « planifier puis écrire » — `project_root()`, validation des noms de retrievers
  (`[A-Za-z0-9._-]+`), rendu de tous les gabarits et détection des placeholders inconnus **avant**
  toute écriture ; `truthloop.yaml` généré avec le chemin en scalaire YAML entre guillemets et
  validé par `Config.model_validate` (aller-retour du chemin) avant écriture.
- `_wired_retrievers` lit le frontmatter YAML (`yaml.safe_load`) au lieu d'une regex.
- Schémas mis en transit dans un `tempfile.TemporaryDirectory()` ; écritures avec `newline="\n"` ;
  `target.resolve()`.
- CLI : en-tête « Installation dans … », chemins relatifs au dépôt cible, avertissement
  « --knowledge ignoré » quand la configuration est conservée, `help=` sur les options.
- Confirmé par le reviewer : `uv build --wheel` embarque les ressources du kit sans réglage.

---

## Chunk 2 : gabarits d'agents, contrat, prompt d'installation, checklist

Les cinq fichiers provisoires de la Task 2 sont remplacés par leur contenu réel. Les tests de cette partie lisent les ressources via `importlib.resources` et vérifient : frontmatter YAML valide avant et après substitution, champs attendus, exemples JSON du contrat valides, absence de placeholder inconnu.

### Task 4 : Agent juge

**Files:**
- Replace: `src/truthloop/integration/copilot/agents/truthloop-judge.agent.md`
- Modify: `tests/test_kit_templates.py`

- [ ] **Step 1 : Test rouge** (ajouter à `tests/test_kit_templates.py`)

```python
from truthloop.integration.installer import render

SUBS = {"TRUTHLOOP_PROJECT": "/abs/truthloop", "MAX_ITERATIONS": "3"}


def frontmatter(text: str) -> dict[str, object]:
    assert text.startswith("---\n"), "frontmatter attendu"
    _, block, _ = text.split("---\n", 2)
    data = yaml.safe_load(block)
    assert isinstance(data, dict)
    return data


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
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_kit_templates.py::test_judge_template --no-cov -q`
Expected: FAIL (`assert "judge.json" in rendered` sur le gabarit provisoire)

- [ ] **Step 3 : Écrire le gabarit**

```markdown
<!-- fichier : agents/truthloop-judge.agent.md -->
---
name: truthloop-judge
description: "Juge sémantique truthloop, invoqué par l'orchestrateur ; remplit judge.json et lance truthloop verify."
user-invocable: false
tools: ['runCommands', 'read', 'edit']
---
# Rôle

Tu es le juge sémantique du harness truthloop. On t'indique un dossier de run
(`runs/<id>`) et un numéro d'itération `NN`. Tu évalues la fidélité des claims aux évidences
citées, tu écris `judge.json`, tu lances la vérification déterministe, et tu renvoies un bloc
de quatre lignes. Tu ne modifies jamais `answer.json`, `evidence.json` ni `question.json`.

# Protocole

1. Lis `runs/<id>/question.json`, `runs/<id>/iter-NN/answer.json` et
   `runs/<id>/iter-NN/evidence.json`.
2. Pour chaque claim de `answer.json`, dans l'ordre, lis les chunks cités (`citations`) dans
   `evidence.json` et attribue un verdict :
   - `supported` : tous les éléments factuels de la claim sont écrits dans un chunk cité ;
   - `partially` : une partie seulement est écrite ;
   - `unsupported` : aucun chunk cité n'étaye la claim (une citation absente compte comme
     non étayée) ;
   - `contradicted` : un chunk cité affirme le contraire.
   `rationale` : une phrase qui cite l'id du chunk décisif. Ne juge pas l'existence des
   entités ni les relations d'appel : le graphe s'en charge.
3. Note `relevance` (la réponse répond-elle à la question posée : 1 oui, 0.5 partiellement,
   0 non) et `completeness` (couvre-t-elle tous les aspects demandés : mêmes ancrages).
   `notes` : une phrase sur le manque principal, ou vide.
4. Écris `runs/<id>/iter-NN/judge.json` exactement dans ce format (schéma :
   `.github/truthloop/schemas/judge.schema.json`) :

   ```json
   {
     "schema_version": 1,
     "question_id": "<question.id>",
     "iteration": 1,
     "judge_model": "copilot-chat",
     "claims": [{"id": "c1", "verdict": "supported", "rationale": "ev-1 montre l'appel."}],
     "relevance": 0.9,
     "completeness": 0.7,
     "notes": ""
   }
   ```

   `question_id` et `iteration` sont recopiés depuis `answer.json`. Chaque `id` doit exister
   dans `answer.json`.
5. Depuis la racine du dépôt, exécute :

   ```
   uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop verify --run "runs/<id>" --iteration NN --json
   ```

   La sortie standard est un JSON. Lis `score`, `decision` et
   `repair_plan.summary_for_agent`. Le code de retour vaut 0 (release), 2 (repair),
   3 (escalate), 4 (invalid) ou 1 (erreur).
6. Réponds **uniquement** par ce bloc, sans autre texte :

   ```
   score: <score>
   decision: <release|repair|escalate|invalid>
   verdict: runs/<id>/iter-NN/verdict.json
   summary: <repair_plan.summary_for_agent, ou vide si release>
   ```

   Si la commande échoue (code 1), réponds `decision: error` suivi du message d'erreur
   affiché, et rien d'autre.
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_kit_templates.py --no-cov -q`
Expected: `5 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 5 : Agent orchestrateur

**Files:**
- Replace: `src/truthloop/integration/copilot/agents/truthloop-orchestrator.agent.md`
- Modify: `tests/test_kit_templates.py`

- [ ] **Step 1 : Test rouge**

```python
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
    for kind in ("retrieve_entities", "verify_claim", "write_claims", "improve_answer", "run_judge", "fix_question", "fix_contract"):
        assert kind in rendered
    assert "truthloop-contract.instructions.md" in rendered
    assert "Consigne à copier" in rendered
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_kit_templates.py::test_orchestrator_template_before_and_after_substitution --no-cov -q`
Expected: FAIL (`KeyError: 'handoffs'` sur le gabarit provisoire)

- [ ] **Step 3 : Écrire le gabarit**

```markdown
<!-- fichier : agents/truthloop-orchestrator.agent.md -->
---
name: truthloop-orchestrator
description: "Répond aux questions d'architecture et d'impact Magic XPA avec un score de confiance vérifié par truthloop."
tools: ['agent', 'runCommands', 'read', 'edit', 'search']
agents: ['truthloop-judge', '{{RETRIEVER_AGENTS}}']
handoffs:
  - label: Escalader à un humain
    agent: agent
    prompt: La réponse n'a pas atteint le seuil de confiance truthloop. Voici les zones d'ombre à trancher avant de conclure.
    send: false
---
# Rôle

Tu orchestres une boucle de recherche vérifiée. Tes retrievers cherchent, le juge
`truthloop-judge` évalue, le harness truthloop décide. Tu ne publies une réponse que si la
décision est `release`. Avant toute chose, si la liste `agents` de ta propre configuration
contient encore un nom entre doubles accolades (placeholder non remplacé), arrête-toi et
demande de lancer le prompt `/truthloop-install`.

Le harness s'appelle depuis la racine du dépôt :
`uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop …`. Au plus {{MAX_ITERATIONS}} itérations
par question.

# Protocole

## 1. Cadrer

Déduis de la question :
- `intent` : `impact_analysis` (programmes / tables impactés), `architecture`, `feature`,
  `diagram` ;
- `pivot_entities` : les programmes et tables nommés, `id` tel qu'il apparaît dans le dossier
  de connaissance (le harness normalise casse et séparateurs, mais n'invente rien) ;
- `direction` : `callers`, `callees` ou `both` (défaut) ;
- `depth` : 1 par défaut ; 2 si la question parle de transitif, cascade, indirect.

Crée `runs/<id>/question.json` (schéma `.github/truthloop/schemas/question.schema.json`) avec
`<id>` = `q-<AAAAMMJJ>-<3 chiffres>` non encore utilisé :

```json
{"schema_version": 1, "id": "<id>", "text": "<question>", "intent": "impact_analysis",
 "pivot_entities": [{"type": "program", "id": "PRG_X"}], "direction": "both", "depth": 1}
```

## 2. Chercher

Pour chaque retriever de ta liste `agents`, lance un subagent avec une consigne
**autosuffisante** : la question, les entités déjà connues (itération 2 et plus), et le bloc
« Consigne à copier » de `.github/instructions/truthloop-contract.instructions.md`
(lis ce fichier une fois et recopie le bloc tel quel : le retriever n'a pas à le lire lui-même).
Exige en retour un unique bloc ```json de fragment. Si un retriever ne renvoie pas de bloc
JSON exploitable, relance-le une fois avec la même consigne ; au second échec, continue avec
les autres fragments.

## 3. Assembler

Écris `runs/<id>/iter-NN/answer.json` et `runs/<id>/iter-NN/evidence.json` (`NN` = numéro
d'itération sur deux chiffres, `iter-01` d'abord) :
- `entities` : union des fragments, dédoublonnée sur `(type, id)` ;
- `claims` : concaténées dans l'ordre des retrievers et renumérotées `c1`, `c2`, … ;
- `chunks` : concaténés dans le même ordre et renumérotés `ev-1`, `ev-2`, … ; réécris les
  `citations` de chaque claim en conséquence ;
- `abstentions` : concaténées ;
- `producer` : `"truthloop-orchestrator"` ; `question_id` = `<id>` ; `iteration` = NN ;
- `final_text` : ta rédaction de la réponse, à partir des claims uniquement.

## 4. Juger

Lance `truthloop-judge` en subagent avec : « Run `runs/<id>`, itération NN. » Sa réponse est
un bloc `score / decision / verdict / summary`. Si le bloc manque, lis
`runs/<id>/iter-NN/verdict.json` (`score`, `decision`, `repair_plan.summary_for_agent`) ; si ce
fichier n'existe pas, arrête-toi et affiche la réponse du juge.

## 5. Décider

- `release` : réponds avec, en tête, « Score truthloop : <score> / seuil <threshold>
  (verdict : runs/<id>/iter-NN/verdict.json) », puis `final_text`, puis les
  `declared_gaps` du verdict s'il y en a.
- `repair` : lis `repair_plan.actions` dans `verdict.json`. Si la première action est
  `fix_question` (pivot inconnu du graphe), n'itère pas : propose le handoff « Escalader à un
  humain » en demandant de reformuler le pivot (`question.json` n'est jamais modifié). Sinon,
  applique les actions dans l'ordre de `priority` :
  - `retrieve_entities` : nouvelle consigne au retriever concerné avec `queries.graph`
    (retriever graphe) ou `queries.rag` (retriever documentation), en listant `entities` ;
  - `verify_claim` : demander une évidence pour les `claim_ids`, sinon retirer la claim ;
  - `write_claims` : rédiger des claims citées pour les entités présentes ;
  - `improve_answer` : reformuler `final_text` selon `instruction` ;
  - `run_judge` : réinvoquer le juge sur la même itération ;
  - `fix_contract` : corriger les erreurs listées dans `errors`.
  Puis crée `iter-NN+1/` en repartant des claims et chunks de l'itération précédente (moins
  les claims retirées par `verify_claim`), auxquels tu ajoutes les nouveaux fragments, et
  reprends à l'étape 3.
- `escalate` ou itération {{MAX_ITERATIONS}} atteinte sans `release` : propose le handoff
  « Escalader à un humain » avec `summary` et la liste des findings ouverts du verdict.
- `invalid` : corrige selon `repair_plan.actions[0].errors`, sans changer d'itération, et
  réinvoque le juge.
- `error` : affiche le message et arrête-toi.

# Règles dures

- Jamais de réponse publiée sans décision `release`.
- Jamais de modification de `verdict.json`, `trace.jsonl` ni `question.json`.
- Au plus {{MAX_ITERATIONS}} itérations ; toute commande qui sort avec le code 1 arrête la
  boucle avec son message.
- Les identifiants viennent du dossier de connaissance ; ne complète jamais une liste
  d'appelants ou de tables de mémoire.
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_kit_templates.py --no-cov -q`
Expected: `6 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 6 : Contrat des retrievers

**Files:**
- Replace: `src/truthloop/integration/copilot/instructions/truthloop-contract.instructions.md`
- Modify: `tests/test_kit_templates.py`

- [ ] **Step 1 : Test rouge**

```python
import json
import re

JSON_BLOCK = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


def test_contract_examples_are_valid() -> None:
    raw = kit_path("instructions/truthloop-contract.instructions.md").read_text(encoding="utf-8")
    assert frontmatter(raw)["description"]
    assert "Consigne à copier" in raw
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
    Evidence.model_validate({"schema_version": 1, "question_id": "q", "iteration": 1, "chunks": fragment["chunks"]})
    parsed_answer = Answer.model_validate(answer)
    parsed_evidence = Evidence.model_validate(evidence)
    chunk_ids = set(parsed_evidence.chunk_by_id())
    assert all(set(c.citations) <= chunk_ids for c in parsed_answer.claims)
    assert "{{" not in render(raw, SUBS, [])
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_kit_templates.py::test_contract_examples_are_valid --no-cov -q`
Expected: FAIL (`AssertionError` sur `frontmatter` : le gabarit provisoire n'a pas de frontmatter)

- [ ] **Step 3 : Écrire le contrat**

```markdown
<!-- fichier : instructions/truthloop-contract.instructions.md -->
---
description: "Contrat truthloop pour les agents retrievers : format du fragment, règles d'identifiants, citations et abstentions."
---
# Contrat truthloop pour les retrievers

Ce fichier est la référence. L'orchestrateur `truthloop-orchestrator` copie la section
« Consigne à copier » dans chaque délégation : un retriever n'a pas besoin de le lire.

## Qui écrit quoi

| Fichier | Auteur |
|---|---|
| fragment (bloc JSON renvoyé dans la réponse) | chaque retriever |
| `runs/<id>/iter-NN/answer.json`, `evidence.json` | l'orchestrateur, par assemblage des fragments |
| `runs/<id>/iter-NN/judge.json` | `truthloop-judge` |
| `runs/<id>/iter-NN/verdict.json`, `runs/<id>/trace.jsonl` | le harness (`truthloop verify`), jamais un agent |

Schémas JSON : `.github/truthloop/schemas/`.

## Consigne à copier

> Tu travailles pour truthloop. Réponds par un **unique** bloc ```json de la forme
> `{"entities": [...], "claims": [...], "chunks": [...], "abstentions": [...]}` et rien d'autre.
>
> - `entities` : chaque programme, table, document ou release que tu cites, sous la forme
>   `{"type": "program|table|doc|release", "id": "<identifiant exact du dossier de connaissance>"}`.
>   N'invente aucun identifiant : si tu n'es pas sûr qu'il existe, ne le cite pas.
> - `chunks` : les extraits qui prouvent ce que tu affirmes,
>   `{"id": "ev-1", "source": "<fichier ou vue du graphe>", "text": "<extrait littéral>", "score": 0.0-1.0}`.
>   Le texte doit contenir les identifiants tels qu'ils apparaissent dans la source.
> - `claims` : une affirmation par élément de réponse,
>   `{"id": "c1", "text": "...", "entities": ["<ids cités par la claim>"], "citations": ["ev-1"],
>   "relation": {"subject": "PRG_A", "predicate": "calls|called_by|reads|writes", "object": "PRG_B"},
>   "confidence_self": 0.0-1.0}`. `relation` est optionnelle. Chaque id de `entities` de la claim
>   doit figurer dans la liste `entities` globale ; chaque citation doit exister dans `chunks`.
> - `abstentions` : ce que tu n'as pas trouvé, `{"text": "...", "entities": ["<ids concernés>"]}`.
>   Une abstention honnête vaut mieux qu'une invention : elle n'est jamais pénalisée.
> - `confidence_self` : ta confiance réelle dans la claim ; un chiffre honnête, pas un
>   chiffre flatteur (le harness la compare au verdict).
> - Numérote localement (`c1`, `ev-1`, …) : l'orchestrateur renumérote.

## Exemple de fragment

```json
{
  "entities": [
    {"type": "program", "id": "PRG_ORD_VALID"},
    {"type": "program", "id": "PRG_ORD_SAVE"},
    {"type": "table", "id": "T_ORDERS"}
  ],
  "claims": [
    {
      "id": "c1",
      "text": "PRG_ORD_SAVE appelle PRG_ORD_VALID après validation du panier.",
      "entities": ["PRG_ORD_SAVE", "PRG_ORD_VALID"],
      "citations": ["ev-1"],
      "relation": {"subject": "PRG_ORD_SAVE", "predicate": "calls", "object": "PRG_ORD_VALID"},
      "confidence_self": 0.9
    },
    {
      "id": "c2",
      "text": "PRG_ORD_SAVE écrit dans T_ORDERS.",
      "entities": ["PRG_ORD_SAVE", "T_ORDERS"],
      "citations": ["ev-2"],
      "relation": {"subject": "PRG_ORD_SAVE", "predicate": "writes", "object": "T_ORDERS"}
    }
  ],
  "chunks": [
    {"id": "ev-1", "source": "graph:calls", "text": "PRG_ORD_SAVE -> PRG_ORD_VALID (call, task 3)", "score": 0.95},
    {"id": "ev-2", "source": "graph:program_tables", "text": "PRG_ORD_SAVE writes T_ORDERS", "score": 0.9}
  ],
  "abstentions": [
    {"text": "Appelants de PRG_ORD_VALID au-delà de la profondeur 1 non explorés.", "entities": ["PRG_ORD_VALID"]}
  ]
}
```

## Assemblage par l'orchestrateur

Le fragment ci-dessus, seul, devient `answer.json` :

```json
{
  "schema_version": 1,
  "question_id": "q-20260909-001",
  "iteration": 1,
  "producer": "truthloop-orchestrator",
  "entities": [
    {"type": "program", "id": "PRG_ORD_VALID"},
    {"type": "program", "id": "PRG_ORD_SAVE"},
    {"type": "table", "id": "T_ORDERS"}
  ],
  "claims": [
    {
      "id": "c1",
      "text": "PRG_ORD_SAVE appelle PRG_ORD_VALID après validation du panier.",
      "entities": ["PRG_ORD_SAVE", "PRG_ORD_VALID"],
      "citations": ["ev-1"],
      "relation": {"subject": "PRG_ORD_SAVE", "predicate": "calls", "object": "PRG_ORD_VALID"},
      "confidence_self": 0.9
    },
    {
      "id": "c2",
      "text": "PRG_ORD_SAVE écrit dans T_ORDERS.",
      "entities": ["PRG_ORD_SAVE", "T_ORDERS"],
      "citations": ["ev-2"],
      "relation": {"subject": "PRG_ORD_SAVE", "predicate": "writes", "object": "T_ORDERS"}
    }
  ],
  "abstentions": [
    {"text": "Appelants de PRG_ORD_VALID au-delà de la profondeur 1 non explorés.", "entities": ["PRG_ORD_VALID"]}
  ],
  "final_text": "PRG_ORD_VALID est appelé par PRG_ORD_SAVE, qui écrit dans T_ORDERS."
}
```

et `evidence.json` :

```json
{
  "schema_version": 1,
  "question_id": "q-20260909-001",
  "iteration": 1,
  "chunks": [
    {"id": "ev-1", "source": "graph:calls", "text": "PRG_ORD_SAVE -> PRG_ORD_VALID (call, task 3)", "score": 0.95},
    {"id": "ev-2", "source": "graph:program_tables", "text": "PRG_ORD_SAVE writes T_ORDERS", "score": 0.9}
  ]
}
```

## Ce que le harness vérifie ensuite

Existence des entités dans le graphe, rappel des appelants / appelés et des tables attendus,
présence d'une évidence par claim, cohérence des relations avec le graphe, puis le verdict
sémantique du juge. Le score doit atteindre le seuil (90 par défaut) pour publier.
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_kit_templates.py --no-cov -q`
Expected: `7 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 7 : Prompt d'installation, checklist, README, vérification finale

**Files:**
- Replace: `src/truthloop/integration/copilot/prompts/truthloop-install.prompt.md`
- Replace: `src/truthloop/integration/copilot/ACCEPTANCE.md`
- Modify: `tests/test_kit_templates.py`
- Modify: `README.md`

- [ ] **Step 1 : Test rouge**

```python
def test_install_prompt_and_acceptance() -> None:
    prompt = kit_path("prompts/truthloop-install.prompt.md").read_text(encoding="utf-8")
    meta = frontmatter(prompt)
    assert meta["name"] == "truthloop-install"
    assert meta["tools"] == ["read", "edit", "search", "runCommands"]
    rendered = render(prompt, SUBS, [])
    assert "'{{RETRIEVER_AGENTS}}'" in rendered  # the token Copilot must look for, left verbatim
    assert "{{" not in rendered.replace("'{{RETRIEVER_AGENTS}}'", "")
    assert ".github/truthloop/smoke/truthloop.yaml" in rendered
    assert "--version" in rendered
    acceptance = render(kit_path("ACCEPTANCE.md").read_text(encoding="utf-8"), SUBS, [])
    assert "{{" not in acceptance
    assert acceptance.count("- [ ]") >= 6
```

Note : le prompt cite le token `'{{RETRIEVER_AGENTS}}'` pour que Copilot sache quoi remplacer. L'installateur rend donc le prompt avec `retrievers=[]` (règle appliquée en Task 2, Step 4), ce qui laisse le token intact même quand `--retrievers` est fourni ; d'où l'exclusion dans l'assertion.

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_kit_templates.py::test_install_prompt_and_acceptance --no-cov -q`
Expected: FAIL (`".github/truthloop/smoke/truthloop.yaml" in rendered` faux sur le gabarit provisoire)

- [ ] **Step 3 : Écrire le prompt**

```markdown
<!-- fichier : prompts/truthloop-install.prompt.md -->
---
name: truthloop-install
description: "Câble les agents truthloop sur les retrievers existants de ce dépôt et lance le test de fumée."
tools: ['read', 'edit', 'search', 'runCommands']
---
Tu installes truthloop dans ce dépôt. Le kit a déjà été copié par
`truthloop install-copilot` ; il te reste le câblage et le test de fumée. Procède dans l'ordre
et demande confirmation avant l'étape 2.

1. **Inventaire.** Liste `.github/agents/*.agent.md`. Pour chaque agent, lis son frontmatter
   et son corps, et classe-le : *retriever* (il interroge le dossier de connaissance, le graphe
   des programmes, la documentation ou les release notes) ou *autre*. Note pour chaque
   retriever s'il dispose des outils `read` et `search` (information seulement). Présente un
   tableau nom / rôle / outils et demande confirmation de la liste des retrievers.
2. **Câblage de l'orchestrateur.** Dans `.github/agents/truthloop-orchestrator.agent.md`,
   remplace le token `'{{RETRIEVER_AGENTS}}'` (avec ses quotes) par les noms confirmés,
   chacun entre quotes simples et séparés par une virgule et une espace, par exemple
   `'rag-agent', 'graph-agent'`. Noms exacts, sensibles à la casse. Ne touche à rien d'autre
   dans ce fichier.
3. **Renvoi au contrat.** À la fin du corps de chaque retriever confirmé, ajoute la ligne :
   « Quand la consigne mentionne truthloop, respecte le format de fragment de
   `.github/instructions/truthloop-contract.instructions.md`. » Ne modifie rien d'autre.
4. **Test de fumée.** Depuis la racine du dépôt, exécute :
   `uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop --version`
   puis
   `uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop verify --run "runs/smoke" --config ".github/truthloop/smoke/truthloop.yaml" --json`.
   Attendu : code de retour 2, `"decision": "repair"`, deux actions `retrieve_entities`.
   Ce test utilise le graphe de fumée, pas la base de connaissance du dépôt. Rapporte le
   résultat exact ; si `uv` est introuvable, indique-le.
5. **Suite.** Rappelle la checklist `.github/truthloop/ACCEPTANCE.md` et propose de commencer
   par son premier point.
```

- [ ] **Step 4 : Écrire la checklist**

```markdown
<!-- fichier : ACCEPTANCE.md -->
# truthloop — checklist d'acceptation de l'intégration Copilot

À dérouler à la main dans ce dépôt, après `/truthloop-install`. Le harness s'exécute avec
`uv run --project "{{TRUTHLOOP_PROJECT}}" truthloop …` ; `uv` doit être sur le PATH du
terminal intégré (installation : https://docs.astral.sh/uv/).

- [ ] `/truthloop-install` a listé les retrievers, remplacé le placeholder de l'orchestrateur,
      et le test de fumée (graphe de fumée) a rendu `repair` avec deux actions
      `retrieve_entities`.
- [ ] Avec l'agent `truthloop-orchestrator`, une question d'impact sur un programme connu
      produit `runs/<id>/question.json`, `iter-01/{answer,evidence,judge,verdict}.json` et
      `trace.jsonl`.
- [ ] La boucle atteint `release` en au plus {{MAX_ITERATIONS}} itérations et la réponse
      affiche « Score truthloop : … ».
- [ ] Une question sur un programme inexistant donne un verdict avec `UNKNOWN_PIVOT` et une
      action `fix_question` ; l'orchestrateur propose le handoff dès la première itération.
- [ ] Après suppression de `iter-01/judge.json` et `truthloop verify --run runs/<id>
      --iteration 1` à la main : finding `JUDGE_MISSING`, plafond 85, action `run_judge`.
- [ ] Deux `truthloop verify` successifs sur la même itération donnent un `verdict.json`
      identique hors `provenance.generated_at`.
- [ ] `truthloop trace --run runs/<id>` liste toutes les itérations avec score et décision.
```

- [ ] **Step 5 : Vérifier le succès**

Run: `uv run pytest tests/test_kit_templates.py --no-cov -q`
Expected: `8 passed`

- [ ] **Step 6 : README**

Remplacer la section « Phase 2 : agents Copilot (à venir) » par « Phase 2 : intégration
Copilot » : la commande d'installation avec ses options (`--target`, `--knowledge`,
`--retrievers`, `--force`), ce qui est écrit dans le dépôt cible, le prompt `/truthloop-install`,
le principe (l'orchestrateur délègue, le juge écrit `judge.json` et lance `verify`, le harness
décide), et le renvoi à `ACCEPTANCE.md` et au spec de phase 2. Garder la section « Dépannage ».

- [ ] **Step 7 : Suite complète, lint, essai réel**

Run: `uv run ruff format src tests && uv run pytest -q && uv run ruff check src tests && uv run mypy`
Expected: 180 tests, couverture ≥ 85 %, aucune erreur.

Puis un essai réel dans un dossier vide du scratchpad :

```bash
uv run truthloop install-copilot --target <scratch>/magic --knowledge files:knowledge --retrievers rag-agent,graph-agent
cd <scratch>/magic && uv run --project "<repo>" truthloop verify --run runs/smoke --config .github/truthloop/smoke/truthloop.yaml --json ; echo "exit=$?"
```

Expected: liste des fichiers `créé`, puis `exit=2` avec `"decision": "repair"` et deux actions.
Vérifier aussi que `.github/agents/truthloop-orchestrator.agent.md` contient
`agents: ['truthloop-judge', 'rag-agent', 'graph-agent']` et le chemin absolu du dépôt.

- [ ] **Step 8 : Point de contrôle**

Commit du chunk : `✨ feat(truthloop): copilot agents, retriever contract and install prompt (phase 2)`.
