"""Install the Copilot kit into a target repository (spec phase 2 §4, §9)."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Final, Literal

import yaml
from pydantic import ValidationError

from truthloop.config import DEFAULT_CONFIG_YAML, Config, ConfigError, load_config
from truthloop.contracts.schemas import export_schemas

KnowledgeKind = Literal["sqlite", "files"]
Status = Literal["créé", "conservé", "remplacé"]

_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
_RETRIEVERS_TOKEN: Final = "'{{RETRIEVER_AGENTS}}'"
_RETRIEVER_NAME = re.compile(r"[A-Za-z0-9._-]+")
_KIT: Final = "truthloop.integration.copilot"

# (resource path inside the kit, destination relative to the target, substitute placeholders?)
_TEMPLATES: Final[tuple[tuple[str, str, bool], ...]] = (
    (
        "agents/truthloop-orchestrator.agent.md",
        ".github/agents/truthloop-orchestrator.agent.md",
        True,
    ),
    ("agents/truthloop-judge.agent.md", ".github/agents/truthloop-judge.agent.md", True),
    (
        "instructions/truthloop-contract.instructions.md",
        ".github/instructions/truthloop-contract.instructions.md",
        True,
    ),
    ("prompts/truthloop-install.prompt.md", ".github/prompts/truthloop-install.prompt.md", True),
    ("ACCEPTANCE.md", ".github/truthloop/ACCEPTANCE.md", True),
    ("smoke/graph.json", ".github/truthloop/smoke/graph.json", False),
    ("smoke/truthloop.yaml", ".github/truthloop/smoke/truthloop.yaml", False),
    ("smoke/run/question.json", "runs/smoke/question.json", False),
    ("smoke/run/iter-01/answer.json", "runs/smoke/iter-01/answer.json", False),
    ("smoke/run/iter-01/evidence.json", "runs/smoke/iter-01/evidence.json", False),
    ("smoke/run/iter-01/judge.json", "runs/smoke/iter-01/judge.json", False),
)

_PROMPT_RESOURCE: Final = "prompts/truthloop-install.prompt.md"
_MIN_FRONTMATTER_PARTS: Final = 3


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
        raise InstallError(
            "--knowledge attend la forme kind:chemin (ex. sqlite:knowledge/magic.db)"
        )
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


def _check_no_unknown_placeholders(content: str, resource: str) -> None:
    remainder = content.replace(_RETRIEVERS_TOKEN, "")
    if "{{" in remainder:
        raise InstallError(f"placeholder inconnu dans {resource}")


def install_copilot(
    target: Path, knowledge: KnowledgeSpec | None, retrievers: Sequence[str], *, force: bool
) -> list[InstallResult]:
    root = project_root()
    for name in retrievers:
        if not _RETRIEVER_NAME.fullmatch(name):
            raise InstallError(
                f"nom de retriever invalide : {name!r} (lettres, chiffres, . _ - seulement)"
            )
    if not target.is_dir():
        raise InstallError(f"--target doit être un dossier existant : {target}")
    target = target.resolve()

    config_path = target / "truthloop.yaml"
    config, new_config_content = _prepare_config(config_path, knowledge)
    values = {
        "TRUTHLOOP_PROJECT": root.as_posix().rstrip("/"),
        "MAX_ITERATIONS": str(config.loop.max_iterations),
    }
    if not retrievers:
        retrievers = _wired_retrievers(
            target / ".github" / "agents" / "truthloop-orchestrator.agent.md"
        )

    kit = resources.files(_KIT)
    rendered: list[tuple[str, str]] = []
    for resource, destination, substitute in _TEMPLATES:
        content = (kit / resource).read_text(encoding="utf-8")
        if substitute:
            # The install prompt must keep the retrievers token verbatim: it tells Copilot what to replace.
            content = render(content, values, [] if resource == _PROMPT_RESOURCE else retrievers)
            if resource != _PROMPT_RESOURCE:
                _check_no_unknown_placeholders(content, resource)
        rendered.append((destination, content))

    results: list[InstallResult] = []
    if new_config_content is not None:
        config_path.write_text(new_config_content, encoding="utf-8", newline="\n")
        results.append(InstallResult(config_path, "créé"))
    else:
        results.append(InstallResult(config_path, "conservé"))
    if force:
        shutil.rmtree(target / "runs" / "smoke", ignore_errors=True)
    for destination, content in rendered:
        results.append(_write(target / destination, content, force))
    results.extend(_write_schemas(target / ".github" / "truthloop" / "schemas", force))
    results.append(_write(target / "runs" / ".gitkeep", "", force))
    return results


def _wired_retrievers(orchestrator_path: Path) -> list[str]:
    """Retriever names already wired in an installed orchestrator (kept across ``--force``)."""
    if not orchestrator_path.is_file():
        return []
    text = orchestrator_path.read_text(encoding="utf-8")
    parts = text.split("---\n")
    if len(parts) < _MIN_FRONTMATTER_PARTS:
        return []
    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return []
    if not isinstance(frontmatter, dict):
        return []
    agents = frontmatter.get("agents")
    if not isinstance(agents, list) or not all(isinstance(name, str) for name in agents):
        return []
    return [name for name in agents if name != "truthloop-judge" and not name.startswith("{{")]


def _prepare_config(
    config_path: Path, knowledge: KnowledgeSpec | None
) -> tuple[Config, str | None]:
    """Validate the config to write, without writing it.

    Returns the effective ``Config`` (existing, or about to be created) and, when the
    file still needs to be created, the YAML text to write — ``None`` when it already
    exists and is kept untouched ("conservé").
    """
    if config_path.exists():
        try:
            return load_config(config_path), None
        except ConfigError as exc:
            raise InstallError(
                f"truthloop.yaml invalide dans {config_path.parent} : {exc}"
            ) from exc
    if knowledge is None:
        raise InstallError("--knowledge est requis quand truthloop.yaml n'existe pas encore")
    content = DEFAULT_CONFIG_YAML.replace(
        "  kind: sqlite\n", f"  kind: {knowledge.kind}\n", 1
    ).replace("  path: knowledge/magic.db\n", f"  path: {json.dumps(knowledge.path)}\n", 1)
    try:
        config = Config.model_validate(yaml.safe_load(content))
    except (ValidationError, yaml.YAMLError) as exc:
        raise InstallError(f"--knowledge produit une configuration invalide : {exc}") from exc
    if config.knowledge.path != knowledge.path or config.knowledge.kind != knowledge.kind:
        raise InstallError(
            f"--knowledge produit une configuration invalide : "
            f"knowledge.path={config.knowledge.path!r}, knowledge.kind={config.knowledge.kind!r}"
        )
    return config, content


def _write(path: Path, content: str, force: bool) -> InstallResult:
    exists = path.exists()
    if exists and not force:
        return InstallResult(path, "conservé")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return InstallResult(path, "remplacé" if exists else "créé")


def _write_schemas(out_dir: Path, force: bool) -> list[InstallResult]:
    with tempfile.TemporaryDirectory() as staging_dir:
        written = export_schemas(Path(staging_dir))
        return [
            _write(out_dir / path.name, path.read_text(encoding="utf-8"), force) for path in written
        ]
