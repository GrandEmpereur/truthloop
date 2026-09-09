"""Load one iteration of a run and apply cross-file rules (spec §4.0, §4.4, §10)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from truthloop.contracts.answer import Answer
from truthloop.contracts.evidence import Evidence
from truthloop.contracts.judge import Judge
from truthloop.contracts.question import Question
from truthloop.contracts.repair_plan import ContractError

ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(frozen=True)
class RunBundle:
    question: Question
    answer: Answer
    evidence: Evidence
    judge: Judge | None


@dataclass
class LoadedIteration:
    """Either a valid bundle or the list of contract errors, plus raw JSON for hashing."""

    bundle: RunBundle | None
    errors: list[ContractError] = field(default_factory=list)
    raw: dict[str, object] = field(default_factory=dict)


def load_iteration(question: Question, iteration_dir: Path, iteration: int) -> LoadedIteration:
    loaded = LoadedIteration(bundle=None)
    answer_data = _read(iteration_dir / "answer.json", "answer", loaded, required=True)
    evidence_data = _read(iteration_dir / "evidence.json", "evidence", loaded, required=True)
    judge_data = _read(iteration_dir / "judge.json", "judge", loaded, required=False)

    answer = _validate(Answer, answer_data, "answer", loaded) if answer_data is not None else None
    evidence = (
        _validate(Evidence, evidence_data, "evidence", loaded)
        if evidence_data is not None
        else None
    )
    judge = _validate(Judge, judge_data, "judge", loaded) if judge_data is not None else None

    for label, doc in (("answer", answer), ("evidence", evidence), ("judge", judge)):
        if doc is None:
            continue
        if doc.question_id != question.id:
            loaded.errors.append(
                ContractError(loc=f"{label}.question_id", msg=f"attendu {question.id!r}")
            )
        if doc.iteration != iteration:
            loaded.errors.append(
                ContractError(loc=f"{label}.iteration", msg=f"attendu {iteration}")
            )
    if judge is not None and answer is not None:
        known = {claim.id for claim in answer.claims}
        for index, claim in enumerate(judge.claims):
            if claim.id not in known:
                loaded.errors.append(
                    ContractError(
                        loc=_format_loc("judge", ("claims", index, "id")),
                        msg=f"claim {claim.id!r} absente de answer.json",
                    )
                )
    if not loaded.errors and answer is not None and evidence is not None:
        loaded.bundle = RunBundle(question=question, answer=answer, evidence=evidence, judge=judge)
    return loaded


def _read(path: Path, label: str, loaded: LoadedIteration, *, required: bool) -> object | None:
    if not path.is_file():
        if required:
            loaded.errors.append(ContractError(loc=label, msg="fichier manquant"))
        return None
    try:
        data: object = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        loaded.errors.append(ContractError(loc=label, msg=f"JSON invalide : {exc}"))
        return None
    loaded.raw[label] = data
    if not isinstance(data, dict):
        loaded.errors.append(ContractError(loc=label, msg="objet JSON attendu"))
        return None
    return data


def _validate(
    model: type[ModelT], data: object, label: str, loaded: LoadedIteration
) -> ModelT | None:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        loaded.errors.extend(errors_from(exc, label))
        return None


def errors_from(exc: ValidationError, label: str) -> list[ContractError]:
    errors: list[ContractError] = []
    for err in exc.errors():
        errors.append(ContractError(loc=_format_loc(label, err["loc"]), msg=str(err["msg"])))
    return errors


def _format_loc(label: str, parts: Sequence[object]) -> str:
    suffix = ".".join(str(part) for part in parts)
    return f"{label}.{suffix}" if suffix else label
