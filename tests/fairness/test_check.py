"""Tests for the fairness checker: channels, reports, and their separation.

PLAN.md M6 decision 1: three channels, three tests, never mixed. A spy NLI
backend proves that no numeric variant, and no pair whose numbers differ, ever
reaches the model; wording is never checked with SymPy or band arithmetic.
"""

from __future__ import annotations

import subprocess
import sys
from collections import Counter

import pytest

from examfp.fairness import answers, bands
from examfp.fairness.check import Channel as Ch
from examfp.fairness.check import (
    CheckResult,
    FairnessChecker,
    FairnessReport,
    candidate_text,
    numbers,
    option_order_structure,
    reference_text,
    slot_channel,
)
from examfp.models import OptionOrderSlot, Paper, Question, TextSlot, UnitFormSlot
from tests.fairness.support import RaisingNli, RejectingNli, SpyNli, common


def _q(paper: Paper, qid: str) -> Question:
    return next(q for q in paper.questions if q.id == qid)


# --- the core stays light ----------------------------------------------------------------------
def test_importing_the_checker_does_not_import_torch_or_transformers() -> None:
    code = (
        "import sys, examfp.fairness.check; "
        "assert 'torch' not in sys.modules and 'transformers' not in sys.modules, "
        "sorted(m for m in sys.modules if m.startswith(('torch', 'transformers')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


# --- channels --------------------------------------------------------------------------------
def test_slot_channels(sample_paper: Paper) -> None:
    q1 = _q(sample_paper, "q1")
    kinds = {s.name: slot_channel(s) for s in q1.slots}
    assert kinds == {"intro": Ch.WORDING, "speed": Ch.NUMERIC, "unit": Ch.UNIT_FORM,
                     "lead": Ch.INSTRUCTION, "closing": Ch.INSTRUCTION}
    assert slot_channel(_q(sample_paper, "q2").slots[1]) is Ch.OPTION_ORDER


# --- numbers ---------------------------------------------------------------------------------
def test_numbers_ignore_superscripts_and_read_any_decimal_digits() -> None:
    assert numbers("area in cm² and volume in cm³") == Counter()
    assert numbers("drives 180 km in 3 hours") == Counter({"180": 1, "3": 1})
    assert numbers("Option 0.5 and 0.25") == Counter({"0.5": 1, "0.25": 1})
    assert numbers("३० km") == Counter({"30": 1})  # Devanagari digits are numbers too
    assert numbers("1,440") == Counter({"1": 1, "440": 1})  # never silently merged
    assert numbers("a 30-minute stop") == Counter({"30": 1})


# --- texts compared ---------------------------------------------------------------------------
def test_reference_text_holds_every_slot_at_symbol_0(sample_paper: Paper) -> None:
    q1 = _q(sample_paper, "q1")
    text, _ = q1.resolve({s.name: 0 for s in q1.slots})
    assert reference_text(q1) == text


def test_candidate_text_changes_only_the_candidate_slot(sample_paper: Paper) -> None:
    q1 = _q(sample_paper, "q1")
    ref = reference_text(q1)
    cand = candidate_text(q1, "lead", ["Find"])
    assert cand == ref.replace("Calculate", "Find", 1)


def test_candidate_text_refuses_a_wrong_value_count(sample_paper: Paper) -> None:
    with pytest.raises(ValueError):
        candidate_text(_q(sample_paper, "q1"), "speed", ["300"])


# --- reports ----------------------------------------------------------------------------------
def test_report_passes_only_when_every_check_ran_and_passed() -> None:
    ok = CheckResult("numbers", True, "same")
    skipped = CheckResult("nli", False, "not run", ran=False)
    failed = CheckResult("nli", False, "no")
    report = FairnessReport("q1", "lead", Ch.WORDING, ("Find",), (ok,))
    assert report.passed and report.failed == frozenset()
    assert not FairnessReport("q1", "lead", Ch.WORDING, ("Find",), ()).passed  # fail closed
    assert not FairnessReport("q1", "lead", Ch.WORDING, ("Find",), (ok, skipped)).passed
    two = FairnessReport("q1", "lead", Ch.WORDING, ("Find",), (ok, failed, skipped))
    assert two.failed == frozenset({"nli"})  # a skipped check is not a failed rule


# --- wording channel ------------------------------------------------------------------------
TEXT_CHANNELS = (Ch.WORDING, Ch.INSTRUCTION, Ch.UNIT_FORM)


def test_wording_runs_separation_ask_numbers_nli_then_readability(sample_paper: Paper) -> None:
    spy = SpyNli()
    report = FairnessChecker(spy, common).check_candidate(
        _q(sample_paper, "q1"), "intro", ["While driving to Nashik,"])
    assert report.channel is Ch.WORDING
    assert [c.name for c in report.checks] == [
        "separation", "ask", "numbers", "nli", "readability"]
    assert report.passed
    assert report.nli_version == "spy-nli@0"
    assert len(spy.calls) == 2  # both directions


def test_a_wording_slot_in_the_ask_never_reaches_the_model() -> None:
    # Held-out N06 as a slot: the quantity asked may not vary, whatever NLI thinks.
    question = Question.model_validate({
        "id": "t", "template": "A circle has a radius of 7 cm.\n{{lead}} its {{what}}.",
        "answer": "44 cm",
        "slots": [{"name": "lead", "variants": ["Calculate", "Work out"]},
                  {"name": "what", "variants": ["circumference", "area"]}]})
    report = FairnessChecker(RaisingNli(), common).check_candidate(question, "what", ["area"])
    assert report.failed == frozenset({"ask"})
    assert report.nli_version is None
    assert next(c for c in report.checks if c.name == "nli").ran is False


def test_wording_with_different_numbers_never_reaches_the_model(sample_paper: Paper) -> None:
    checker = FairnessChecker(RaisingNli(), common)
    report = checker.check_candidate(
        _q(sample_paper, "q1"), "intro", ["After a 30-minute stop on the way to Nashik,"])
    assert not report.passed
    # It also contains the reference "On the way to Nashik,": a structural failure.
    assert report.failed == frozenset({"separation", "numbers"})
    assert report.nli_version is None
    assert [c.ran for c in report.checks] == [True, True, True, False, False]


def test_nli_rejection_fails_the_nli_check_only(sample_paper: Paper) -> None:
    report = FairnessChecker(RejectingNli(), common).check_candidate(
        _q(sample_paper, "q1"), "intro", ["On the Pune highway,"])
    assert report.failed == frozenset({"nli"})


def test_wording_never_uses_sympy_or_band_arithmetic(
    sample_paper: Paper, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> tuple[bool, str]:
        raise AssertionError("numeric rule used on a wording candidate")

    monkeypatch.setattr(answers, "check_answer", forbidden)
    for name in ("check_digits", "check_trivial", "check_steps"):
        monkeypatch.setattr(bands, name, forbidden)
    checker = FairnessChecker(SpyNli(), common)
    for question in sample_paper.questions:
        for slot in question.slots:
            if slot_channel(slot) in TEXT_CHANNELS:
                assert isinstance(slot, TextSlot | UnitFormSlot)
                for variant in slot.variants:
                    checker.check_candidate(question, slot.name, variant.values)


# --- instruction phrasing: the curated table, never NLI ----------------------------------------
def test_instructions_use_the_table_never_the_model(sample_paper: Paper) -> None:
    checker = FairnessChecker(RaisingNli(), common)
    report = checker.check_candidate(_q(sample_paper, "q1"), "closing", ["Include your working."])
    assert report.channel is Ch.INSTRUCTION
    assert [c.name for c in report.checks] == [
        "separation", "numbers", "instruction", "readability"]
    assert report.passed and report.nli_version is None
    # U09 and U10: a changed ask in an instruction slot is caught by the table.
    unit = checker.check_candidate(_q(sample_paper, "q3"), "closing",
                                   ["Give your answer in square metres."])
    assert unit.failed == frozenset({"instruction"})
    other = checker.check_candidate(_q(sample_paper, "q5"), "lead",
                                    ["Identify a value other than"])
    assert other.failed == frozenset({"separation", "instruction"})  # also a prefix of "Identify"


def test_unlisted_fair_synonyms_fail_closed(sample_paper: Paper) -> None:
    report = FairnessChecker(RaisingNli(), common).check_candidate(
        _q(sample_paper, "q1"), "lead", ["Find"])
    assert report.failed == frozenset({"instruction"})


def test_instruction_variants_never_reach_the_model(sample_paper: Paper) -> None:
    checker = FairnessChecker(RaisingNli(), common)
    for question in sample_paper.questions:
        for slot in question.slots:
            if slot_channel(slot) is Ch.INSTRUCTION:
                assert isinstance(slot, TextSlot)
                for variant in slot.variants:
                    assert checker.check_candidate(question, slot.name, variant.values).passed


# --- separation: the reader must tell a slot's variants apart ----------------------------------
def test_a_near_prefix_variant_fails_separation(sample_paper: Paper) -> None:
    report = FairnessChecker(RaisingNli(), common).check_candidate(
        _q(sample_paper, "q1"), "closing", ["Show your work."])
    assert "separation" in report.failed


def test_the_minimum_distance_is_configurable(sample_paper: Paper) -> None:
    from examfp.fairness.check import FairnessConfig

    strict = FairnessChecker(RaisingNli(), common, FairnessConfig(min_edit_distance=50))
    report = strict.check_candidate(_q(sample_paper, "q1"), "closing", ["Include your working."])
    assert report.failed == frozenset({"separation"})


# --- unit forms: the owner-approved table, never NLI ------------------------------------------
def test_unit_forms_use_the_table_never_the_model(sample_paper: Paper) -> None:
    checker = FairnessChecker(RaisingNli(), common)
    report = checker.check_candidate(_q(sample_paper, "q3"), "unit", ["square centimetres"])
    assert report.channel is Ch.UNIT_FORM
    assert [c.name for c in report.checks] == ["separation", "numbers", "units", "readability"]
    assert report.passed and report.nli_version is None
    wrong = checker.check_candidate(_q(sample_paper, "q3"), "unit", ["square metres"])
    assert wrong.failed == frozenset({"units"})


def test_unit_form_variants_never_reach_the_model(sample_paper: Paper) -> None:
    checker = FairnessChecker(RaisingNli(), common)
    for question in sample_paper.questions:
        for slot in question.slots:
            if isinstance(slot, UnitFormSlot):
                for variant in slot.variants:
                    assert checker.check_candidate(question, slot.name, variant.values).passed


# --- numeric channel ------------------------------------------------------------------------
def test_numeric_runs_answer_digits_trivial_then_steps(sample_paper: Paper) -> None:
    report = FairnessChecker(RaisingNli(), common).check_candidate(
        _q(sample_paper, "q4"), "pctval", ["12", "500"])
    assert report.channel is Ch.NUMERIC
    assert [c.name for c in report.checks] == ["answer", "digits", "trivial", "steps"]
    assert report.passed and report.nli_version is None


def test_steps_are_compared_only_inside_the_band(sample_paper: Paper) -> None:
    # A wrong answer, a digit jump or a trivial operand is the rule that fails;
    # the step comparison presupposes a valid band member with the right answer.
    checker = FairnessChecker(RaisingNli(), common)
    wrong = checker.check_candidate(_q(sample_paper, "q1"), "speed", ["200", "3"])
    assert wrong.failed == frozenset({"answer"})
    assert next(c for c in wrong.checks if c.name == "steps").ran is False
    jump = checker.check_candidate(_q(sample_paper, "q3"), "dims", ["12", "120"])
    assert jump.failed == frozenset({"digits"})


def test_numeric_variants_never_reach_the_model(sample_paper: Paper) -> None:
    checker = FairnessChecker(RaisingNli(), common)
    for question in sample_paper.questions:
        for slot in question.slots:
            if slot_channel(slot) is Ch.NUMERIC:
                assert isinstance(slot, TextSlot)
                for variant in slot.variants:
                    report = checker.check_candidate(question, slot.name, variant.values)
                    assert report.passed, report


# --- option order: structural only ---------------------------------------------------------------
def test_every_sample_option_order_passes_the_structural_check(sample_paper: Paper) -> None:
    checker = FairnessChecker(RaisingNli(), common)
    for qid in ("q2", "q5", "q8"):
        question = _q(sample_paper, qid)
        slot = next(s for s in question.slots if isinstance(s, OptionOrderSlot))
        for symbol in range(slot.alphabet):
            report = checker.check_option_order(question, slot.name, symbol)
            assert report.passed and report.channel is Ch.OPTION_ORDER
            assert [c.name for c in report.checks] == ["options"]


def test_option_order_structure_rejects_changed_options_or_answer() -> None:
    slot = OptionOrderSlot(name="opts", fills=["a", "b", "c"], options=["17", "21", "27"],
                           correct=0)
    assert option_order_structure(slot, ["21", "17", "27"], "B")[0]
    assert not option_order_structure(slot, ["21", "19", "27"], "A")[0]  # distractor changed
    assert not option_order_structure(slot, ["21", "17", "27"], "A")[0]  # letter points at 21
    assert not option_order_structure(slot, ["21", "21", "17"], "C")[0]  # duplicated option
    assert not option_order_structure(slot, ["21", "17"], "B")[0]  # option dropped


# --- the whole paper -------------------------------------------------------------------------
def test_check_paper_covers_every_variant(sample_paper: Paper) -> None:
    reports = FairnessChecker(SpyNli(), common).check_paper(sample_paper)
    expected = 0
    for question in sample_paper.questions:
        for slot in question.slots:
            # Text-slot symbol 0 is the reference itself; numeric references are
            # checked for answer and band; every permutation against the options.
            textual = slot_channel(slot) in TEXT_CHANNELS
            expected += slot.alphabet - 1 if textual else slot.alphabet
    assert len(reports) == expected


def test_spy_proves_only_same_number_wording_pairs_reach_the_model(sample_paper: Paper) -> None:
    spy = SpyNli()
    FairnessChecker(spy, common).check_paper(sample_paper)
    references = {reference_text(q) for q in sample_paper.questions}
    assert spy.calls
    for premise, hypothesis in spy.calls:
        assert numbers(premise) == numbers(hypothesis)
        assert premise in references or hypothesis in references
    # Every text the model saw carries exactly some question's reference numbers, so
    # every numeric group in it sits at its reference variant.
    reference_numbers = [numbers(reference_text(q)) for q in sample_paper.questions]
    for premise, hypothesis in spy.calls:
        assert numbers(premise) in reference_numbers
        assert numbers(hypothesis) in reference_numbers
