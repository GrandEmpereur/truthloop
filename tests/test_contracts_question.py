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
