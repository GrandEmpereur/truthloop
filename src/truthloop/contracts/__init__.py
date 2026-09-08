"""Pydantic contracts exchanged between Copilot agents and the harness (spec §4)."""

from truthloop.contracts.answer import Abstention, Answer, Claim, Relation
from truthloop.contracts.common import EntityRef, StrictModel, normalize_id
from truthloop.contracts.evidence import Chunk, Evidence
from truthloop.contracts.judge import Judge, JudgedClaim
from truthloop.contracts.question import Question
from truthloop.contracts.repair_plan import ContractError, RepairAction, RepairPlan
from truthloop.contracts.verdict import CapApplied, Component, Finding, Provenance, Verdict

__all__ = [
    "Abstention",
    "Answer",
    "CapApplied",
    "Chunk",
    "Claim",
    "Component",
    "ContractError",
    "EntityRef",
    "Evidence",
    "Finding",
    "Judge",
    "JudgedClaim",
    "Provenance",
    "Question",
    "Relation",
    "RepairAction",
    "RepairPlan",
    "StrictModel",
    "Verdict",
    "normalize_id",
]
