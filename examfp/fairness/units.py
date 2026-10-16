"""Unit-form channel: equivalent renderings of one unit, from an owner-approved table.

Owner decision (2026-10-17, M6): unit-form slots are judged by this table, not
by NLI. A unit form is a notational variant chosen from a closed set, and the
NLI tokenizer reads ² and ³ as ``[UNK]``, so the model cannot see ``cm²`` or
``g/cm³`` at all. The checker still requires identical numbers and readability
within tolerance; only the entailment step is replaced.

The table holds exactly the forms the sample paper and the approved fixture
use. Forms match exactly (no case folding, no fuzzy matching), and a form that
is not in the table fails closed. Adding a form or a unit is an owner decision:
review it like a change to a frozen file.
"""

from __future__ import annotations

from dataclasses import dataclass

Check = tuple[bool, str]


@dataclass(frozen=True)
class UnitEntry:
    """One unit and every rendering of it accepted as equivalent."""

    unit: str
    forms: frozenset[str]


UNIT_TABLE: tuple[UnitEntry, ...] = (
    UnitEntry("kilometre per hour",
              frozenset({"km/h", "kmph", "kilometres per hour", "km per hour"})),
    UnitEntry("square centimetre", frozenset({"cm²", "sq cm", "square centimetres"})),
    UnitEntry("gram per cubic centimetre",
              frozenset({"g/cm³", "grams per cubic centimetre", "g per cm³"})),
    UnitEntry("Indian rupee", frozenset({"₹", "Rs."})),
)


def unit_of(form: str, table: tuple[UnitEntry, ...] = UNIT_TABLE) -> str | None:
    """The unit ``form`` renders, or ``None`` if the table does not list it exactly."""
    for entry in table:
        if form in entry.forms:
            return entry.unit
    return None


def check_unit_form(
    reference: str, candidate: str, table: tuple[UnitEntry, ...] = UNIT_TABLE
) -> Check:
    """Do ``reference`` and ``candidate`` render the same unit, per the table?

    Guarantees: passes only when both forms are listed, under the same unit;
    an unlisted form fails closed, even if unchanged.
    """
    ref_unit, cand_unit = unit_of(reference, table), unit_of(candidate, table)
    for form, unit in ((reference, ref_unit), (candidate, cand_unit)):
        if unit is None:
            return False, f"{form!r} is not in the unit table"
    if ref_unit != cand_unit:
        return False, f"{candidate!r} is a {cand_unit}, the reference {reference!r} a {ref_unit}"
    return True, f"{candidate!r} and {reference!r} both render the {ref_unit}"
