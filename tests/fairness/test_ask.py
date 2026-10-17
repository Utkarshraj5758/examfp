"""Tests for the ask rule: the quantity asked is a radical, never a wording slot.

The two held-out false acceptances (circumference -> area, factors -> multiples)
changed the quantity asked. Such a change must be impossible by construction,
not left to NLI: an NLI-judged wording slot may sit only in the stem, before the
ask region (ADR 0004).
"""

from __future__ import annotations

from examfp.fairness.ask import ask_region_start, check_ask, sentences
from examfp.models import Paper, Question


def _q(template: str, slots: list[dict[str, object]], answer: str = "x") -> Question:
    return Question.model_validate({"id": "t", "template": template, "answer": answer,
                                    "slots": slots})


def _slot(q: Question, name: str):  # type: ignore[no-untyped-def]
    return next(s for s in q.slots if s.name == name)


def test_sentences_split_on_terminal_punctuation_and_line_breaks() -> None:
    spans = sentences("{{intro}} Rohan drives 180 km in 3.5 hours.\n{{lead}} his speed. {{c}}")
    texts = ["{{intro}} Rohan drives 180 km in 3.5 hours.", "{{lead}} his speed.", "{{c}}"]
    template = "{{intro}} Rohan drives 180 km in 3.5 hours.\n{{lead}} his speed. {{c}}"
    assert [template[a:b].strip() for a, b in spans] == texts


def test_every_sample_question_has_an_ask_and_keeps_intros_in_the_stem(
    sample_paper: Paper
) -> None:
    for question in sample_paper.questions:
        start = ask_region_start(question)
        assert start is not None, question.id
        assert question.template.index("{{lead}}") >= start
        for slot in question.slots:
            if slot.name == "intro":
                assert check_ask(question, slot)[0], question.id


def test_a_wording_slot_naming_the_quantity_is_rejected() -> None:
    # Held-out N06: circumference -> area.
    q = _q("A circle has a radius of 7 cm.\n{{lead}} its {{what}}.",
           [{"name": "lead", "variants": ["Calculate", "Work out"]},
            {"name": "what", "variants": ["circumference", "area"]}])
    passed, reason = check_ask(q, _slot(q, "what"))
    assert not passed and "ask" in reason


def test_a_wording_slot_in_the_command_sentence_is_rejected_even_before_the_command() -> None:
    q = _q("{{intro}} calculate the factors of 18.",
           [{"name": "intro", "variants": ["Without a calculator,", "Mentally,"]}])
    assert not check_ask(q, _slot(q, "intro"))[0]


def test_a_wording_slot_after_the_command_is_rejected() -> None:
    # Answer format and constraints follow the command; they are part of the ask.
    q = _q("A square has a perimeter of 36 cm.\nCalculate the length of one side. {{fmt}}",
           [{"name": "fmt", "variants": ["Give the exact value.", "Round to 1 d.p."]}])
    assert not check_ask(q, _slot(q, "fmt"))[0]


def test_a_literal_command_anchors_the_ask() -> None:
    q = _q("{{intro}} Rohan drives 180 km in 3 hours.\nCalculate his average speed.",
           [{"name": "intro", "variants": ["On the way to Nashik,", "While driving to Nashik,"]}])
    passed, reason = check_ask(q, _slot(q, "intro"))
    assert passed and "stem" in reason


def test_a_question_mark_anchors_the_ask() -> None:
    q = _q("{{intro}} a box holds 12 red and 18 blue marbles.\nWhat fraction are red?",
           [{"name": "intro", "variants": ["In a classroom,", "In a school classroom,"]}])
    assert check_ask(q, _slot(q, "intro"))[0]


def test_no_locatable_ask_fails_closed() -> None:
    q = _q("{{intro}} the speed of a car is 60 km/h.",
           [{"name": "intro", "variants": ["Today,", "This morning,"]}])
    passed, reason = check_ask(q, _slot(q, "intro"))
    assert not passed and "cannot locate" in reason


def test_command_detection_is_on_word_boundaries() -> None:
    # "statement" is not the command "State"; with no real command the rule fails closed.
    q = _q("{{intro}} read the statement below.",
           [{"name": "intro", "variants": ["First,", "To begin,"]}])
    assert not check_ask(q, _slot(q, "intro"))[0]
