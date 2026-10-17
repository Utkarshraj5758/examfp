"""Tests for variant separation: no variant contained in another; a measured distance.

M6 finding: "Show your work." beside "Show your working." made the fuzzy reader
misread the reference 6 times in 104,048 reads. ``eval/separation.py`` measured
prefix and containment pairs misreading at 0.3-9% per read, so no variant may
contain another (owner, 2026-10-17). The edit-distance minimum it measured (11)
is recorded but not adopted (ADR 0004).
"""

from __future__ import annotations

import pytest

from examfp.fairness.separation import (
    MEASURED_MIN_EDIT_DISTANCE,
    MIN_EDIT_DISTANCE,
    check_separation,
    edit_distance,
    is_contained_pair,
    is_prefix_pair,
    normalise,
)


def test_normalise_matches_what_the_reader_compares() -> None:
    assert normalise("  Show your  Working. ") == "show your working"
    assert normalise("Rs.") == "rs"
    assert normalise("Choose one option only.") == "choose one option only"


def test_edit_distance_is_case_insensitive_levenshtein() -> None:
    assert edit_distance("Show your work.", "Show your working.") == 3
    assert edit_distance("km/h", "KMPH") == 1
    assert edit_distance("State", "State") == 0


@pytest.mark.parametrize(
    ("a", "b"),
    [("Show your work.", "Show your working."),  # the M6 near-prefix finding
     ("km", "kmph"),
     ("Identify", "Identify a value other than"),
     ("Calculate", "calculated")],
)
def test_prefix_pairs_are_detected_either_way(a: str, b: str) -> None:
    assert is_prefix_pair(a, b) and is_prefix_pair(b, a)


@pytest.mark.parametrize(
    ("a", "b"),
    [("Show your working.", "Include your working."), ("km/h", "kmph"), ("₹", "Rs."),
     ("State", "State")],  # identical text is the same variant, not a prefix pair
)
def test_non_prefix_pairs(a: str, b: str) -> None:
    assert not is_prefix_pair(a, b)


@pytest.mark.parametrize(
    ("a", "b"),
    [("your working.", "Show your working."),  # suffix
     ("your work", "Show your working."),  # infix
     ("Show your work.", "Show your working."),  # prefix is containment too
     ("On the way to Nashik,", "After a 30-minute stop on the way to Nashik,")],  # U11
)
def test_containment_pairs_are_detected_either_way(a: str, b: str) -> None:
    assert is_contained_pair(a, b) and is_contained_pair(b, a)


def test_the_m6_near_prefix_pair_is_rejected() -> None:
    passed, reason = check_separation("Show your work.", ["Show your working."])
    assert not passed and "contains" in reason


def test_too_close_variants_are_rejected_with_the_distance() -> None:
    passed, reason = check_separation("Show yuor working.", ["Show your working."],
                                      min_distance=3)
    assert not passed and "distance 2" in reason and "3" in reason


def test_separated_variants_pass() -> None:
    passed, reason = check_separation("Include your working.", ["Show your working."])
    assert passed and "distance 7" in reason


def test_identical_text_is_not_compared_with_itself() -> None:
    assert check_separation("Work out", ["Calculate", "Work out"])[0]


def test_every_other_variant_is_checked() -> None:
    passed, reason = check_separation("Show your work.", ["Calculate", "Show your working."])
    assert not passed and "Show your working." in reason


def test_a_suffix_variant_is_rejected() -> None:
    assert not check_separation("your working.", ["Show your working."])[0]


def test_the_measured_minimum_is_recorded_but_not_adopted() -> None:
    # Owner decision, 2026-10-17: at 11, 17 of the paper's 29 text-variant pairs fail.
    assert MEASURED_MIN_EDIT_DISTANCE == 11
    assert MIN_EDIT_DISTANCE == 1  # the distance rule is off: distinct texts always pass it
