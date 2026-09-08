"""One evaluation: load, grade, score, decide, plan, persist (spec §3, §6, §7, §10)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

from truthloop import __version__
from truthloop.config import Config, config_sha256
from truthloop.contracts.bundle import RunBundle, load_iteration
from truthloop.contracts.question import Question
from truthloop.contracts.repair_plan import ContractError
from truthloop.contracts.verdict import COMPONENT_NAMES, Component, Decision, Provenance, Verdict
from truthloop.graders import run_graders
from truthloop.graders.base import GraderContext
from truthloop.knowledge import KnowledgeSource
from truthloop.planner import PlannerInput, build_plan
from truthloop.runs import RunDir, RunError, inputs_sha256
from truthloop.scoring import aggregate, decide

EXIT_CODES: Final[dict[Decision, int]] = {"release": 0, "repair": 2, "escalate": 3, "invalid": 4}


def evaluate(
    run: RunDir,
    config: Config,
    knowledge: KnowledgeSource,
    iteration: int | None = None,
    now: datetime | None = None,
) -> Verdict:
    question, question_raw = run.load_question()
    number = run.latest_iteration() if iteration is None else iteration
    if number < 1:
        raise RunError(f"itération invalide : {number}")
    iteration_dir = run.iteration_path(number)
    if not iteration_dir.is_dir():
        raise RunError(f"itération {number} introuvable dans {run.path}")
    loaded = load_iteration(question, iteration_dir, number)
    stamp = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    provenance = Provenance(
        harness_version=__version__,
        inputs_sha256=inputs_sha256(
            [
                question_raw,
                loaded.raw.get("answer"),
                loaded.raw.get("evidence"),
                loaded.raw.get("judge"),
            ]
        ),
        config_sha256=config_sha256(config),
        knowledge_source=f"{config.knowledge.kind}:{config.knowledge.path}",
        knowledge_fingerprint=knowledge.fingerprint(),
        generated_at=stamp,
    )
    if loaded.bundle is None:
        verdict = _invalid_verdict(question, number, loaded.errors, config, provenance)
    else:
        verdict = _evaluate_bundle(loaded.bundle, number, config, knowledge, provenance)
    run.write_verdict(verdict)
    run.append_trace(
        {
            "ts": stamp,
            "iteration": number,
            "event": "verify",
            "score": verdict.score,
            "decision": verdict.decision,
        }
    )
    return verdict


def _invalid_verdict(
    question: Question,
    number: int,
    errors: Sequence[ContractError],
    config: Config,
    provenance: Provenance,
) -> Verdict:
    components = {
        name: Component(value=None, weight=config.scoring.weights[name], applicable=False)
        for name in COMPONENT_NAMES
    }
    plan = build_plan(
        PlannerInput(
            decision="invalid",
            score=0.0,
            raw=0.0,
            findings=[],
            caps_applied=[],
            weights=config.scoring.weights,
            components=components,
            contract_errors=errors,
        )
    )
    return Verdict(
        question_id=question.id,
        iteration=number,
        score=0.0,
        decision="invalid",
        threshold=config.scoring.release_threshold,
        components=components,
        repair_plan=plan,
        provenance=provenance,
    )


def _evaluate_bundle(
    bundle: RunBundle,
    number: int,
    config: Config,
    knowledge: KnowledgeSource,
    provenance: Provenance,
) -> Verdict:
    ctx = GraderContext(
        question=bundle.question,
        answer=bundle.answer,
        evidence=bundle.evidence,
        judge=bundle.judge,
        knowledge=knowledge,
    )
    results = run_graders(ctx)
    findings = [finding for result in results for finding in result.findings]
    breakdown = aggregate(results, config.scoring.weights, config.scoring.caps)
    decision, threshold = decide(
        breakdown.score,
        findings,
        coverage_applicable=breakdown.components["context_recall"].applicable,
        iteration=number,
        max_iterations=config.loop.max_iterations,
        release_threshold=config.scoring.release_threshold,
        release_threshold_no_reference=config.scoring.release_threshold_no_reference,
    )
    sizes = {
        r.component: r.expected_size for r in results if r.component and r.expected_size is not None
    }
    plan = build_plan(
        PlannerInput(
            decision=decision,
            score=breakdown.score,
            raw=breakdown.raw,
            findings=findings,
            caps_applied=breakdown.caps_applied,
            weights=config.scoring.weights,
            components=breakdown.components,
            expected_programs=sizes.get("context_recall", 0),
            expected_tables=sizes.get("table_recall", 0),
            claim_entities={claim.id: claim.entities for claim in bundle.answer.claims},
            pivot_ids=[pivot.id for pivot in bundle.question.pivot_entities],
            direction=bundle.question.direction,
            depth=bundle.question.depth,
            judge_notes=bundle.judge.notes if bundle.judge is not None else "",
        )
    )
    return Verdict(
        question_id=bundle.question.id,
        iteration=number,
        score=round(breakdown.score, 1),
        decision=decision,
        threshold=threshold,
        components=breakdown.components,
        caps_applied=breakdown.caps_applied,
        findings=findings,
        declared_gaps=[abstention.text for abstention in bundle.answer.abstentions],
        repair_plan=plan,
        provenance=provenance,
    )
