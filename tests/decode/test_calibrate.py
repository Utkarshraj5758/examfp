"""Tests for the decision-rule calibration helpers (binomial tolerance, misread bound)."""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from examfp.decode.calibrate import (
    binomial_tail,
    mismatch_tolerance,
    misread_upper_bound,
)


def test_binomial_tail_known_values() -> None:
    # P(X > 4) for X ~ Bin(10, 1/2) = 1 - (1 + 10 + 45 + 120 + 210) / 1024.
    assert binomial_tail(10, 0.5, 4) == pytest.approx(638 / 1024)
    assert binomial_tail(10, 0.5, 10) == 0.0
    assert binomial_tail(10, 0.5, -1) == pytest.approx(1.0)
    assert binomial_tail(5, 0.0, 0) == 0.0
    assert binomial_tail(5, 1.0, 4) == pytest.approx(1.0)


def test_binomial_tail_is_accurate_far_out() -> None:
    # Direct summation, no 1 - cdf cancellation: P(X > 1), n = 31, p = 1e-6.
    expected = sum(
        math.comb(31, i) * 1e-6**i * (1 - 1e-6) ** (31 - i) for i in range(2, 32)
    )
    assert binomial_tail(31, 1e-6, 1) == pytest.approx(expected, rel=1e-9)


def test_tolerance_is_zero_with_no_misreads() -> None:
    assert mismatch_tolerance(31, 0.0, 1e-3) == 0


def test_tolerance_is_the_smallest_t_within_budget() -> None:
    reads, rate, budget = 31, 2.6e-4, 1e-3
    t = mismatch_tolerance(reads, rate, budget)
    assert binomial_tail(reads, rate, t) <= budget
    assert t == 0 or binomial_tail(reads, rate, t - 1) > budget
    assert t == 1  # 31 reads at this rate: one misread is too likely to forbid


@given(
    reads=st.integers(1, 200),
    rate=st.floats(0.0, 0.2),
    budget=st.sampled_from([1e-2, 1e-3, 1e-6]),
)
def test_tolerance_grows_with_misread_rate(reads: int, rate: float, budget: float) -> None:
    assert mismatch_tolerance(reads, rate, budget) <= mismatch_tolerance(
        reads, min(1.0, rate * 2 + 1e-3), budget
    )


def test_upper_bound_with_zero_misreads_is_exact() -> None:
    # One-sided Clopper-Pearson with no events: 1 - alpha^(1/n).
    assert misread_upper_bound(0, 100, 0.95) == pytest.approx(1 - 0.05 ** (1 / 100), rel=1e-6)


def test_upper_bound_solves_the_binomial_cdf() -> None:
    upper = misread_upper_bound(5, 1000, 0.95)
    cdf = sum(math.comb(1000, i) * upper**i * (1 - upper) ** (1000 - i) for i in range(6))
    assert cdf == pytest.approx(0.05, rel=1e-6)
    assert upper > 5 / 1000  # an upper bound sits above the point estimate


def test_upper_bound_validation() -> None:
    assert misread_upper_bound(10, 10) == 1.0
    with pytest.raises(ValueError):
        misread_upper_bound(0, 0)
