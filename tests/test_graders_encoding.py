from conftest import ContextBuilder
from helpers import sample_answer
from truthloop.graders.encoding import grade_encoding


def test_clean_utf8_text_has_no_finding(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        final_text="Ihm:163 est appelé par Ihm:2 ; portée directe, tâches internes."
    )
    [result] = grade_encoding(make_ctx(answer=answer))
    assert result.component is None
    assert result.value is None
    assert result.cap is None
    assert result.findings == ()


def test_double_encoded_final_text_is_critical(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        final_text="Aucune action de table n'est publiÃ©e pour Ihm:163 lui-mÃªme."
    )
    [result] = grade_encoding(make_ctx(answer=answer))
    [finding] = result.findings
    assert finding.code == "MOJIBAKE"
    assert finding.severity == "critical"
    assert finding.claim_id is None
    assert "final_text" in finding.detail
    assert result.cap is None


def test_mojibake_in_claims_and_abstentions_is_located(make_ctx: ContextBuilder) -> None:
    answer = sample_answer(
        claims=[
            {
                "id": "c1",
                "text": "PRG_ORD_SAVE appelle PRG_ORD_VALID.",
                "entities": ["PRG_ORD_SAVE", "PRG_ORD_VALID"],
                "citations": ["ev-1"],
            },
            {
                "id": "c2",
                "text": "PRG_ORD_NOTIFY lit T_ORDERS (donnÃ©es).",
                "entities": ["PRG_ORD_NOTIFY", "T_ORDERS"],
                "citations": ["ev-2"],
            },
        ],
        abstentions=[{"text": "Profondeur 2 non explorÃ©e.", "entities": []}],
        final_text="Texte propre.",
    )
    [result] = grade_encoding(make_ctx(answer=answer))
    assert [(f.code, f.claim_id) for f in result.findings] == [
        ("MOJIBAKE", "c2"),
        ("MOJIBAKE", None),
    ]
    assert "abstention" in result.findings[1].detail


def test_embedded_bom_and_euro_sign_sequences_are_detected(make_ctx: ContextBuilder) -> None:
    for text in ("\ufeffTexte", "Il a dit â€œoui â€", "TempÃ©rature 20Â°C"):
        [result] = grade_encoding(make_ctx(answer=sample_answer(final_text=text)))
        assert [f.code for f in result.findings] == ["MOJIBAKE"], text


def test_legitimate_accented_and_polish_text_is_not_flagged(make_ctx: ContextBuilder) -> None:
    for text in ("Zażółć gęślą jaźń", "Ângela e João", "Prix : 20 € — 30 °C", "naïve façade"):
        [result] = grade_encoding(make_ctx(answer=sample_answer(final_text=text)))
        assert result.findings == (), text
