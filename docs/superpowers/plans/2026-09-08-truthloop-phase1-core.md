# truthloop phase 1 (cœur) — Plan d'implémentation

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer le harness déterministe `truthloop verify` : contrats pydantic, sources de connaissance (SQLite + fichiers), six graders, score avec plafonds, décision, plan de réparation, dossier de run et CLI, avec tests.

**Architecture:** Un paquet Python pur (`src/truthloop`) organisé par responsabilité : `contracts` (modèles strictes + validation croisée), `knowledge` (graphe en mémoire chargé depuis SQLite ou JSON/CSV), `graders` (fonctions pures qui produisent valeurs, findings et plafonds), `scoring` (agrégation + décision), `planner` (findings → actions), `runs` (layout disque + provenance), `engine` (orchestration d'une évaluation) et `cli` (argparse + Rich). Aucun appel réseau, aucun LLM : mêmes entrées ⇒ même verdict.

**Tech Stack:** Python 3.11, uv 0.11 (`uv_build`), pydantic 2.13 (`strict=True`, `extra="forbid"`), PyYAML 6, Rich 15, pytest 9 + pytest-cov, ruff 0.16, mypy strict. Spec de référence : `docs/superpowers/specs/2026-09-08-truthloop-design.md` (§ cités ci-dessous).

**Règles de travail :**
- TDD strict : test rouge, implémentation minimale, test vert, puis `ruff` + `mypy`.
- Lancer un test isolé avec `--no-cov` (le `--cov-fail-under=85` du `pyproject.toml` ferait échouer une exécution partielle). La suite complète, avec couverture, se lance en fin de chunk.
- **Commits :** la règle globale de l'utilisateur interdit tout commit non demandé. À la fin de chaque chunk, demander explicitement s'il faut committer ; ne jamais committer d'initiative.
- Toute la prose utilisateur (messages CLI, findings, instructions du plan de réparation) est en français ; le code, les identifiants et les docstrings sont en anglais.
- La première ligne de chaque bloc de code (`# src/truthloop/…` ou `# tests/…`) indique le fichier cible ; ne pas la recopier dans le fichier.
- `conftest` et `helpers` sont des modules first-party pour isort (`src = ["src", "tests"]`) : ils se placent dans le même bloc d'imports que `truthloop`, après une ligne vide qui suit les imports tiers.

---

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `pyproject.toml` (modifier) | Ajouter `[project.scripts] truthloop = "truthloop.cli:main"`. |
| `src/truthloop/__init__.py` | `__version__` depuis les métadonnées du paquet. |
| `src/truthloop/contracts/common.py` | `normalize_id`, `StrictModel`, `EntityRef`, alias `Literal` (`EntityType`, `Direction`, `Predicate`, `Intent`). |
| `src/truthloop/contracts/question.py` | `Question` (§4.1). |
| `src/truthloop/contracts/evidence.py` | `Chunk`, `Evidence` (§4.3). |
| `src/truthloop/contracts/judge.py` | `JudgedClaim`, `Judge` (§4.4). |
| `src/truthloop/contracts/answer.py` | `Relation`, `Claim`, `Abstention`, `Answer` + validation des références (§4.2, §4.0). |
| `src/truthloop/contracts/repair_plan.py` | `RepairEntity`, `RetrievalQueries`, `ContractError`, `RepairAction`, `RepairPlan` (§7). |
| `src/truthloop/contracts/verdict.py` | `Finding`, `Component`, `CapApplied`, `Provenance`, `Verdict`, constantes `COMPONENT_NAMES`, `CAP_NAMES` (§4.5). |
| `src/truthloop/contracts/schemas.py` | Export JSON Schema des six contrats. |
| `src/truthloop/contracts/bundle.py` | Chargement d'une itération + validation croisée → `LoadedIteration` (§4.0, §10). |
| `src/truthloop/contracts/__init__.py` | Ré-exports. |
| `src/truthloop/knowledge/graph.py` | `GraphRows`, `InMemoryGraph` (parcours, `has_edge`, `fingerprint`) (§5). |
| `src/truthloop/knowledge/sqlite.py` | `load_sqlite` : requêtes par défaut / surchargées → `InMemoryGraph` (§5.1). |
| `src/truthloop/knowledge/files.py` | `load_files` : `graph.json` ou CSV → `InMemoryGraph` (§5.2). |
| `src/truthloop/knowledge/__init__.py` | Protocole `KnowledgeSource` et ré-export de `KnowledgeError` (définie dans `graph.py`). |
| `src/truthloop/knowledge/factory.py` | `open_knowledge(kind, path, queries)` : choisit le backend depuis la config. |
| `src/truthloop/graders/base.py` | `GraderContext`, `GraderResult`, type `Grader`. |
| `src/truthloop/graders/citation.py` | CitationValidity (gate-only). |
| `src/truthloop/graders/coverage.py` | Coverage + TableCoverage (partagent E). |
| `src/truthloop/graders/evidence.py` | EvidenceSupport + règle de contenance par fenêtre de tokens. |
| `src/truthloop/graders/consistency.py` | Consistency (gate-only). |
| `src/truthloop/graders/rubric.py` | Adaptateur `judge.json`. |
| `src/truthloop/graders/__init__.py` | `ALL_GRADERS`, `run_graders`. |
| `src/truthloop/scoring.py` | `aggregate`, `decide` (§6.1, §6.2). |
| `src/truthloop/planner.py` | `PlannerInput`, `build_plan` (§7). |
| `src/truthloop/config.py` | Modèles de `truthloop.yaml`, `load_config`, `config_sha256`, `DEFAULT_CONFIG_YAML` (§8.3). |
| `src/truthloop/runs.py` | `RunDir`, `canonical_json`, `inputs_sha256`, trace (§8.1, §4.5). |
| `src/truthloop/engine.py` | `evaluate(run, config, knowledge, iteration, now) -> Verdict`, `EXIT_CODES`. |
| `src/truthloop/render.py` | Rendu Rich du verdict et de la trace. |
| `src/truthloop/cli.py` | `main(argv) -> int` : `init`, `verify`, `schema export`, `trace` (§8.2). |
| `tests/fixtures/graph.json` | Mini-graphe Magic fictif (8 programmes, 4 tables). |
| `tests/helpers.py` | Fabriques de dictionnaires `sample_question/answer/evidence/judge`. |
| `tests/conftest.py` | Fixtures `graph`, `sqlite_path`, `make_run`. |
| `tests/test_*.py` | Un fichier de test par module. |

Faits attendus sur le graphe de fixture (utilisés partout dans les tests) :

| Requête | Résultat |
|---|---|
| `neighbors(prg_ord_valid, callers, 1)` | `{prg_ord_save, prg_ord_notify}` |
| `neighbors(prg_ord_valid, callers, 2)` | `{prg_ord_save, prg_ord_notify, prg_main_menu}` |
| `neighbors(prg_ord_valid, callees, 1)` | `{prg_cust_load, prg_inv_check}` |
| `neighbors(prg_ord_valid, both, 1)` | `{prg_ord_save, prg_ord_notify, prg_cust_load, prg_inv_check}` |
| `neighbors(prg_ord_valid, both, 2)` | les 4 ci-dessus + `{prg_main_menu, prg_ord_archive}` |
| `programs_of({t_orders})` | `{prg_ord_save, prg_ord_valid, prg_ord_archive, prg_report}` |
| `tables_of({prg_ord_save})` | `{t_orders, t_order_lines}` |
| `tables_of(E(both,1) ∪ {prg_ord_valid})` | `{t_orders, t_order_lines, t_customers, t_stock}` |

---

## Chunk 1 : socle et contrats

### Task 1 : Point d'entrée et version

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/truthloop/__init__.py`
- Create: `tests/test_package.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_package.py
import truthloop


def test_version_is_exposed() -> None:
    assert truthloop.__version__ == "0.1.0"
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_package.py --no-cov -q`
Expected: FAIL, `AttributeError: module 'truthloop' has no attribute '__version__'`

- [ ] **Step 3 : Implémenter**

Remplacer `src/truthloop/__init__.py` :

```python
# src/truthloop/__init__.py
"""truthloop: deterministic retrieval-evaluation harness."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("truthloop")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = ["__version__"]
```

Ajouter dans `pyproject.toml`, juste après le bloc `[project]` (avant `[project.optional-dependencies]`) :

```toml
[project.scripts]
truthloop = "truthloop.cli:main"
```

Dans `[tool.mypy]`, ajouter le plugin pydantic (sans lui, `disallow_any_explicit` rejette toute
sous-classe de `BaseModel` ; vérifié le 2026-09-08 avec mypy 2.3.1 et pydantic 2.13.5) :

```toml
plugins = ["pydantic.mypy"]
```

Dans `[[tool.mypy.overrides]]`, remplacer `module = ["tests.*"]` par
`module = ["conftest", "helpers"]` (sans `tests/__init__.py`, les modules de test ne sont pas dans
un paquet `tests`, et mypy n'accepte pas le motif `test_*`).

Dans `[tool.ruff.lint] ignore`, ajouter `"PLR0917"` (trop d'arguments positionnels : même
justification que `PLR0913`, déjà ignoré, pour `decide` et les helpers de parcours du graphe) et `"E501"` avec le commentaire
`# line-too-long : le formateur gère la longueur ; seules les chaînes longues restent` (les
messages d'erreur en français dépassent parfois 100 colonnes, et `ruff format` ne coupe pas les
chaînes).

Puis `uv sync` (réinstalle le paquet en mode éditable avec le script).

- [ ] **Step 4 : Vérifier le succès**

Run: `uv sync -q && uv run pytest tests/test_package.py --no-cov -q`
Expected: `1 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur. `ruff format` réécrit les fichiers (longueur de ligne, virgules finales) : c'est voulu, le code du plan n'est pas garanti formaté.

### Task 2 : Contrats communs (`normalize_id`, `EntityRef`)

**Files:**
- Create: `src/truthloop/contracts/__init__.py` (vide pour l'instant)
- Create: `src/truthloop/contracts/common.py`
- Create: `tests/test_contracts_common.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_contracts_common.py
import pytest
from pydantic import ValidationError

from truthloop.contracts.common import EntityRef, normalize_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PRG_ORD_VALID", "prg_ord_valid"),
        ("  PRG-ORD  VALID ", "prg_ord_valid"),
        ("prg__ord-_valid", "prg_ord_valid"),
        ("T ORDERS", "t_orders"),
        ("-", "_"),
    ],
)
def test_normalize_id(raw: str, expected: str) -> None:
    assert normalize_id(raw) == expected


def test_entity_ref_normalizes_and_hashes() -> None:
    a = EntityRef(type="program", id="PRG-ORD-VALID")
    b = EntityRef(type="program", id="prg_ord_valid")
    assert a.id == "prg_ord_valid"
    assert a == b
    assert len({a, b}) == 1


def test_entity_ref_rejects_blank_and_unknown_type() -> None:
    with pytest.raises(ValidationError):
        EntityRef(type="program", id="   ")
    with pytest.raises(ValidationError):
        EntityRef.model_validate({"type": "module", "id": "x"})


def test_entity_ref_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EntityRef.model_validate({"type": "program", "id": "x", "name": "y"})
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_contracts_common.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.contracts'`

- [ ] **Step 3 : Implémenter**

`src/truthloop/contracts/__init__.py` : fichier vide (une docstring suffit).

```python
# src/truthloop/contracts/common.py
"""Shared building blocks for every truthloop contract (spec §4.0)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EntityType = Literal["program", "table", "doc", "release"]
Direction = Literal["callers", "callees", "both"]
Predicate = Literal["calls", "called_by", "reads", "writes"]
Intent = Literal["impact_analysis", "architecture", "feature", "diagram"]
SchemaVersion = Literal[1]

_SEPARATORS = re.compile(r"[-_\s]+")


def normalize_id(raw: str) -> str:
    """Canonical id: trimmed, casefolded, separators collapsed to ``_``."""
    return _SEPARATORS.sub("_", raw.strip().casefold())


class StrictModel(BaseModel):
    """Base for every contract: no coercion, no unknown fields."""

    model_config = ConfigDict(extra="forbid", strict=True)


class EntityRef(StrictModel):
    """A typed, normalized reference to a knowledge-graph entity."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    type: EntityType
    id: str = Field(min_length=1)

    @field_validator("id")
    @classmethod
    def _normalize(cls, value: str) -> str:
        normalized = normalize_id(value)
        if not normalized:
            raise ValueError("entity id is empty after normalization")
        return normalized
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_contracts_common.py --no-cov -q`
Expected: `8 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 3 : Contrat `Question`

**Files:**
- Create: `src/truthloop/contracts/question.py`
- Create: `tests/test_contracts_question.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_contracts_question.py
import pytest
from pydantic import ValidationError

from truthloop.contracts.common import EntityRef
from truthloop.contracts.question import Question


def test_question_defaults_and_pivot_helpers() -> None:
    q = Question.model_validate(
        {
            "schema_version": 1,
            "id": "q-001",
            "text": "Impact de PRG_ORD_VALID ?",
            "intent": "impact_analysis",
            "pivot_entities": [
                {"type": "program", "id": "PRG_ORD_VALID"},
                {"type": "table", "id": "T_ORDERS"},
            ],
        }
    )
    assert q.direction == "both"
    assert q.depth == 1
    assert q.pivot_programs == {EntityRef(type="program", id="prg_ord_valid")}
    assert q.pivot_tables == {EntityRef(type="table", id="t_orders")}


@pytest.mark.parametrize(
    "patch",
    [
        {"depth": 0},
        {"depth": 6},
        {"intent": "other"},
        {"pivot_entities": [{"type": "doc", "id": "d1"}]},
        {"schema_version": 2},
        {"text": ""},
    ],
)
def test_question_rejects_invalid(patch: dict[str, object]) -> None:
    base: dict[str, object] = {"id": "q", "text": "t", "intent": "architecture"}
    with pytest.raises(ValidationError):
        Question.model_validate({**base, **patch})
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_contracts_question.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.contracts.question'`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/contracts/question.py
"""question.json contract (spec §4.1)."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from truthloop.contracts.common import Direction, EntityRef, Intent, SchemaVersion, StrictModel


class Question(StrictModel):
    schema_version: SchemaVersion = 1
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    intent: Intent
    pivot_entities: list[EntityRef] = Field(default_factory=list)
    direction: Direction = "both"
    depth: int = Field(default=1, ge=1, le=5)

    @model_validator(mode="after")
    def _pivots_are_programs_or_tables(self) -> Self:
        for pivot in self.pivot_entities:
            if pivot.type not in ("program", "table"):
                raise ValueError(f"pivot {pivot.id!r} must be a program or a table")
        return self

    @property
    def pivot_programs(self) -> set[EntityRef]:
        return {p for p in self.pivot_entities if p.type == "program"}

    @property
    def pivot_tables(self) -> set[EntityRef]:
        return {p for p in self.pivot_entities if p.type == "table"}
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_contracts_question.py --no-cov -q`
Expected: `7 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 4 : Contrats `Evidence` et `Judge`

**Files:**
- Create: `src/truthloop/contracts/evidence.py`
- Create: `src/truthloop/contracts/judge.py`
- Create: `tests/test_contracts_evidence_judge.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_contracts_evidence_judge.py
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
        Evidence.model_validate(_evidence([{"id": "ev-1", "source": "s", "text": "t", "score": 1.5}]))


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
        _judge([{"id": "c1", "verdict": "supported", "rationale": "ok"}, {"id": "c2", "verdict": "partially"}])
    )
    assert judge.verdict_by_claim() == {"c1": "supported", "c2": "partially"}
    assert judge.judge_model == ""
    assert judge.notes == ""


def test_judge_rejects_duplicate_claim_and_bad_verdict() -> None:
    with pytest.raises(ValidationError):
        Judge.model_validate(_judge([{"id": "c1", "verdict": "supported"}, {"id": "c1", "verdict": "supported"}]))
    with pytest.raises(ValidationError):
        Judge.model_validate(_judge([{"id": "c1", "verdict": "maybe"}]))
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_contracts_evidence_judge.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/contracts/evidence.py
"""evidence.json contract (spec §4.3)."""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from truthloop.contracts.common import SchemaVersion, StrictModel


class Chunk(StrictModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    text: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class Evidence(StrictModel):
    schema_version: SchemaVersion = 1
    question_id: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    chunks: list[Chunk] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_chunk_ids(self) -> Self:
        seen: set[str] = set()
        for chunk in self.chunks:
            if chunk.id in seen:
                raise ValueError(f"duplicate chunk id {chunk.id!r}")
            seen.add(chunk.id)
        return self

    def chunk_by_id(self) -> dict[str, Chunk]:
        return {chunk.id: chunk for chunk in self.chunks}
```

```python
# src/truthloop/contracts/judge.py
"""judge.json contract, filled by the Copilot judge agent (spec §4.4)."""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from truthloop.contracts.common import SchemaVersion, StrictModel

ClaimVerdict = Literal["supported", "partially", "unsupported", "contradicted"]


class JudgedClaim(StrictModel):
    id: str = Field(min_length=1)
    verdict: ClaimVerdict
    rationale: str = ""


class Judge(StrictModel):
    schema_version: SchemaVersion = 1
    question_id: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    judge_model: str = ""
    claims: list[JudgedClaim] = Field(default_factory=list)
    relevance: float = Field(ge=0.0, le=1.0)
    completeness: float = Field(ge=0.0, le=1.0)
    notes: str = ""

    @model_validator(mode="after")
    def _unique_claim_ids(self) -> Self:
        seen: set[str] = set()
        for claim in self.claims:
            if claim.id in seen:
                raise ValueError(f"duplicate judged claim id {claim.id!r}")
            seen.add(claim.id)
        return self

    def verdict_by_claim(self) -> dict[str, ClaimVerdict]:
        return {claim.id: claim.verdict for claim in self.claims}
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_contracts_evidence_judge.py --no-cov -q`
Expected: `4 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 5 : Contrat `Answer` et validation des références

**Files:**
- Create: `src/truthloop/contracts/answer.py`
- Create: `tests/test_contracts_answer.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_contracts_answer.py
import pytest
from pydantic import ValidationError

from truthloop.contracts.answer import RELATION_OBJECT_TYPE, Answer


def _answer(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "question_id": "q",
        "iteration": 1,
        "producer": "graph-retriever",
        "entities": [
            {"type": "program", "id": "PRG_ORD_SAVE"},
            {"type": "program", "id": "prg-ord-save"},
            {"type": "program", "id": "PRG_ORD_VALID"},
            {"type": "table", "id": "T_ORDERS"},
        ],
        "claims": [
            {
                "id": "c1",
                "text": "PRG_ORD_SAVE appelle PRG_ORD_VALID.",
                "entities": ["PRG-ORD-SAVE", "PRG_ORD_VALID"],
                "citations": ["ev-1"],
                "relation": {"subject": "PRG_ORD_SAVE", "predicate": "calls", "object": "PRG_ORD_VALID"},
                "confidence_self": 0.8,
            }
        ],
        "abstentions": [{"text": "Profondeur 2 non explorée.", "entities": ["PRG_ORD_VALID"]}],
        "final_text": "…",
    }
    return {**base, **patch}


def test_answer_dedupes_entities_and_normalizes_claim_ids() -> None:
    answer = Answer.model_validate(_answer())
    assert [e.id for e in answer.entities] == ["prg_ord_save", "prg_ord_valid", "t_orders"]
    assert answer.claims[0].entities == ["prg_ord_save", "prg_ord_valid"]
    assert answer.claims[0].relation is not None
    assert answer.claims[0].relation.object == "prg_ord_valid"
    assert answer.abstentions[0].entities == ["prg_ord_valid"]


def test_relation_object_type_table() -> None:
    assert RELATION_OBJECT_TYPE["reads"] == "table"
    assert RELATION_OBJECT_TYPE["calls"] == "program"


@pytest.mark.parametrize(
    ("patch", "reason"),
    [
        ({"claims": [{"id": "c1", "text": "t", "entities": ["PRG_UNKNOWN"]}]}, "undeclared claim entity"),
        ({"abstentions": [{"text": "t", "entities": ["PRG_UNKNOWN"]}]}, "undeclared abstention entity"),
        ({"claims": [{"id": "c1", "text": "t"}, {"id": "c1", "text": "t"}]}, "duplicate claim id"),
        (
            {
                "claims": [
                    {
                        "id": "c1",
                        "text": "t",
                        "relation": {"subject": "T_ORDERS", "predicate": "calls", "object": "PRG_ORD_VALID"},
                    }
                ]
            },
            "relation subject must be a program",
        ),
        (
            {
                "claims": [
                    {
                        "id": "c1",
                        "text": "t",
                        "relation": {"subject": "PRG_ORD_SAVE", "predicate": "reads", "object": "PRG_ORD_VALID"},
                    }
                ]
            },
            "reads object must be a table",
        ),
        ({"claims": [{"id": "c1", "text": "t", "confidence_self": 2}]}, "confidence out of range"),
        ({"iteration": 0}, "iteration must be >= 1"),
    ],
)
def test_answer_rejects_invalid(patch: dict[str, object], reason: str) -> None:
    with pytest.raises(ValidationError, match=r".+"):
        Answer.model_validate(_answer(**patch))
    assert reason


def test_same_id_declared_as_program_and_table_is_two_entities() -> None:
    answer = Answer.model_validate(
        _answer(entities=[{"type": "program", "id": "X"}, {"type": "table", "id": "X"}], claims=[], abstentions=[])
    )
    assert len(answer.entities) == 2
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_contracts_answer.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/contracts/answer.py
"""answer.json contract and cross-reference rules (spec §4.0, §4.2)."""

from __future__ import annotations

from typing import Final, Self

from pydantic import Field, field_validator, model_validator

from truthloop.contracts.common import (
    EntityRef,
    EntityType,
    Predicate,
    SchemaVersion,
    StrictModel,
    normalize_id,
)

RELATION_OBJECT_TYPE: Final[dict[Predicate, EntityType]] = {
    "calls": "program",
    "called_by": "program",
    "reads": "table",
    "writes": "table",
}


def _normalize_all(values: list[str]) -> list[str]:
    normalized = [normalize_id(v) for v in values]
    if any(not v for v in normalized):
        raise ValueError("entity id is empty after normalization")
    return normalized


class Relation(StrictModel):
    subject: str = Field(min_length=1)
    predicate: Predicate
    object: str = Field(min_length=1)

    @field_validator("subject", "object")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return _normalize_all([value])[0]


class Claim(StrictModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    entities: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    relation: Relation | None = None
    confidence_self: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("entities")
    @classmethod
    def _normalize(cls, value: list[str]) -> list[str]:
        return _normalize_all(value)


class Abstention(StrictModel):
    text: str = Field(min_length=1)
    entities: list[str] = Field(default_factory=list)

    @field_validator("entities")
    @classmethod
    def _normalize(cls, value: list[str]) -> list[str]:
        return _normalize_all(value)


class Answer(StrictModel):
    schema_version: SchemaVersion = 1
    question_id: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    producer: str = Field(min_length=1)
    entities: list[EntityRef] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    abstentions: list[Abstention] = Field(default_factory=list)
    final_text: str = ""

    @model_validator(mode="after")
    def _check_references(self) -> Self:
        self.entities = _dedupe(self.entities)
        declared: dict[str, set[EntityType]] = {}
        for entity in self.entities:
            declared.setdefault(entity.id, set()).add(entity.type)
        claim_ids: set[str] = set()
        for claim in self.claims:
            if claim.id in claim_ids:
                raise ValueError(f"duplicate claim id {claim.id!r}")
            claim_ids.add(claim.id)
            _check_declared(claim.entities, declared, f"claim {claim.id!r}")
            if claim.relation is not None:
                _check_relation(claim.relation, declared, claim.id)
        for abstention in self.abstentions:
            _check_declared(abstention.entities, declared, "abstention")
        return self

    def entities_of_type(self, entity_type: EntityType) -> set[EntityRef]:
        return {e for e in self.entities if e.type == entity_type}


def _dedupe(entities: list[EntityRef]) -> list[EntityRef]:
    seen: set[EntityRef] = set()
    unique: list[EntityRef] = []
    for entity in entities:
        if entity not in seen:
            seen.add(entity)
            unique.append(entity)
    return unique


def _check_declared(ids: list[str], declared: dict[str, set[EntityType]], owner: str) -> None:
    for entity_id in ids:
        if entity_id not in declared:
            raise ValueError(f"{owner} references entity {entity_id!r} not declared in entities")


def _check_relation(relation: Relation, declared: dict[str, set[EntityType]], claim_id: str) -> None:
    if "program" not in declared.get(relation.subject, set()):
        raise ValueError(f"claim {claim_id!r}: relation subject {relation.subject!r} must be a declared program")
    expected = RELATION_OBJECT_TYPE[relation.predicate]
    if expected not in declared.get(relation.object, set()):
        raise ValueError(
            f"claim {claim_id!r}: relation object {relation.object!r} must be a declared {expected}"
        )
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_contracts_answer.py --no-cov -q`
Expected: `10 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 6 : Contrats `RepairPlan`, `Verdict` et export des schémas

**Files:**
- Create: `src/truthloop/contracts/repair_plan.py`
- Create: `src/truthloop/contracts/verdict.py`
- Create: `src/truthloop/contracts/schemas.py`
- Modify: `src/truthloop/contracts/__init__.py`
- Create: `tests/test_contracts_verdict.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_contracts_verdict.py
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from truthloop.contracts.repair_plan import RepairAction, RepairPlan
from truthloop.contracts.schemas import CONTRACTS, export_schemas
from truthloop.contracts.verdict import (
    CAP_NAMES,
    COMPONENT_NAMES,
    CapApplied,
    Component,
    Finding,
    Provenance,
    Verdict,
)


def _provenance() -> Provenance:
    return Provenance(
        harness_version="0.1.0",
        inputs_sha256="0" * 64,
        config_sha256="0" * 64,
        knowledge_source="files:tests/fixtures/graph.json",
        knowledge_fingerprint="0" * 64,
        generated_at="2026-09-08T19:40:12+00:00",
    )


def test_verdict_round_trips_through_json() -> None:
    verdict = Verdict(
        question_id="q",
        iteration=1,
        score=76.5,
        decision="repair",
        threshold=90.0,
        components={
            name: Component(value=0.5, weight=0.2, applicable=True) for name in COMPONENT_NAMES
        },
        caps_applied=[CapApplied(name="contradiction", value=70)],
        findings=[Finding(code="MISSING_ENTITY", severity="major", detail="x", depth=1, via="p")],
        declared_gaps=["gap"],
        repair_plan=RepairPlan(
            actions=[
                RepairAction(
                    id="a1", kind="write_claims", priority=1, expected_gain=23.5, instruction="…"
                )
            ],
            summary_for_agent="…",
        ),
        provenance=_provenance(),
    )
    again = Verdict.model_validate_json(verdict.model_dump_json())
    assert again == verdict
    assert set(COMPONENT_NAMES) == {
        "context_recall",
        "table_recall",
        "evidence_support",
        "faithfulness",
        "relevance_completeness",
    }
    assert set(CAP_NAMES) == {"unknown_entity", "contradiction", "missing_judge", "missing_claims"}


def test_finding_rejects_unknown_code() -> None:
    with pytest.raises(ValidationError):
        Finding.model_validate({"code": "SOMETHING", "severity": "info", "detail": "x"})


def test_export_schemas_writes_six_files(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)
    names = sorted(p.name for p in written)
    assert names == sorted(f"{name}.schema.json" for name in CONTRACTS)
    assert set(CONTRACTS) == {"question", "answer", "evidence", "judge", "verdict", "repair_plan"}
    schema = json.loads((tmp_path / "answer.schema.json").read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_contracts_verdict.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/contracts/repair_plan.py
"""repair_plan contract embedded in verdict.json (spec §7)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from truthloop.contracts.common import EntityType, SchemaVersion, StrictModel

ActionKind = Literal[
    "retrieve_entities",
    "verify_claim",
    "write_claims",
    "improve_answer",
    "fix_question",
    "run_judge",
    "fix_contract",
]


class RepairEntity(StrictModel):
    type: EntityType
    id: str = Field(min_length=1)
    depth: int | None = None
    via: str | None = None


class RetrievalQueries(StrictModel):
    graph: str
    rag: str


class ContractError(StrictModel):
    loc: str
    msg: str


class RepairAction(StrictModel):
    id: str = Field(min_length=1)
    kind: ActionKind
    priority: int = Field(ge=1)
    expected_gain: float = Field(ge=0.0)
    instruction: str
    entities: list[RepairEntity] = Field(default_factory=list)
    queries: RetrievalQueries | None = None
    claim_ids: list[str] = Field(default_factory=list)
    component: str | None = None
    errors: list[ContractError] = Field(default_factory=list)


class RepairPlan(StrictModel):
    schema_version: SchemaVersion = 1
    actions: list[RepairAction] = Field(default_factory=list)
    summary_for_agent: str = ""
```

```python
# src/truthloop/contracts/verdict.py
"""verdict.json contract (spec §4.5)."""

from __future__ import annotations

from typing import Final, Literal, Self

from pydantic import Field, model_validator

from truthloop.contracts.common import EntityRef, SchemaVersion, StrictModel
from truthloop.contracts.repair_plan import RepairPlan

Severity = Literal["critical", "major", "info"]
Decision = Literal["release", "repair", "escalate", "invalid"]
FindingCode = Literal[
    "UNKNOWN_ENTITY",
    "UNKNOWN_PIVOT",
    "MISSING_ENTITY",
    "EXTRA_ENTITY",
    "MISSING_TABLE",
    "UNSUPPORTED_CLAIM",
    "DANGLING_CITATION",
    "NO_CLAIMS",
    "CONTRADICTED_BY_GRAPH",
    "CONTRADICTED_BY_EVIDENCE",
    "JUDGE_MISSING",
    "JUDGE_INCOMPLETE",
    "JUDGE_UNSUPPORTED",
    "JUDGE_PARTIAL",
]

COMPONENT_NAMES: Final[tuple[str, ...]] = (
    "context_recall",
    "table_recall",
    "evidence_support",
    "faithfulness",
    "relevance_completeness",
)
CAP_NAMES: Final[tuple[str, ...]] = ("unknown_entity", "contradiction", "missing_judge", "missing_claims")


class Finding(StrictModel):
    code: FindingCode
    severity: Severity
    detail: str
    entity: EntityRef | None = None
    claim_id: str | None = None
    depth: int | None = None
    via: str | None = None


class Component(StrictModel):
    value: float | None
    weight: float = Field(ge=0.0)
    applicable: bool


class CapApplied(StrictModel):
    name: str
    value: int = Field(ge=0, le=100)


class Provenance(StrictModel):
    harness_version: str
    inputs_sha256: str
    config_sha256: str
    knowledge_source: str
    knowledge_fingerprint: str
    generated_at: str


class Verdict(StrictModel):
    schema_version: SchemaVersion = 1
    question_id: str = Field(min_length=1)
    iteration: int = Field(ge=1)
    score: float = Field(ge=0.0, le=100.0)
    decision: Decision
    threshold: float = Field(ge=0.0, le=100.0)
    components: dict[str, Component]
    caps_applied: list[CapApplied] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    declared_gaps: list[str] = Field(default_factory=list)
    repair_plan: RepairPlan
    provenance: Provenance

    @model_validator(mode="after")
    def _components_are_complete(self) -> Self:
        if set(self.components) != set(COMPONENT_NAMES):
            raise ValueError(f"components doit contenir exactement {sorted(COMPONENT_NAMES)}")
        return self
```

```python
# src/truthloop/contracts/schemas.py
"""JSON Schema export for the contracts (spec §8.2, `truthloop schema export`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from pydantic import BaseModel

from truthloop.contracts.answer import Answer
from truthloop.contracts.evidence import Evidence
from truthloop.contracts.judge import Judge
from truthloop.contracts.question import Question
from truthloop.contracts.repair_plan import RepairPlan
from truthloop.contracts.verdict import Verdict

CONTRACTS: Final[dict[str, type[BaseModel]]] = {
    "question": Question,
    "answer": Answer,
    "evidence": Evidence,
    "judge": Judge,
    "verdict": Verdict,
    "repair_plan": RepairPlan,
}


def export_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, model in CONTRACTS.items():
        path = out_dir / f"{name}.schema.json"
        schema = model.model_json_schema()
        path.write_text(json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written
```

```python
# src/truthloop/contracts/__init__.py
"""Pydantic contracts exchanged between Copilot agents and the harness (spec §4)."""

from truthloop.contracts.answer import Abstention, Answer, Claim, Relation
from truthloop.contracts.common import EntityRef, StrictModel, normalize_id
from truthloop.contracts.evidence import Chunk, Evidence
from truthloop.contracts.judge import Judge, JudgedClaim
from truthloop.contracts.question import Question
from truthloop.contracts.repair_plan import ContractError, RepairAction, RepairPlan
from truthloop.contracts.verdict import CapApplied, Component, Finding, Provenance, Verdict

__all__ = [
    "Abstention",
    "Answer",
    "CapApplied",
    "Chunk",
    "Claim",
    "Component",
    "ContractError",
    "EntityRef",
    "Evidence",
    "Finding",
    "Judge",
    "JudgedClaim",
    "Provenance",
    "Question",
    "Relation",
    "RepairAction",
    "RepairPlan",
    "StrictModel",
    "Verdict",
    "normalize_id",
]
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_contracts_verdict.py --no-cov -q`
Expected: `3 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 7 : Chargement d'une itération et validation croisée (`bundle`)

**Files:**
- Create: `src/truthloop/contracts/bundle.py`
- Create: `tests/helpers.py`
- Create: `tests/conftest.py` (fixture `make_run`, complété en Task 8)
- Create: `tests/test_contracts_bundle.py`

- [ ] **Step 1 : Écrire les fabriques de test**

```python
# tests/helpers.py
"""Dictionary factories mirroring the JSON files agents produce."""

from __future__ import annotations

import json
from pathlib import Path


def sample_question(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "id": "q-001",
        "text": "Quels programmes et tables sont impactés si je modifie PRG_ORD_VALID ?",
        "intent": "impact_analysis",
        "pivot_entities": [{"type": "program", "id": "PRG_ORD_VALID"}],
        "direction": "both",
        "depth": 1,
    }
    return {**base, **patch}


def sample_answer(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "question_id": "q-001",
        "iteration": 1,
        "producer": "graph-retriever",
        "entities": [
            {"type": "program", "id": "PRG_ORD_VALID"},
            {"type": "program", "id": "PRG_ORD_SAVE"},
            {"type": "program", "id": "PRG_ORD_NOTIFY"},
            {"type": "table", "id": "T_ORDERS"},
        ],
        "claims": [
            {
                "id": "c1",
                "text": "PRG_ORD_SAVE appelle PRG_ORD_VALID.",
                "entities": ["PRG_ORD_SAVE", "PRG_ORD_VALID"],
                "citations": ["ev-1"],
                "relation": {"subject": "PRG_ORD_SAVE", "predicate": "calls", "object": "PRG_ORD_VALID"},
                "confidence_self": 0.8,
            },
            {
                "id": "c2",
                "text": "PRG_ORD_NOTIFY appelle PRG_ORD_VALID.",
                "entities": ["PRG_ORD_NOTIFY", "PRG_ORD_VALID"],
                "citations": ["ev-2"],
            },
        ],
        "abstentions": [{"text": "Profondeur 2 non explorée.", "entities": ["PRG_ORD_VALID"]}],
        "final_text": "PRG_ORD_VALID est appelé par PRG_ORD_SAVE et PRG_ORD_NOTIFY.",
    }
    return {**base, **patch}


def sample_evidence(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "question_id": "q-001",
        "iteration": 1,
        "chunks": [
            {"id": "ev-1", "source": "graph:calls", "text": "PRG_ORD_SAVE -> PRG_ORD_VALID (call)", "score": 0.9},
            {"id": "ev-2", "source": "graph:calls", "text": "PRG_ORD_NOTIFY calls PRG-ORD-VALID", "score": 0.8},
        ],
    }
    return {**base, **patch}


def sample_judge(**patch: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "question_id": "q-001",
        "iteration": 1,
        "judge_model": "test-judge",
        "claims": [
            {"id": "c1", "verdict": "supported", "rationale": "ev-1"},
            {"id": "c2", "verdict": "supported", "rationale": "ev-2"},
        ],
        "relevance": 0.9,
        "completeness": 0.7,
        "notes": "",
    }
    return {**base, **patch}


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
```

```python
# tests/conftest.py
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from helpers import write_json

RunBuilder = Callable[..., Path]


@pytest.fixture
def make_run(tmp_path: Path) -> RunBuilder:
    """Write a run directory; pass ``None`` to omit a file."""

    def _make(
        question: dict[str, object] | None,
        answer: dict[str, object] | None,
        evidence: dict[str, object] | None,
        judge: dict[str, object] | None,
        *,
        iteration: int = 1,
        run_id: str = "q-001",
    ) -> Path:
        run_dir = tmp_path / "runs" / run_id
        iter_dir = run_dir / f"iter-{iteration:02d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        if question is not None:
            write_json(run_dir / "question.json", question)
        for name, data in (("answer", answer), ("evidence", evidence), ("judge", judge)):
            if data is not None:
                write_json(iter_dir / f"{name}.json", data)
        return run_dir

    return _make
```

- [ ] **Step 2 : Test rouge**

```python
# tests/test_contracts_bundle.py
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
```

- [ ] **Step 3 : Vérifier l'échec**

Run: `uv run pytest tests/test_contracts_bundle.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.contracts.bundle'`

- [ ] **Step 4 : Implémenter**

```python
# src/truthloop/contracts/bundle.py
"""Load one iteration of a run and apply cross-file rules (spec §4.0, §4.4, §10)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from truthloop.contracts.answer import Answer
from truthloop.contracts.evidence import Evidence
from truthloop.contracts.judge import Judge
from truthloop.contracts.question import Question
from truthloop.contracts.repair_plan import ContractError

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class RunBundle:
    question: Question
    answer: Answer
    evidence: Evidence
    judge: Judge | None


@dataclass
class LoadedIteration:
    """Either a valid bundle or the list of contract errors, plus raw JSON for hashing."""

    bundle: RunBundle | None
    errors: list[ContractError] = field(default_factory=list)
    raw: dict[str, object] = field(default_factory=dict)


def load_iteration(question: Question, iteration_dir: Path, iteration: int) -> LoadedIteration:
    loaded = LoadedIteration(bundle=None)
    answer_data = _read(iteration_dir / "answer.json", "answer", loaded, required=True)
    evidence_data = _read(iteration_dir / "evidence.json", "evidence", loaded, required=True)
    judge_data = _read(iteration_dir / "judge.json", "judge", loaded, required=False)

    answer = _validate(Answer, answer_data, "answer", loaded) if answer_data is not None else None
    evidence = _validate(Evidence, evidence_data, "evidence", loaded) if evidence_data is not None else None
    judge = _validate(Judge, judge_data, "judge", loaded) if judge_data is not None else None

    for label, doc in (("answer", answer), ("evidence", evidence), ("judge", judge)):
        if doc is None:
            continue
        if doc.question_id != question.id:
            loaded.errors.append(ContractError(loc=f"{label}.question_id", msg=f"attendu {question.id!r}"))
        if doc.iteration != iteration:
            loaded.errors.append(ContractError(loc=f"{label}.iteration", msg=f"attendu {iteration}"))
    if judge is not None and answer is not None:
        known = {claim.id for claim in answer.claims}
        for index, claim in enumerate(judge.claims):
            if claim.id not in known:
                loaded.errors.append(
                    ContractError(
                        loc=_format_loc("judge", ("claims", index, "id")),
                        msg=f"claim {claim.id!r} absente de answer.json",
                    )
                )
    if not loaded.errors and answer is not None and evidence is not None:
        loaded.bundle = RunBundle(question=question, answer=answer, evidence=evidence, judge=judge)
    return loaded


def _read(path: Path, label: str, loaded: LoadedIteration, *, required: bool) -> object | None:
    if not path.is_file():
        if required:
            loaded.errors.append(ContractError(loc=label, msg="fichier manquant"))
        return None
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # ValueError covers JSONDecodeError and UnicodeDecodeError
        loaded.errors.append(ContractError(loc=label, msg=f"JSON invalide : {exc}"))
        return None
    loaded.raw[label] = data
    if not isinstance(data, dict):
        loaded.errors.append(ContractError(loc=label, msg="objet JSON attendu"))
        return None
    return data


def _validate(model: type[ModelT], data: object, label: str, loaded: LoadedIteration) -> ModelT | None:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        loaded.errors.extend(errors_from(exc, label))
        return None


def _format_loc(label: str, parts: Sequence[object]) -> str:
    suffix = ".".join(str(part) for part in parts)
    return f"{label}.{suffix}" if suffix else label


def errors_from(exc: ValidationError, label: str) -> list[ContractError]:
    return [ContractError(loc=_format_loc(label, err["loc"]), msg=str(err["msg"])) for err in exc.errors()]
```

- [ ] **Step 5 : Vérifier le succès**

Run: `uv run pytest tests/test_contracts_bundle.py --no-cov -q`
Expected: `6 passed`

- [ ] **Step 6 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur. Si mypy ne résout pas `from helpers import …` ou `from conftest import …`, ajouter `mypy_path = "tests"` sous `[tool.mypy]` dans `pyproject.toml`.

---

## Chunk 2 : sources de connaissance

### Task 8 : Graphe en mémoire (`InMemoryGraph`)

**Files:**
- Create: `tests/fixtures/graph.json`
- Create: `src/truthloop/knowledge/__init__.py`
- Create: `src/truthloop/knowledge/graph.py`
- Modify: `tests/conftest.py`
- Create: `tests/test_knowledge_graph.py`

- [ ] **Step 1 : Fixture**

```json
{
  "programs": [
    {"id": "PRG_MAIN_MENU", "name": "Main menu"},
    {"id": "PRG_ORD_SAVE", "name": "Order save"},
    {"id": "PRG_ORD_VALID", "name": "Order validation"},
    {"id": "PRG_ORD_NOTIFY", "name": "Order notification"},
    {"id": "PRG_ORD_ARCHIVE", "name": "Order archive"},
    {"id": "PRG_CUST_LOAD", "name": "Customer load"},
    {"id": "PRG_INV_CHECK", "name": "Inventory check"},
    {"id": "PRG_REPORT", "name": "Reporting"}
  ],
  "tables": [
    {"id": "T_ORDERS", "name": "Orders"},
    {"id": "T_ORDER_LINES", "name": "Order lines"},
    {"id": "T_CUSTOMERS", "name": "Customers"},
    {"id": "T_STOCK", "name": "Stock"}
  ],
  "calls": [
    {"caller_id": "PRG_MAIN_MENU", "callee_id": "PRG_ORD_SAVE"},
    {"caller_id": "PRG_ORD_SAVE", "callee_id": "PRG_ORD_VALID"},
    {"caller_id": "PRG_ORD_NOTIFY", "callee_id": "PRG_ORD_VALID"},
    {"caller_id": "PRG_ORD_VALID", "callee_id": "PRG_CUST_LOAD"},
    {"caller_id": "PRG_ORD_VALID", "callee_id": "PRG_INV_CHECK"},
    {"caller_id": "PRG_ORD_SAVE", "callee_id": "PRG_ORD_ARCHIVE"},
    {"caller_id": "PRG_REPORT", "callee_id": "PRG_ORD_ARCHIVE"}
  ],
  "program_tables": [
    {"program_id": "PRG_ORD_SAVE", "table_id": "T_ORDERS", "access": "write"},
    {"program_id": "PRG_ORD_SAVE", "table_id": "T_ORDER_LINES", "access": "write"},
    {"program_id": "PRG_ORD_VALID", "table_id": "T_ORDERS", "access": "read"},
    {"program_id": "PRG_CUST_LOAD", "table_id": "T_CUSTOMERS", "access": "read"},
    {"program_id": "PRG_INV_CHECK", "table_id": "T_STOCK", "access": "both"},
    {"program_id": "PRG_ORD_ARCHIVE", "table_id": "T_ORDERS", "access": "read"},
    {"program_id": "PRG_REPORT", "table_id": "T_ORDERS", "access": "read"}
  ],
  "docs": [
    {"id": "REL-2026.1", "title": "Release 2026.1", "source": "docs/releases/2026.1.md"}
  ]
}
```

- [ ] **Step 2 : Test rouge**

```python
# tests/test_knowledge_graph.py
import pytest

from truthloop.contracts.common import EntityRef
from truthloop.knowledge import KnowledgeError
from truthloop.knowledge.graph import GraphRows, InMemoryGraph


def prog(entity_id: str) -> EntityRef:
    return EntityRef(type="program", id=entity_id)


def table(entity_id: str) -> EntityRef:
    return EntityRef(type="table", id=entity_id)


def test_resolve_normalizes_and_is_typed(graph: InMemoryGraph) -> None:
    assert graph.resolve("PRG-ORD-VALID", "program") == prog("prg_ord_valid")
    assert graph.resolve("prg_ord_valid", "table") is None
    assert graph.resolve("nope", "program") is None
    assert graph.resolve("rel-2026.1", "doc") == EntityRef(type="doc", id="rel_2026.1")
    assert graph.has_docs() is True


@pytest.mark.parametrize(
    ("direction", "depth", "expected"),
    [
        ("callers", 1, {"prg_ord_save", "prg_ord_notify"}),
        ("callers", 2, {"prg_ord_save", "prg_ord_notify", "prg_main_menu"}),
        ("callees", 1, {"prg_cust_load", "prg_inv_check"}),
        ("both", 1, {"prg_ord_save", "prg_ord_notify", "prg_cust_load", "prg_inv_check"}),
        (
            "both",
            2,
            {
                "prg_ord_save",
                "prg_ord_notify",
                "prg_cust_load",
                "prg_inv_check",
                "prg_main_menu",
                "prg_ord_archive",
            },
        ),
        ("both", 0, set()),
    ],
)
def test_neighbors(graph: InMemoryGraph, direction: str, depth: int, expected: set[str]) -> None:
    result = graph.neighbors(prog("prg_ord_valid"), direction, depth)  # type: ignore[arg-type]
    assert {e.id for e in result} == expected
    assert all(e.type == "program" for e in result)


def test_neighbors_of_unknown_program_is_empty(graph: InMemoryGraph) -> None:
    assert graph.neighbors(prog("ghost"), "both", 3) == set()


def test_programs_and_tables(graph: InMemoryGraph) -> None:
    assert {e.id for e in graph.programs_of([table("t_orders")])} == {
        "prg_ord_save",
        "prg_ord_valid",
        "prg_ord_archive",
        "prg_report",
    }
    assert {e.id for e in graph.tables_of([prog("prg_ord_save")])} == {"t_orders", "t_order_lines"}
    assert graph.tables_of([prog("prg_main_menu")]) == set()


def test_has_edge_semantics(graph: InMemoryGraph) -> None:
    assert graph.has_edge(prog("prg_ord_save"), "calls", prog("prg_ord_valid"))
    assert graph.has_edge(prog("prg_ord_valid"), "called_by", prog("prg_ord_save"))
    assert not graph.has_edge(prog("prg_ord_valid"), "calls", prog("prg_ord_save"))
    assert graph.has_edge(prog("prg_ord_save"), "writes", table("t_orders"))
    assert not graph.has_edge(prog("prg_ord_save"), "reads", table("t_orders"))
    assert graph.has_edge(prog("prg_inv_check"), "reads", table("t_stock"))
    assert graph.has_edge(prog("prg_inv_check"), "writes", table("t_stock"))


def test_fingerprint_is_stable(graph: InMemoryGraph) -> None:
    assert len(graph.fingerprint()) == 64
    assert graph.fingerprint() == graph.fingerprint()


def test_edges_to_unknown_nodes_fail_closed() -> None:
    rows = GraphRows(programs=(("A", "a"),), tables=(), calls=(("A", "B"),), program_tables=())
    with pytest.raises(KnowledgeError, match="'b'"):
        InMemoryGraph(rows, fingerprint="x")
    rows = GraphRows(programs=(("A", "a"),), tables=(("T", "t"),), calls=(), program_tables=(("A", "T", "rw"),))
    with pytest.raises(KnowledgeError, match="access"):
        InMemoryGraph(rows, fingerprint="x")
```

La fixture `graph` utilisée par ces tests est ajoutée à `tests/conftest.py` en Task 10 (elle charge le graphe via `load_files`, qui n'existe pas encore). Les tests de cette tâche sont donc écrits maintenant et exécutés en Task 10 ; d'ici là, ne pas importer `truthloop.knowledge.files` dans `conftest.py`, sinon toute la collecte pytest échoue.

Ajouter dès maintenant dans `tests/conftest.py`, sous les imports :

```python
FIXTURES = Path(__file__).parent / "fixtures"
```

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/knowledge/__init__.py
"""Knowledge sources: the graph the graders verify answers against (spec §5)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from truthloop.contracts.common import Direction, EntityRef, EntityType, Predicate
from truthloop.knowledge.graph import KnowledgeError


class KnowledgeSource(Protocol):
    def resolve(self, raw_id: str, entity_type: EntityType) -> EntityRef | None: ...
    def neighbors(self, program: EntityRef, direction: Direction, depth: int) -> set[EntityRef]: ...
    def programs_of(self, tables: Iterable[EntityRef]) -> set[EntityRef]: ...
    def tables_of(self, programs: Iterable[EntityRef]) -> set[EntityRef]: ...
    def has_edge(self, subject: EntityRef, predicate: Predicate, obj: EntityRef) -> bool: ...
    def has_docs(self) -> bool: ...
    def fingerprint(self) -> str: ...


__all__ = ["KnowledgeError", "KnowledgeSource"]
```

`graph.py` ne doit jamais importer le paquet `truthloop.knowledge` (le paquet l'importe) : `KnowledgeError` est définie dans `graph.py` et ré-exportée ici.

```python
# src/truthloop/knowledge/graph.py
"""In-memory graph shared by every storage backend (spec §5)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from truthloop.contracts.common import Direction, EntityRef, EntityType, Predicate, normalize_id

Access = Literal["read", "write", "both"]
_ACCESSES: frozenset[str] = frozenset({"read", "write", "both"})


class KnowledgeError(Exception):
    """The knowledge source cannot be opened or is inconsistent (exit code 1)."""


@dataclass(frozen=True)
class GraphRows:
    """Rows of the logical schema, as read from SQLite or files (ids not yet normalized)."""

    programs: tuple[tuple[str, str], ...]
    tables: tuple[tuple[str, str], ...]
    calls: tuple[tuple[str, str], ...]
    program_tables: tuple[tuple[str, str, str], ...]
    docs: tuple[tuple[str, str, str], ...] = ()


class InMemoryGraph:
    def __init__(self, rows: GraphRows, fingerprint: str) -> None:
        self._fingerprint = fingerprint
        self._programs: dict[str, str] = {normalize_id(i): name for i, name in rows.programs}
        self._tables: dict[str, str] = {normalize_id(i): name for i, name in rows.tables}
        self._docs: dict[str, str] = {normalize_id(i): title for i, title, _ in rows.docs}
        self._callees: dict[str, set[str]] = defaultdict(set)
        self._callers: dict[str, set[str]] = defaultdict(set)
        for caller, callee in rows.calls:
            src, dst = normalize_id(caller), normalize_id(callee)
            self._require(src, self._programs, "calls.caller_id")
            self._require(dst, self._programs, "calls.callee_id")
            self._callees[src].add(dst)
            self._callers[dst].add(src)
        self._access: dict[tuple[str, str], str] = {}
        self._program_tables: dict[str, set[str]] = defaultdict(set)
        self._table_programs: dict[str, set[str]] = defaultdict(set)
        for program, table, access in rows.program_tables:
            prog, tbl = normalize_id(program), normalize_id(table)
            self._require(prog, self._programs, "program_tables.program_id")
            self._require(tbl, self._tables, "program_tables.table_id")
            if access not in _ACCESSES:
                raise KnowledgeError(f"program_tables.access invalide pour ({program}, {table}) : {access!r}")
            self._access[(prog, tbl)] = access
            self._program_tables[prog].add(tbl)
            self._table_programs[tbl].add(prog)

    @staticmethod
    def _require(entity_id: str, known: dict[str, str], column: str) -> None:
        if entity_id not in known:
            raise KnowledgeError(f"{column} référence un id inconnu : {entity_id!r}")

    def resolve(self, raw_id: str, entity_type: EntityType) -> EntityRef | None:
        entity_id = normalize_id(raw_id)
        known = {"program": self._programs, "table": self._tables}.get(entity_type, self._docs)
        if entity_id in known:
            return EntityRef(type=entity_type, id=entity_id)
        return None

    def neighbors(self, program: EntityRef, direction: Direction, depth: int) -> set[EntityRef]:
        start = program.id
        if start not in self._programs or depth <= 0:
            return set()
        visited = {start}
        frontier = {start}
        found: set[str] = set()
        for _ in range(depth):
            next_frontier: set[str] = set()
            for node in frontier:
                for neighbor in self._adjacent(node, direction):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.add(neighbor)
                        found.add(neighbor)
            if not next_frontier:
                break
            frontier = next_frontier
        return {EntityRef(type="program", id=i) for i in found}

    def _adjacent(self, node: str, direction: Direction) -> set[str]:
        callers = self._callers.get(node, set())
        callees = self._callees.get(node, set())
        if direction == "callers":
            return callers
        if direction == "callees":
            return callees
        return callers | callees

    def programs_of(self, tables: Iterable[EntityRef]) -> set[EntityRef]:
        return {EntityRef(type="program", id=p) for t in tables for p in self._table_programs.get(t.id, set())}

    def tables_of(self, programs: Iterable[EntityRef]) -> set[EntityRef]:
        return {EntityRef(type="table", id=t) for p in programs for t in self._program_tables.get(p.id, set())}

    def has_edge(self, subject: EntityRef, predicate: Predicate, obj: EntityRef) -> bool:
        if predicate == "calls":
            return obj.id in self._callees.get(subject.id, set())
        if predicate == "called_by":
            return obj.id in self._callers.get(subject.id, set())
        access = self._access.get((subject.id, obj.id))
        if access is None:
            return False
        return access in {"both", "read" if predicate == "reads" else "write"}

    def has_docs(self) -> bool:
        return bool(self._docs)

    def fingerprint(self) -> str:
        return self._fingerprint
```

Note : les `defaultdict` ne servent qu'à la construction ; les lectures passent par `.get(…, set())` pour que `neighbors` et `has_edge` restent purs (aucune insertion de clé à la lecture).

- [ ] **Step 4 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur. Les tests du graphe s'exécutent en Task 10 : si on les lance maintenant, on obtient `1 passed, 11 errors` (fixture `graph` absente), ce qui n'est pas une régression.

### Task 9 : Source SQLite

**Files:**
- Create: `src/truthloop/knowledge/sqlite.py`
- Modify: `tests/conftest.py` (fixture `sqlite_path`)
- Create: `tests/test_knowledge_sqlite.py`

- [ ] **Step 1 : Fixture SQLite (dans `tests/conftest.py`)**

```python
import json
import sqlite3


@pytest.fixture
def sqlite_path(tmp_path: Path) -> Path:
    """Build a SQLite database with the logical schema from tests/fixtures/graph.json."""
    data = json.loads((FIXTURES / "graph.json").read_text(encoding="utf-8"))
    path = tmp_path / "magic.db"
    conn = sqlite3.connect(path)
    with conn:
        conn.executescript(
            """
            CREATE TABLE programs (id TEXT, name TEXT);
            CREATE TABLE tables (id TEXT, name TEXT);
            CREATE TABLE calls (caller_id TEXT, callee_id TEXT);
            CREATE TABLE program_tables (program_id TEXT, table_id TEXT, access TEXT);
            CREATE TABLE docs (id TEXT, title TEXT, source TEXT);
            """
        )
        conn.executemany("INSERT INTO programs VALUES (?, ?)", [(r["id"], r["name"]) for r in data["programs"]])
        conn.executemany("INSERT INTO tables VALUES (?, ?)", [(r["id"], r["name"]) for r in data["tables"]])
        conn.executemany(
            "INSERT INTO calls VALUES (?, ?)", [(r["caller_id"], r["callee_id"]) for r in data["calls"]]
        )
        conn.executemany(
            "INSERT INTO program_tables VALUES (?, ?, ?)",
            [(r["program_id"], r["table_id"], r["access"]) for r in data["program_tables"]],
        )
        conn.executemany(
            "INSERT INTO docs VALUES (?, ?, ?)", [(r["id"], r["title"], r["source"]) for r in data["docs"]]
        )
    conn.close()
    return path
```

- [ ] **Step 2 : Test rouge**

```python
# tests/test_knowledge_sqlite.py
import sqlite3
from pathlib import Path

import pytest

from truthloop.contracts.common import EntityRef
from truthloop.knowledge import KnowledgeError
from truthloop.knowledge.sqlite import DEFAULT_QUERIES, load_sqlite


def test_load_sqlite_with_default_queries(sqlite_path: Path) -> None:
    graph = load_sqlite(sqlite_path, {})
    valid = EntityRef(type="program", id="prg_ord_valid")
    assert {e.id for e in graph.neighbors(valid, "callers", 1)} == {"prg_ord_save", "prg_ord_notify"}
    assert graph.has_docs()
    assert len(graph.fingerprint()) == 64


def test_load_sqlite_with_overridden_queries(sqlite_path: Path) -> None:
    conn = sqlite3.connect(sqlite_path)
    with conn:
        conn.executescript(
            """
            CREATE TABLE xpa_programs (prog_id TEXT, prog_name TEXT);
            INSERT INTO xpa_programs SELECT id, name FROM programs;
            DROP TABLE programs;
            DROP TABLE docs;
            """
        )
    conn.close()
    graph = load_sqlite(sqlite_path, {"programs": "SELECT prog_id AS id, prog_name AS name FROM xpa_programs"})
    assert graph.resolve("PRG_ORD_VALID", "program") is not None
    assert graph.has_docs() is False


def test_missing_file_and_bad_query_raise(sqlite_path: Path, tmp_path: Path) -> None:
    with pytest.raises(KnowledgeError, match="introuvable"):
        load_sqlite(tmp_path / "nope.db", {})
    with pytest.raises(KnowledgeError, match="calls"):
        load_sqlite(sqlite_path, {"calls": "SELECT caller_id FROM calls"})
    with pytest.raises(KnowledgeError, match="programs"):
        load_sqlite(sqlite_path, {"programs": "SELECT * FROM does_not_exist"})


def test_default_queries_cover_logical_schema() -> None:
    assert set(DEFAULT_QUERIES) == {"programs", "tables", "calls", "program_tables", "docs"}
```

- [ ] **Step 3 : Vérifier l'échec**

Run: `uv run pytest tests/test_knowledge_sqlite.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.knowledge.sqlite'`

- [ ] **Step 4 : Implémenter**

```python
# src/truthloop/knowledge/sqlite.py
"""SQLite backend: configurable SQL → logical rows → InMemoryGraph (spec §5.1)."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from truthloop.knowledge.graph import GraphRows, InMemoryGraph, KnowledgeError

DEFAULT_QUERIES: Final[dict[str, str]] = {
    "programs": "SELECT id, name FROM programs",
    "tables": "SELECT id, name FROM tables",
    "calls": "SELECT caller_id, callee_id FROM calls",
    "program_tables": "SELECT program_id, table_id, access FROM program_tables",
    "docs": "SELECT id, title, source FROM docs",
}
_WIDTHS: Final[dict[str, int]] = {"programs": 2, "tables": 2, "calls": 2, "program_tables": 3, "docs": 3}


def load_sqlite(path: Path, queries: Mapping[str, str]) -> InMemoryGraph:
    if not path.is_file():
        raise KnowledgeError(f"base SQLite introuvable : {path}")
    merged = {**DEFAULT_QUERIES, **queries}
    uri = path.resolve().as_uri() + "?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise KnowledgeError(f"ouverture impossible de {path} : {exc}") from exc
    try:
        programs = _rows(conn, "programs", merged["programs"])
        tables = _rows(conn, "tables", merged["tables"])
        calls = _rows(conn, "calls", merged["calls"])
        program_tables = _rows(conn, "program_tables", merged["program_tables"])
        docs = _rows(conn, "docs", merged["docs"], optional=True)
    finally:
        conn.close()
    stat = path.stat()
    fingerprint = hashlib.sha256(f"{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()
    return InMemoryGraph(
        GraphRows(
            programs=tuple((r[0], r[1]) for r in programs),
            tables=tuple((r[0], r[1]) for r in tables),
            calls=tuple((r[0], r[1]) for r in calls),
            program_tables=tuple((r[0], r[1], r[2]) for r in program_tables),
            docs=tuple((r[0], r[1], r[2]) for r in docs),
        ),
        fingerprint,
    )


def _rows(
    conn: sqlite3.Connection, name: str, sql: str, *, optional: bool = False
) -> tuple[tuple[str, ...], ...]:
    """Run one logical-schema query; ``optional`` relations (docs) vanish when their table is absent."""
    try:
        cursor = conn.execute(sql)
        fetched = cursor.fetchall()
    except sqlite3.OperationalError as exc:
        # Textual check on purpose: sqlite3 exposes no error code for a missing table.
        if optional and "no such table" in str(exc):
            return ()
        raise KnowledgeError(f"requête {name} en erreur : {exc}") from exc
    except sqlite3.Error as exc:
        raise KnowledgeError(f"requête {name} en erreur : {exc}") from exc
    width = _WIDTHS[name]
    actual = len(cursor.description or ())
    if actual != width:
        raise KnowledgeError(f"requête {name} : {width} colonnes attendues, {actual} obtenues")
    return tuple(tuple("" if value is None else str(value) for value in row) for row in fetched)
```

- [ ] **Step 5 : Vérifier le succès**

Run: `uv run pytest tests/test_knowledge_sqlite.py --no-cov -q`
Expected: `4 passed`

- [ ] **Step 6 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 10 : Source fichiers (JSON / CSV) et `open_knowledge`

**Files:**
- Create: `src/truthloop/knowledge/files.py`
- Create: `tests/test_knowledge_files.py`

- [ ] **Step 1 : Fixture `graph` (dans `tests/conftest.py`)**

Ajouter les imports `from truthloop.knowledge.files import load_files` et `from truthloop.knowledge.graph import InMemoryGraph`, puis :

```python
@pytest.fixture
def graph() -> InMemoryGraph:
    return load_files(FIXTURES / "graph.json")
```

- [ ] **Step 2 : Test rouge**

```python
# tests/test_knowledge_files.py
import csv
import json
from pathlib import Path

import pytest

from truthloop.contracts.common import EntityRef
from truthloop.knowledge import KnowledgeError
from truthloop.knowledge.factory import open_knowledge
from truthloop.knowledge.files import load_files

FIXTURE = Path(__file__).parent / "fixtures" / "graph.json"


def test_load_json_file_and_directory(tmp_path: Path) -> None:
    direct = load_files(FIXTURE)
    (tmp_path / "graph.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    from_dir = load_files(tmp_path)
    assert direct.fingerprint() == from_dir.fingerprint()
    assert direct.resolve("T_ORDERS", "table") == EntityRef(type="table", id="t_orders")


def test_load_csv_directory(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for name in ("programs", "tables", "calls", "program_tables"):
        rows = data[name]
        with (tmp_path / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    graph = load_files(tmp_path)
    assert graph.has_docs() is False
    valid = EntityRef(type="program", id="prg_ord_valid")
    assert {e.id for e in graph.neighbors(valid, "callees", 1)} == {"prg_cust_load", "prg_inv_check"}


def test_invalid_inputs_raise(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeError, match="introuvable"):
        load_files(tmp_path / "missing")
    (tmp_path / "graph.json").write_text('{"programs": []}', encoding="utf-8")
    with pytest.raises(KnowledgeError, match=r"graph\.json"):
        load_files(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(KnowledgeError, match=r"programs\.csv"):
        load_files(empty)


def test_open_knowledge_dispatch(sqlite_path: Path) -> None:
    assert open_knowledge("files", FIXTURE, {}).has_docs()
    assert open_knowledge("sqlite", sqlite_path, {}).has_docs()
    with pytest.raises(KnowledgeError):
        open_knowledge("neo4j", FIXTURE, {})
```

- [ ] **Step 3 : Vérifier l'échec**

Run: `uv run pytest tests/test_knowledge_files.py tests/test_knowledge_graph.py --no-cov -q`
Expected: erreur de collecte, `ModuleNotFoundError: No module named 'truthloop.knowledge.files'`

- [ ] **Step 4 : Implémenter**

```python
# src/truthloop/knowledge/factory.py
"""Pick the knowledge backend from the configuration (spec §5, §8.3)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from truthloop.knowledge import KnowledgeSource
from truthloop.knowledge.files import load_files
from truthloop.knowledge.graph import KnowledgeError
from truthloop.knowledge.sqlite import load_sqlite


def open_knowledge(kind: str, path: Path, queries: Mapping[str, str]) -> KnowledgeSource:
    if kind == "sqlite":
        return load_sqlite(path, queries)
    if kind == "files":
        return load_files(path)
    raise KnowledgeError(f"kind de source inconnu : {kind!r}")
```

```python
# src/truthloop/knowledge/files.py
"""File backend: graph.json or one CSV per relation → InMemoryGraph (spec §5.2)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path
from typing import Final

from pydantic import Field, ValidationError

from truthloop.contracts.common import StrictModel
from truthloop.knowledge.graph import GraphRows, InMemoryGraph, KnowledgeError

_CSV_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "programs": ("id", "name"),
    "tables": ("id", "name"),
    "calls": ("caller_id", "callee_id"),
    "program_tables": ("program_id", "table_id", "access"),
    "docs": ("id", "title", "source"),
}


class _Program(StrictModel):
    id: str
    name: str = ""
    kind: str | None = None
    folder: str | None = None


class _Table(StrictModel):
    id: str
    name: str = ""


class _Call(StrictModel):
    caller_id: str
    callee_id: str
    call_type: str | None = None


class _ProgramTable(StrictModel):
    program_id: str
    table_id: str
    access: str


class _Doc(StrictModel):
    id: str
    title: str = ""
    source: str = ""
    version: str | None = None


class _GraphFile(StrictModel):
    programs: list[_Program]
    tables: list[_Table]
    calls: list[_Call]
    program_tables: list[_ProgramTable]
    docs: list[_Doc] = Field(default_factory=list)


def load_files(path: Path) -> InMemoryGraph:
    json_path = path if path.is_file() else path / "graph.json"
    if json_path.is_file():
        return _from_json(json_path)
    if path.is_dir():
        return _from_csv(path)
    raise KnowledgeError(f"source fichiers introuvable : {path}")


def _from_json(path: Path) -> InMemoryGraph:
    text = path.read_text(encoding="utf-8")
    try:
        parsed = _GraphFile.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise KnowledgeError(f"{path.name} invalide : {exc}") from exc
    rows = GraphRows(
        programs=tuple((p.id, p.name) for p in parsed.programs),
        tables=tuple((t.id, t.name) for t in parsed.tables),
        calls=tuple((c.caller_id, c.callee_id) for c in parsed.calls),
        program_tables=tuple((pt.program_id, pt.table_id, pt.access) for pt in parsed.program_tables),
        docs=tuple((d.id, d.title, d.source) for d in parsed.docs),
    )
    return InMemoryGraph(rows, hashlib.sha256(text.encode("utf-8")).hexdigest())


def _from_csv(directory: Path) -> InMemoryGraph:
    digest = hashlib.sha256()
    loaded: dict[str, tuple[tuple[str, ...], ...]] = {}
    for name, columns in _CSV_COLUMNS.items():
        csv_path = directory / f"{name}.csv"
        if not csv_path.is_file():
            if name == "docs":
                loaded[name] = ()
                continue
            raise KnowledgeError(f"{name}.csv manquant dans {directory}")
        text = csv_path.read_text(encoding="utf-8")
        digest.update(name.encode("utf-8"))
        digest.update(text.encode("utf-8"))
        reader = csv.DictReader(io.StringIO(text))
        missing = set(columns) - set(reader.fieldnames or [])
        if missing:
            raise KnowledgeError(f"{name}.csv : colonnes manquantes {sorted(missing)}")
        loaded[name] = tuple(tuple(row[col] for col in columns) for row in reader)
    rows = GraphRows(
        programs=tuple((r[0], r[1]) for r in loaded["programs"]),
        tables=tuple((r[0], r[1]) for r in loaded["tables"]),
        calls=tuple((r[0], r[1]) for r in loaded["calls"]),
        program_tables=tuple((r[0], r[1], r[2]) for r in loaded["program_tables"]),
        docs=tuple((r[0], r[1], r[2]) for r in loaded["docs"]),
    )
    return InMemoryGraph(rows, digest.hexdigest())
```

- [ ] **Step 5 : Vérifier le succès**

Run: `uv run pytest tests/test_knowledge_files.py tests/test_knowledge_graph.py --no-cov -q`
Expected: `16 passed` (4 fichiers + 12 graphe : 1 + 6 paramétrés + 5)

- [ ] **Step 6 : Suite complète du chunk et lint**

Run: `uv run ruff format src tests && uv run pytest -q && uv run ruff check src tests && uv run mypy`
Expected: tous les tests passent, couverture ≥ 85 %, aucune erreur de lint. Si la couverture est sous 85 % à ce stade (les modules CLI n'existent pas encore, donc c'est peu probable), ne pas baisser le seuil : ajouter les tests manquants.

- [ ] **Step 7 : Point de contrôle**

Demander à l'utilisateur s'il souhaite un commit des chunks 1 et 2 (message proposé : `✨ feat(truthloop): contracts and knowledge sources`). Ne pas committer sans réponse.

---

## Chunk 3 : graders et scoring

Tous les graders ont la même signature `grade_x(ctx: GraderContext) -> list[GraderResult]`. Ils ne lèvent jamais d'exception sur un bundle valide : toute anomalie devient un `Finding`. Fixture commune ajoutée à `tests/conftest.py` :

```python
from collections.abc import Callable

from helpers import sample_answer, sample_evidence, sample_judge, sample_question
from truthloop.contracts.answer import Answer
from truthloop.contracts.evidence import Evidence
from truthloop.contracts.judge import Judge
from truthloop.contracts.question import Question
from truthloop.graders.base import GraderContext

ContextBuilder = Callable[..., GraderContext]


@pytest.fixture
def make_ctx(graph: InMemoryGraph) -> ContextBuilder:
    def _make(
        question: dict[str, object] | None = None,
        answer: dict[str, object] | None = None,
        evidence: dict[str, object] | None = None,
        judge: dict[str, object] | None = None,
        *,
        no_judge: bool = False,
    ) -> GraderContext:
        return GraderContext(
            question=Question.model_validate(question or sample_question()),
            answer=Answer.model_validate(answer or sample_answer()),
            evidence=Evidence.model_validate(evidence or sample_evidence()),
            judge=None if no_judge else Judge.model_validate(judge or sample_judge()),
            knowledge=graph,
        )

    return _make
```

État attendu de `tests/conftest.py` à la fin de Task 11, une fois les cinq snippets fusionnés (Tasks 7, 8, 9, 10, 11). En cas de doute, remplacer le fichier par ce bloc :

```python
# tests/conftest.py
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from helpers import sample_answer, sample_evidence, sample_judge, sample_question, write_json
from truthloop.contracts.answer import Answer
from truthloop.contracts.evidence import Evidence
from truthloop.contracts.judge import Judge
from truthloop.contracts.question import Question
from truthloop.graders.base import GraderContext
from truthloop.knowledge.files import load_files
from truthloop.knowledge.graph import InMemoryGraph

FIXTURES = Path(__file__).parent / "fixtures"

RunBuilder = Callable[..., Path]
ContextBuilder = Callable[..., GraderContext]


@pytest.fixture
def make_run(tmp_path: Path) -> RunBuilder:
    """Write a run directory; pass ``None`` to omit a file."""

    def _make(
        question: dict[str, object] | None,
        answer: dict[str, object] | None,
        evidence: dict[str, object] | None,
        judge: dict[str, object] | None,
        *,
        iteration: int = 1,
        run_id: str = "q-001",
    ) -> Path:
        run_dir = tmp_path / "runs" / run_id
        iter_dir = run_dir / f"iter-{iteration:02d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        if question is not None:
            write_json(run_dir / "question.json", question)
        for name, data in (("answer", answer), ("evidence", evidence), ("judge", judge)):
            if data is not None:
                write_json(iter_dir / f"{name}.json", data)
        return run_dir

    return _make


@pytest.fixture
def graph() -> InMemoryGraph:
    return load_files(FIXTURES / "graph.json")


@pytest.fixture
def sqlite_path(tmp_path: Path) -> Path:
    """Build a SQLite database with the logical schema from tests/fixtures/graph.json."""
    data = json.loads((FIXTURES / "graph.json").read_text(encoding="utf-8"))
    path = tmp_path / "magic.db"
    conn = sqlite3.connect(path)
    with conn:
        conn.executescript(
            """
            CREATE TABLE programs (id TEXT, name TEXT);
            CREATE TABLE tables (id TEXT, name TEXT);
            CREATE TABLE calls (caller_id TEXT, callee_id TEXT);
            CREATE TABLE program_tables (program_id TEXT, table_id TEXT, access TEXT);
            CREATE TABLE docs (id TEXT, title TEXT, source TEXT);
            """
        )
        conn.executemany("INSERT INTO programs VALUES (?, ?)", [(r["id"], r["name"]) for r in data["programs"]])
        conn.executemany("INSERT INTO tables VALUES (?, ?)", [(r["id"], r["name"]) for r in data["tables"]])
        conn.executemany(
            "INSERT INTO calls VALUES (?, ?)", [(r["caller_id"], r["callee_id"]) for r in data["calls"]]
        )
        conn.executemany(
            "INSERT INTO program_tables VALUES (?, ?, ?)",
            [(r["program_id"], r["table_id"], r["access"]) for r in data["program_tables"]],
        )
        conn.executemany(
            "INSERT INTO docs VALUES (?, ?, ?)", [(r["id"], r["title"], r["source"]) for r in data["docs"]]
        )
    conn.close()
    return path


@pytest.fixture
def make_ctx(graph: InMemoryGraph) -> ContextBuilder:
    def _make(
        question: dict[str, object] | None = None,
        answer: dict[str, object] | None = None,
        evidence: dict[str, object] | None = None,
        judge: dict[str, object] | None = None,
        *,
        no_judge: bool = False,
    ) -> GraderContext:
        return GraderContext(
            question=Question.model_validate(question or sample_question()),
            answer=Answer.model_validate(answer or sample_answer()),
            evidence=Evidence.model_validate(evidence or sample_evidence()),
            judge=None if no_judge else Judge.model_validate(judge or sample_judge()),
            knowledge=graph,
        )

    return _make
```

Rappel des valeurs de l'échantillon (`helpers.py`, pivot `prg_ord_valid`, `both`, profondeur 1) : E = {save, notify, cust_load, inv_check}, cités save + notify ⇒ `context_recall = 0.5` ; T = {t_orders, t_order_lines, t_customers, t_stock}, citée t_orders ⇒ `table_recall = 0.25` ; deux claims supportées ⇒ `evidence_support = 1.0`, `faithfulness = 1.0` ; juge 0.9 / 0.7 ⇒ `relevance_completeness = 0.8`. Score brut = 100 × (0.175 + 0.0375 + 0.15 + 0.25 + 0.08) = **69.25**.

### Task 11 : Base des graders et CitationValidity

**Files:**
- Create: `src/truthloop/graders/__init__.py` (vide pour l'instant, complété en Task 16)
- Create: `src/truthloop/graders/base.py`
- Create: `src/truthloop/graders/citation.py`
- Modify: `tests/conftest.py` (fixture `make_ctx` ci-dessus)
- Create: `tests/test_graders_citation.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_graders_citation.py
from conftest import ContextBuilder
from helpers import sample_answer, sample_question
from truthloop.graders.base import GraderContext
from truthloop.graders.citation import grade_citations
from truthloop.knowledge.graph import GraphRows, InMemoryGraph


def test_all_entities_known(make_ctx: ContextBuilder) -> None:
    [result] = grade_citations(make_ctx())
    assert result.component is None
    assert result.value is None
    assert result.findings == ()
    assert result.cap is None


def test_unknown_entity_is_critical_and_caps(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        entities=[{"type": "program", "id": "PRG_ORD_VALID"}, {"type": "program", "id": "PRG_GHOST"}],
        claims=[],
        abstentions=[],
    )
    [result] = grade_citations(make_ctx(answer=answer))
    assert [f.code for f in result.findings] == ["UNKNOWN_ENTITY"]
    assert result.findings[0].severity == "critical"
    assert result.findings[0].entity is not None
    assert result.findings[0].entity.id == "prg_ghost"
    assert result.cap == "unknown_entity"


def test_unknown_pivot_is_reported_once(make_ctx: ContextBuilder) -> None:
    question = sample_question(pivot_entities=[{"type": "program", "id": "PRG_GHOST"}])
    answer = sample_answer(entities=[{"type": "program", "id": "PRG_GHOST"}], claims=[], abstentions=[])
    [result] = grade_citations(make_ctx(question=question, answer=answer))
    assert [f.code for f in result.findings] == ["UNKNOWN_PIVOT"]
    assert result.cap == "unknown_entity"


def test_docs_are_checked_only_when_source_has_docs(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(entities=[{"type": "release", "id": "REL-9999"}], claims=[], abstentions=[])
    [with_docs] = grade_citations(make_ctx(answer=answer))
    assert [f.code for f in with_docs.findings] == ["UNKNOWN_ENTITY"]

    ctx = make_ctx(answer=answer)
    bare = InMemoryGraph(GraphRows(programs=(("PRG_ORD_VALID", ""),), tables=(), calls=(), program_tables=()), "x")
    without_docs = GraderContext(ctx.question, ctx.answer, ctx.evidence, ctx.judge, bare)
    [result] = grade_citations(without_docs)
    assert result.findings == ()
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_graders_citation.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.graders'`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/graders/base.py
"""Types shared by all graders (spec §6)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from truthloop.contracts.answer import Answer
from truthloop.contracts.evidence import Evidence
from truthloop.contracts.judge import Judge
from truthloop.contracts.question import Question
from truthloop.contracts.verdict import Finding
from truthloop.knowledge import KnowledgeSource


@dataclass(frozen=True)
class GraderContext:
    question: Question
    answer: Answer
    evidence: Evidence
    judge: Judge | None
    knowledge: KnowledgeSource


@dataclass(frozen=True)
class GraderResult:
    """One component value (or a gate-only result when ``component`` is None)."""

    component: str | None
    value: float | None
    findings: tuple[Finding, ...] = ()
    # ``cap`` names a key of ``scoring.caps``; ``scoring.aggregate`` resolves it to a value.
    cap: str | None = None
    expected_size: int | None = None


Grader = Callable[[GraderContext], list[GraderResult]]
```

```python
# src/truthloop/graders/citation.py
"""CitationValidity: every cited program/table must exist in the graph (spec §6)."""

from __future__ import annotations

from truthloop.contracts.common import EntityRef
from truthloop.contracts.verdict import Finding
from truthloop.graders.base import GraderContext, GraderResult


def grade_citations(ctx: GraderContext) -> list[GraderResult]:
    findings: list[Finding] = []
    unknown_pivots: set[EntityRef] = set()
    for pivot in ctx.question.pivot_entities:
        if ctx.knowledge.resolve(pivot.id, pivot.type) is None:
            unknown_pivots.add(pivot)
            findings.append(
                Finding(
                    code="UNKNOWN_PIVOT",
                    severity="critical",
                    entity=pivot,
                    detail=f"Pivot {pivot.id} ({pivot.type}) inconnu du graphe : corriger question.json.",
                )
            )
    check_docs = ctx.knowledge.has_docs()
    for entity in ctx.answer.entities:
        if entity in unknown_pivots:
            continue
        if entity.type in ("doc", "release") and not check_docs:
            continue
        if ctx.knowledge.resolve(entity.id, entity.type) is None:
            findings.append(
                Finding(
                    code="UNKNOWN_ENTITY",
                    severity="critical",
                    entity=entity,
                    detail=f"Entité {entity.id} ({entity.type}) inconnue du graphe.",
                )
            )
    return [GraderResult(component=None, value=None, findings=tuple(findings), cap="unknown_entity" if findings else None)]
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_graders_citation.py --no-cov -q`
Expected: `4 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 12 : Coverage et TableCoverage

**Files:**
- Create: `src/truthloop/graders/coverage.py`
- Create: `tests/test_graders_coverage.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_graders_coverage.py
import pytest

from conftest import ContextBuilder
from helpers import sample_answer, sample_question
from truthloop.contracts.common import EntityRef
from truthloop.graders.coverage import expected_programs, grade_coverage
from truthloop.knowledge.graph import InMemoryGraph


def _ids(entities: list[dict[str, str]]) -> list[dict[str, object]]:
    return [{"type": e["type"], "id": e["id"]} for e in entities]


def test_sample_recall_and_findings(make_ctx: ContextBuilder) -> None:
    coverage, tables = grade_coverage(make_ctx())
    assert coverage.component == "context_recall"
    assert coverage.value == 0.5
    assert coverage.expected_size == 4
    assert [(f.code, f.entity.id if f.entity else None, f.depth, f.via) for f in coverage.findings] == [
        ("MISSING_ENTITY", "prg_cust_load", 1, "prg_ord_valid"),
        ("MISSING_ENTITY", "prg_inv_check", 1, "prg_ord_valid"),
    ]
    assert tables.component == "table_recall"
    assert tables.value == 0.25
    assert tables.expected_size == 4
    assert [(f.code, f.entity.id if f.entity else None, f.via) for f in tables.findings] == [
        ("MISSING_TABLE", "t_customers", "prg_cust_load"),
        ("MISSING_TABLE", "t_order_lines", "prg_ord_save"),
        ("MISSING_TABLE", "t_stock", "prg_inv_check"),
    ]


def test_not_applicable_without_pivot_or_with_unknown_pivot(make_ctx: ContextBuilder) -> None:
    for question in (
        sample_question(pivot_entities=[], intent="architecture"),
        sample_question(pivot_entities=[{"type": "program", "id": "PRG_GHOST"}]),
    ):
        coverage, tables = grade_coverage(make_ctx(question=question))
        assert coverage.value is None
        assert tables.value is None
        assert coverage.findings == ()


def test_extra_known_entity_is_info_and_pivot_is_never_extra(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        entities=_ids(
            [
                {"type": "program", "id": "PRG_ORD_VALID"},
                {"type": "program", "id": "PRG_ORD_SAVE"},
                {"type": "program", "id": "PRG_REPORT"},
            ]
        ),
        claims=[],
        abstentions=[],
    )
    coverage, _ = grade_coverage(make_ctx(answer=answer))
    extras = [f for f in coverage.findings if f.code == "EXTRA_ENTITY"]
    assert [f.entity.id for f in extras if f.entity] == ["prg_report"]
    assert extras[0].severity == "info"
    assert coverage.value == 0.25


def test_depth_attribution_for_callers(make_ctx: ContextBuilder) -> None:
    question = sample_question(direction="callers", depth=2)
    coverage, _ = grade_coverage(make_ctx(question=question))
    missing = {f.entity.id: (f.depth, f.via) for f in coverage.findings if f.entity}
    assert missing == {"prg_main_menu": (2, "prg_ord_valid")}
    assert coverage.value == pytest.approx(2 / 3)


def test_table_pivot(make_ctx: ContextBuilder, graph: InMemoryGraph) -> None:
    question = sample_question(pivot_entities=[{"type": "table", "id": "T_CUSTOMERS"}], depth=2)
    expected = expected_programs(question=make_ctx(question=question).question, knowledge=graph)
    assert expected is not None
    assert {e.id: (info.depth, info.via) for e, info in expected.items()} == {
        "prg_cust_load": (1, "t_customers"),
        "prg_ord_valid": (2, "t_customers"),
    }
    answer = sample_answer(
        entities=_ids(
            [
                {"type": "table", "id": "T_CUSTOMERS"},
                {"type": "program", "id": "PRG_CUST_LOAD"},
                {"type": "program", "id": "PRG_ORD_VALID"},
            ]
        ),
        claims=[],
        abstentions=[],
    )
    coverage, tables = grade_coverage(make_ctx(question=question, answer=answer))
    assert coverage.value == 1.0
    assert tables.value == 0.0
    assert [f.entity.id for f in tables.findings if f.entity] == ["t_orders"]


def test_recall_never_decreases_when_adding_expected_entities(make_ctx: ContextBuilder) -> None:
    cited = [{"type": "program", "id": "PRG_ORD_VALID"}]
    previous = 0.0
    for extra in ("PRG_ORD_SAVE", "PRG_ORD_NOTIFY", "PRG_CUST_LOAD", "PRG_INV_CHECK"):
        cited.append({"type": "program", "id": extra})
        coverage, _ = grade_coverage(make_ctx(answer=sample_answer(entities=_ids(cited), claims=[], abstentions=[])))
        assert coverage.value is not None
        assert coverage.value >= previous
        previous = coverage.value
    assert previous == 1.0
    assert EntityRef(type="program", id="prg_ord_valid") not in {
        f.entity for f in coverage.findings if f.entity is not None
    }
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_graders_coverage.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.graders.coverage'`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/graders/coverage.py
"""Coverage (context_recall) and TableCoverage (table_recall) graders (spec §6)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from truthloop.contracts.common import EntityRef
from truthloop.contracts.question import Question
from truthloop.contracts.verdict import Finding
from truthloop.graders.base import GraderContext, GraderResult
from truthloop.knowledge import KnowledgeSource


@dataclass(frozen=True)
class ExpectedProgram:
    depth: int
    via: str


def _by_id(entity: EntityRef) -> str:
    return entity.id


def expected_programs(question: Question, knowledge: KnowledgeSource) -> dict[EntityRef, ExpectedProgram] | None:
    """E with the depth/pivot each program was first reached from; None if a pivot is unknown."""
    if any(knowledge.resolve(p.id, p.type) is None for p in question.pivot_entities):
        return None
    pivot_programs = question.pivot_programs
    expected: dict[EntityRef, ExpectedProgram] = {}

    def record(program: EntityRef, depth: int, via: str) -> None:
        if program in pivot_programs:
            return
        current = expected.get(program)
        if current is None or depth < current.depth:
            expected[program] = ExpectedProgram(depth=depth, via=via)

    for pivot in sorted(pivot_programs, key=_by_id):
        _expand(knowledge, question, pivot, question.depth, 0, pivot.id, record)
    for table in sorted(question.pivot_tables, key=_by_id):
        for program in sorted(knowledge.programs_of([table]), key=_by_id):
            record(program, 1, table.id)
            _expand(knowledge, question, program, question.depth - 1, 1, table.id, record)
    return expected


def _expand(
    knowledge: KnowledgeSource,
    question: Question,
    start: EntityRef,
    depth: int,
    base_depth: int,
    via: str,
    record: Callable[[EntityRef, int, str], None],
) -> None:
    reached: set[EntityRef] = set()
    for hop in range(1, depth + 1):
        layer = knowledge.neighbors(start, question.direction, hop) - reached
        for program in sorted(layer, key=_by_id):
            record(program, base_depth + hop, via)
        reached |= layer


_NOT_APPLICABLE = (
    GraderResult(component="context_recall", value=None),
    GraderResult(component="table_recall", value=None),
)


def grade_coverage(ctx: GraderContext) -> list[GraderResult]:
    question = ctx.question
    if not question.pivot_entities:
        return list(_NOT_APPLICABLE)
    expected = expected_programs(question, ctx.knowledge)
    if not expected:
        return list(_NOT_APPLICABLE)
    pivot_programs = question.pivot_programs
    cited = ctx.answer.entities_of_type("program") - pivot_programs
    expected_set = set(expected)
    findings: list[Finding] = []
    for program in sorted(expected_set - cited, key=_by_id):
        info = expected[program]
        findings.append(
            Finding(
                code="MISSING_ENTITY",
                severity="major",
                entity=program,
                depth=info.depth,
                via=info.via,
                detail=f"Programme attendu à la profondeur {info.depth} via {info.via}, non cité.",
            )
        )
    for program in sorted(cited - expected_set, key=_by_id):
        if ctx.knowledge.resolve(program.id, "program") is not None:
            findings.append(
                Finding(
                    code="EXTRA_ENTITY",
                    severity="info",
                    entity=program,
                    detail="Programme cité hors du périmètre attendu.",
                )
            )
    recall = len(expected_set & cited) / len(expected_set)
    coverage = GraderResult(
        component="context_recall", value=recall, findings=tuple(findings), expected_size=len(expected_set)
    )
    return [coverage, _grade_tables(ctx, expected_set | pivot_programs)]


def _grade_tables(ctx: GraderContext, scope: set[EntityRef]) -> GraderResult:
    pivot_tables = ctx.question.pivot_tables
    expected_tables = ctx.knowledge.tables_of(scope) - pivot_tables
    if not expected_tables:
        return GraderResult(component="table_recall", value=None)
    cited_tables = ctx.answer.entities_of_type("table") - pivot_tables
    findings: list[Finding] = []
    for table in sorted(expected_tables - cited_tables, key=_by_id):
        users = sorted(ctx.knowledge.programs_of([table]) & scope, key=_by_id)
        via = users[0].id if users else "?"
        findings.append(
            Finding(
                code="MISSING_TABLE",
                severity="major",
                entity=table,
                via=via,
                detail=f"Table référencée par {via}, non citée.",
            )
        )
    recall = len(expected_tables & cited_tables) / len(expected_tables)
    return GraderResult(
        component="table_recall", value=recall, findings=tuple(findings), expected_size=len(expected_tables)
    )
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_graders_coverage.py --no-cov -q`
Expected: `6 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 13 : EvidenceSupport

**Files:**
- Create: `src/truthloop/graders/evidence.py`
- Create: `tests/test_graders_evidence.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_graders_evidence.py
import pytest

from conftest import ContextBuilder
from helpers import sample_answer, sample_evidence, sample_question
from truthloop.graders.evidence import contains_id, grade_evidence


@pytest.mark.parametrize(
    ("text", "entity_id", "expected"),
    [
        ("PRG_ORD_SAVE -> PRG_ORD_VALID (call)", "prg_ord_valid", True),
        ("Appel de PRG-ORD-VALID en tâche 3", "prg_ord_valid", True),
        ("Le programme PRG ORD VALID contrôle…", "prg_ord_valid", True),
        ("PRG-ORD VALID", "prg_ord_valid", True),
        ("PRG - ORD - VALID", "prg_ord_valid", True),
        ("écrit dans T_ORDER_LINES", "t_orders", False),
        ("T ORDERS LINES", "t_orders", True),
        ("rien ici", "prg_ord_valid", False),
        ("", "prg_ord_valid", False),
    ],
)
def test_contains_id(text: str, entity_id: str, expected: bool) -> None:
    assert contains_id(text, entity_id) is expected


def test_sample_is_fully_supported(make_ctx: ContextBuilder) -> None:
    [result] = grade_evidence(make_ctx())
    assert result.component == "evidence_support"
    assert result.value == 1.0
    assert result.findings == ()


def test_dangling_and_unsupported(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        claims=[
            {"id": "c1", "text": "t", "entities": ["PRG_ORD_SAVE"], "citations": ["ev-404"]},
            {"id": "c2", "text": "t", "entities": ["PRG_ORD_NOTIFY"], "citations": ["ev-1"]},
            {"id": "c3", "text": "t", "entities": [], "citations": ["ev-1"]},
            {"id": "c4", "text": "t", "entities": [], "citations": []},
        ]
    )
    [result] = grade_evidence(make_ctx(answer=answer))
    assert result.value == 0.25
    assert [(f.code, f.claim_id) for f in result.findings] == [
        ("DANGLING_CITATION", "c1"),
        ("UNSUPPORTED_CLAIM", "c1"),
        ("UNSUPPORTED_CLAIM", "c2"),
        ("UNSUPPORTED_CLAIM", "c4"),
    ]


def test_empty_claims(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(claims=[])
    [diagram] = grade_evidence(make_ctx(question=sample_question(intent="diagram"), answer=answer))
    assert diagram.value is None
    assert diagram.findings == ()
    assert diagram.cap is None
    [impact] = grade_evidence(make_ctx(answer=answer))
    assert impact.value is None
    assert [f.code for f in impact.findings] == ["NO_CLAIMS"]
    assert impact.cap == "missing_claims"


def test_evidence_without_chunks(make_ctx: ContextBuilder) -> None:
    [result] = grade_evidence(make_ctx(evidence=sample_evidence(chunks=[])))
    assert result.value == 0.0
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_graders_evidence.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/graders/evidence.py
"""EvidenceSupport: every claim must rest on a cited chunk that names one of its entities (spec §6)."""

from __future__ import annotations

import re

from truthloop.contracts.answer import Claim
from truthloop.contracts.common import normalize_id
from truthloop.contracts.evidence import Chunk
from truthloop.contracts.verdict import Finding
from truthloop.graders.base import GraderContext, GraderResult

_TOKEN_SPLIT = re.compile(r"[^\w-]+")


def tokens_of(text: str) -> list[str]:
    """Normalized tokens; separators that normalize to a bare ``_`` (e.g. ``-``) are dropped."""
    normalized = (normalize_id(token) for token in _TOKEN_SPLIT.split(text) if token)
    return [token for token in normalized if token and token != "_"]


def contains_id(text: str, entity_id: str) -> bool:
    """Windowed containment: some run of ≤ k tokens joined by ``_`` equals the id (spec §6)."""
    tokens = tokens_of(text)
    width = entity_id.count("_") + 1
    for size in range(1, width + 1):
        for start in range(len(tokens) - size + 1):
            if "_".join(tokens[start : start + size]) == entity_id:
                return True
    return False


def grade_evidence(ctx: GraderContext) -> list[GraderResult]:
    claims = ctx.answer.claims
    if not claims:
        if ctx.question.intent == "diagram":
            return [GraderResult(component="evidence_support", value=None)]
        finding = Finding(
            code="NO_CLAIMS",
            severity="major",
            detail="Aucune claim : rédiger des claims citées pour les entités présentes.",
        )
        return [GraderResult(component="evidence_support", value=None, findings=(finding,), cap="missing_claims")]
    chunks = ctx.evidence.chunk_by_id()
    findings: list[Finding] = []
    supported = 0
    for claim in claims:
        present: list[Chunk] = []
        for citation in claim.citations:
            chunk = chunks.get(citation)
            if chunk is None:
                findings.append(
                    Finding(
                        code="DANGLING_CITATION",
                        severity="major",
                        claim_id=claim.id,
                        detail=f"Citation {citation} introuvable dans evidence.json.",
                    )
                )
            else:
                present.append(chunk)
        if _is_supported(claim, present):
            supported += 1
        else:
            findings.append(
                Finding(
                    code="UNSUPPORTED_CLAIM",
                    severity="major",
                    claim_id=claim.id,
                    detail="Aucune évidence citée ne mentionne une entité de la claim.",
                )
            )
    return [GraderResult(component="evidence_support", value=supported / len(claims), findings=tuple(findings))]


def _is_supported(claim: Claim, chunks: list[Chunk]) -> bool:
    if not chunks:
        return False
    if not claim.entities:
        return True
    return any(contains_id(chunk.text, entity_id) for chunk in chunks for entity_id in claim.entities)
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_graders_evidence.py --no-cov -q`
Expected: `13 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 14 : Consistency

**Files:**
- Create: `src/truthloop/graders/consistency.py`
- Create: `tests/test_graders_consistency.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_graders_consistency.py
from conftest import ContextBuilder
from helpers import sample_answer
from truthloop.graders.consistency import grade_consistency


def _claim(subject: str, predicate: str, obj: str) -> dict[str, object]:
    return {
        "id": "c1",
        "text": "t",
        "entities": [subject, obj],
        "citations": ["ev-1"],
        "relation": {"subject": subject, "predicate": predicate, "object": obj},
    }


def test_sample_relation_is_consistent(make_ctx: ContextBuilder) -> None:
    [result] = grade_consistency(make_ctx())
    assert result.component is None
    assert result.findings == ()
    assert result.cap is None


def test_contradicted_relation_caps(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(claims=[_claim("PRG_ORD_VALID", "calls", "PRG_ORD_SAVE")])
    [result] = grade_consistency(make_ctx(answer=answer))
    assert [(f.code, f.severity, f.claim_id) for f in result.findings] == [
        ("CONTRADICTED_BY_GRAPH", "critical", "c1")
    ]
    assert result.cap == "contradiction"


def test_table_predicates(make_ctx: ContextBuilder) -> None:
    ok = sample_answer(claims=[_claim("PRG_ORD_SAVE", "writes", "T_ORDERS")])
    [result] = grade_consistency(make_ctx(answer=ok))
    assert result.findings == ()
    bad = sample_answer(claims=[_claim("PRG_ORD_SAVE", "reads", "T_ORDERS")])
    [result] = grade_consistency(make_ctx(answer=bad))
    assert [f.code for f in result.findings] == ["CONTRADICTED_BY_GRAPH"]


def test_unknown_entities_are_skipped(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        entities=[{"type": "program", "id": "PRG_GHOST"}, {"type": "program", "id": "PRG_ORD_VALID"}],
        claims=[_claim("PRG_GHOST", "calls", "PRG_ORD_VALID")],
        abstentions=[],
    )
    [result] = grade_consistency(make_ctx(answer=answer))
    assert result.findings == ()
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_graders_consistency.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/graders/consistency.py
"""Consistency: a claimed relation must exist in the graph (spec §6, gate-only)."""

from __future__ import annotations

from truthloop.contracts.answer import RELATION_OBJECT_TYPE
from truthloop.contracts.verdict import Finding
from truthloop.graders.base import GraderContext, GraderResult


def grade_consistency(ctx: GraderContext) -> list[GraderResult]:
    findings: list[Finding] = []
    for claim in ctx.answer.claims:
        relation = claim.relation
        if relation is None:
            continue
        subject = ctx.knowledge.resolve(relation.subject, "program")
        obj = ctx.knowledge.resolve(relation.object, RELATION_OBJECT_TYPE[relation.predicate])
        if subject is None or obj is None:
            continue
        if not ctx.knowledge.has_edge(subject, relation.predicate, obj):
            findings.append(
                Finding(
                    code="CONTRADICTED_BY_GRAPH",
                    severity="critical",
                    claim_id=claim.id,
                    detail=f"Le graphe ne contient pas {relation.subject} {relation.predicate} {relation.object}.",
                )
            )
    return [GraderResult(component=None, value=None, findings=tuple(findings), cap="contradiction" if findings else None)]
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_graders_consistency.py --no-cov -q`
Expected: `4 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 15 : Rubric (adaptateur `judge.json`)

**Files:**
- Create: `src/truthloop/graders/rubric.py`
- Create: `tests/test_graders_rubric.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_graders_rubric.py
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
    faith, rel = grade_rubric(make_ctx(answer=sample_answer(claims=[]), judge=sample_judge(claims=[])))
    assert faith.value is None
    assert faith.findings == ()
    assert rel.value == pytest.approx(0.8)
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_graders_rubric.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/graders/rubric.py
"""Rubric adapter: turns judge.json into faithfulness and relevance_completeness (spec §6)."""

from __future__ import annotations

from truthloop.contracts.verdict import Finding
from truthloop.graders.base import GraderContext, GraderResult


def grade_rubric(ctx: GraderContext) -> list[GraderResult]:
    judge = ctx.judge
    if judge is None:
        finding = Finding(code="JUDGE_MISSING", severity="major", detail="judge.json absent : aucune revue sémantique.")
        return [
            GraderResult(component="faithfulness", value=None, findings=(finding,), cap="missing_judge"),
            GraderResult(component="relevance_completeness", value=None),
        ]
    verdicts = judge.verdict_by_claim()
    findings: list[Finding] = []
    points = 0.0
    contradicted = False
    for claim in ctx.answer.claims:
        verdict = verdicts.get(claim.id)
        if verdict is None:
            findings.append(_finding("JUDGE_INCOMPLETE", "major", claim.id, "Claim non jugée : la faire juger."))
        elif verdict == "supported":
            points += 1.0
        elif verdict == "partially":
            points += 0.5
            findings.append(_finding("JUDGE_PARTIAL", "info", claim.id, "Claim partiellement supportée : la préciser."))
        elif verdict == "unsupported":
            findings.append(_finding("JUDGE_UNSUPPORTED", "major", claim.id, "Le juge ne trouve pas de support."))
        else:
            contradicted = True
            findings.append(
                _finding("CONTRADICTED_BY_EVIDENCE", "critical", claim.id, "Le juge estime la claim contredite.")
            )
    faithfulness = points / len(ctx.answer.claims) if ctx.answer.claims else None
    relevance = (judge.relevance + judge.completeness) / 2
    return [
        GraderResult(
            component="faithfulness",
            value=faithfulness,
            findings=tuple(findings),
            cap="contradiction" if contradicted else None,
        ),
        GraderResult(component="relevance_completeness", value=relevance),
    ]


def _finding(code: str, severity: str, claim_id: str, detail: str) -> Finding:
    return Finding.model_validate({"code": code, "severity": severity, "claim_id": claim_id, "detail": detail})
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_graders_rubric.py --no-cov -q`
Expected: `4 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 16 : `run_graders`, agrégation et décision

**Files:**
- Modify: `src/truthloop/graders/__init__.py`
- Create: `src/truthloop/scoring.py`
- Create: `tests/test_scoring.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_scoring.py
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
        context_recall=0.6, table_recall=0.5, evidence_support=1.0, faithfulness=1.0, relevance_completeness=0.8
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
        *_results(context_recall=1.0, table_recall=1.0, evidence_support=1.0, faithfulness=1.0, relevance_completeness=1.0),
        GraderResult(component=None, value=None, cap="contradiction"),
        GraderResult(component=None, value=None, cap="unknown_entity"),
    ]
    breakdown = aggregate(results, WEIGHTS, CAPS)
    assert breakdown.raw == 100.0
    assert breakdown.score == 50.0
    assert [c.name for c in breakdown.caps_applied] == ["contradiction", "unknown_entity"]


def test_no_applicable_component_gives_zero() -> None:
    assert aggregate(_results(), WEIGHTS, CAPS).raw == 0.0


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
    score: float, findings: list[Finding], coverage: bool, iteration: int, expected: tuple[str, float]
) -> None:
    assert decide(score, findings, coverage, iteration, 3, 90.0, 95.0) == expected


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
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_scoring.py --no-cov -q`
Expected: FAIL, `ImportError: cannot import name 'run_graders'`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/graders/__init__.py
"""Deterministic graders (spec §6). Order matters for finding order in the verdict."""

from __future__ import annotations

from typing import Final

from truthloop.graders.base import Grader, GraderContext, GraderResult
from truthloop.graders.citation import grade_citations
from truthloop.graders.consistency import grade_consistency
from truthloop.graders.coverage import grade_coverage
from truthloop.graders.evidence import grade_evidence
from truthloop.graders.rubric import grade_rubric

ALL_GRADERS: Final[tuple[Grader, ...]] = (
    grade_citations,
    grade_coverage,
    grade_evidence,
    grade_consistency,
    grade_rubric,
)


def run_graders(ctx: GraderContext) -> list[GraderResult]:
    return [result for grader in ALL_GRADERS for result in grader(ctx)]


__all__ = ["ALL_GRADERS", "GraderContext", "GraderResult", "run_graders"]
```

```python
# src/truthloop/scoring.py
"""Aggregation with caps and the release decision (spec §6.1, §6.2)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from truthloop.contracts.verdict import COMPONENT_NAMES, CapApplied, Component, Decision, Finding
from truthloop.graders.base import GraderResult


@dataclass(frozen=True)
class ScoreBreakdown:
    raw: float
    score: float
    components: dict[str, Component]
    caps_applied: list[CapApplied]


def aggregate(
    results: Sequence[GraderResult], weights: Mapping[str, float], caps: Mapping[str, int]
) -> ScoreBreakdown:
    components = {
        name: Component(value=None, weight=weights[name], applicable=False) for name in COMPONENT_NAMES
    }
    for result in results:
        if result.component is not None:
            components[result.component] = Component(
                value=result.value, weight=weights[result.component], applicable=result.value is not None
            )
    numerator = sum(c.weight * c.value for c in components.values() if c.applicable and c.value is not None)
    denominator = sum(c.weight for c in components.values() if c.applicable)
    raw = 100.0 * numerator / denominator if denominator > 0 else 0.0
    cap_names = sorted({result.cap for result in results if result.cap is not None})
    caps_applied = [CapApplied(name=name, value=caps[name]) for name in cap_names]
    score = min([raw, *(float(cap.value) for cap in caps_applied)])
    return ScoreBreakdown(raw=raw, score=score, components=components, caps_applied=caps_applied)


def decide(
    score: float,
    findings: Sequence[Finding],
    coverage_applicable: bool,
    iteration: int,
    max_iterations: int,
    release_threshold: float,
    release_threshold_no_reference: float,
) -> tuple[Decision, float]:
    threshold = release_threshold if coverage_applicable else release_threshold_no_reference
    has_critical = any(finding.severity == "critical" for finding in findings)
    if score >= threshold and not has_critical:
        return "release", threshold
    if iteration < max_iterations:
        return "repair", threshold
    return "escalate", threshold
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_scoring.py --no-cov -q`
Expected: `12 passed`

- [ ] **Step 5 : Suite complète du chunk et lint**

Run: `uv run ruff format src tests && uv run pytest -q && uv run ruff check src tests && uv run mypy`
Expected: tous les tests passent, couverture ≥ 85 %, aucune erreur.

- [ ] **Step 6 : Point de contrôle**

Demander à l'utilisateur s'il souhaite un commit (message proposé : `✨ feat(truthloop): deterministic graders and scoring`). Ne pas committer sans réponse.

---

## Chunk 4 : planner, configuration, dossier de run

### Task 17 : Repair planner

**Files:**
- Create: `src/truthloop/planner.py`
- Create: `tests/test_planner.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_planner.py
from truthloop.contracts.common import EntityRef
from truthloop.contracts.repair_plan import ContractError
from truthloop.contracts.verdict import COMPONENT_NAMES, CapApplied, Component, Finding
from truthloop.planner import PlannerInput, build_plan

WEIGHTS = {
    "context_recall": 0.35,
    "table_recall": 0.15,
    "evidence_support": 0.15,
    "faithfulness": 0.25,
    "relevance_completeness": 0.10,
}


def _components(**values: float) -> dict[str, Component]:
    return {
        name: Component(value=values.get(name), weight=WEIGHTS[name], applicable=name in values)
        for name in COMPONENT_NAMES
    }


def _missing(kind: str, entity_id: str, via: str, depth: int | None = None) -> Finding:
    code = "MISSING_ENTITY" if kind == "program" else "MISSING_TABLE"
    return Finding.model_validate(
        {
            "code": code,
            "severity": "major",
            "detail": "x",
            "entity": {"type": kind, "id": entity_id},
            "via": via,
            "depth": depth,
        }
    )


def _input(**patch: object) -> PlannerInput:
    base: dict[str, object] = {
        "decision": "repair",
        "score": 69.25,
        "raw": 69.25,
        "findings": [],
        "caps_applied": [],
        "weights": WEIGHTS,
        "components": _components(
            context_recall=0.5, table_recall=0.25, evidence_support=1.0, faithfulness=1.0, relevance_completeness=0.8
        ),
        "claim_entities": {"c1": ["prg_ord_save", "prg_ord_valid"], "c2": ["prg_ord_notify", "prg_ord_valid"]},
        "pivot_ids": ["prg_ord_valid"],
        "direction": "both",
        "depth": 1,
    }
    return PlannerInput(**{**base, **patch})  # type: ignore[arg-type]


def test_release_gives_empty_plan() -> None:
    plan = build_plan(_input(decision="release", score=99.0, raw=99.0, findings=[_missing("program", "x", "p")]))
    assert plan.actions == []
    assert plan.summary_for_agent == ""


def test_contract_errors_give_single_fix_contract() -> None:
    errors = [ContractError(loc="answer", msg="fichier manquant")]
    plan = build_plan(_input(decision="invalid", score=0.0, raw=0.0, contract_errors=errors))
    [action] = plan.actions
    assert (action.kind, action.priority, action.expected_gain) == ("fix_contract", 1, 100.0)
    assert action.errors == errors
    assert "1 erreur(s) de contrat" in plan.summary_for_agent


def test_missing_programs_and_tables_become_retrieve_actions() -> None:
    findings = [
        _missing("program", "prg_cust_load", "prg_ord_valid", 1),
        _missing("program", "prg_inv_check", "prg_ord_valid", 1),
        _missing("table", "t_customers", "prg_cust_load"),
        _missing("table", "t_order_lines", "prg_ord_save"),
        _missing("table", "t_stock", "prg_inv_check"),
    ]
    plan = build_plan(_input(findings=findings, expected_programs=4, expected_tables=4))
    programs, tables = plan.actions
    assert (programs.id, programs.kind, programs.priority, programs.expected_gain) == ("a1", "retrieve_entities", 1, 17.5)
    assert [e.id for e in programs.entities] == ["prg_cust_load", "prg_inv_check"]
    assert programs.entities[0].depth == 1
    assert programs.entities[0].via == "prg_ord_valid"
    assert programs.queries is not None
    assert "prg_ord_valid" in programs.queries.graph
    assert programs.queries.rag == "prg_cust_load prg_inv_check"
    assert (tables.kind, tables.priority, tables.expected_gain) == ("retrieve_entities", 2, 11.25)
    assert [e.type for e in tables.entities] == ["table", "table", "table"]
    assert plan.summary_for_agent == (
        "Rappel 0.50 : 2 programme(s) manquant(s) (prg_cust_load, prg_inv_check). "
        "3 table(s) manquante(s) (t_customers, t_order_lines, t_stock)."
    )


def test_claim_findings_are_grouped_and_cap_bonus_goes_to_last_gate_finding() -> None:
    ghost = EntityRef(type="program", id="prg_ghost")
    findings = [
        Finding(code="UNKNOWN_ENTITY", severity="critical", detail="x", entity=ghost),
        Finding(code="UNSUPPORTED_CLAIM", severity="major", detail="x", claim_id="c1"),
        Finding(code="JUDGE_PARTIAL", severity="info", detail="x", claim_id="c2"),
    ]
    plan = build_plan(
        _input(
            findings=findings,
            raw=80.0,
            score=50.0,
            caps_applied=[CapApplied(name="unknown_entity", value=50)],
            claim_entities={"c1": ["prg_ghost"], "c2": ["prg_ord_valid"]},
        )
    )
    first, second = plan.actions
    assert (first.kind, first.claim_ids, first.expected_gain) == ("verify_claim", ["c1"], 50.0)
    assert [e.id for e in first.entities] == ["prg_ghost"]
    assert "corriger l'identifiant" in first.instruction
    assert (second.kind, second.claim_ids, second.expected_gain) == ("verify_claim", ["c2"], 20.0)
    assert plan.summary_for_agent == "2 claim(s) à vérifier (c1, c2)."


def test_orphan_unknown_entity() -> None:
    ghost = EntityRef(type="table", id="t_ghost")
    findings = [Finding(code="UNKNOWN_ENTITY", severity="critical", detail="x", entity=ghost)]
    plan = build_plan(
        _input(findings=findings, raw=90.0, score=50.0, caps_applied=[CapApplied(name="unknown_entity", value=50)])
    )
    [action] = plan.actions
    assert action.kind == "verify_claim"
    assert action.claim_ids == []
    assert [e.id for e in action.entities] == ["t_ghost"]
    assert action.expected_gain == 40.0


def test_structural_actions() -> None:
    pivot = EntityRef(type="program", id="prg_ghost")
    findings = [
        Finding(code="UNKNOWN_PIVOT", severity="critical", detail="x", entity=pivot),
        Finding(code="JUDGE_MISSING", severity="major", detail="x"),
        Finding(code="NO_CLAIMS", severity="major", detail="x"),
    ]
    plan = build_plan(_input(findings=findings, score=40.0, raw=60.0, claim_entities={}))
    kinds = [(a.kind, a.expected_gain) for a in plan.actions]
    assert kinds == [("fix_question", 60.0), ("write_claims", 60.0), ("run_judge", 35.0)]
    assert plan.actions[0].entities[0].id == "prg_ghost"


def test_fallback_improve_answer_targets_lowest_component() -> None:
    plan = build_plan(_input(findings=[], score=94.0, raw=94.0, judge_notes=""))
    [action] = plan.actions
    assert (action.kind, action.component, action.expected_gain) == ("improve_answer", "table_recall", 6.0)
    with_notes = build_plan(_input(findings=[], score=94.0, raw=94.0, judge_notes="Couvrir les tables écrites."))
    assert with_notes.actions[0].instruction == "Couvrir les tables écrites."


def test_non_release_always_has_an_action() -> None:
    for decision in ("repair", "escalate", "invalid"):
        plan = build_plan(_input(decision=decision, findings=[]))
        assert len(plan.actions) >= 1
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_planner.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.planner'`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/planner.py
"""Repair planner: findings → prioritized actions for the orchestrator (spec §7)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from truthloop.contracts.common import Direction
from truthloop.contracts.repair_plan import (
    ActionKind,
    ContractError,
    RepairAction,
    RepairEntity,
    RepairPlan,
    RetrievalQueries,
)
from truthloop.contracts.verdict import CapApplied, Component, Decision, Finding

_SEVERITY_RANK: Final[dict[str, int]] = {"critical": 3, "major": 2, "info": 1}
_GATE_CODES: Final[dict[str, frozenset[str]]] = {
    "unknown_entity": frozenset({"UNKNOWN_ENTITY", "UNKNOWN_PIVOT"}),
    "contradiction": frozenset({"CONTRADICTED_BY_GRAPH", "CONTRADICTED_BY_EVIDENCE"}),
    "missing_judge": frozenset({"JUDGE_MISSING"}),
    "missing_claims": frozenset({"NO_CLAIMS"}),
}
_CLAIM_CODES: Final[frozenset[str]] = frozenset(
    {
        "UNSUPPORTED_CLAIM",
        "DANGLING_CITATION",
        "CONTRADICTED_BY_GRAPH",
        "CONTRADICTED_BY_EVIDENCE",
        "JUDGE_INCOMPLETE",
        "JUDGE_UNSUPPORTED",
        "JUDGE_PARTIAL",
    }
)
_CLAIM_HINTS: Final[dict[str, str]] = {
    "UNSUPPORTED_CLAIM": "trouver une évidence ou retirer la claim",
    "DANGLING_CITATION": "remplacer les citations introuvables",
    "CONTRADICTED_BY_GRAPH": "la relation affirmée est contredite par le graphe, reformuler ou retirer",
    "CONTRADICTED_BY_EVIDENCE": "la claim est contredite par l'évidence, reformuler ou retirer",
    "JUDGE_INCOMPLETE": "faire juger la claim",
    "JUDGE_UNSUPPORTED": "le juge ne trouve pas de support, renforcer l'évidence ou retirer",
    "JUDGE_PARTIAL": "préciser la claim pour qu'elle soit entièrement supportée",
    "UNKNOWN_ENTITY": "entité inconnue du graphe, corriger l'identifiant ou retirer",
}
_COMPONENT_HINTS: Final[dict[str, str]] = {
    "context_recall": "Élargir la recherche des programmes appelants et appelés autour des pivots.",
    "table_recall": "Lister les tables lues et écrites par chaque programme cité.",
    "evidence_support": "Appuyer chaque claim sur un chunk qui nomme explicitement ses entités.",
    "faithfulness": "Reformuler les claims pour qu'elles soient entièrement supportées par l'évidence.",
    "relevance_completeness": "Recentrer la réponse sur la question et couvrir les points manquants.",
}
_DIRECTION_LABEL: Final[dict[Direction, str]] = {
    "callers": "appelants",
    "callees": "appelés",
    "both": "appelants et appelés",
}
_SUMMARY_LIMIT: Final = 3


@dataclass(frozen=True)
class PlannerInput:
    """Everything the planner needs. ``claim_entities`` must list every claim (even without
    entities): its length is the ``total_claims`` denominator of spec §7."""

    decision: Decision
    score: float
    raw: float
    findings: Sequence[Finding]
    caps_applied: Sequence[CapApplied]
    weights: Mapping[str, float]
    components: Mapping[str, Component]
    contract_errors: Sequence[ContractError] = ()
    expected_programs: int = 0
    expected_tables: int = 0
    claim_entities: Mapping[str, Sequence[str]] = field(default_factory=dict)
    pivot_ids: Sequence[str] = ()
    direction: Direction = "both"
    depth: int = 1
    judge_notes: str = ""


@dataclass
class _Candidate:
    kind: ActionKind
    severity: int
    gain: float
    instruction: str
    keys: set[tuple[str, str]] = field(default_factory=set)
    entities: list[RepairEntity] = field(default_factory=list)
    queries: RetrievalQueries | None = None
    claim_ids: list[str] = field(default_factory=list)
    component: str | None = None
    order: int = 0


def build_plan(inp: PlannerInput) -> RepairPlan:
    if inp.decision == "release":
        return RepairPlan()
    if inp.contract_errors:
        action = RepairAction(
            id="a1",
            kind="fix_contract",
            priority=1,
            expected_gain=100.0,
            instruction="Corriger les erreurs de contrat listées dans errors, puis relancer verify.",
            errors=list(inp.contract_errors),
        )
        summary = f"{len(inp.contract_errors)} erreur(s) de contrat à corriger avant toute évaluation."
        return RepairPlan(actions=[action], summary_for_agent=summary)
    candidates = [*_structural_candidates(inp), *_claim_candidates(inp)]
    if not candidates:
        candidates = [_fallback(inp)]
    for index, candidate in enumerate(candidates):
        candidate.order = index
    _apply_cap_bonus(candidates, inp)
    ordered = sorted(candidates, key=lambda c: (-c.severity, -c.gain, c.kind, c.order))
    actions = [_to_action(candidate, priority) for priority, candidate in enumerate(ordered, start=1)]
    return RepairPlan(actions=actions, summary_for_agent=_summary(ordered, inp))


def _finding_key(finding: Finding) -> tuple[str, str]:
    if finding.claim_id is not None:
        return ("claim", finding.claim_id)
    if finding.entity is not None:
        return ("entity", finding.entity.id)
    return ("code", finding.code)


def _keys(findings: Sequence[Finding]) -> set[tuple[str, str]]:
    return {_finding_key(f) for f in findings}


def _entities(findings: Sequence[Finding]) -> list[RepairEntity]:
    return [
        RepairEntity(type=f.entity.type, id=f.entity.id, depth=f.depth, via=f.via)
        for f in findings
        if f.entity is not None
    ]


def _structural_candidates(inp: PlannerInput) -> list[_Candidate]:
    by_code: dict[str, list[Finding]] = defaultdict(list)
    for finding in inp.findings:
        by_code[finding.code].append(finding)
    total_weight = sum(inp.weights.values())
    out: list[_Candidate] = []
    if by_code["UNKNOWN_PIVOT"]:
        out.append(
            _Candidate(
                kind="fix_question",
                severity=_SEVERITY_RANK["critical"],
                gain=100.0 - inp.score,
                instruction="Pivot inconnu du graphe : corriger l'identifiant dans question.json puis relancer.",
                keys=_keys(by_code["UNKNOWN_PIVOT"]),
                entities=_entities(by_code["UNKNOWN_PIVOT"]),
            )
        )
    if by_code["JUDGE_MISSING"]:
        gain = 100.0 * (inp.weights["faithfulness"] + inp.weights["relevance_completeness"]) / total_weight
        out.append(
            _Candidate(
                kind="run_judge",
                severity=_SEVERITY_RANK["major"],
                gain=gain,
                instruction="Produire judge.json (rubrique claim par claim) puis relancer verify.",
                keys=_keys(by_code["JUDGE_MISSING"]),
            )
        )
    out.extend(_retrieve_candidates(inp, by_code["MISSING_ENTITY"], by_code["MISSING_TABLE"], total_weight))
    if by_code["NO_CLAIMS"]:
        out.append(
            _Candidate(
                kind="write_claims",
                severity=_SEVERITY_RANK["major"],
                gain=100.0 - inp.score,
                instruction="Rédiger des claims citées (entités + citations) pour les entités présentes dans answer.entities.",
                keys=_keys(by_code["NO_CLAIMS"]),
            )
        )
    return out


def _retrieve_candidates(
    inp: PlannerInput, programs: list[Finding], tables: list[Finding], total_weight: float
) -> list[_Candidate]:
    out: list[_Candidate] = []
    if programs:
        ids = [f.entity.id for f in programs if f.entity is not None]
        gain = 100.0 * inp.weights["context_recall"] * len(ids) / max(inp.expected_programs, 1) / total_weight
        pivots = ", ".join(inp.pivot_ids) or "les pivots"
        graph_query = (
            f"Lister les {_DIRECTION_LABEL[inp.direction]} de {pivots} jusqu'à la profondeur {inp.depth}, "
            f"inclure {', '.join(ids)}."
        )
        out.append(
            _Candidate(
                kind="retrieve_entities",
                severity=_SEVERITY_RANK["major"],
                gain=gain,
                instruction="Citer chaque programme trouvé dans answer.entities et appuyer chaque claim par un chunk.",
                keys=_keys(programs),
                entities=_entities(programs),
                queries=RetrievalQueries(graph=graph_query, rag=" ".join(ids)),
            )
        )
    if tables:
        ids = [f.entity.id for f in tables if f.entity is not None]
        gain = 100.0 * inp.weights["table_recall"] * len(ids) / max(inp.expected_tables, 1) / total_weight
        users = ", ".join(sorted({f.via for f in tables if f.via is not None})) or "les programmes cités"
        graph_query = f"Lister les tables lues et écrites par {users}, inclure {', '.join(ids)}."
        out.append(
            _Candidate(
                kind="retrieve_entities",
                severity=_SEVERITY_RANK["major"],
                gain=gain,
                instruction="Citer chaque table trouvée dans answer.entities avec le programme qui la lit ou l'écrit.",
                keys=_keys(tables),
                entities=_entities(tables),
                queries=RetrievalQueries(graph=graph_query, rag=" ".join(ids)),
            )
        )
    return out


def _claim_candidates(inp: PlannerInput) -> list[_Candidate]:
    per_claim: dict[str, list[Finding]] = {}
    orphans: list[Finding] = []
    for finding in inp.findings:
        if finding.code in _CLAIM_CODES and finding.claim_id is not None:
            per_claim.setdefault(finding.claim_id, []).append(finding)
    for finding in inp.findings:
        if finding.code != "UNKNOWN_ENTITY" or finding.entity is None:
            continue
        entity_id = finding.entity.id
        owners = [claim_id for claim_id, ids in inp.claim_entities.items() if entity_id in ids]
        if not owners:
            orphans.append(finding)
        for claim_id in owners:
            per_claim.setdefault(claim_id, []).append(finding)
    total_weight = sum(inp.weights.values())
    total_claims = max(len(inp.claim_entities), 1)
    per_claim_gain = (
        100.0 * (inp.weights["evidence_support"] + inp.weights["faithfulness"]) / total_claims / total_weight
    )
    out: list[_Candidate] = []
    for claim_id, findings in per_claim.items():
        hints = list(dict.fromkeys(_CLAIM_HINTS[f.code] for f in findings))
        out.append(
            _Candidate(
                kind="verify_claim",
                severity=max(_SEVERITY_RANK[f.severity] for f in findings),
                gain=per_claim_gain,
                instruction=f"Claim {claim_id} : " + " ; ".join(hints) + ".",
                keys=_keys(findings),
                claim_ids=[claim_id],
                entities=_entities([f for f in findings if f.code == "UNKNOWN_ENTITY"]),
            )
        )
    if orphans:
        out.append(
            _Candidate(
                kind="verify_claim",
                severity=_SEVERITY_RANK["critical"],
                gain=0.0,
                instruction=(
                    "Entités inconnues du graphe et référencées par aucune claim : "
                    "corriger l'identifiant ou les retirer de answer.entities."
                ),
                keys=_keys(orphans),
                entities=_entities(orphans),
            )
        )
    return out


def _apply_cap_bonus(candidates: list[_Candidate], inp: PlannerInput) -> None:
    """Spec §7: the verify_claim action holding the last finding of a gate earns the lifted cap.

    "Last" follows the emission order of ``inp.findings`` (graders run in a fixed order and each
    walks claims and entities in answer.json order), which keeps the gain deterministic.
    """
    values = {cap.name: float(cap.value) for cap in inp.caps_applied}
    for name, value in values.items():
        codes = _GATE_CODES.get(name, frozenset())
        last = next((f for f in reversed(inp.findings) if f.code in codes), None)
        if last is None:
            continue
        others = [v for n, v in values.items() if n != name]
        bonus = max(0.0, min([inp.raw, *others]) - value)
        key = _finding_key(last)
        for candidate in candidates:
            if candidate.kind == "verify_claim" and key in candidate.keys:
                candidate.gain += bonus
                break


def _fallback(inp: PlannerInput) -> _Candidate:
    applicable = [(name, c.value) for name, c in inp.components.items() if c.applicable and c.value is not None]
    lowest = min(applicable, key=lambda item: (item[1], item[0]))[0] if applicable else "relevance_completeness"
    notes = inp.judge_notes.strip()
    return _Candidate(
        kind="improve_answer",
        severity=_SEVERITY_RANK["major"],
        gain=100.0 - inp.score,
        instruction=notes or _COMPONENT_HINTS[lowest],
        component=lowest,
    )


def _to_action(candidate: _Candidate, priority: int) -> RepairAction:
    return RepairAction(
        id=f"a{priority}",
        kind=candidate.kind,
        priority=priority,
        expected_gain=round(max(candidate.gain, 0.0), 2),
        instruction=candidate.instruction,
        entities=candidate.entities,
        queries=candidate.queries,
        claim_ids=candidate.claim_ids,
        component=candidate.component,
    )


def _family(candidate: _Candidate) -> str:
    if candidate.kind == "retrieve_entities":
        is_table = bool(candidate.entities) and candidate.entities[0].type == "table"
        return "retrieve:table" if is_table else "retrieve:program"
    if candidate.kind == "verify_claim":
        return "verify"
    return candidate.kind


def _summary(ordered: Sequence[_Candidate], inp: PlannerInput) -> str:
    sentences: list[str] = []
    seen: set[str] = set()
    verify_ids = [claim_id for c in ordered if c.kind == "verify_claim" for claim_id in c.claim_ids]
    for candidate in ordered:
        family = _family(candidate)
        if family in seen:
            continue
        seen.add(family)
        ids = ", ".join(e.id for e in candidate.entities)
        if family == "retrieve:program":
            recall = inp.components["context_recall"].value
            prefix = f"Rappel {recall:.2f} : " if recall is not None else ""
            sentences.append(f"{prefix}{len(candidate.entities)} programme(s) manquant(s) ({ids}).")
        elif family == "retrieve:table":
            sentences.append(f"{len(candidate.entities)} table(s) manquante(s) ({ids}).")
        elif family == "verify" and verify_ids:
            sentences.append(f"{len(verify_ids)} claim(s) à vérifier ({', '.join(verify_ids)}).")
        else:
            sentences.append(candidate.instruction)
        if len(sentences) == _SUMMARY_LIMIT:
            break
    return " ".join(sentences)
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_planner.py --no-cov -q`
Expected: `8 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur. Si ruff signale `PLR0912`/`PLR0915` (trop de branches) sur `_structural_candidates`, extraire les blocs `fix_question` / `run_judge` / `write_claims` dans une fonction `_single_candidates` plutôt que d'ajouter un `noqa`.

### Task 18 : Configuration `truthloop.yaml`

**Files:**
- Create: `src/truthloop/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_config.py
from pathlib import Path

import pytest

from truthloop.config import DEFAULT_CONFIG_YAML, Config, ConfigError, config_sha256, load_config, resolve_path


def test_default_yaml_loads_and_matches_spec(tmp_path: Path) -> None:
    path = tmp_path / "truthloop.yaml"
    path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
    config = load_config(path)
    assert config.knowledge.kind == "sqlite"
    assert config.knowledge.path == "knowledge/magic.db"
    assert config.scoring.weights["context_recall"] == 0.35
    assert config.scoring.caps["missing_claims"] == 85
    assert config.scoring.release_threshold == 90.0
    assert config.scoring.release_threshold_no_reference == 95.0
    assert config.loop.max_iterations == 3
    assert config.paths.runs == "runs"
    assert len(config_sha256(config)) == 64
    assert config_sha256(config) == config_sha256(Config.model_validate(config.model_dump()))


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ("  release_threshold: 101\n", "release_threshold"),
        ("  weights: {context_recall: 1}\n", "weights"),
        ("  caps: {unknown_entity: 50}\n", "caps"),
        ("  weights: {context_recall: 0, table_recall: 0, evidence_support: 0, faithfulness: 0, relevance_completeness: 0}\n", "weights"),
    ],
)
def test_invalid_scoring_is_rejected(tmp_path: Path, patch: str, message: str) -> None:
    text = DEFAULT_CONFIG_YAML.replace("  release_threshold: 90\n", patch if "threshold" in patch else "  release_threshold: 90\n" + patch)
    path = tmp_path / "truthloop.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_config(path)


def test_missing_or_broken_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="introuvable"):
        load_config(tmp_path / "nope.yaml")
    path = tmp_path / "truthloop.yaml"
    path.write_text("knowledge: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="YAML"):
        load_config(path)
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError, match="vide"):
        load_config(path)


def test_resolve_path_is_relative_to_config(tmp_path: Path) -> None:
    config_path = tmp_path / "sub" / "truthloop.yaml"
    assert resolve_path(config_path, "knowledge/magic.db") == tmp_path / "sub" / "knowledge" / "magic.db"
    assert resolve_path(config_path, str(tmp_path / "abs.db")) == tmp_path / "abs.db"
```

Note sur le deuxième test : le remplacement de texte construit une config invalide en remplaçant ou en dupliquant une clé. YAML rejette les clés dupliquées ? Non, `yaml.safe_load` garde la dernière occurrence, ce qui est le comportement attendu ici (la clé ajoutée après `release_threshold: 90` écrase `weights`/`caps` définis plus haut).

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_config.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.config'`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/config.py
"""truthloop.yaml loading and validation (spec §8.3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final, Literal, Self

import yaml
from pydantic import Field, ValidationError, model_validator

from truthloop.contracts.common import SchemaVersion, StrictModel
from truthloop.contracts.verdict import CAP_NAMES, COMPONENT_NAMES

_MAX_PERCENT: Final = 100


class ConfigError(Exception):
    """Configuration missing or invalid (exit code 1)."""


class KnowledgeConfig(StrictModel):
    kind: Literal["sqlite", "files"]
    path: str = Field(min_length=1)
    queries: dict[str, str] = Field(default_factory=dict)


class ScoringConfig(StrictModel):
    weights: dict[str, float]
    caps: dict[str, int]
    release_threshold: float = Field(ge=0.0, le=100.0)
    release_threshold_no_reference: float = Field(ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if set(self.weights) != set(COMPONENT_NAMES):
            raise ValueError(f"weights doit contenir exactement {sorted(COMPONENT_NAMES)}")
        if any(w < 0 for w in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise ValueError("weights doivent être ≥ 0 et de somme > 0")
        if set(self.caps) != set(CAP_NAMES):
            raise ValueError(f"caps doit contenir exactement {sorted(CAP_NAMES)}")
        if any(not 0 <= c <= _MAX_PERCENT for c in self.caps.values()):
            raise ValueError("caps doivent être dans [0, 100]")
        return self


class LoopConfig(StrictModel):
    max_iterations: int = Field(default=3, ge=1)


class PathsConfig(StrictModel):
    runs: str = "runs"
    golden: str = "golden"
    reports: str = "reports"


class Config(StrictModel):
    schema_version: SchemaVersion = 1
    knowledge: KnowledgeConfig
    scoring: ScoringConfig
    loop: LoopConfig = Field(default_factory=LoopConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)


DEFAULT_CONFIG_YAML: Final[str] = """\
schema_version: 1
knowledge:
  kind: sqlite
  path: knowledge/magic.db
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
"""


def load_config(path: Path) -> Config:
    if not path.is_file():
        raise ConfigError(f"configuration introuvable : {path}")
    try:
        data: object = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML invalide ({path}) : {exc}") from exc
    if data is None:
        raise ConfigError(f"configuration vide : {path}")
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"configuration invalide ({path}) : {exc}") from exc


def config_sha256(config: Config) -> str:
    canonical = json.dumps(config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_path(config_path: Path, relative: str) -> Path:
    path = Path(relative)
    return path if path.is_absolute() else config_path.parent / path
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_config.py --no-cov -q`
Expected: `7 passed`

- [ ] **Step 5 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 19 : Dossier de run, canonisation et trace

**Files:**
- Create: `src/truthloop/runs.py`
- Create: `tests/test_runs.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_runs.py
import json
from pathlib import Path

import pytest

from conftest import RunBuilder
from helpers import sample_answer, sample_question
from truthloop.runs import RunDir, RunError, canonical_json, inputs_sha256


def test_canonical_json_and_inputs_hash() -> None:
    assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'
    assert canonical_json({"é": "ü"}) == '{"é":"ü"}'
    same = inputs_sha256([{"a": 1}, None, {"b": 2}])
    assert same == inputs_sha256([{"a": 1}, None, {"b": 2}])
    assert same != inputs_sha256([{"b": 2}, None, {"a": 1}])
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


def test_trace_append_and_read(make_run: RunBuilder) -> None:
    run = RunDir(make_run(sample_question(), None, None, None))
    run.append_trace({"ts": "t1", "iteration": 1, "event": "verify", "score": 10.0, "decision": "repair"})
    run.append_trace({"ts": "t2", "iteration": 2, "event": "verify", "score": 95.0, "decision": "release"})
    rows = run.read_trace()
    assert [r["iteration"] for r in rows] == [1, 2]
    assert (run.path / "trace.jsonl").read_text(encoding="utf-8").count("\n") == 2
    assert json.loads((run.path / "trace.jsonl").read_text(encoding="utf-8").splitlines()[0])["decision"] == "repair"
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_runs.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.runs'`

- [ ] **Step 3 : Implémenter**

```python
# src/truthloop/runs.py
"""Run directory layout, canonical hashing and trace (spec §8.1, §4.5)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from truthloop.contracts.bundle import errors_from
from truthloop.contracts.question import Question
from truthloop.contracts.verdict import Verdict

_ITERATION_DIR: Final = re.compile(r"^iter-(\d+)$")


class RunError(Exception):
    """The run directory is unusable (exit code 1, no verdict written)."""


def canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def inputs_sha256(parts: Sequence[object | None]) -> str:
    """Spec §4.5: canonical JSON of question, answer, evidence, judge; absent → empty string."""
    return sha256_text("".join(canonical_json(part) if part is not None else "" for part in parts))


@dataclass(frozen=True)
class RunDir:
    path: Path

    @property
    def question_path(self) -> Path:
        return self.path / "question.json"

    @property
    def trace_path(self) -> Path:
        return self.path / "trace.jsonl"

    def iteration_path(self, iteration: int) -> Path:
        return self.path / f"iter-{iteration:02d}"

    def iterations(self) -> list[int]:
        if not self.path.is_dir():
            return []
        numbers: list[int] = []
        for child in self.path.iterdir():
            match = _ITERATION_DIR.match(child.name)
            if child.is_dir() and match:
                numbers.append(int(match.group(1)))
        return sorted(numbers)

    def latest_iteration(self) -> int:
        iterations = self.iterations()
        if not iterations:
            raise RunError(f"aucune itération (dossier iter-NN) dans {self.path}")
        return iterations[-1]

    def load_question(self) -> tuple[Question, object]:
        if not self.question_path.is_file():
            raise RunError(f"question.json introuvable dans {self.path}")
        try:
            raw: object = json.loads(self.question_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RunError(f"question.json illisible : {exc}") from exc
        try:
            question = Question.model_validate(raw)
        except ValidationError as exc:
            details = "; ".join(f"{e.loc}: {e.msg}" for e in errors_from(exc, "question"))
            raise RunError(f"question.json invalide : {details}") from exc
        return question, raw

    def verdict_path(self, iteration: int) -> Path:
        return self.iteration_path(iteration) / "verdict.json"

    def write_verdict(self, verdict: Verdict) -> Path:
        path = self.verdict_path(verdict.iteration)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(verdict.model_dump_json(indent=2) + "\n", encoding="utf-8")
        return path

    def load_verdict(self, iteration: int) -> Verdict | None:
        path = self.verdict_path(iteration)
        if not path.is_file():
            return None
        return Verdict.model_validate_json(path.read_text(encoding="utf-8"))

    def append_trace(self, event: Mapping[str, object]) -> None:
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(dict(event)) + "\n")

    def read_trace(self) -> list[dict[str, object]]:
        if not self.trace_path.is_file():
            return []
        rows: list[dict[str, object]] = []
        for line in self.trace_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parsed: object = json.loads(line)
            if isinstance(parsed, dict):
                rows.append({str(k): v for k, v in parsed.items()})
        return rows
```

- [ ] **Step 4 : Vérifier le succès**

Run: `uv run pytest tests/test_runs.py --no-cov -q`
Expected: `4 passed`

- [ ] **Step 5 : Suite complète du chunk et lint**

Run: `uv run ruff format src tests && uv run pytest -q && uv run ruff check src tests && uv run mypy`
Expected: tous les tests passent, couverture ≥ 85 %, aucune erreur.

- [ ] **Step 6 : Point de contrôle**

Demander à l'utilisateur s'il souhaite un commit (message proposé : `✨ feat(truthloop): repair planner, config and run directory`). Ne pas committer sans réponse.

---

## Chunk 5 : moteur d'évaluation et CLI

### Task 20 : Moteur `evaluate`

**Files:**
- Create: `src/truthloop/engine.py`
- Modify: `tests/helpers.py` (fabrique `release_answer`, `files_config`)
- Create: `tests/test_engine.py`

- [ ] **Step 1 : Fabriques supplémentaires (`tests/helpers.py`)**

```python
def release_answer() -> dict[str, object]:
    """Cites every expected program and table of the sample question: raw score 99."""
    return sample_answer(
        entities=[
            {"type": "program", "id": "PRG_ORD_VALID"},
            {"type": "program", "id": "PRG_ORD_SAVE"},
            {"type": "program", "id": "PRG_ORD_NOTIFY"},
            {"type": "program", "id": "PRG_CUST_LOAD"},
            {"type": "program", "id": "PRG_INV_CHECK"},
            {"type": "table", "id": "T_ORDERS"},
            {"type": "table", "id": "T_ORDER_LINES"},
            {"type": "table", "id": "T_CUSTOMERS"},
            {"type": "table", "id": "T_STOCK"},
        ]
    )


def files_config(graph_path: Path) -> dict[str, object]:
    """Config dict pointing the files backend at a graph.json (absolute path)."""
    return {
        "schema_version": 1,
        "knowledge": {"kind": "files", "path": str(graph_path), "queries": {}},
        "scoring": {
            "weights": {
                "context_recall": 0.35,
                "table_recall": 0.15,
                "evidence_support": 0.15,
                "faithfulness": 0.25,
                "relevance_completeness": 0.10,
            },
            "caps": {"unknown_entity": 50, "contradiction": 70, "missing_judge": 85, "missing_claims": 85},
            "release_threshold": 90,
            "release_threshold_no_reference": 95,
        },
        "loop": {"max_iterations": 3},
        "paths": {"runs": "runs", "golden": "golden", "reports": "reports"},
    }
```

- [ ] **Step 2 : Test rouge**

```python
# tests/test_engine.py
from datetime import UTC, datetime

import pytest

from conftest import FIXTURES, RunBuilder
from helpers import files_config, release_answer, sample_answer, sample_evidence, sample_judge, sample_question
from truthloop.config import Config
from truthloop.engine import EXIT_CODES, evaluate
from truthloop.knowledge.graph import InMemoryGraph
from truthloop.runs import RunDir, RunError

NOW = datetime(2026, 9, 8, 19, 40, 12, tzinfo=UTC)


@pytest.fixture
def config() -> Config:
    return Config.model_validate(files_config(FIXTURES / "graph.json"))


def test_sample_run_is_repair(make_run: RunBuilder, config: Config, graph: InMemoryGraph) -> None:
    run = RunDir(make_run(sample_question(), sample_answer(), sample_evidence(), sample_judge(notes="n")))
    verdict = evaluate(run, config, graph, now=NOW)
    assert verdict.decision == "repair"
    assert verdict.score in (69.2, 69.3)  # round(69.25, 1) depends on float error of raw
    assert verdict.threshold == 90.0
    assert verdict.components["context_recall"].value == 0.5
    assert verdict.declared_gaps == ["Profondeur 2 non explorée."]
    assert [a.kind for a in verdict.repair_plan.actions] == ["retrieve_entities", "retrieve_entities"]
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


def test_missing_judge_caps_and_plans_run_judge(make_run: RunBuilder, config: Config, graph: InMemoryGraph) -> None:
    judge = None
    run = RunDir(make_run(sample_question(), release_answer(), sample_evidence(), judge))
    verdict = evaluate(run, config, graph, now=NOW)
    assert [c.name for c in verdict.caps_applied] == ["missing_judge"]
    assert verdict.score == 85.0
    assert any(a.kind == "run_judge" for a in verdict.repair_plan.actions)


def test_escalate_at_max_iterations(make_run: RunBuilder, config: Config, graph: InMemoryGraph) -> None:
    run_dir = make_run(sample_question(), sample_answer(iteration=3), sample_evidence(iteration=3), sample_judge(iteration=3), iteration=3)
    verdict = evaluate(RunDir(run_dir), config, graph, now=NOW)
    assert verdict.decision == "escalate"
    assert len(verdict.repair_plan.actions) >= 1
    assert EXIT_CODES["escalate"] == 3


def test_verdict_is_deterministic(make_run: RunBuilder, config: Config, graph: InMemoryGraph) -> None:
    run = RunDir(make_run(sample_question(), sample_answer(), sample_evidence(), sample_judge()))
    first = evaluate(run, config, graph, now=NOW)
    second = evaluate(run, config, graph, now=NOW)
    assert first == second


def test_explicit_iteration_and_missing_iteration(make_run: RunBuilder, config: Config, graph: InMemoryGraph) -> None:
    run = RunDir(make_run(sample_question(), sample_answer(), sample_evidence(), sample_judge()))
    assert evaluate(run, config, graph, iteration=1, now=NOW).iteration == 1
    with pytest.raises(RunError, match="itération 2"):
        evaluate(run, config, graph, iteration=2, now=NOW)
```

`FIXTURES` doit être exporté par `tests/conftest.py` (déjà défini en Task 8).

- [ ] **Step 3 : Vérifier l'échec**

Run: `uv run pytest tests/test_engine.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.engine'`

- [ ] **Step 4 : Implémenter**

```python
# src/truthloop/engine.py
"""One evaluation: load, grade, score, decide, plan, persist (spec §3, §6, §7, §10)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

from truthloop import __version__
from truthloop.config import Config, config_sha256
from truthloop.contracts.bundle import RunBundle, load_iteration
from truthloop.contracts.question import Question
from truthloop.contracts.repair_plan import ContractError
from truthloop.contracts.verdict import COMPONENT_NAMES, Component, Decision, Provenance, Verdict
from truthloop.graders import run_graders
from truthloop.graders.base import GraderContext
from truthloop.knowledge import KnowledgeSource
from truthloop.planner import PlannerInput, build_plan
from truthloop.runs import RunDir, RunError, inputs_sha256
from truthloop.scoring import aggregate, decide

EXIT_CODES: Final[dict[Decision, int]] = {"release": 0, "repair": 2, "escalate": 3, "invalid": 4}


def evaluate(
    run: RunDir,
    config: Config,
    knowledge: KnowledgeSource,
    iteration: int | None = None,
    now: datetime | None = None,
) -> Verdict:
    question, question_raw = run.load_question()
    number = run.latest_iteration() if iteration is None else iteration
    iteration_dir = run.iteration_path(number)
    if not iteration_dir.is_dir():
        raise RunError(f"itération {number} introuvable dans {run.path}")
    loaded = load_iteration(question, iteration_dir, number)
    stamp = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    provenance = Provenance(
        harness_version=__version__,
        inputs_sha256=inputs_sha256(
            [question_raw, loaded.raw.get("answer"), loaded.raw.get("evidence"), loaded.raw.get("judge")]
        ),
        config_sha256=config_sha256(config),
        knowledge_source=f"{config.knowledge.kind}:{config.knowledge.path}",
        knowledge_fingerprint=knowledge.fingerprint(),
        generated_at=stamp,
    )
    if loaded.bundle is None:
        verdict = _invalid_verdict(question, number, loaded.errors, config, provenance)
    else:
        verdict = _evaluate_bundle(loaded.bundle, number, config, knowledge, provenance)
    run.write_verdict(verdict)
    run.append_trace(
        {"ts": stamp, "iteration": number, "event": "verify", "score": verdict.score, "decision": verdict.decision}
    )
    return verdict


def _invalid_verdict(
    question: Question, number: int, errors: Sequence[ContractError], config: Config, provenance: Provenance
) -> Verdict:
    components = {
        name: Component(value=None, weight=config.scoring.weights[name], applicable=False) for name in COMPONENT_NAMES
    }
    plan = build_plan(
        PlannerInput(
            decision="invalid",
            score=0.0,
            raw=0.0,
            findings=[],
            caps_applied=[],
            weights=config.scoring.weights,
            components=components,
            contract_errors=errors,
        )
    )
    return Verdict(
        question_id=question.id,
        iteration=number,
        score=0.0,
        decision="invalid",
        threshold=config.scoring.release_threshold,
        components=components,
        repair_plan=plan,
        provenance=provenance,
    )


def _evaluate_bundle(
    bundle: RunBundle, number: int, config: Config, knowledge: KnowledgeSource, provenance: Provenance
) -> Verdict:
    ctx = GraderContext(
        question=bundle.question,
        answer=bundle.answer,
        evidence=bundle.evidence,
        judge=bundle.judge,
        knowledge=knowledge,
    )
    results = run_graders(ctx)
    findings = [finding for result in results for finding in result.findings]
    breakdown = aggregate(results, config.scoring.weights, config.scoring.caps)
    decision, threshold = decide(
        breakdown.score,
        findings,
        breakdown.components["context_recall"].applicable,
        number,
        config.loop.max_iterations,
        config.scoring.release_threshold,
        config.scoring.release_threshold_no_reference,
    )
    sizes = {r.component: r.expected_size for r in results if r.component and r.expected_size is not None}
    plan = build_plan(
        PlannerInput(
            decision=decision,
            score=breakdown.score,
            raw=breakdown.raw,
            findings=findings,
            caps_applied=breakdown.caps_applied,
            weights=config.scoring.weights,
            components=breakdown.components,
            expected_programs=sizes.get("context_recall", 0),
            expected_tables=sizes.get("table_recall", 0),
            claim_entities={claim.id: claim.entities for claim in bundle.answer.claims},
            pivot_ids=[pivot.id for pivot in bundle.question.pivot_entities],
            direction=bundle.question.direction,
            depth=bundle.question.depth,
            judge_notes=bundle.judge.notes if bundle.judge is not None else "",
        )
    )
    return Verdict(
        question_id=bundle.question.id,
        iteration=number,
        score=round(breakdown.score, 1),
        decision=decision,
        threshold=threshold,
        components=breakdown.components,
        caps_applied=breakdown.caps_applied,
        findings=findings,
        declared_gaps=[abstention.text for abstention in bundle.answer.abstentions],
        repair_plan=plan,
        provenance=provenance,
    )
```

- [ ] **Step 5 : Vérifier le succès**

Run: `uv run pytest tests/test_engine.py --no-cov -q`
Expected: `7 passed`

- [ ] **Step 6 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur.

### Task 21 : Rendu Rich et CLI

**Files:**
- Create: `src/truthloop/render.py`
- Create: `src/truthloop/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1 : Test rouge**

```python
# tests/test_cli.py
import json
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURES, RunBuilder
from helpers import files_config, release_answer, sample_answer, sample_evidence, sample_judge, sample_question
from truthloop.cli import main


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "truthloop.yaml"
    path.write_text(yaml.safe_dump(files_config(FIXTURES / "graph.json"), sort_keys=False), encoding="utf-8")
    return path


def test_init_creates_layout(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config = tmp_path / "proj" / "truthloop.yaml"
    assert main(["init", "--config", str(config)]) == 0
    assert config.is_file()
    assert (config.parent / "runs").is_dir()
    assert (config.parent / "golden").is_dir()
    assert (config.parent / "reports").is_dir()
    assert (config.parent / "schemas" / "verdict.schema.json").is_file()
    first = config.read_text(encoding="utf-8")
    assert main(["init", "--config", str(config)]) == 0
    assert config.read_text(encoding="utf-8") == first
    assert "truthloop.yaml" in capsys.readouterr().out


def test_verify_exit_codes_and_json(
    make_run: RunBuilder, config_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run_dir = make_run(sample_question(), sample_answer(), sample_evidence(), sample_judge())
    assert main(["verify", "--run", str(run_dir), "--config", str(config_path)]) == 2
    out = capsys.readouterr().out
    assert "repair" in out
    assert main(["verify", "--run", str(run_dir), "--config", str(config_path), "--json"]) == 2
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["decision"] == "repair"
    assert (run_dir / "iter-01" / "verdict.json").is_file()


def test_verify_release_invalid_and_errors(
    make_run: RunBuilder, config_path: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    judge = sample_judge(relevance=0.9, completeness=0.9)
    release = make_run(sample_question(), release_answer(), sample_evidence(), judge, run_id="rel")
    assert main(["verify", "--run", str(release), "--config", str(config_path)]) == 0
    invalid = make_run(sample_question(), None, sample_evidence(), None, run_id="inv")
    assert main(["verify", "--run", str(invalid), "--config", str(config_path)]) == 4
    assert main(["verify", "--run", str(tmp_path / "nope"), "--config", str(config_path)]) == 1
    assert "question.json" in capsys.readouterr().err
    assert main(["verify", "--run", str(release), "--config", str(tmp_path / "missing.yaml")]) == 1


def test_schema_export(tmp_path: Path) -> None:
    out = tmp_path / "schemas"
    assert main(["schema", "export", "--out", str(out)]) == 0
    assert len(list(out.glob("*.schema.json"))) == 6


def test_trace(make_run: RunBuilder, config_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run_dir = make_run(sample_question(), sample_answer(), sample_evidence(), sample_judge())
    make_run(None, sample_answer(iteration=2), sample_evidence(iteration=2), sample_judge(iteration=2), iteration=2)
    main(["verify", "--run", str(run_dir), "--config", str(config_path), "--iteration", "1"])
    main(["verify", "--run", str(run_dir), "--config", str(config_path), "--iteration", "2"])
    capsys.readouterr()
    assert main(["trace", "--run", str(run_dir), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["iteration"] for r in rows] == [1, 2]
    assert rows[0]["open_findings"] == 5
    assert rows[1]["resolved_findings"] == 0
    assert main(["trace", "--run", str(run_dir)]) == 0
    assert "repair" in capsys.readouterr().out
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `uv run pytest tests/test_cli.py --no-cov -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'truthloop.cli'`

- [ ] **Step 3 : Implémenter le rendu**

```python
# src/truthloop/render.py
"""Rich rendering for the terminal (spec §8.2)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from truthloop.contracts.verdict import Verdict


@dataclass(frozen=True)
class TraceRow:
    iteration: int
    score: float
    decision: str
    open_findings: int
    resolved_findings: int


def render_verdict(verdict: Verdict, console: Console) -> None:
    console.print(
        f"[bold]{escape(verdict.question_id)}[/bold] itération {verdict.iteration} : "
        f"score [bold]{verdict.score:.1f}[/bold] / seuil {verdict.threshold:.0f} "
        f"→ [bold]{verdict.decision}[/bold]"
    )
    components = Table(title="Composantes")
    components.add_column("composante")
    components.add_column("valeur", justify="right")
    components.add_column("poids", justify="right")
    components.add_column("applicable")
    for name, component in verdict.components.items():
        value = "n/a" if component.value is None else f"{component.value:.2f}"
        components.add_row(name, value, f"{component.weight:.2f}", "oui" if component.applicable else "non")
    console.print(components)
    if verdict.caps_applied:
        console.print("Plafonds : " + ", ".join(f"{c.name} ({c.value})" for c in verdict.caps_applied))
    if verdict.findings:
        findings = Table(title="Findings")
        findings.add_column("code")
        findings.add_column("sévérité")
        findings.add_column("cible")
        findings.add_column("détail")
        for finding in verdict.findings:
            target = finding.claim_id or (finding.entity.id if finding.entity else "")
            findings.add_row(finding.code, finding.severity, escape(target), escape(finding.detail))
        console.print(findings)
    if verdict.repair_plan.actions:
        actions = Table(title="Plan de réparation")
        actions.add_column("#", justify="right")
        actions.add_column("action")
        actions.add_column("gain", justify="right")
        actions.add_column("instruction")
        for action in verdict.repair_plan.actions:
            actions.add_row(
                str(action.priority), action.kind, f"{action.expected_gain:.1f}", escape(action.instruction)
            )
        console.print(actions)
        console.print(f"[italic]{escape(verdict.repair_plan.summary_for_agent)}[/italic]")


def render_trace(rows: Sequence[TraceRow], console: Console) -> None:
    table = Table(title="Trace")
    table.add_column("itération", justify="right")
    table.add_column("score", justify="right")
    table.add_column("décision")
    table.add_column("findings ouverts", justify="right")
    table.add_column("résolus", justify="right")
    for row in rows:
        table.add_row(
            str(row.iteration), f"{row.score:.1f}", row.decision, str(row.open_findings), str(row.resolved_findings)
        )
    console.print(table)
```

- [ ] **Step 4 : Implémenter la CLI**

```python
# src/truthloop/cli.py
"""Command-line entry point (spec §8.2): init, verify, schema export, trace."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path

from rich.console import Console

from truthloop.config import DEFAULT_CONFIG_YAML, ConfigError, load_config, resolve_path
from truthloop.contracts.schemas import export_schemas
from truthloop.engine import EXIT_CODES, evaluate
from truthloop.knowledge import KnowledgeError
from truthloop.knowledge.factory import open_knowledge
from truthloop.render import TraceRow, render_trace, render_verdict
from truthloop.runs import RunDir, RunError

Handler = Callable[[argparse.Namespace, Console], int]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler: Handler = args.handler
    console = Console(soft_wrap=True)
    try:
        return handler(args, console)
    except (RunError, ConfigError, KnowledgeError) as exc:
        Console(stderr=True, soft_wrap=True).print(f"erreur : {exc}", markup=False, style="red")
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="truthloop", description="Harness d'évaluation déterministe.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="crée truthloop.yaml, runs/, golden/, reports/ et schemas/")
    init.add_argument("--config", type=Path, default=Path("truthloop.yaml"))
    init.set_defaults(handler=cmd_init)

    verify = subparsers.add_parser("verify", help="évalue une itération et écrit verdict.json")
    verify.add_argument("--run", type=Path, required=True)
    verify.add_argument("--iteration", type=int, default=None)
    verify.add_argument("--config", type=Path, default=Path("truthloop.yaml"))
    verify.add_argument("--json", action="store_true", dest="as_json")
    verify.set_defaults(handler=cmd_verify)

    schema = subparsers.add_parser("schema", help="outils sur les schémas JSON")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)
    export = schema_sub.add_parser("export", help="écrit les JSON Schema des contrats")
    export.add_argument("--out", type=Path, default=Path("schemas"))
    export.set_defaults(handler=cmd_schema_export)

    trace = subparsers.add_parser("trace", help="historique des itérations d'un run")
    trace.add_argument("--run", type=Path, required=True)
    trace.add_argument("--json", action="store_true", dest="as_json")
    trace.set_defaults(handler=cmd_trace)
    return parser


def cmd_init(args: argparse.Namespace, console: Console) -> int:
    config_path: Path = args.config
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
        console.print(f"créé : {config_path}", markup=False)
    else:
        console.print(f"conservé : {config_path}", markup=False)
    config = load_config(config_path)
    for relative in (config.paths.runs, config.paths.golden, config.paths.reports):
        resolve_path(config_path, relative).mkdir(parents=True, exist_ok=True)
    written = export_schemas(resolve_path(config_path, "schemas"))
    console.print(f"{len(written)} schémas exportés dans {written[0].parent}", markup=False)
    console.print("Prochaine étape : renseigner knowledge.path dans truthloop.yaml.")
    return 0


def cmd_verify(args: argparse.Namespace, console: Console) -> int:
    config_path: Path = args.config
    config = load_config(config_path)
    knowledge = open_knowledge(
        config.knowledge.kind, resolve_path(config_path, config.knowledge.path), config.knowledge.queries
    )
    verdict = evaluate(RunDir(args.run), config, knowledge, iteration=args.iteration)
    if args.as_json:
        sys.stdout.write(verdict.model_dump_json(indent=2) + "\n")
    else:
        render_verdict(verdict, console)
    return EXIT_CODES[verdict.decision]


def cmd_schema_export(args: argparse.Namespace, console: Console) -> int:
    written = export_schemas(args.out)
    console.print(f"{len(written)} schémas exportés dans {args.out}", markup=False)
    return 0


def cmd_trace(args: argparse.Namespace, console: Console) -> int:
    run = RunDir(args.run)
    run.load_question()
    rows: list[TraceRow] = []
    previous: set[tuple[str, str]] = set()
    for iteration in run.iterations():
        verdict = run.load_verdict(iteration)
        if verdict is None:
            continue
        current: set[tuple[str, str]] = {
            (f.code, f.claim_id or (f.entity.id if f.entity else "")) for f in verdict.findings
        }
        rows.append(
            TraceRow(
                iteration=iteration,
                score=verdict.score,
                decision=verdict.decision,
                open_findings=len(current),
                resolved_findings=len(previous - current),
            )
        )
        previous = current
    if args.as_json:
        sys.stdout.write(json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2) + "\n")
    else:
        render_trace(rows, console)
    return 0
```

- [ ] **Step 5 : Vérifier le succès**

Run: `uv run pytest tests/test_cli.py --no-cov -q`
Expected: `5 passed`. Si le test `test_trace` échoue sur `open_findings == 5`, recompter : l'échantillon produit 2 `MISSING_ENTITY` + 3 `MISSING_TABLE` = 5 findings à l'itération 1 ; l'itération 2 est identique, donc 0 résolu.

- [ ] **Step 6 : Vérifier le script installé**

Run: `uv run truthloop --help`
Expected: l'aide argparse avec les quatre sous-commandes.

- [ ] **Step 7 : Lint**

Run: `uv run ruff format src tests && uv run ruff check src tests && uv run mypy`
Expected: aucune erreur. `args.handler` est `Any` : l'affectation à `handler: Handler` est acceptée par mypy strict (pas d'`Any` explicite).

### Task 22 : Vérification finale de la phase 1

**Files:**
- Modify: `README.md`

- [ ] **Step 1 : Suite complète avec couverture**

Run: `uv run pytest -q`
Expected: tous les tests passent, `Required test coverage of 85% reached`.

- [ ] **Step 2 : Lint et typage complets**

Run: `uv run ruff format src tests && uv run ruff check --fix src tests && uv run mypy`
Expected: aucune erreur (`--fix` ne corrige que les tris d'imports, les autres règles sont déjà satisfaites).

- [ ] **Step 3 : Scénario de bout en bout dans un dossier temporaire**

```bash
cd "$(mktemp -d)" && uv run --project "<chemin du repo>" truthloop init
```

Puis éditer `truthloop.yaml` (`kind: files`, `path: <chemin absolu>/tests/fixtures/graph.json`), créer `runs/demo/question.json` et `runs/demo/iter-01/{answer,evidence,judge}.json` avec exactement le contenu renvoyé par `sample_question()`, `sample_answer()`, `sample_evidence()`, `sample_judge()` de `tests/helpers.py` (par exemple via `uv run --project <repo> python -c "import json, sys; sys.path.insert(0, '<repo>/tests'); from helpers import *; ..."` ou en copiant à la main). Le nom du dossier `demo` n'a pas à correspondre à `question.id` (`q-001`) : aucune vérification n'est faite, c'est voulu. Lancer ensuite :

```bash
uv run --project "<chemin du repo>" truthloop verify --run runs/demo ; echo "exit=$?"
uv run --project "<chemin du repo>" truthloop trace --run runs/demo
```

Expected: `exit=2`, tableau des composantes avec `context_recall 0.50`, plan de réparation à deux actions, puis la trace avec une ligne.

- [ ] **Step 4 : README**

Écrire `README.md` (français) : objectif en trois phrases, installation (`uv sync`), les quatre commandes avec leurs codes retour, le layout `runs/`, un lien vers le spec, une note indiquant que `verify` ouvre la source de connaissance avant de lire le run (une base absente est donc signalée en premier), et une section « Phase 2 : agents Copilot » à venir.

- [ ] **Step 5 : Point de contrôle**

Demander à l'utilisateur s'il souhaite un commit (message proposé : `✨ feat(truthloop): evaluation engine and CLI (phase 1)`), puis proposer d'écrire le plan de la phase 2 (repair loop côté Copilot : agents `.agent.md` et fichier d'instructions).
