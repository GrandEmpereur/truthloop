import pytest

from conftest import ContextBuilder
from helpers import sample_answer, sample_evidence, sample_question
from truthloop.graders.evidence import contains_id, grade_evidence


@pytest.mark.parametrize(
    ("text", "entity_id", "expected"),
    [
        ("PRG_ORD_SAVE -> PRG_ORD_VALID (call)", "prg_ord_valid", True),
        ("Appel de PRG-ORD-VALID en tâche 3", "prg_ord_valid", True),
        ("Le programme PRG ORD VALID contrôle…", "prg_ord_valid", True),
        ("PRG-ORD VALID", "prg_ord_valid", True),
        ("PRG - ORD - VALID", "prg_ord_valid", True),
        ("écrit dans T_ORDER_LINES", "t_orders", False),
        ("T ORDERS LINES", "t_orders", True),
        ("rien ici", "prg_ord_valid", False),
        ("", "prg_ord_valid", False),
        ("Voir REL-2026.1 pour le détail", "rel_2026.1", True),
        ("PRG- ORD- VALID", "prg_ord_valid", True),
        ("PRG -ORD -VALID", "prg_ord_valid", True),
        ("t_orders", "t_order_lines", False),
        ("PRG_ORD_VALID_X", "prg_ord_valid", True),  # prefix ids match: documented in spec §6
    ],
)
def test_contains_id(text: str, entity_id: str, expected: bool) -> None:
    assert contains_id(text, entity_id) is expected


def test_sample_is_fully_supported(make_ctx: ContextBuilder) -> None:
    [result] = grade_evidence(make_ctx())
    assert result.component == "evidence_support"
    assert result.value == 1.0
    assert result.findings == ()


def test_dangling_and_unsupported(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        claims=[
            {"id": "c1", "text": "t", "entities": ["PRG_ORD_SAVE"], "citations": ["ev-404"]},
            {"id": "c2", "text": "t", "entities": ["PRG_ORD_NOTIFY"], "citations": ["ev-1"]},
            {"id": "c3", "text": "t", "entities": [], "citations": ["ev-1"]},
            {"id": "c4", "text": "t", "entities": [], "citations": []},
        ]
    )
    [result] = grade_evidence(make_ctx(answer=answer))
    assert result.value == 0.25
    assert [(f.code, f.claim_id) for f in result.findings] == [
        ("DANGLING_CITATION", "c1"),
        ("UNSUPPORTED_CLAIM", "c1"),
        ("UNSUPPORTED_CLAIM", "c2"),
        ("UNSUPPORTED_CLAIM", "c4"),
    ]


def test_empty_claims(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(claims=[])
    [diagram] = grade_evidence(make_ctx(question=sample_question(intent="diagram"), answer=answer))
    assert diagram.value is None
    assert diagram.findings == ()
    assert diagram.cap is None
    [impact] = grade_evidence(make_ctx(answer=answer))
    assert impact.value is None
    assert [f.code for f in impact.findings] == ["NO_CLAIMS"]
    assert impact.cap == "missing_claims"


def test_evidence_without_chunks(make_ctx: ContextBuilder) -> None:
    [result] = grade_evidence(make_ctx(evidence=sample_evidence(chunks=[])))
    assert result.value == 0.0
