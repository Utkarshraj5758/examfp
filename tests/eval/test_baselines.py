"""Tests for the superseded mixed-radix codebook kept as the 'before' baseline."""

from __future__ import annotations

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
