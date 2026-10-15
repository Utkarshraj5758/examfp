"""Tests for the examfp data model."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import ValidationError

from examfp.models import (
    DifficultyBand,
    OptionOrderSlot,
    Paper,
    Question,
    TextSlot,
    UnitFormSlot,
    Variant,
    validate_symbols,
)


# --- Variant sugar -----------------------------------------------------------
def test_variant_accepts_bare_string_and_values() -> None:
    assert Variant.model_validate("Calculate").values == ["Calculate"]
    assert Variant.model_validate({"values": ["180", "3"]}).values == ["180", "3"]


# --- group slots + difficulty band ------------------------------------------
def _group(
    values: list[list[str]],
    digits: list[int],
    op: Literal["divide", "multiply", "percent", "add", "subtract"] = "divide",
) -> TextSlot:
    return TextSlot(
        name="g",
        fills=["a", "b"],
        difficulty_band=DifficultyBand(operation=op, operand_digits=digits),
        variants=[Variant(values=v) for v in values],
    )


def test_group_slot_ok_within_band() -> None:
    slot = _group([["180", "3"], ["240", "4"]], [3, 1])
    assert slot.channel == "group"
    assert slot.alphabet == 2
    assert slot.fill(1) == {"a": "240", "b": "4"}


def test_group_rejects_wrong_digit_count() -> None:
    with pytest.raises(ValidationError):
        _group([["18", "3"]], [3, 1])  # "18" is 2 digits, band wants 3


def test_group_rejects_trivial_operand() -> None:
    with pytest.raises(ValidationError):
        _group([["100", "2"]], [3, 1])  # 2 is trivial


def test_percent_band_excludes_50_and_100() -> None:
    with pytest.raises(ValidationError):
        _group([["50", "240"]], [2, 3], op="percent")  # 50 trivial for percent


def test_group_operand_digits_must_match_fills() -> None:
    with pytest.raises(ValidationError):
        TextSlot(
            name="g",
            fills=["a", "b"],
            difficulty_band=DifficultyBand(operation="divide", operand_digits=[3]),
            variants=[Variant(values=["180", "3"])],
        )


# --- unit form slots ---------------------------------------------------------
def test_unit_form_slot() -> None:
    slot = UnitFormSlot(name="unit", variants=[Variant(values=["km/h"]), Variant(values=["kmph"])])
    assert slot.channel == "units"
    assert slot.alphabet == 2
    assert slot.fill(0) == {"unit": "km/h"}


# --- option order slots ------------------------------------------------------
def _opts(n: int = 4, correct: int = 0) -> OptionOrderSlot:
    return OptionOrderSlot(
        name="opts",
        kind="option_order",
        fills=[f"o{i}" for i in range(n)],
        options=[f"opt{i}" for i in range(n)],
        correct=correct,
    )


def test_option_order_excludes_identity() -> None:
    slot = _opts(4)
    assert slot.alphabet == 23  # 4! - 1
    # No symbol reproduces the natural order.
    for i in range(slot.alphabet):
        assert list(slot.fill(i).values()) != [f"opt{j}" for j in range(4)]


def test_option_order_five_options_is_119() -> None:
    assert _opts(5).alphabet == 119


def test_option_letter_tracks_correct_position() -> None:
    slot = _opts(4, correct=0)
    letters = {slot.option_letter(i) for i in range(slot.alphabet)}
    assert letters == {"A", "B", "C", "D"}


def test_option_order_fills_must_match_options() -> None:
    with pytest.raises(ValidationError):
        OptionOrderSlot(
            name="opts", kind="option_order",
            fills=["a", "b"], options=["x", "y", "z"], correct=0,
        )


# --- question bijection ------------------------------------------------------
def _q(template: str, slots: list[object], answer: str = "x") -> Question:
    return Question.model_validate(
        {"id": "q", "template": template, "answer": answer,
         "slots": [s.model_dump() if hasattr(s, "model_dump") else s for s in slots]}
    )


def test_bijection_every_placeholder_filled_once() -> None:
    q = _q(
        "{{lead}} {{a}} by {{b}} in {{unit}}",
        [
            {"name": "lead", "variants": ["Calc", "Find"]},
            {"name": "g", "fills": ["a", "b"],
             "difficulty_band": {"operation": "multiply", "operand_digits": [2, 1]},
             "variants": [{"values": ["12", "3"]}, {"values": ["24", "6"]}]},
            {"name": "unit", "kind": "unit_form", "variants": ["cm", "centimetres"]},
        ],
    )
    assert {s.name for s in q.slots} == {"lead", "g", "unit"}


def test_bijection_rejects_unfilled_placeholder() -> None:
    with pytest.raises(ValidationError):
        _q("{{a}} {{missing}}", [
            {"name": "g", "fills": ["a"], "variants": ["1"]},
        ])


def test_bijection_rejects_double_fill() -> None:
    with pytest.raises(ValidationError):
        _q("{{a}}", [
            {"name": "s1", "fills": ["a"], "variants": ["1"]},
            {"name": "s2", "fills": ["a"], "variants": ["2"]},
        ])


def test_bijection_rejects_fill_without_placeholder() -> None:
    with pytest.raises(ValidationError):
        _q("{{a}}", [
            {"name": "g", "fills": ["a", "b"], "variants": [{"values": ["1", "2"]}]},
        ])


# --- sample paper ------------------------------------------------------------
def test_sample_parses_and_positions(sample_paper: Paper) -> None:
    assert [q.id for q in sample_paper.questions] == [f"q{i}" for i in range(1, 9)]
    positions = sample_paper.positions()
    assert len(positions) == 31
    assert positions[0] == ("q1", "intro")


def test_sample_min_three_positions_per_question(sample_paper: Paper) -> None:
    per_q: dict[str, int] = {}
    for qid, _ in sample_paper.positions():
        per_q[qid] = per_q.get(qid, 0) + 1
    assert min(per_q.values()) >= 3


def test_sample_option_alphabets_are_119(sample_paper: Paper) -> None:
    alph = sample_paper.alphabets()
    assert alph[("q2", "opts")] == 119
    assert alph[("q5", "opts")] == 119
    assert alph[("q8", "opts")] == 119


# --- symbol vectors keyed by position ---------------------------------------
def _zeros(paper: Paper) -> dict[tuple[str, str], int]:
    return {k: 0 for k in paper.alphabets()}


def test_validate_symbols_rejects_key_mismatch(sample_paper: Paper) -> None:
    syms = _zeros(sample_paper)
    del syms[("q1", "intro")]
    with pytest.raises(ValueError):
        validate_symbols(sample_paper, syms)


def test_validate_symbols_rejects_out_of_range(sample_paper: Paper) -> None:
    syms = _zeros(sample_paper)
    syms[("q2", "opts")] = 119  # one past 4!-1 alphabet... 5!-1 here
    syms[("q2", "opts")] = sample_paper.alphabets()[("q2", "opts")]
    with pytest.raises(IndexError):
        validate_symbols(sample_paper, syms)


def test_inserting_question_does_not_change_existing_keys(sample_paper: Paper) -> None:
    before = set(sample_paper.alphabets())
    extra = Question.model_validate({
        "id": "q9", "template": "{{lead}} 2 + 2.", "answer": "4",
        "slots": [{"name": "lead", "variants": ["Find", "State"]}],
    })
    bigger = Paper(id=sample_paper.id, title=sample_paper.title,
                   questions=[*sample_paper.questions, extra])
    after = set(bigger.alphabets())
    assert before <= after  # every existing (qid, slot) key is unchanged
    assert after - before == {("q9", "lead")}


# --- answer key --------------------------------------------------------------
def test_answer_key_canonical_identical_across_centres(sample_paper: Paper) -> None:
    alph = sample_paper.alphabets()
    zeros = {k: 0 for k in alph}
    maxes = {k: v - 1 for k, v in alph.items()}
    k0 = {q: a.canonical for q, a in sample_paper.answer_key(zeros).items()}
    k1 = {q: a.canonical for q, a in sample_paper.answer_key(maxes).items()}
    assert k0 == k1
    assert k0["q1"] == "60 km/h" and k0["q7"] == "₹1440"


def test_answer_key_option_letter_varies_with_option_symbols(sample_paper: Paper) -> None:
    alph = sample_paper.alphabets()
    letters = set()
    for sym in range(alph[("q2", "opts")]):
        v = {k: 0 for k in alph}
        v[("q2", "opts")] = sym
        letters.add(sample_paper.answer_key(v)["q2"].option_letter)
    # Correct option reaches every one of the 5 display positions.
    assert letters == {"A", "B", "C", "D", "E"}
    # Non-MCQ questions have no option letter.
    assert sample_paper.answer_key({k: 0 for k in alph})["q1"].option_letter is None
