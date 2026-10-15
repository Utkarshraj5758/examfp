"""Tests for the crude codebook assignment."""

from __future__ import annotations

from examfp.codebook.assign import assign, load_codebook, save_codebook
from examfp.models import Paper


def _hashable(symbols: dict[tuple[str, str], int]) -> tuple[tuple[tuple[str, str], int], ...]:
    return tuple(sorted(symbols.items()))


def test_assign_injective_over_1000_centres(sample_paper: Paper) -> None:
    book = assign(sample_paper, 1000, seed=0)
    assert len(book) == 1000
    assert len({_hashable(s) for s in book.values()}) == 1000


def test_every_symbol_within_its_alphabet(sample_paper: Paper) -> None:
    alphabets = sample_paper.alphabets()
    book = assign(sample_paper, 1000, seed=0)
    for symbols in book.values():
        assert set(symbols) == set(alphabets)  # exactly the paper's positions
        for position, symbol in symbols.items():
            assert 0 <= symbol < alphabets[position]


def test_assign_is_deterministic(sample_paper: Paper) -> None:
    assert assign(sample_paper, 50, seed=7) == assign(sample_paper, 50, seed=7)


def test_seed_shifts_assignment(sample_paper: Paper) -> None:
    a = assign(sample_paper, 50, seed=0)
    b = assign(sample_paper, 50, seed=1)
    assert a != b


def test_save_load_round_trip(sample_paper: Paper, tmp_path) -> None:  # type: ignore[no-untyped-def]
    book = assign(sample_paper, 20, seed=0)
    path = tmp_path / "codebook.json"
    save_codebook(book, path)
    assert load_codebook(path) == book
    # Keyed by "qid::slot" in the JSON.
    assert "q1::intro" in path.read_text(encoding="utf-8")
