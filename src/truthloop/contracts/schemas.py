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
        path.write_text(
            json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written
