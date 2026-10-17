"""Test doubles and fixture helpers shared by the fairness tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "variants.json"

# The rule each unfair label names, as check names in a FairnessReport. A
# changed question is caught by the numbers rule (U11), by NLI (a wording slot),
# or by the instruction table (U09, U10 sit in instruction slots).
VIOLATION_CHECKS: dict[str, frozenset[str]] = {
    "wrong_answer": frozenset({"answer"}),
    "extra_step": frozenset({"steps"}),
    "trivial_operand": frozenset({"trivial"}),
    "digit_jump": frozenset({"digits"}),
    "changes_question": frozenset({"numbers", "nli", "instruction"}),
}
# Structural rules may fail beside an unfair entry's labelled rule: U10 ("Identify a
# value other than") is also a prefix of the variant "Identify".
STRUCTURAL_CHECKS = frozenset({"separation", "ask"})

# Fair entries the checker rejects, measured 2026-10-17 with nli-deberta-v3-small
# @fa28048 at threshold 0.5 (NOTES.md, M6). Pinned so that any drift fails a test.
# Every one but those marked is decided without the model.
RECORDED_FALSE_REJECTIONS: frozenset[str] = frozenset({
    "F01", "F03", "F04", "F07", "F09",  # fair command synonyms the paper does not use
    "F11", "F12", "F13", "F14",  # fair closings the paper does not use
})


def caught_for_its_label(entry: dict[str, Any], report: Any) -> bool:
    """Did the labelled rule reject an unfair entry, with only structural rules beside it?"""
    labelled = VIOLATION_CHECKS[entry["violation"]]
    failed: frozenset[str] = report.failed
    return bool(failed & labelled) and failed - labelled <= STRUCTURAL_CHECKS


def load_fixture() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return data


class SpyNli:
    """Records every pair it is asked to score and entails all of them."""

    version = "spy-nli@0"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def entailment(self, premise: str, hypothesis: str) -> float:
        self.calls.append((premise, hypothesis))
        return 1.0


class RaisingNli:
    """Fails the test if the model is consulted at all."""

    version = "raising-nli@0"

    def entailment(self, premise: str, hypothesis: str) -> float:
        raise AssertionError(f"NLI consulted: {premise!r} / {hypothesis!r}")


class RejectingNli:
    """Entails nothing."""

    version = "rejecting-nli@0"

    def entailment(self, premise: str, hypothesis: str) -> float:
        return 0.0


def common(word: str) -> float:
    """Word frequency stand-in: every word is common, so rarity never decides."""
    return 5.0
