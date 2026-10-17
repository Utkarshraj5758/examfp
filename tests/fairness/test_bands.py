"""Tests for the difficulty-band channel: digits, trivial operands, and the step rule.

The step rule is ADR 0004 (owner decisions, 2026-10-17): two variants are equal
in steps when the canonical written method needs the same number of positional
operations AND the same number of carries, borrows or non-zero remainders.
Every carry counts, including the leftmost column's and those in the addition
of partial products; the multiplier is the second operand in fill order.
"""

from __future__ import annotations

import pytest

from examfp.fairness.bands import StepCount, check_digits, check_steps, check_trivial, step_count
from examfp.models import DifficultyBand, TextSlot


def _slot(operation: str, digits: list[int], reference: list[str]) -> TextSlot:
    band = DifficultyBand.model_validate({"operation": operation, "operand_digits": digits})
    return TextSlot(
        name="g",
        fills=[f"x{i}" for i in range(len(digits))],
        variants=[{"values": reference}],  # type: ignore[list-item]
        difficulty_band=band,
    )


# --- multiplication: one positional operation per multiplier digit; every carry ---------------
def test_multiplication_counts_every_multiplier_digit_including_zeros() -> None:
    assert step_count("multiply", [16, 90]).operations == 2
    assert step_count("multiply", [16, 9]).operations == 1
    assert step_count("multiply", [12, 120]).operations == 3


@pytest.mark.parametrize(
    ("operands", "carries"),
    [
        # 16x0 = 0; 16x9: 6x9=54 carry, 1x9+5=14 carry (leftmost); 0 + 1440 none
        ((16, 90), 2),
        # 90x6: 0, 9x6=54 carry; 90x1 none; 540 + 900: 5+9=14 carry
        ((90, 16), 2),
        # 32x5: 10 carry, 16 carry; 32x4: 12 carry; 160 + 1280: 6+8=14 carry
        ((32, 45), 4),
        ((45, 32), 4),
        # 20x2 none; 20x7: 2x7=14 carry; 40 + 1400 none
        ((20, 72), 1),
        ((72, 20), 1),
        # 12x4 = 48, 12x3 = 36: no carries; 48 + 360: 4+6=10 carry
        ((12, 34), 1),
        # 18x5: 8x5=40 carry; 18x2: 8x2=16 carry; 90 + 360: 9+6=15 carry
        ((18, 25), 3),
        # 25x8: 5x8=40 carry, 2x8+4=20 carry (leftmost); 25x1 none; 200 + 250 none
        ((25, 18), 2),
        # 11x9 = 99 twice, no carries; 99 + 990: 9+9=18 carry, 0+9+1=10 carry
        ((11, 99), 2),
    ],
)
def test_multiplication_counts_every_carry(operands: tuple[int, int], carries: int) -> None:
    assert step_count("multiply", list(operands)).events == carries


def test_multiplier_is_the_second_operand() -> None:
    # 18 x 25 and 25 x 18 differ: the order in `fills` decides which is written below.
    assert step_count("multiply", [18, 25]) == StepCount(operations=2, events=3)
    assert step_count("multiply", [25, 18]) == StepCount(operations=2, events=2)


# --- division: one positional operation per dividend digit; non-zero remainders ----------------
def test_division_counts_dividend_digits_not_answer_digits() -> None:
    # 180 / 3 = 60 has two answer digits, but the method works through 1, 18, 0.
    assert step_count("divide", [180, 3]) == StepCount(operations=3, events=1)


@pytest.mark.parametrize(
    ("operands", "expected"),
    [
        ((240, 4), StepCount(3, 1)),  # 2 r2, 24 r0, 0 r0
        ((540, 9), StepCount(3, 1)),
        ((24, 3), StepCount(2, 1)),  # 2 r2, 24 r0
        ((72, 9), StepCount(2, 1)),
        ((200, 3), StepCount(3, 3)),  # 2 r2, 20 r2, 20 r2
        ((112, 14), StepCount(3, 2)),  # 1 r1, 11 r11, 112 r0
        ((84, 4), StepCount(2, 0)),  # 8 r0, 4 r0
    ],
)
def test_division_counts_non_zero_remainders(
    operands: tuple[int, int], expected: StepCount
) -> None:
    assert step_count("divide", list(operands)) == expected


# --- percentage: one step if 100 / p is whole, two otherwise -------------------------------------
@pytest.mark.parametrize(
    ("percent", "steps"),
    [(20, 1), (25, 1), (4, 1), (15, 2), (16, 2), (24, 2), (30, 2), (40, 2), (75, 2), (12, 2),
     (48, 2), (150, 2)],
)
def test_percentage_steps(percent: int, steps: int) -> None:
    count = step_count("percent", [percent, 400])
    assert count.operations == steps
    assert count.events is None  # the percentage rule counts operations only


# --- addition and subtraction: one per digit column; carries or borrows --------------------------
@pytest.mark.parametrize(
    ("operands", "expected"),
    [
        ((57, 68), StepCount(2, 2)),  # 7+8=15 carry; 5+6+1=12 carry (leftmost counts)
        ((12, 34), StepCount(2, 0)),
        ((99, 1), StepCount(2, 2)),
        ((15, 25, 35), StepCount(2, 1)),  # 5+5+5=15 carry; 1+2+3+1=7
        ((305, 47), StepCount(3, 1)),
    ],
)
def test_addition_counts_columns_and_carries(
    operands: tuple[int, ...], expected: StepCount
) -> None:
    assert step_count("add", list(operands)) == expected


@pytest.mark.parametrize(
    ("operands", "expected"),
    [
        ((52, 17), StepCount(2, 1)),  # 2-7 borrow; 5-1-1=3
        ((100, 1), StepCount(3, 2)),  # 0-1 borrow; 0-0-1 borrow; 1-0-1=0
        ((86, 42), StepCount(2, 0)),
    ],
)
def test_subtraction_counts_columns_and_borrows(
    operands: tuple[int, int], expected: StepCount
) -> None:
    assert step_count("subtract", list(operands)) == expected


# --- fail closed: no canonical method -> no step count ---------------------------------------
@pytest.mark.parametrize(
    ("operation", "operands"),
    [
        ("multiply", [2, 3, 4]),  # no canonical method for three factors
        ("divide", [12, 0]),
        ("divide", [12]),
        ("percent", [0, 400]),
        ("subtract", [17, 52]),  # negative result
        ("add", [5]),
        ("exponent", [2, 3]),
    ],
)
def test_no_canonical_method_gives_no_count(operation: str, operands: list[int]) -> None:
    assert step_count(operation, operands) is None


# --- check_steps compares a candidate with the reference variant (symbol 0) ---------------------
def test_check_steps_rejects_extra_carries_with_a_reason() -> None:
    slot = _slot("multiply", [2, 2], ["16", "90"])
    passed, reason = check_steps(slot, ["45", "32"])
    assert not passed
    assert "4 carries" in reason and "2 carries" in reason


def test_check_steps_accepts_equal_counts() -> None:
    slot = _slot("multiply", [2, 2], ["16", "90"])
    assert check_steps(slot, ["90", "16"])[0]
    assert check_steps(slot, ["18", "80"])[0]
    passed, reason = check_steps(slot, ["20", "72"])  # 1 carry against 2
    assert not passed and "and 1 carry;" in reason


def test_check_steps_on_percentages() -> None:
    slot = _slot("percent", [2, 3], ["15", "400"])
    assert check_steps(slot, ["12", "500"])[0]
    assert check_steps(slot, ["48", "125"])[0]
    passed, reason = check_steps(slot, ["20", "300"])
    assert not passed and "1 positional operation" in reason


def test_check_steps_fails_closed_without_a_canonical_method() -> None:
    slot = _slot("subtract", [2, 2], ["52", "17"])
    passed, reason = check_steps(slot, ["17", "52"])
    assert not passed and "no canonical" in reason


def test_check_steps_fails_closed_on_non_numeric_operands() -> None:
    slot = _slot("divide", [3, 1], ["180", "3"])
    assert not check_steps(slot, ["18O", "3"])[0]


# --- the frozen band validator in models.py stays the source of truth ---------------------------
def test_check_digits_wraps_the_band_validator() -> None:
    slot = _slot("multiply", [2, 2], ["16", "90"])
    assert check_digits(slot, ["18", "80"]) == (True, "operand digit counts match the band [2, 2]")
    passed, reason = check_digits(slot, ["12", "120"])
    assert not passed and "'120' is not a 2-digit number" in reason


def test_check_digits_ignores_trivial_operands() -> None:
    slot = _slot("divide", [3, 1], ["180", "3"])
    assert check_digits(slot, ["120", "2"])[0]  # 2 is trivial, but the digits are right


def test_check_trivial_wraps_the_band_validator() -> None:
    slot = _slot("divide", [3, 1], ["180", "3"])
    passed, reason = check_trivial(slot, ["120", "2"])
    assert not passed and "'2' is trivial" in reason
    assert check_trivial(slot, ["300", "5"])[0]


def test_check_trivial_uses_the_percent_trivial_set() -> None:
    slot = _slot("percent", [2, 3], ["15", "400"])
    passed, reason = check_trivial(slot, ["50", "120"])
    assert not passed and "'50' is trivial" in reason


def test_check_trivial_ignores_digit_counts() -> None:
    slot = _slot("multiply", [2, 2], ["16", "90"])
    assert check_trivial(slot, ["12", "120"])[0]  # a digit jump, but no trivial operand


def test_band_checks_reject_a_wrong_number_of_values() -> None:
    slot = _slot("multiply", [2, 2], ["16", "90"])
    for check in (check_digits, check_trivial, check_steps):
        passed, reason = check(slot, ["16"])
        assert not passed and "2 operand" in reason
