"""The approved fixture without the model: its shape, its flags, and every entry
whose verdict needs no NLI (all numeric entries, and U11). Runs in CI.

The model-backed half of the acceptance test is ``test_acceptance.py``.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from examfp.fairness.check import Channel, FairnessChecker, slot_channel
from examfp.models import OptionOrderSlot, Paper, Question
from tests.fairness.support import (
    RECORDED_FALSE_REJECTIONS,
    VIOLATION_CHECKS,
    RaisingNli,
    SpyNli,
    caught_for_its_label,
    common,
    load_fixture,
)


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
        # The fixture's "wording" covers instruction phrasing and unit forms too; the
        # checker gives each its own table instead of NLI (owner decisions, 2026-10-17).
        expected = ({Channel.NUMERIC} if entry["channel"] == "numeric"
                    else {Channel.WORDING, Channel.INSTRUCTION, Channel.UNIT_FORM})
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


def _channel(paper: Paper, entry: dict[str, Any]) -> Channel:
    slot = next(s for s in _question(paper, entry["question"]).slots if s.name == entry["slot"])
    return slot_channel(slot)


def test_entries_decided_without_the_model(
    sample_paper: Paper, fixture_entries: list[dict[str, Any]]
) -> None:
    # Numeric, instruction and unit-form entries, and U11 (numbers differ), must be
    # decided before any model call: only stem wording ever reaches NLI.
    checker = FairnessChecker(RaisingNli(), common)
    decided = [e for e in fixture_entries
               if _channel(sample_paper, e) is not Channel.WORDING or e["id"] == "U11"]
    assert len(decided) == 37
    for entry in decided:
        report = checker.check_candidate(
            _question(sample_paper, entry["question"]), entry["slot"], entry["values"])
        if entry["fair"]:
            assert report.passed is (entry["id"] not in RECORDED_FALSE_REJECTIONS), (
                entry["id"], report)
        else:
            assert caught_for_its_label(entry, report), (entry["id"], report)


def test_fair_stem_wording_passes_every_check_but_nli(
    sample_paper: Paper, fixture_entries: list[dict[str, Any]]
) -> None:
    # With a model that entails everything, the structural rules, numbers and
    # readability decide; none of them rejects a fair stem paraphrase.
    checker = FairnessChecker(SpyNli(), common)
    wording = [e for e in fixture_entries
               if e["fair"] and _channel(sample_paper, e) is Channel.WORDING]
    assert [e["id"] for e in wording] == ["F16", "F17", "F18"]
    for entry in wording:
        report = checker.check_candidate(
            _question(sample_paper, entry["question"]), entry["slot"], entry["values"])
        assert report.passed, (entry["id"], report)
