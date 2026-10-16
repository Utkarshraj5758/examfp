"""Difficulty-band channel: digit counts, trivial operands and the step rule.

Digit counts and trivial operands are judged by the band validator in
:mod:`examfp.models` (frozen), which stays the single source of truth: each
check here builds a one-variant :class:`~examfp.models.TextSlot` and reports
the validator's verdict. The step rule is new and is defined in ADR 0004:

    Two variants are equal in steps when, in the canonical written method, they
    need the same number of positional operations AND the same number of
    carries, borrows or non-zero remainders.

* **Multiplication** (long multiplication; the multiplier is the second operand
  in fill order): one positional operation per digit of the multiplier, zeros
  included. Every carry counts: each column whose result is 10 or more, in every
  partial-product row and in the addition of the rows, the leftmost column too.
* **Division** (short or long division; dividend first): one positional
  operation per digit of the dividend, not of the answer, so a dropped leading
  zero cannot undercount; the events are the non-zero remainders.
* **Addition / subtraction**: one positional operation per digit column; the
  events are carries (every carry, the leftmost too) or borrows.
* **Percentage** (percentage first, then the whole): one step when ``100 / p``
  is a whole number (one division), two otherwise (a division and a
  multiplication). This rule counts operations only.

Anything without a canonical method (three factors, a zero divisor, a negative
difference, an unknown operation) has no step count, and the check fails closed.
Operands are read in fill order; this module never reorders them. Arithmetic
only: no SymPy, no NLI.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from examfp.models import DifficultyBand, TextSlot, Variant

Check = tuple[bool, str]


@dataclass(frozen=True)
class StepCount:
    """Positional operations and events (carries, borrows or non-zero remainders).

    ``events`` is ``None`` where the rule counts operations only (percentage).
    """

    operations: int
    events: int | None


# (singular, plural) of what each method counts besides positional operations.
_EVENT_NAMES = {
    "multiply": ("carry", "carries"),
    "add": ("carry", "carries"),
    "subtract": ("borrow", "borrows"),
    "divide": ("non-zero remainder", "non-zero remainders"),
}
_METHODS = {
    "multiply": "long multiplication",
    "divide": "division",
    "add": "column addition",
    "subtract": "column subtraction",
    "percent": "percentage",
}


def _digits_lsb_first(n: int) -> list[int]:
    return [int(c) for c in reversed(str(n))]


def _column_addition_carries(numbers: Sequence[int]) -> int:
    """Carries in adding ``numbers`` column by column, the leftmost column's included."""
    width = max(len(str(n)) for n in numbers)
    carry = carries = 0
    for column in range(width):
        total = sum((n // 10**column) % 10 for n in numbers) + carry
        carry = total // 10
        carries += carry > 0
    return carries


def _multiply(multiplicand: int, multiplier: int) -> StepCount:
    carries = 0
    rows: list[int] = []
    for place, digit in enumerate(_digits_lsb_first(multiplier)):
        carry = 0
        for column in _digits_lsb_first(multiplicand):
            carry = (column * digit + carry) // 10
            carries += carry > 0
        rows.append(multiplicand * digit * 10**place)
    if len(rows) > 1:
        carries += _column_addition_carries(rows)
    return StepCount(operations=len(rows), events=carries)


def _divide(dividend: int, divisor: int) -> StepCount:
    remainder = non_zero = 0
    digits = str(dividend)
    for digit in digits:
        remainder = (remainder * 10 + int(digit)) % divisor
        non_zero += remainder != 0
    return StepCount(operations=len(digits), events=non_zero)


def _subtract(minuend: int, subtrahend: int) -> StepCount:
    borrow = borrows = 0
    width = len(str(minuend))
    for column in range(width):
        top = (minuend // 10**column) % 10 - borrow
        bottom = (subtrahend // 10**column) % 10
        borrow = int(top < bottom)
        borrows += borrow
    return StepCount(operations=width, events=borrows)


def step_count(operation: str, operands: Sequence[int]) -> StepCount | None:
    """Steps of ``operation`` on ``operands`` (fill order) in the canonical written method.

    Guarantees: implements ADR 0004 exactly; returns ``None``, never a guess, when
    the method is undefined (wrong operand count, negative operand, zero divisor
    or percentage, negative difference, unknown operation).
    """
    if any(n < 0 for n in operands):
        return None
    if operation == "multiply" and len(operands) == 2:
        return _multiply(operands[0], operands[1])
    if operation == "divide" and len(operands) == 2 and operands[1] != 0:
        return _divide(operands[0], operands[1])
    if operation == "percent" and len(operands) == 2 and operands[0] != 0:
        return StepCount(operations=1 if 100 % operands[0] == 0 else 2, events=None)
    if operation == "add" and len(operands) >= 2:
        width = max(len(str(n)) for n in operands)
        return StepCount(operations=width, events=_column_addition_carries(operands))
    if operation == "subtract" and len(operands) == 2 and operands[0] >= operands[1]:
        return _subtract(operands[0], operands[1])
    return None


_SYMBOLS = {"multiply": " x ", "divide": " / ", "add": " + ", "subtract": " - "}


def expression(operation: str, values: Sequence[str]) -> str:
    """Human-readable form of a group, operands in fill order (``"16 x 90"``)."""
    if operation == "percent" and len(values) == 2:
        return f"{values[0]}% of {values[1]}"
    return _SYMBOLS.get(operation, f" {operation} ").join(values)


def _count(n: int, nouns: tuple[str, str]) -> str:
    return f"{n} {nouns[0] if n == 1 else nouns[1]}"


def _describe(operation: str, count: StepCount) -> str:
    text = _count(count.operations, ("positional operation", "positional operations"))
    if count.events is not None:
        text += f" and {_count(count.events, _EVENT_NAMES[operation])}"
    return text


def _band(slot: TextSlot) -> DifficultyBand:
    if slot.difficulty_band is None:
        raise ValueError(f"slot {slot.name!r} has no difficulty band")
    return slot.difficulty_band


def _arity_error(slot: TextSlot, values: Sequence[str]) -> str | None:
    expected = len(slot.fills)
    if len(values) != expected:
        return f"the band takes {expected} operand(s); got {len(values)} value(s)"
    return None


def _validate(slot: TextSlot, values: Sequence[str], band: DifficultyBand) -> Check:
    """Run the frozen validator in models.py on a one-variant copy of ``slot``."""
    try:
        TextSlot(
            name=slot.name,
            fills=list(slot.fills),
            variants=[Variant(values=list(values))],
            difficulty_band=band,
        )
    except ValidationError as exc:
        messages = "; ".join(str(err["msg"]).removeprefix("Value error, ") for err in exc.errors())
        return False, messages
    return True, ""


def check_digits(slot: TextSlot, values: Sequence[str]) -> Check:
    """Do the operands have the band's digit counts? (Trivial operands are not judged.)

    Guarantees: the verdict is the frozen band validator's, run with
    ``exclude_trivial`` off.
    """
    if (error := _arity_error(slot, values)) is not None:
        return False, error
    band = _band(slot)
    passed, message = _validate(slot, values, band.model_copy(update={"exclude_trivial": False}))
    if passed:
        return True, f"operand digit counts match the band {band.operand_digits}"
    return False, message


def check_trivial(slot: TextSlot, values: Sequence[str]) -> Check:
    """Is any operand trivial for the band's operation? (Digit counts are not judged.)

    Guarantees: the verdict is the frozen band validator's, run with the
    candidate's own digit counts so that only triviality can fail.
    """
    if (error := _arity_error(slot, values)) is not None:
        return False, error
    band = _band(slot)
    if not band.exclude_trivial:
        return True, "the band allows trivial operands"
    own = band.model_copy(update={"operand_digits": [len(v) for v in values]})
    passed, message = _validate(slot, values, own)
    if passed:
        return True, f"no operand is trivial for a {band.operation} band"
    return False, message


def _whole_numbers(values: Sequence[str]) -> list[int] | None:
    if all(v.isascii() and v.isdigit() for v in values):
        return [int(v) for v in values]
    return None


def check_steps(slot: TextSlot, values: Sequence[str]) -> Check:
    """Does the candidate need the same steps as the reference variant (symbol 0)?

    Guarantees: equal only when both the positional operations and the events of
    ADR 0004 match; fails closed when either side has no canonical method or an
    operand is not a plain whole number.
    """
    if (error := _arity_error(slot, values)) is not None:
        return False, error
    operation = _band(slot).operation
    method = _METHODS[operation]
    reference = slot.variants[0].values
    mine, theirs = _whole_numbers(values), _whole_numbers(reference)
    if mine is None or theirs is None:
        return False, "an operand is not a plain whole number"
    candidate_count = step_count(operation, mine)
    reference_count = step_count(operation, theirs)
    if candidate_count is None:
        return False, f"no canonical written method for {expression(operation, values)} (ADR 0004)"
    if reference_count is None:
        return False, (f"no canonical written method for the reference "
                       f"{expression(operation, reference)} (ADR 0004)")
    detail = (f"{method}: {expression(operation, values)} needs "
              f"{_describe(operation, candidate_count)}; the reference "
              f"{expression(operation, reference)} needs {_describe(operation, reference_count)}")
    return candidate_count == reference_count, detail
