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
            "caps": {
                "unknown_entity": 50,
                "contradiction": 70,
                "missing_judge": 85,
                "missing_claims": 85,
            },
            "release_threshold": 90,
            "release_threshold_no_reference": 95,
        },
        "loop": {"max_iterations": 3},
        "paths": {"runs": "runs", "golden": "golden", "reports": "reports"},
    }


def write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
