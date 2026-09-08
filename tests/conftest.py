from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from helpers import write_json

RunBuilder = Callable[..., Path]


@pytest.fixture
def make_run(tmp_path: Path) -> RunBuilder:
    """Write a run directory; pass ``None`` to omit a file."""

    def _make(
        question: dict[str, object] | None,
        answer: dict[str, object] | None,
        evidence: dict[str, object] | None,
        judge: dict[str, object] | None,
        *,
        iteration: int = 1,
        run_id: str = "q-001",
    ) -> Path:
        run_dir = tmp_path / "runs" / run_id
        iter_dir = run_dir / f"iter-{iteration:02d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        if question is not None:
            write_json(run_dir / "question.json", question)
        for name, data in (("answer", answer), ("evidence", evidence), ("judge", judge)):
            if data is not None:
                write_json(iter_dir / f"{name}.json", data)
        return run_dir

    return _make
