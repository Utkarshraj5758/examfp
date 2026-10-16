"""Test doubles and fixture helpers shared by the fairness tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "variants.json"

# The rule each unfair label names, as check names in a FairnessReport. A
# changed question is caught by the numbers rule (U11) or by NLI (U09, U10).
VIOLATION_CHECKS: dict[str, frozenset[str]] = {
    "wrong_answer": frozenset({"answer"}),
    "extra_step": frozenset({"steps"}),
    "trivial_operand": frozenset({"trivial"}),
    "digit_jump": frozenset({"digits"}),
    "changes_question": frozenset({"numbers", "nli"}),
}


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
