"""Numeric channel: exact answer equivalence with SymPy rationals.

A banded group's operands, combined by the band's operation in fill order,
must give exactly the question's canonical answer. Every value is a SymPy
``Rational``: ``200 / 3`` is ``200/3``, never ``66.67``. Operation semantics
(fill order): divide ``a / b``; multiply ``a * b``; percent ``a * b / 100``
(the percentage first); add ``a + b + ...``; subtract ``a - b``.

Fails closed: an operand that is not a plain ASCII whole number, a zero
divisor, an unknown operation, or a canonical answer without exactly one number
gives a failed check, never a guess. Never used on wording (PLAN.md M6,
decision 1).
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from sympy import Integer, Rational

from examfp.fairness.bands import expression
from examfp.models import Question, TextSlot

Check = tuple[bool, str]

# A number in a canonical answer: optional sign (hyphen not glued to a word, or
# U+2212), ASCII digits, an optional decimal part or a "/denominator". Superscripts
# such as the 2 in cm² are not ASCII digits, so they are never read as numbers.
_ANSWER_NUMBER = re.compile(r"(?:(?<![0-9A-Za-z])-|−)?[0-9]+(?:\.[0-9]+|/[0-9]+)?")


def canonical_value(answer: str) -> Rational | None:
    """The exact value of the one number in ``answer``, or ``None``.

    Guarantees: ``None`` unless the answer holds exactly one number, so
    ``"66 2/3"`` and ``"1,440"`` are refused rather than half-read.
    """
    found = _ANSWER_NUMBER.findall(answer)
    if len(found) != 1:
        return None
    return Rational(found[0].replace("−", "-"))


def group_value(operation: str, values: Sequence[str]) -> Rational | None:
    """Exact value of the group, operands in fill order; ``None`` if undefined."""
    if not values or not all(v.isascii() and v.isdigit() for v in values):
        return None
    operands = [Integer(int(v)) for v in values]
    if operation == "multiply":
        product: Rational = Integer(1)
        for operand in operands:
            product *= operand
        return product
    if operation == "add":
        return sum(operands, Integer(0))
    if len(operands) != 2:
        return None
    a, b = operands
    if operation == "divide":
        return None if b == 0 else Rational(a, b)
    if operation == "percent":
        return a * b / Integer(100)
    if operation == "subtract":
        return a - b
    return None


def check_answer(question: Question, slot_name: str, values: Sequence[str]) -> Check:
    """Do ``values`` in the slot's band give exactly the question's canonical answer?

    Guarantees: exact rational comparison; fails closed on an unbanded slot, an
    undefined group value or a canonical answer without exactly one number.
    """
    slot = next((s for s in question.slots if s.name == slot_name), None)
    if not isinstance(slot, TextSlot) or slot.difficulty_band is None:
        return False, f"slot {slot_name!r} is not a numeric group with a difficulty band"
    operation = slot.difficulty_band.operation
    target = canonical_value(question.answer)
    if target is None:
        return False, (f"canonical answer {question.answer!r} must contain exactly one number "
                       "to compare against")
    value = group_value(operation, values)
    if value is None:
        return False, f"{expression(operation, values)} has no exact value"
    shown = f"{expression(operation, values)} = {value}"
    if value == target:
        return True, f"{shown}, the canonical answer {question.answer!r}"
    return False, f"{shown}, not the canonical {target} ({question.answer!r})"
