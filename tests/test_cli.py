import json
from pathlib import Path

import pytest
import yaml

from conftest import FIXTURES, RunBuilder
from helpers import (
    files_config,
    release_answer,
    sample_answer,
    sample_evidence,
    sample_judge,
    sample_question,
)
from truthloop.cli import main


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "truthloop.yaml"
    path.write_text(
        yaml.safe_dump(files_config(FIXTURES / "graph.json"), sort_keys=False), encoding="utf-8"
    )
    return path


def test_argparse_errors_exit_1_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["verify", "--bogus"])
    assert excinfo.value.code == 1
    assert "erreur" in capsys.readouterr().err
    with pytest.raises(SystemExit) as excinfo:
        main(["verify", "--run", "x", "--iteration", "0"])
    assert excinfo.value.code == 1
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "truthloop" in capsys.readouterr().out


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
    make_run(
        None,
        sample_answer(iteration=2),
        sample_evidence(iteration=2),
        sample_judge(iteration=2),
        iteration=2,
    )
    main(["verify", "--run", str(run_dir), "--config", str(config_path), "--iteration", "1"])
    main(["verify", "--run", str(run_dir), "--config", str(config_path), "--iteration", "2"])
    (run_dir / "iter-03").mkdir()
    capsys.readouterr()
    assert main(["trace", "--run", str(run_dir), "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert [r["iteration"] for r in rows] == [1, 2, 3]
    assert rows[0]["open_findings"] == 5
    assert rows[0]["resolved_findings"] == 0
    assert rows[1]["open_findings"] == 5
    assert rows[1]["resolved_findings"] == 0
    assert rows[2] == {
        "iteration": 3,
        "score": None,
        "decision": None,
        "open_findings": 0,
        "resolved_findings": 0,
    }
    assert main(["trace", "--run", str(run_dir)]) == 0
    assert "repair" in capsys.readouterr().out
