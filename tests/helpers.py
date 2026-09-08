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
                "relation": {
                    "subject": "PRG_ORD_SAVE",
                    "predicate": "calls",
                    "object": "PRG_ORD_VALID",
                },
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
            {
                "id": "ev-1",
                "source": "graph:calls",
                "text": "PRG_ORD_SAVE -> PRG_ORD_VALID (call)",
                "score": 0.9,
            },
            {
                "id": "ev-2",
                "source": "graph:calls",
                "text": "PRG_ORD_NOTIFY calls PRG-ORD-VALID",
                "score": 0.8,
            },
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
