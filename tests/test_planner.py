from truthloop.contracts.common import EntityRef
from truthloop.contracts.repair_plan import ContractError
from truthloop.contracts.verdict import COMPONENT_NAMES, CapApplied, Component, Finding
from truthloop.planner import PlannerInput, build_plan

WEIGHTS = {
    "context_recall": 0.35,
    "table_recall": 0.15,
    "evidence_support": 0.15,
    "faithfulness": 0.25,
    "relevance_completeness": 0.10,
}


def _components(**values: float) -> dict[str, Component]:
    return {
        name: Component(value=values.get(name), weight=WEIGHTS[name], applicable=name in values)
        for name in COMPONENT_NAMES
    }


def _missing(kind: str, entity_id: str, via: str, depth: int | None = None) -> Finding:
    code = "MISSING_ENTITY" if kind == "program" else "MISSING_TABLE"
    return Finding.model_validate(
        {
            "code": code,
            "severity": "major",
            "detail": "x",
            "entity": {"type": kind, "id": entity_id},
            "via": via,
            "depth": depth,
        }
    )


def _input(**patch: object) -> PlannerInput:
    base: dict[str, object] = {
        "decision": "repair",
        "score": 69.25,
        "raw": 69.25,
        "findings": [],
        "caps_applied": [],
        "weights": WEIGHTS,
        "components": _components(
            context_recall=0.5,
            table_recall=0.25,
            evidence_support=1.0,
            faithfulness=1.0,
            relevance_completeness=0.8,
        ),
        "claim_entities": {
            "c1": ["prg_ord_save", "prg_ord_valid"],
            "c2": ["prg_ord_notify", "prg_ord_valid"],
        },
        "pivot_ids": ["prg_ord_valid"],
        "direction": "both",
        "depth": 1,
    }
    return PlannerInput(**{**base, **patch})  # type: ignore[arg-type]


def test_release_gives_empty_plan() -> None:
    plan = build_plan(
        _input(decision="release", score=99.0, raw=99.0, findings=[_missing("program", "x", "p")])
    )
    assert plan.actions == []
    assert plan.summary_for_agent == ""


def test_contract_errors_give_single_fix_contract() -> None:
    errors = [ContractError(loc="answer", msg="fichier manquant")]
    plan = build_plan(_input(decision="invalid", score=0.0, raw=0.0, contract_errors=errors))
    [action] = plan.actions
    assert (action.kind, action.priority, action.expected_gain) == ("fix_contract", 1, 100.0)
    assert action.errors == errors
    assert "1 erreur(s) de contrat" in plan.summary_for_agent


def test_missing_programs_and_tables_become_retrieve_actions() -> None:
    findings = [
        _missing("program", "prg_cust_load", "prg_ord_valid", 1),
        _missing("program", "prg_inv_check", "prg_ord_valid", 1),
        _missing("table", "t_customers", "prg_cust_load"),
        _missing("table", "t_order_lines", "prg_ord_save"),
        _missing("table", "t_stock", "prg_inv_check"),
    ]
    plan = build_plan(_input(findings=findings, expected_programs=4, expected_tables=4))
    programs, tables = plan.actions
    assert (programs.id, programs.kind, programs.priority, programs.expected_gain) == (
        "a1",
        "retrieve_entities",
        1,
        17.5,
    )
    assert [e.id for e in programs.entities] == ["prg_cust_load", "prg_inv_check"]
    assert programs.entities[0].depth == 1
    assert programs.entities[0].via == "prg_ord_valid"
    assert programs.queries is not None
    assert "prg_ord_valid" in programs.queries.graph
    assert programs.queries.rag == "prg_cust_load prg_inv_check"
    assert (tables.kind, tables.priority, tables.expected_gain) == ("retrieve_entities", 2, 11.25)
    assert [e.type for e in tables.entities] == ["table", "table", "table"]
    assert plan.summary_for_agent == (
        "Rappel 0.50 : 2 programme(s) manquant(s) (prg_cust_load, prg_inv_check). "
        "3 table(s) manquante(s) (t_customers, t_order_lines, t_stock)."
    )


def test_claim_findings_are_grouped_and_cap_bonus_goes_to_last_gate_finding() -> None:
    ghost = EntityRef(type="program", id="prg_ghost")
    findings = [
        Finding(code="UNKNOWN_ENTITY", severity="critical", detail="x", entity=ghost),
        Finding(code="UNSUPPORTED_CLAIM", severity="major", detail="x", claim_id="c1"),
        Finding(code="JUDGE_PARTIAL", severity="info", detail="x", claim_id="c2"),
    ]
    plan = build_plan(
        _input(
            findings=findings,
            raw=80.0,
            score=50.0,
            caps_applied=[CapApplied(name="unknown_entity", value=50)],
            claim_entities={"c1": ["prg_ghost"], "c2": ["prg_ord_valid"]},
        )
    )
    first, second = plan.actions
    assert (first.kind, first.claim_ids, first.expected_gain) == ("verify_claim", ["c1"], 50.0)
    assert [e.id for e in first.entities] == ["prg_ghost"]
    assert "corriger l'identifiant" in first.instruction
    assert (second.kind, second.claim_ids, second.expected_gain) == ("verify_claim", ["c2"], 20.0)
    assert plan.summary_for_agent == "2 claim(s) à vérifier (c1, c2)."


def test_orphan_unknown_entity() -> None:
    ghost = EntityRef(type="table", id="t_ghost")
    findings = [Finding(code="UNKNOWN_ENTITY", severity="critical", detail="x", entity=ghost)]
    plan = build_plan(
        _input(
            findings=findings,
            raw=90.0,
            score=50.0,
            caps_applied=[CapApplied(name="unknown_entity", value=50)],
        )
    )
    [action] = plan.actions
    assert action.kind == "verify_claim"
    assert action.claim_ids == []
    assert [e.id for e in action.entities] == ["t_ghost"]
    assert action.expected_gain == 40.0


def test_structural_actions() -> None:
    pivot = EntityRef(type="program", id="prg_ghost")
    findings = [
        Finding(code="UNKNOWN_PIVOT", severity="critical", detail="x", entity=pivot),
        Finding(code="JUDGE_MISSING", severity="major", detail="x"),
        Finding(code="NO_CLAIMS", severity="major", detail="x"),
    ]
    plan = build_plan(_input(findings=findings, score=40.0, raw=60.0, claim_entities={}))
    kinds = [(a.kind, a.expected_gain) for a in plan.actions]
    assert kinds == [("fix_question", 60.0), ("write_claims", 60.0), ("run_judge", 35.0)]
    assert plan.actions[0].entities[0].id == "prg_ghost"


def test_fallback_improve_answer_targets_lowest_component() -> None:
    plan = build_plan(_input(findings=[], score=94.0, raw=94.0, judge_notes=""))
    [action] = plan.actions
    assert (action.kind, action.component, action.expected_gain) == (
        "improve_answer",
        "table_recall",
        6.0,
    )
    with_notes = build_plan(
        _input(findings=[], score=94.0, raw=94.0, judge_notes="Couvrir les tables écrites.")
    )
    assert with_notes.actions[0].instruction == "Couvrir les tables écrites."


def test_non_release_always_has_an_action() -> None:
    for decision in ("repair", "escalate", "invalid"):
        plan = build_plan(_input(decision=decision, findings=[]))
        assert len(plan.actions) >= 1


def test_summary_keeps_three_families_and_zero_expected_is_safe() -> None:
    findings = [
        Finding(code="JUDGE_MISSING", severity="major", detail="x"),
        _missing("program", "prg_x", "p", 1),
        _missing("table", "t_x", "p"),
        Finding(code="UNSUPPORTED_CLAIM", severity="major", detail="x", claim_id="c1"),
    ]
    plan = build_plan(_input(findings=findings, expected_programs=0, expected_tables=0))
    assert len(plan.actions) == 4
    # "Rappel 0.50" and "judge.json" each contain an internal period, so a raw "."
    # count does not track sentence count here; split on ". " (period + space) instead,
    # which only matches actual sentence boundaries in this deterministic output.
    assert len(plan.summary_for_agent.split(". ")) == 3
    assert all(a.expected_gain >= 0 for a in plan.actions)
