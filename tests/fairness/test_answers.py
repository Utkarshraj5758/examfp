"""Tests for exact answer equivalence of numeric groups (SymPy, exact Rational)."""

from __future__ import annotations

import pytest
from sympy import Integer, Rational

from examfp.fairness.answers import canonical_value, check_answer, group_value
from examfp.models import Question


@pytest.mark.parametrize(
    ("answer", "value"),
    [
        ("60 km/h", Integer(60)),
        ("₹1440", Integer(1440)),
        ("1440 cm²", Integer(1440)),  # the superscript is not a number
        ("8 g/cm³", Integer(8)),
        ("60 students", Integer(60)),
        ("0.5", Rational(1, 2)),
        ("2/3", Rational(2, 3)),
        ("-5 °C", Integer(-5)),
        ("−5 °C", Integer(-5)),  # U+2212 minus sign
    ],
)
def test_canonical_value_reads_the_one_number(answer: str, value: Rational) -> None:
    assert canonical_value(answer) == value


@pytest.mark.parametrize("answer", ["Carbon dioxide", "66 2/3", "1,440", "3 m 20 cm", ""])
def test_canonical_value_fails_closed_without_exactly_one_number(answer: str) -> None:
    assert canonical_value(answer) is None


def test_group_value_is_exact() -> None:
    value = group_value("divide", ["200", "3"])
    assert value == Rational(200, 3)
    assert value != Integer(66)  # no float rounding: 66.666... is not 66 or 67
    assert group_value("multiply", ["16", "90"]) == Integer(1440)
    assert group_value("percent", ["12", "500"]) == Integer(60)
    assert group_value("percent", ["15", "300"]) == Integer(45)
    assert group_value("add", ["12", "30", "8"]) == Integer(50)
    assert group_value("subtract", ["52", "17"]) == Integer(35)


@pytest.mark.parametrize(
    ("operation", "values"),
    [
        ("divide", ["12", "0"]),
        ("divide", ["12"]),
        ("percent", ["12", "500", "3"]),
        ("multiply", ["1_000", "2"]),  # int() would accept this; the checker must not
        ("multiply", ["٣", "2"]),  # non-ASCII digits are not plain operands
        ("multiply", ["2.5", "4"]),
        ("exponent", ["2", "3"]),
    ],
)
def test_group_value_fails_closed(operation: str, values: list[str]) -> None:
    assert group_value(operation, values) is None


def _question(answer: str, operation: str, reference: list[str]) -> Question:
    return Question.model_validate({
        "id": "q", "template": "{{a}} and {{b}}", "answer": answer,
        "slots": [{"name": "g", "fills": ["a", "b"], "variants": [{"values": reference}],
                   "difficulty_band": {"operation": operation, "operand_digits": [3, 1]}}],
    })


def test_check_answer_accepts_the_canonical_answer() -> None:
    question = _question("60 km/h", "divide", ["180", "3"])
    passed, reason = check_answer(question, "g", ["300", "5"])
    assert passed
    assert "300 / 5 = 60" in reason


def test_check_answer_rejects_a_different_exact_value() -> None:
    question = _question("60 km/h", "divide", ["180", "3"])
    passed, reason = check_answer(question, "g", ["200", "3"])
    assert not passed
    assert "200/3" in reason and "60" in reason


def test_check_answer_fails_closed_when_the_canonical_answer_has_no_single_number() -> None:
    question = _question("sixty", "divide", ["180", "3"])
    passed, reason = check_answer(question, "g", ["180", "3"])
    assert not passed and "exactly one number" in reason


def test_check_answer_fails_closed_on_an_unbanded_slot() -> None:
    question = Question.model_validate({
        "id": "q", "template": "{{lead}} it.", "answer": "4",
        "slots": [{"name": "lead", "variants": ["Find", "State"]}],
    })
    passed, reason = check_answer(question, "lead", ["Find"])
    assert not passed and "difficulty band" in reason
