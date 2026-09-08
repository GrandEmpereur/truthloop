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
                "relation": {
                    "subject": "PRG_ORD_SAVE",
                    "predicate": "calls",
                    "object": "PRG_ORD_VALID",
                },
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
    ("patch", "message"),
    [
        (
            {"claims": [{"id": "c1", "text": "t", "entities": ["PRG_UNKNOWN"]}]},
            "not declared in entities",
        ),
        (
            {"abstentions": [{"text": "t", "entities": ["PRG_UNKNOWN"]}]},
            "not declared in entities",
        ),
        (
            {"claims": [{"id": "c1", "text": "t"}, {"id": "c1", "text": "t"}]},
            "duplicate claim id",
        ),
        (
            {
                "claims": [
                    {
                        "id": "c1",
                        "text": "t",
                        "relation": {
                            "subject": "T_ORDERS",
                            "predicate": "calls",
                            "object": "PRG_ORD_VALID",
                        },
                    }
                ]
            },
            "must be a declared program",
        ),
        (
            {
                "claims": [
                    {
                        "id": "c1",
                        "text": "t",
                        "relation": {
                            "subject": "PRG_ORD_SAVE",
                            "predicate": "reads",
                            "object": "PRG_ORD_VALID",
                        },
                    }
                ]
            },
            "must be a declared table",
        ),
        (
            {"claims": [{"id": "c1", "text": "t", "confidence_self": 2}]},
            "less than or equal to 1",
        ),
        ({"iteration": 0}, "greater than or equal to 1"),
    ],
)
def test_answer_rejects_invalid(patch: dict[str, object], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Answer.model_validate(_answer(**patch))


def test_same_id_declared_as_program_and_table_is_two_entities() -> None:
    answer = Answer.model_validate(
        _answer(
            entities=[{"type": "program", "id": "X"}, {"type": "table", "id": "X"}],
            claims=[],
            abstentions=[],
        )
    )
    assert len(answer.entities) == 2
