"""Encoding gate: released text must not carry a double-encoded UTF-8 signature (spec §6).

Windows shells frequently re-encode a UTF-8 command line as Windows-1252 before writing
``answer.json``; ``é`` then lands on disk as ``Ã©`` and would be published as-is. The check is a
pure text heuristic on the fields shown to the end user, so it stays deterministic and needs no
knowledge source.
"""

from __future__ import annotations

import re
from typing import Final

from truthloop.contracts.verdict import Finding
from truthloop.graders.base import GraderContext, GraderResult

# ``Ã``/``Â`` followed by a Latin-1 supplement char is the fingerprint of a UTF-8 two-byte
# sequence (U+00C0 to U+00FF and U+0080 to U+00BF) read as Windows-1252/Latin-1; ``â€`` is the same
# fingerprint for the three-byte punctuation block (curly quotes, dashes, ellipsis); U+FEFF is a
# BOM that ended up inside a string. None of these sequences occurs in French, English or
# Polish prose.
_MOJIBAKE: Final = re.compile("[ÃÂ][\u0080-\u00bf]|â€|\ufeff")


def _looks_double_encoded(text: str) -> bool:
    return _MOJIBAKE.search(text) is not None


def grade_encoding(ctx: GraderContext) -> list[GraderResult]:
    findings: list[Finding] = []
    for claim in ctx.answer.claims:
        if _looks_double_encoded(claim.text):
            findings.append(
                Finding(
                    code="MOJIBAKE",
                    severity="critical",
                    claim_id=claim.id,
                    detail=f"Texte de la claim {claim.id} double-encodé (`Ã©` au lieu de `é`) : "
                    "réécrire answer.json avec l'outil d'édition, en UTF-8.",
                )
            )
    broken = [
        name
        for name, present in (
            ("final_text", _looks_double_encoded(ctx.answer.final_text)),
            ("abstentions", any(_looks_double_encoded(a.text) for a in ctx.answer.abstentions)),
        )
        if present
    ]
    if broken:
        findings.append(
            Finding(
                code="MOJIBAKE",
                severity="critical",
                detail=f"Champ(s) {', '.join(broken)} double-encodé(s) (`Ã©` au lieu de `é`) : "
                "réécrire answer.json avec l'outil d'édition, en UTF-8.",
            )
        )
    return [GraderResult(component=None, value=None, findings=tuple(findings))]
