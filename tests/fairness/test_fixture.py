"""The approved fixture without the model: its shape, its flags, and every entry
whose verdict needs no NLI (all numeric entries, and U11). Runs in CI.

The model-backed half of the acceptance test is ``test_acceptance.py``.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from examfp.fairness.check import Channel, FairnessChecker, slot_channel
from examfp.models import OptionOrderSlot, Paper, Question
from tests.fairness.support import VIOLATION_CHECKS, RaisingNli, SpyNli, common, load_fixture


def _question(paper: Paper, qid: str) -> Question:
    return next(q for q in paper.questions if q.id == qid)


def test_fixture_shape(fixture_entries: list[dict[str, Any]]) -> None:
    assert len(fixture_entries) == 40
    assert len({e["id"] for e in fixture_entries}) == 40
    fair = [e for e in fixture_entries if e["fair"]]
    unfair = [e for e in fixture_entries if not e["fair"]]
    assert len(fair) == 29 and all(e["violation"] is None for e in fair)
    assert Counter(e["violation"] for e in unfair) == {
        "wrong_answer": 2, "extra_step": 2, "trivial_operand": 2, "digit_jump": 2,
        "changes_question": 3}
    assert set(VIOLATION_CHECKS) == set(load_fixture()["violations"])


def test_fixture_channels_match_the_checker(
    sample_paper: Paper, fixture_entries: list[dict[str, Any]]
) -> None:
    for entry in fixture_entries:
        slot = next(s for s in _question(sample_paper, entry["question"]).slots
                    if s.name == entry["slot"])
        # The fixture's "wording" covers unit forms too; the checker gives unit forms
        # their own path (the unit table replaces NLI, owner decision 2026-10-17).
        expected = ({Channel.NUMERIC} if entry["channel"] == "numeric"
                    else {Channel.WORDING, Channel.UNIT_FORM})
        assert slot_channel(slot) in expected, entry["id"]


def test_approved_flags_match_the_sample_paper(
    sample_paper: Paper, fixture_entries: list[dict[str, Any]]
) -> None:
    for entry in fixture_entries:
        slot = next(s for s in _question(sample_paper, entry["question"]).slots
                    if s.name == entry["slot"])
        assert not isinstance(slot, OptionOrderSlot)
        in_paper = any(v.values == entry["values"] for v in slot.variants)
        assert in_paper == entry["approved"], entry["id"]


def test_entries_decided_without_the_model(
    sample_paper: Paper, fixture_entries: list[dict[str, Any]]
) -> None:
    # Numeric entries and U11 (numbers differ) must be decided before any model call.
    checker = FairnessChecker(RaisingNli(), common)
    decided = [e for e in fixture_entries if e["channel"] == "numeric" or e["id"] == "U11"]
    assert len(decided) == 15
    for entry in decided:
        report = checker.check_candidate(
            _question(sample_paper, entry["question"]), entry["slot"], entry["values"])
        if entry["fair"]:
            assert report.passed, (entry["id"], report)
        else:
            # Each unfair entry fails exactly the rule on its label.
            assert report.failed, entry["id"]
            assert report.failed <= VIOLATION_CHECKS[entry["violation"]], (entry["id"], report)


def test_fair_wording_entries_pass_every_check_but_nli(
    sample_paper: Paper, fixture_entries: list[dict[str, Any]]
) -> None:
    # With a model that entails everything, only numbers and readability decide.
    checker = FairnessChecker(SpyNli(), common)
    for entry in fixture_entries:
        if entry["channel"] == "wording" and entry["fair"]:
            report = checker.check_candidate(
                _question(sample_paper, entry["question"]), entry["slot"], entry["values"])
            assert report.passed, (entry["id"], report)
