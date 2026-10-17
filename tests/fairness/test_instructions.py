"""Tests for the instruction table: instruction and option-choice phrasing, never NLI.

Owner decision (2026-10-17): instruction boilerplate is judged by a curated
table, like unit forms, built from the sample paper's complete instruction
vocabulary - not from the fixture's rejected entries (F11, F13, F14).
"""

from __future__ import annotations

from examfp.fairness.instructions import (
    COMMAND,
    INSTRUCTION_TABLE,
    check_instruction,
    instruction_class,
)
from examfp.models import Paper, TextSlot


def _instruction_slots(paper: Paper) -> list[tuple[str, TextSlot]]:
    out = []
    for question in paper.questions:
        for slot in question.slots:
            if (isinstance(slot, TextSlot) and slot.difficulty_band is None
                    and instruction_class(slot.variants[0].values[0]) is not None):
                out.append((question.id, slot))
    return out


def test_same_class_passes() -> None:
    passed, reason = check_instruction("Calculate", "Work out")
    assert passed and "compute" in reason
    assert check_instruction("Choose one option only.", "Select only one option.")[0]


def test_a_different_class_fails() -> None:
    passed, reason = check_instruction("Calculate", "State")
    assert not passed and "different instruction" in reason


def test_unlisted_phrasing_fails_closed() -> None:
    passed, reason = check_instruction("Show your working.", "Show all your steps.")
    assert not passed and "not in the instruction table" in reason
    assert not check_instruction("Determine", "Determine")[0]  # even unchanged: unknown


def test_matching_is_exact() -> None:
    assert instruction_class("Work out") is not None
    assert instruction_class("work out") is None
    assert instruction_class("Work out ") is None


def test_no_phrase_belongs_to_two_classes() -> None:
    phrases = [p for entry in INSTRUCTION_TABLE for p in entry.phrases]
    assert len(phrases) == len(set(phrases))


def test_command_classes_are_marked_for_the_ask_rule() -> None:
    commands = {p for e in INSTRUCTION_TABLE if e.role == COMMAND for p in e.phrases}
    assert commands == {"Calculate", "Work out", "State", "Identify"}


def test_table_is_exactly_the_sample_papers_instruction_vocabulary(sample_paper: Paper) -> None:
    # Provenance: every phrase comes from the paper, and the paper's every
    # instruction variant is listed. Nothing was added from the fixture.
    vocabulary = {v.values[0] for _qid, slot in _instruction_slots(sample_paper)
                  for v in slot.variants}
    table = {p for entry in INSTRUCTION_TABLE for p in entry.phrases}
    assert table == vocabulary


def test_every_instruction_slot_stays_inside_one_class(sample_paper: Paper) -> None:
    slots = _instruction_slots(sample_paper)
    assert {slot.name for _qid, slot in slots} == {"lead", "closing"}
    assert len(slots) == 16
    for qid, slot in slots:
        classes = {instruction_class(v.values[0]) for v in slot.variants}
        assert len(classes) == 1, (qid, slot.name)
