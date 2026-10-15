"""Tests for the superseded mixed-radix codebook kept as the 'before' baseline."""

from __future__ import annotations

import pytest

from eval.baselines import mixed_radix_assign
from examfp.models import Paper


def test_mixed_radix_is_injective_and_in_range(sample_paper: Paper) -> None:
    book = mixed_radix_assign(sample_paper, 1000)
    alphabets = sample_paper.alphabets()
    assert len({tuple(sorted(s.items())) for s in book.values()}) == 1000
    assert all(0 <= v < alphabets[p] for s in book.values() for p, v in s.items())


def test_mixed_radix_is_position_dependent(sample_paper: Paper) -> None:
    # The weakness M5 removes (NOTES.md, F3): high-order positions never change.
    book = mixed_radix_assign(sample_paper, 1000)
    constant = [p for p in sample_paper.positions() if len({book[c][p] for c in book}) == 1]
    assert len(constant) == 20


def test_ungated_rule_names_the_nearest_innocent_in_a_hybrid() -> None:
    # The live bug M5.5 fixes: margin-only ranking under collusion.
    from eval.baselines import score_ungated
    from examfp.decode.score import Outcome, score

    positions = [("q", f"p{i}") for i in range(10)]
    hybrid = {p: (0 if i < 5 else 1, 1.0) for i, p in enumerate(positions)}  # A then B
    toy = {
        1: {p: 0 for p in positions},  # colluder A
        2: {p: 1 for p in positions},  # colluder B
        3: {p: v for p, v in zip(positions, [0, 0, 0, 0, 2, 1, 1, 1, 1, 2], strict=True)},
    }
    before = score_ungated(hybrid, toy)
    assert before.outcome is Outcome.IDENTIFIED and before.ranked[0][0] == 3  # innocent
    assert before.margin == pytest.approx(7.2)
    after = score(hybrid, toy, misread_rate=0.0, min_read_slots=5)
    assert after.outcome is not Outcome.IDENTIFIED
