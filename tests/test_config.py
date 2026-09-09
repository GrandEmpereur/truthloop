from pathlib import Path

import pytest

from truthloop.config import (
    DEFAULT_CONFIG_YAML,
    Config,
    ConfigError,
    config_sha256,
    load_config,
    resolve_path,
)


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
        (
            "  weights: {context_recall: 0, table_recall: 0, evidence_support: 0, faithfulness: 0, relevance_completeness: 0}\n",
            "weights",
        ),
    ],
)
def test_invalid_scoring_is_rejected(tmp_path: Path, patch: str, message: str) -> None:
    text = DEFAULT_CONFIG_YAML.replace(
        "  release_threshold: 90\n",
        patch if "threshold" in patch else "  release_threshold: 90\n" + patch,
    )
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


def test_config_with_invalid_encoding_is_illisible(tmp_path: Path) -> None:
    path = tmp_path / "truthloop.yaml"
    path.write_bytes(b"\xff\xfe{")
    with pytest.raises(ConfigError, match="illisible"):
        load_config(path)


def test_resolve_path_is_relative_to_config(tmp_path: Path) -> None:
    config_path = tmp_path / "sub" / "truthloop.yaml"
    assert (
        resolve_path(config_path, "knowledge/magic.db")
        == tmp_path / "sub" / "knowledge" / "magic.db"
    )
    assert resolve_path(config_path, str(tmp_path / "abs.db")) == tmp_path / "abs.db"


def test_unreadable_and_unknown_query_keys(tmp_path: Path) -> None:
    path = tmp_path / "truthloop.yaml"
    path.write_text(
        DEFAULT_CONFIG_YAML.replace("  queries: {}\n", "  queries: {callss: 'SELECT 1'}\n"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="clés inconnues"):
        load_config(path)
    path.write_text(
        DEFAULT_CONFIG_YAML.replace("  path: knowledge/magic.db\n", "  path: '   '\n"),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="vide"):
        load_config(path)
    directory = tmp_path / "dir.yaml"
    directory.mkdir()
    with pytest.raises(ConfigError, match=r"illisible|introuvable"):
        load_config(directory)


def test_config_with_bom_loads(tmp_path: Path) -> None:
    path = tmp_path / "truthloop.yaml"
    path.write_bytes(b"\xef\xbb\xbf" + DEFAULT_CONFIG_YAML.encode("utf-8"))
    assert load_config(path).loop.max_iterations == 3
