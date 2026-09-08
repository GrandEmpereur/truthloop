import pytest
from pydantic import ValidationError

from truthloop.contracts.common import EntityRef, normalize_id


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("PRG_ORD_VALID", "prg_ord_valid"),
        ("  PRG-ORD  VALID ", "prg_ord_valid"),
        ("prg__ord-_valid", "prg_ord_valid"),
        ("T ORDERS", "t_orders"),
        ("-", "_"),
    ],
)
def test_normalize_id(raw: str, expected: str) -> None:
    assert normalize_id(raw) == expected


def test_entity_ref_normalizes_and_hashes() -> None:
    a = EntityRef(type="program", id="PRG-ORD-VALID")
    b = EntityRef(type="program", id="prg_ord_valid")
    assert a.id == "prg_ord_valid"
    assert a == b
    assert len({a, b}) == 1


def test_entity_ref_rejects_blank_and_unknown_type() -> None:
    with pytest.raises(ValidationError):
        EntityRef(type="program", id="   ")
    with pytest.raises(ValidationError):
        EntityRef.model_validate({"type": "module", "id": "x"})


def test_entity_ref_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        EntityRef.model_validate({"type": "program", "id": "x", "name": "y"})
