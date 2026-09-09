"""truthloop.yaml loading and validation (spec §8.3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final, Literal, Self

import yaml
from pydantic import Field, ValidationError, model_validator

from truthloop.contracts.bundle import errors_from
from truthloop.contracts.common import SchemaVersion, StrictModel
from truthloop.contracts.verdict import CAP_NAMES, COMPONENT_NAMES
from truthloop.knowledge.sqlite import DEFAULT_QUERIES

_MAX_PERCENT: Final = 100


class ConfigError(Exception):
    """Configuration missing or invalid (exit code 1)."""


class KnowledgeConfig(StrictModel):
    kind: Literal["sqlite", "files"]
    path: str = Field(min_length=1)
    queries: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.path.strip():
            raise ValueError("knowledge.path vide")
        unknown = set(self.queries) - set(DEFAULT_QUERIES)
        if unknown:
            raise ValueError(f"knowledge.queries : clés inconnues {sorted(unknown)}")
        return self


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
    runs: str = Field(default="runs", min_length=1)
    golden: str = Field(default="golden", min_length=1)
    reports: str = Field(default="reports", min_length=1)


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
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, ValueError) as exc:
        raise ConfigError(f"configuration illisible ({path}) : {exc}") from exc
    try:
        data: object = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML invalide ({path}) : {exc}") from exc
    if data is None:
        raise ConfigError(f"configuration vide : {path}")
    try:
        return Config.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(f"{e.loc}: {e.msg}" for e in errors_from(exc, "config"))
        raise ConfigError(f"configuration invalide ({path}) : {details}") from exc


def config_sha256(config: Config) -> str:
    canonical = json.dumps(
        config.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def resolve_path(config_path: Path, relative: str) -> Path:
    path = Path(relative)
    return path if path.is_absolute() else config_path.parent / path
