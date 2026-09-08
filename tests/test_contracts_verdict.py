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


def test_verdict_requires_all_components() -> None:
    complete = {
        name: Component(value=None, weight=0.2, applicable=False) for name in COMPONENT_NAMES
    }
    base = {
        "question_id": "q",
        "iteration": 1,
        "score": 0.0,
        "decision": "invalid",
        "threshold": 90.0,
        "repair_plan": RepairPlan(),
        "provenance": _provenance(),
    }
    Verdict(components=complete, **base)  # type: ignore[arg-type]
    missing = dict(complete)
    del missing["faithfulness"]
    with pytest.raises(ValidationError, match="components"):
        Verdict(components=missing, **base)  # type: ignore[arg-type]
    extra = {**complete, "bonus": Component(value=None, weight=0.0, applicable=False)}
    with pytest.raises(ValidationError, match="components"):
        Verdict(components=extra, **base)  # type: ignore[arg-type]


def test_export_schemas_writes_six_files(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)
    names = sorted(p.name for p in written)
    assert names == sorted(f"{name}.schema.json" for name in CONTRACTS)
    assert set(CONTRACTS) == {"question", "answer", "evidence", "judge", "verdict", "repair_plan"}
    schema = json.loads((tmp_path / "answer.schema.json").read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    raw = (tmp_path / "answer.schema.json").read_text(encoding="utf-8")
    assert raw.count('"description"') >= 10
