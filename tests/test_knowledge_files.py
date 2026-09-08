import csv
import json
from pathlib import Path

import pytest

from truthloop.contracts.common import EntityRef
from truthloop.knowledge import KnowledgeError
from truthloop.knowledge.factory import open_knowledge
from truthloop.knowledge.files import load_files

FIXTURE = Path(__file__).parent / "fixtures" / "graph.json"


def test_load_json_file_and_directory(tmp_path: Path) -> None:
    direct = load_files(FIXTURE)
    (tmp_path / "graph.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    from_dir = load_files(tmp_path)
    assert direct.fingerprint() == from_dir.fingerprint()
    assert direct.resolve("T_ORDERS", "table") == EntityRef(type="table", id="t_orders")


def test_load_csv_directory(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for name in ("programs", "tables", "calls", "program_tables"):
        rows = data[name]
        with (tmp_path / f"{name}.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    graph = load_files(tmp_path)
    assert graph.has_docs() is False
    valid = EntityRef(type="program", id="prg_ord_valid")
    assert {e.id for e in graph.neighbors(valid, "callees", 1)} == {
        "prg_cust_load",
        "prg_inv_check",
    }


def test_invalid_inputs_raise(tmp_path: Path) -> None:
    with pytest.raises(KnowledgeError, match="introuvable"):
        load_files(tmp_path / "missing")
    (tmp_path / "graph.json").write_text('{"programs": []}', encoding="utf-8")
    with pytest.raises(KnowledgeError, match=r"graph\.json"):
        load_files(tmp_path)
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(KnowledgeError, match=r"programs\.csv"):
        load_files(empty)


def test_open_knowledge_dispatch(sqlite_path: Path) -> None:
    assert open_knowledge("files", FIXTURE, {}).has_docs()
    assert open_knowledge("sqlite", sqlite_path, {}).has_docs()
    with pytest.raises(KnowledgeError):
        open_knowledge("neo4j", FIXTURE, {})


def test_csv_with_bom_and_short_rows(tmp_path: Path) -> None:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for name in ("programs", "tables", "calls", "program_tables"):
        rows = data[name]
        with (tmp_path / f"{name}.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    assert load_files(tmp_path).has_docs() is False
    (tmp_path / "calls.csv").write_text("caller_id,callee_id\nPRG_MAIN_MENU\n", encoding="utf-8")
    with pytest.raises(KnowledgeError, match="vide"):
        load_files(tmp_path)
