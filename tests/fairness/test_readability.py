"""Tests for the readability check: word, syllable and rare-word counts within tolerance."""

from __future__ import annotations

import pytest

from examfp.fairness.readability import (
    ReadabilityCounts,
    ReadabilityTolerance,
    check_readability,
    count_syllables,
    readability_counts,
    words,
)

RARE = {"photosynthesis", "kmph", "centimetre", "centimetres"}


def fake_zipf(word: str) -> float:
    """Deterministic stand-in for wordfreq: listed words are rare, the rest common."""
    return 2.0 if word.lower() in RARE else 5.0


def test_words_are_letter_runs() -> None:
    assert words("Calculate its area in cm². Show your working.") == [
        "Calculate", "its", "area", "in", "cm", "Show", "your", "working"]
    assert words("Rohan drives 180 km in 3 hours at 60 km/h.") == [
        "Rohan", "drives", "km", "in", "hours", "at", "km", "h"]
    assert words("Rs. 90 or ₹90") == ["Rs", "or"]


@pytest.mark.parametrize(
    ("word", "syllables"),
    [("cat", 1), ("water", 2), ("hour", 1), ("show", 1), ("working", 2), ("calculate", 3),
     ("km", 2), ("h", 1), ("kmph", 4), ("Rs", 2), ("make", 1), ("the", 1)],
)
def test_count_syllables(word: str, syllables: int) -> None:
    assert count_syllables(word) == syllables


def test_readability_counts() -> None:
    counts = readability_counts("State the gas plants absorb during photosynthesis.", fake_zipf)
    assert counts == ReadabilityCounts(words=7, syllables=counts.syllables, rare_words=1)
    assert counts.syllables >= 7


def test_identical_text_passes() -> None:
    text = "A school has 400 students. Calculate 15% of them. Show your working."
    passed, reason = check_readability(text, text, fake_zipf)
    assert passed and "words 10 vs 10" in reason


def test_a_much_longer_candidate_fails_on_words() -> None:
    reference = "Calculate its area. Show your working."
    candidate = ("Calculate its area, and then, once you have done so, show every part of your "
                 "working in full.")
    passed, reason = check_readability(reference, candidate, fake_zipf)
    assert not passed and "words" in reason


def test_rare_words_beyond_tolerance_fail() -> None:
    reference = "Give its speed in km/h. Show your working here please today."
    candidate = "Give its speed in kmph. Show your photosynthesis here please today."
    passed, reason = check_readability(reference, candidate, fake_zipf)
    assert not passed and "rare words 0 vs 2" in reason
    one_rare = "Give its speed in kmph. Show your working here please today."
    assert check_readability(reference, one_rare, fake_zipf, ReadabilityTolerance())[0]


def test_tolerance_is_configurable() -> None:
    reference = "Calculate its area. Show your working."
    candidate = "Calculate its area. Show all of your working."
    assert check_readability(reference, candidate, fake_zipf)[0] is False
    loose = ReadabilityTolerance(words=0.5, syllables=0.5, rare_words=1)
    assert check_readability(reference, candidate, fake_zipf, loose)[0] is True


def test_tolerance_is_symmetric() -> None:
    # An easier variant is as unfair to the other centres as a harder one.
    long = "Calculate its area, and then show every part of your working in full."
    short = "Find its area."
    assert not check_readability(long, short, fake_zipf)[0]
    assert not check_readability(short, long, fake_zipf)[0]
