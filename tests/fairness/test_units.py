"""Tests for the unit-form channel: an owner-approved equivalence table, never NLI.

Owner decision (2026-10-17): unit-form slots are judged by a deterministic
table of equivalent renderings. The NLI tokenizer reads ² and ³ as [UNK], so
the model cannot see cm² or g/cm³ at all.
"""

from __future__ import annotations

from examfp.fairness.units import UNIT_TABLE, check_unit_form, unit_of
from examfp.models import Paper, UnitFormSlot


def test_equivalent_forms_pass() -> None:
    assert check_unit_form("cm²", "square centimetres")[0]
    assert check_unit_form("km/h", "kmph")[0]
    assert check_unit_form("₹", "Rs.")[0]
    passed, reason = check_unit_form("g/cm³", "grams per cubic centimetre")
    assert passed and "gram per cubic centimetre" in reason


def test_different_units_fail() -> None:
    passed, reason = check_unit_form("cm²", "km/h")
    assert not passed and "square centimetre" in reason and "kilometre per hour" in reason


def test_forms_outside_the_table_fail_closed() -> None:
    passed, reason = check_unit_form("cm²", "square metres")
    assert not passed and "not in the unit table" in reason
    assert not check_unit_form("furlongs", "furlongs")[0]  # even unchanged: unknown unit


def test_forms_match_exactly() -> None:
    assert unit_of("Rs.") == unit_of("₹")
    assert unit_of("rs.") is None  # no case folding or fuzzy matching
    assert unit_of(" km/h") is None


def test_no_form_belongs_to_two_units() -> None:
    forms = [form for entry in UNIT_TABLE for form in entry.forms]
    assert len(forms) == len(set(forms))


def test_every_sample_unit_form_is_in_the_table(sample_paper: Paper) -> None:
    for question in sample_paper.questions:
        for slot in question.slots:
            if isinstance(slot, UnitFormSlot):
                units = {unit_of(v.values[0]) for v in slot.variants}
                assert None not in units, (question.id, slot.name)
                assert len(units) == 1, (question.id, slot.name, units)
