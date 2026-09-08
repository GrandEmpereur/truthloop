"""Repair planner: findings → prioritized actions for the orchestrator (spec §7)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, cast

from truthloop.contracts.common import ComponentName, Direction
from truthloop.contracts.repair_plan import (
    ActionKind,
    ContractError,
    RepairAction,
    RepairEntity,
    RepairPlan,
    RetrievalQueries,
)
from truthloop.contracts.verdict import CapApplied, Component, Decision, Finding

_SEVERITY_RANK: Final[dict[str, int]] = {"critical": 3, "major": 2, "info": 1}
_GATE_CODES: Final[dict[str, frozenset[str]]] = {
    "unknown_entity": frozenset({"UNKNOWN_ENTITY", "UNKNOWN_PIVOT"}),
    "contradiction": frozenset({"CONTRADICTED_BY_GRAPH", "CONTRADICTED_BY_EVIDENCE"}),
    "missing_judge": frozenset({"JUDGE_MISSING"}),
    "missing_claims": frozenset({"NO_CLAIMS"}),
}
_CLAIM_CODES: Final[frozenset[str]] = frozenset(
    {
        "UNSUPPORTED_CLAIM",
        "DANGLING_CITATION",
        "CONTRADICTED_BY_GRAPH",
        "CONTRADICTED_BY_EVIDENCE",
        "JUDGE_INCOMPLETE",
        "JUDGE_UNSUPPORTED",
        "JUDGE_PARTIAL",
    }
)
_CLAIM_HINTS: Final[dict[str, str]] = {
    "UNSUPPORTED_CLAIM": "trouver une évidence ou retirer la claim",
    "DANGLING_CITATION": "remplacer les citations introuvables",
    "CONTRADICTED_BY_GRAPH": "la relation affirmée est contredite par le graphe, reformuler ou retirer",
    "CONTRADICTED_BY_EVIDENCE": "la claim est contredite par l'évidence, reformuler ou retirer",
    "JUDGE_INCOMPLETE": "faire juger la claim",
    "JUDGE_UNSUPPORTED": "le juge ne trouve pas de support, renforcer l'évidence ou retirer",
    "JUDGE_PARTIAL": "préciser la claim pour qu'elle soit entièrement supportée",
    "UNKNOWN_ENTITY": "entité inconnue du graphe, corriger l'identifiant ou retirer",
}
_COMPONENT_HINTS: Final[dict[str, str]] = {
    "context_recall": "Élargir la recherche des programmes appelants et appelés autour des pivots.",
    "table_recall": "Lister les tables lues et écrites par chaque programme cité.",
    "evidence_support": "Appuyer chaque claim sur un chunk qui nomme explicitement ses entités.",
    "faithfulness": "Reformuler les claims pour qu'elles soient entièrement supportées par l'évidence.",
    "relevance_completeness": "Recentrer la réponse sur la question et couvrir les points manquants.",
}
_DIRECTION_LABEL: Final[dict[Direction, str]] = {
    "callers": "appelants",
    "callees": "appelés",
    "both": "appelants et appelés",
}
_SUMMARY_LIMIT: Final = 3


@dataclass(frozen=True)
class PlannerInput:
    """Everything the planner needs. ``claim_entities`` must list every claim (even without
    entities): its length is the ``total_claims`` denominator of spec §7."""

    decision: Decision
    score: float
    raw: float
    findings: Sequence[Finding]
    caps_applied: Sequence[CapApplied]
    weights: Mapping[str, float]
    components: Mapping[str, Component]
    contract_errors: Sequence[ContractError] = ()
    expected_programs: int = 0
    expected_tables: int = 0
    claim_entities: Mapping[str, Sequence[str]] = field(default_factory=dict)
    pivot_ids: Sequence[str] = ()
    direction: Direction = "both"
    depth: int = 1
    judge_notes: str = ""


@dataclass
class _Candidate:
    kind: ActionKind
    severity: int
    gain: float
    instruction: str
    keys: set[tuple[str, str]] = field(default_factory=set)
    entities: list[RepairEntity] = field(default_factory=list)
    queries: RetrievalQueries | None = None
    claim_ids: list[str] = field(default_factory=list)
    component: ComponentName | None = None
    order: int = 0
    family: str = ""


def build_plan(inp: PlannerInput) -> RepairPlan:
    if inp.decision == "release":
        return RepairPlan()
    if inp.contract_errors:
        action = RepairAction(
            id="a1",
            kind="fix_contract",
            priority=1,
            expected_gain=100.0,
            instruction="Corriger les erreurs de contrat listées dans errors, puis relancer verify.",
            errors=list(inp.contract_errors),
        )
        summary = (
            f"{len(inp.contract_errors)} erreur(s) de contrat à corriger avant toute évaluation."
        )
        return RepairPlan(actions=[action], summary_for_agent=summary)
    candidates = [*_structural_candidates(inp), *_claim_candidates(inp)]
    if not candidates:
        candidates = [_fallback(inp)]
    for index, candidate in enumerate(candidates):
        candidate.order = index
    _apply_cap_bonus(candidates, inp)
    ordered = sorted(candidates, key=lambda c: (-c.severity, -c.gain, c.kind, c.order))
    actions = [
        _to_action(candidate, priority) for priority, candidate in enumerate(ordered, start=1)
    ]
    return RepairPlan(actions=actions, summary_for_agent=_summary(ordered, inp))


def _finding_key(finding: Finding) -> tuple[str, str]:
    if finding.claim_id is not None:
        return ("claim", finding.claim_id)
    if finding.entity is not None:
        return ("entity", finding.entity.id)
    return ("code", finding.code)


def _keys(findings: Sequence[Finding]) -> set[tuple[str, str]]:
    return {_finding_key(f) for f in findings}


def _entities(findings: Sequence[Finding]) -> list[RepairEntity]:
    return [
        RepairEntity(type=f.entity.type, id=f.entity.id, depth=f.depth, via=f.via)
        for f in findings
        if f.entity is not None
    ]


def _structural_candidates(inp: PlannerInput) -> list[_Candidate]:
    by_code: dict[str, list[Finding]] = defaultdict(list)
    for finding in inp.findings:
        by_code[finding.code].append(finding)
    total_weight = sum(inp.weights.values())
    out: list[_Candidate] = []
    if by_code["UNKNOWN_PIVOT"]:
        out.append(
            _Candidate(
                kind="fix_question",
                severity=_SEVERITY_RANK["critical"],
                gain=100.0 - inp.score,
                instruction="Pivot inconnu du graphe : corriger l'identifiant dans question.json puis relancer.",
                keys=_keys(by_code["UNKNOWN_PIVOT"]),
                entities=_entities(by_code["UNKNOWN_PIVOT"]),
                family="fix_question",
            )
        )
    if by_code["JUDGE_MISSING"]:
        gain = (
            100.0
            * (inp.weights["faithfulness"] + inp.weights["relevance_completeness"])
            / total_weight
        )
        out.append(
            _Candidate(
                kind="run_judge",
                severity=_SEVERITY_RANK["major"],
                gain=gain,
                instruction="Produire judge.json (rubrique claim par claim) puis relancer verify.",
                keys=_keys(by_code["JUDGE_MISSING"]),
                family="run_judge",
            )
        )
    out.extend(
        _retrieve_candidates(inp, by_code["MISSING_ENTITY"], by_code["MISSING_TABLE"], total_weight)
    )
    if by_code["NO_CLAIMS"]:
        out.append(
            _Candidate(
                kind="write_claims",
                severity=_SEVERITY_RANK["major"],
                gain=100.0 - inp.score,
                instruction="Rédiger des claims citées (entités + citations) pour les entités présentes dans answer.entities.",
                keys=_keys(by_code["NO_CLAIMS"]),
                family="write_claims",
            )
        )
    return out


def _retrieve_candidates(
    inp: PlannerInput, programs: list[Finding], tables: list[Finding], total_weight: float
) -> list[_Candidate]:
    out: list[_Candidate] = []
    if programs:
        ids = [f.entity.id for f in programs if f.entity is not None]
        gain = (
            100.0
            * inp.weights["context_recall"]
            * len(ids)
            / max(inp.expected_programs, 1)
            / total_weight
        )
        pivots = ", ".join(inp.pivot_ids) or "les pivots"
        graph_query = (
            f"Lister les {_DIRECTION_LABEL[inp.direction]} de {pivots} jusqu'à la profondeur {inp.depth}, "
            f"inclure {', '.join(ids)}."
        )
        out.append(
            _Candidate(
                kind="retrieve_entities",
                severity=_SEVERITY_RANK["major"],
                gain=gain,
                instruction="Citer chaque programme trouvé dans answer.entities et appuyer chaque claim par un chunk.",
                keys=_keys(programs),
                entities=_entities(programs),
                queries=RetrievalQueries(graph=graph_query, rag=" ".join(ids)),
                family="retrieve:program",
            )
        )
    if tables:
        ids = [f.entity.id for f in tables if f.entity is not None]
        gain = (
            100.0
            * inp.weights["table_recall"]
            * len(ids)
            / max(inp.expected_tables, 1)
            / total_weight
        )
        users = (
            ", ".join(sorted({f.via for f in tables if f.via is not None}))
            or "les programmes cités"
        )
        graph_query = f"Lister les tables lues et écrites par {users}, inclure {', '.join(ids)}."
        out.append(
            _Candidate(
                kind="retrieve_entities",
                severity=_SEVERITY_RANK["major"],
                gain=gain,
                instruction="Citer chaque table trouvée dans answer.entities avec le programme qui la lit ou l'écrit.",
                keys=_keys(tables),
                entities=_entities(tables),
                queries=RetrievalQueries(graph=graph_query, rag=" ".join(ids)),
                family="retrieve:table",
            )
        )
    return out


def _claim_candidates(inp: PlannerInput) -> list[_Candidate]:
    per_claim: dict[str, list[Finding]] = {}
    orphans: list[Finding] = []
    for finding in inp.findings:
        if finding.code in _CLAIM_CODES and finding.claim_id is not None:
            per_claim.setdefault(finding.claim_id, []).append(finding)
    for finding in inp.findings:
        if finding.code != "UNKNOWN_ENTITY" or finding.entity is None:
            continue
        entity_id = finding.entity.id
        owners = [claim_id for claim_id, ids in inp.claim_entities.items() if entity_id in ids]
        if not owners:
            orphans.append(finding)
        for claim_id in owners:
            per_claim.setdefault(claim_id, []).append(finding)
    total_weight = sum(inp.weights.values())
    total_claims = max(len(inp.claim_entities), 1)
    per_claim_gain = (
        100.0
        * (inp.weights["evidence_support"] + inp.weights["faithfulness"])
        / total_claims
        / total_weight
    )
    out: list[_Candidate] = []
    for claim_id, findings in per_claim.items():
        hints = list(dict.fromkeys(_CLAIM_HINTS[f.code] for f in findings))
        out.append(
            _Candidate(
                kind="verify_claim",
                severity=max(_SEVERITY_RANK[f.severity] for f in findings),
                gain=per_claim_gain,
                instruction=f"Claim {claim_id} : " + " ; ".join(hints) + ".",
                keys=_keys(findings),
                claim_ids=[claim_id],
                entities=_entities([f for f in findings if f.code == "UNKNOWN_ENTITY"]),
                family="verify",
            )
        )
    if orphans:
        out.append(
            _Candidate(
                kind="verify_claim",
                severity=_SEVERITY_RANK["critical"],
                gain=0.0,
                instruction=(
                    "Entités inconnues du graphe et référencées par aucune claim : "
                    "corriger l'identifiant ou les retirer de answer.entities."
                ),
                keys=_keys(orphans),
                entities=_entities(orphans),
                family="verify",
            )
        )
    return out


def _apply_cap_bonus(candidates: list[_Candidate], inp: PlannerInput) -> None:
    """Spec §7: the verify_claim action holding the last finding of a gate earns the lifted cap.

    "Last" follows the emission order of ``inp.findings`` (graders run in a fixed order and each
    walks claims and entities in answer.json order), which keeps the gain deterministic.
    """
    values = {cap.name: float(cap.value) for cap in inp.caps_applied}
    for name, value in values.items():
        codes = _GATE_CODES.get(name, frozenset())
        last = next((f for f in reversed(inp.findings) if f.code in codes), None)
        if last is None:
            continue
        others = [v for n, v in values.items() if n != name]
        bonus = max(0.0, min([inp.raw, *others]) - value)
        key = _finding_key(last)
        for candidate in candidates:
            if candidate.kind == "verify_claim" and key in candidate.keys:
                candidate.gain += bonus
                break


def _fallback(inp: PlannerInput) -> _Candidate:
    applicable = [
        (name, c.value)
        for name, c in inp.components.items()
        if c.applicable and c.value is not None
    ]
    # inp.components is keyed by str (it flows from scoring.ScoreBreakdown, built by iterating
    # COMPONENT_NAMES), but every key is in fact a ComponentName; cast rather than re-key the
    # whole scoring pipeline just for this fallback branch.
    lowest = cast(
        ComponentName,
        min(applicable, key=lambda item: (item[1], item[0]))[0]
        if applicable
        else "relevance_completeness",
    )
    notes = inp.judge_notes.strip()
    return _Candidate(
        kind="improve_answer",
        severity=_SEVERITY_RANK["major"],
        gain=100.0 - inp.score,
        instruction=notes or _COMPONENT_HINTS[lowest],
        component=lowest,
        family="improve_answer",
    )


def _to_action(candidate: _Candidate, priority: int) -> RepairAction:
    return RepairAction(
        id=f"a{priority}",
        kind=candidate.kind,
        priority=priority,
        expected_gain=round(max(candidate.gain, 0.0), 2),
        instruction=candidate.instruction,
        entities=candidate.entities,
        queries=candidate.queries,
        claim_ids=candidate.claim_ids,
        component=candidate.component,
    )


def _family(candidate: _Candidate) -> str:
    return candidate.family


def _summary(ordered: Sequence[_Candidate], inp: PlannerInput) -> str:
    sentences: list[str] = []
    seen: set[str] = set()
    verify_ids = [claim_id for c in ordered if c.kind == "verify_claim" for claim_id in c.claim_ids]
    for candidate in ordered:
        family = _family(candidate)
        if family in seen:
            continue
        seen.add(family)
        ids = ", ".join(e.id for e in candidate.entities)
        if family == "retrieve:program":
            recall = inp.components["context_recall"].value
            prefix = f"Rappel {recall:.2f} : " if recall is not None else ""
            sentences.append(f"{prefix}{len(candidate.entities)} programme(s) manquant(s) ({ids}).")
        elif family == "retrieve:table":
            sentences.append(f"{len(candidate.entities)} table(s) manquante(s) ({ids}).")
        elif family == "verify" and verify_ids:
            sentences.append(f"{len(verify_ids)} claim(s) à vérifier ({', '.join(verify_ids)}).")
        else:
            sentences.append(candidate.instruction)
        if len(sentences) == _SUMMARY_LIMIT:
            break
    return " ".join(sentences)
