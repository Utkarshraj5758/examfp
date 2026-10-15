"""Tests for the Reed-Solomon codebook assignment and its slot packing."""

from __future__ import annotations

import inspect
from math import prod
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from examfp.codebook.assign import (
    assign,
    byte_to_symbols,
    complete_symbols,
    load_codebook,
    rs_shape,
    save_codebook,
    slot_groups,
    symbols_to_byte,
)
from examfp.codebook.rs import RSDecodeError
from examfp.models import Paper


def _hashable(symbols: dict[tuple[str, str], int]) -> tuple[tuple[tuple[str, str], int], ...]:
    return tuple(sorted(symbols.items()))


@pytest.fixture(scope="module")
def book_1000(sample_paper_module: Paper) -> dict[int, dict[tuple[str, str], int]]:
    return assign(sample_paper_module, 1000, seed=0)


@pytest.fixture(scope="module")
def sample_paper_module() -> Paper:
    root = Path(__file__).resolve().parents[2]
    text = (root / "data" / "papers" / "sample.json").read_text(encoding="utf-8")
    return Paper.model_validate_json(text)


# --- public contract unchanged ---------------------------------------------------------------
def test_assign_signature_is_unchanged() -> None:
    sig = inspect.signature(assign)
    assert list(sig.parameters) == ["paper", "n_centres", "seed"]
    assert sig.parameters["seed"].default == 0


def test_assign_injective_over_1000_centres(
    book_1000: dict[int, dict[tuple[str, str], int]],
) -> None:
    assert len(book_1000) == 1000
    assert len({_hashable(s) for s in book_1000.values()}) == 1000


def test_every_symbol_within_its_alphabet(
    sample_paper_module: Paper, book_1000: dict[int, dict[tuple[str, str], int]]
) -> None:
    alphabets = sample_paper_module.alphabets()
    for symbols in book_1000.values():
        assert list(symbols) == sample_paper_module.positions()  # paper order, all positions
        for position, symbol in symbols.items():
            assert 0 <= symbol < alphabets[position]


def test_assign_is_deterministic(sample_paper: Paper) -> None:
    assert assign(sample_paper, 50, seed=7) == assign(sample_paper, 50, seed=7)


def test_seed_shifts_assignment(sample_paper: Paper) -> None:
    assert assign(sample_paper, 50, seed=0) != assign(sample_paper, 50, seed=1)


def test_save_load_round_trip(sample_paper: Paper, tmp_path: Path) -> None:
    book = assign(sample_paper, 20, seed=0)
    path = tmp_path / "codebook.json"
    save_codebook(book, path)
    assert load_codebook(path) == book
    assert "q1::intro" in path.read_text(encoding="utf-8")  # keyed by "qid::slot"


# --- the M5 fix: every position carries information --------------------------------------------
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_no_position_is_constant_over_1000_centres(sample_paper_module: Paper, seed: int) -> None:
    book = assign(sample_paper_module, 1000, seed=seed)
    constant = [
        pos for pos in sample_paper_module.positions() if len({book[c][pos] for c in book}) == 1
    ]
    assert constant == [], f"constant positions: {constant}"


# --- slot packing ------------------------------------------------------------------------------
def test_slot_groups_partition_every_position(sample_paper: Paper) -> None:
    groups = slot_groups(sample_paper)
    members = [pos for g in groups for pos in g.positions]
    assert sorted(members) == sorted(sample_paper.positions())
    assert len(members) == len(set(members))  # each position in exactly one group


def test_every_group_embeds_a_byte_and_lets_each_member_vary(sample_paper: Paper) -> None:
    alphabets = sample_paper.alphabets()
    for g in slot_groups(sample_paper):
        assert g.alphabets == tuple(alphabets[p] for p in g.positions)
        assert g.capacity == prod(g.alphabets) >= 256  # injective byte embedding
        assert g.alphabets[0] == max(g.alphabets)  # largest alphabet is most significant
        assert g.capacity // g.alphabets[0] <= 255  # its place value lets it vary


def test_byte_packing_round_trips_all_256_values(sample_paper: Paper) -> None:
    for g in slot_groups(sample_paper):
        seen = set()
        for value in range(256):
            symbols = byte_to_symbols(g, value)
            assert symbols_to_byte(g, symbols) == value
            seen.add(tuple(symbols[p] for p in g.positions))
        assert len(seen) == 256  # injective


def test_unpacking_never_guesses(sample_paper: Paper) -> None:
    g = slot_groups(sample_paper)[0]
    full = byte_to_symbols(g, 200)
    partial = {p: s for p, s in full.items() if p != g.positions[0]}
    assert symbols_to_byte(g, partial) is None  # a missing member erases the symbol
    out_of_range = {p: a - 1 for p, a in zip(g.positions, g.alphabets, strict=True)}
    assert symbols_to_byte(g, out_of_range) is None  # combination > 255 is not a codeword byte


def test_sample_paper_rs_shape(sample_paper: Paper) -> None:
    n, k = rs_shape(sample_paper, 1000)
    assert (n, k) == (7, 2)  # 7 GF(256) symbols; 2 suffice to name 1,000 centres


def test_too_many_centres_for_the_paper_is_refused(sample_paper: Paper) -> None:
    with pytest.raises(ValueError):
        rs_shape(sample_paper, 256**7)  # k would reach n: no parity left


# --- slot-level erasure decoding recovers the centre exactly ---------------------------------
@settings(max_examples=150, deadline=None)
@given(data=st.data())
def test_any_k_surviving_groups_recover_the_centre(
    sample_paper_module: Paper,
    book_1000: dict[int, dict[tuple[str, str], int]],
    data: st.DataObject,
) -> None:
    groups = slot_groups(sample_paper_module)
    n, k = rs_shape(sample_paper_module, 1000)
    centre = data.draw(st.integers(0, 999))
    lost = data.draw(st.lists(st.integers(0, n - 1), max_size=n - k, unique=True))
    erased = {pos for i in lost for pos in groups[i].positions}
    observed = {p: s for p, s in book_1000[centre].items() if p not in erased}

    recovered = complete_symbols(sample_paper_module, 1000, observed)
    assert recovered == book_1000[centre]
    assert [c for c, s in book_1000.items() if s == recovered] == [centre]


def test_one_missing_slot_erases_only_its_group(
    sample_paper_module: Paper, book_1000: dict[int, dict[tuple[str, str], int]]
) -> None:
    observed = dict(book_1000[42])
    del observed[("q1", "intro")]  # a single unread wording slot
    assert complete_symbols(sample_paper_module, 1000, observed) == book_1000[42]


def test_more_than_n_minus_k_lost_groups_is_refused(
    sample_paper_module: Paper, book_1000: dict[int, dict[tuple[str, str], int]]
) -> None:
    groups = slot_groups(sample_paper_module)
    n, k = rs_shape(sample_paper_module, 1000)
    keep = groups[: k - 1]  # fewer than k symbols survive
    observed = {p: book_1000[5][p] for g in keep for p in g.positions}
    with pytest.raises(RSDecodeError):
        complete_symbols(sample_paper_module, 1000, observed)
