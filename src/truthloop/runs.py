"""Run directory layout, canonical hashing and trace (spec §8.1, §4.5)."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from truthloop.contracts.bundle import errors_from
from truthloop.contracts.question import Question
from truthloop.contracts.verdict import Verdict

_ITERATION_DIR: Final = re.compile(r"^iter-([0-9]{2,})$")


class RunError(Exception):
    """The run directory is unusable (exit code 1, no verdict written)."""


def canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def inputs_sha256(parts: Sequence[object | None]) -> str:
    """Spec §4.5: one line per input ``<position>:<canonical JSON>`` (absent → empty JSON)."""
    lines = (
        f"{index}:{canonical_json(part) if part is not None else ''}\n"
        for index, part in enumerate(parts)
    )
    return sha256_text("".join(lines))


@dataclass(frozen=True)
class RunDir:
    path: Path

    @property
    def question_path(self) -> Path:
        return self.path / "question.json"

    @property
    def trace_path(self) -> Path:
        return self.path / "trace.jsonl"

    def iteration_path(self, iteration: int) -> Path:
        return self.path / f"iter-{iteration:02d}"

    def iterations(self) -> list[int]:
        if not self.path.is_dir():
            return []
        numbers: dict[int, str] = {}
        for child in self.path.iterdir():
            match = _ITERATION_DIR.match(child.name)
            if not child.is_dir() or not match:
                continue
            number = int(match.group(1))
            if number == 0:
                continue
            if number in numbers:
                raise RunError(f"itérations en double dans {self.path} : {number}")
            numbers[number] = child.name
        return sorted(numbers)

    def latest_iteration(self) -> int:
        iterations = self.iterations()
        if not iterations:
            raise RunError(f"aucune itération (dossier iter-NN) dans {self.path}")
        return iterations[-1]

    def load_question(self) -> tuple[Question, object]:
        if not self.question_path.is_file():
            raise RunError(f"question.json introuvable dans {self.path}")
        try:
            raw: object = json.loads(self.question_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RunError(f"question.json illisible : {exc}") from exc
        try:
            question = Question.model_validate(raw)
        except ValidationError as exc:
            details = "; ".join(f"{e.loc}: {e.msg}" for e in errors_from(exc, "question"))
            raise RunError(f"question.json invalide : {details}") from exc
        return question, raw

    def verdict_path(self, iteration: int) -> Path:
        return self.iteration_path(iteration) / "verdict.json"

    def write_verdict(self, verdict: Verdict) -> Path:
        path = self.verdict_path(verdict.iteration)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(verdict.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        return path

    def load_verdict(self, iteration: int) -> Verdict | None:
        path = self.verdict_path(iteration)
        if not path.is_file():
            return None
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise RunError(f"verdict.json illisible ({path}) : {exc}") from exc
        try:
            return Verdict.model_validate(raw)
        except ValidationError as exc:
            details = "; ".join(f"{e.loc}: {e.msg}" for e in errors_from(exc, "verdict"))
            raise RunError(f"verdict.json invalide : {details}") from exc

    def append_trace(self, event: Mapping[str, object]) -> None:
        with self.trace_path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_json(dict(event)) + "\n")

    def read_trace(self) -> list[dict[str, object]]:
        if not self.trace_path.is_file():
            return []
        rows: list[dict[str, object]] = []
        lines = self.trace_path.read_text(encoding="utf-8").splitlines()
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                parsed: object = json.loads(line)
            except ValueError as exc:
                raise RunError(f"trace.jsonl ligne {line_number} invalide : {exc}") from exc
            if not isinstance(parsed, dict):
                raise RunError(f"trace.jsonl ligne {line_number} : objet JSON attendu")
            rows.append({str(k): v for k, v in parsed.items()})
        return rows
