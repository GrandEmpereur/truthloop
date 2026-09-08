from conftest import ContextBuilder
from helpers import sample_answer
from truthloop.graders.consistency import grade_consistency


def _claim(subject: str, predicate: str, obj: str) -> dict[str, object]:
    return {
        "id": "c1",
        "text": "t",
        "entities": [subject, obj],
        "citations": ["ev-1"],
        "relation": {"subject": subject, "predicate": predicate, "object": obj},
    }


def test_sample_relation_is_consistent(make_ctx: ContextBuilder) -> None:
    [result] = grade_consistency(make_ctx())
    assert result.component is None
    assert result.findings == ()
    assert result.cap is None


def test_contradicted_relation_caps(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(claims=[_claim("PRG_ORD_VALID", "calls", "PRG_ORD_SAVE")])
    [result] = grade_consistency(make_ctx(answer=answer))
    assert [(f.code, f.severity, f.claim_id) for f in result.findings] == [
        ("CONTRADICTED_BY_GRAPH", "critical", "c1")
    ]
    assert result.cap == "contradiction"


def test_table_predicates(make_ctx: ContextBuilder) -> None:
    ok = sample_answer(claims=[_claim("PRG_ORD_SAVE", "writes", "T_ORDERS")])
    [result] = grade_consistency(make_ctx(answer=ok))
    assert result.findings == ()
    bad = sample_answer(claims=[_claim("PRG_ORD_SAVE", "reads", "T_ORDERS")])
    [result] = grade_consistency(make_ctx(answer=bad))
    assert [f.code for f in result.findings] == ["CONTRADICTED_BY_GRAPH"]


def test_unknown_entities_are_skipped(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        entities=[
            {"type": "program", "id": "PRG_GHOST"},
            {"type": "program", "id": "PRG_ORD_VALID"},
        ],
        claims=[_claim("PRG_GHOST", "calls", "PRG_ORD_VALID")],
        abstentions=[],
    )
    [result] = grade_consistency(make_ctx(answer=answer))
    assert result.findings == ()
