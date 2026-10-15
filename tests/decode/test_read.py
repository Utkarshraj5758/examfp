"""Tests for the leak reader."""

from __future__ import annotations

import pytest

from examfp.codebook.assign import assign
from examfp.decode.read import read_leak, split_chunks
from examfp.models import Paper


@pytest.fixture
def book(sample_paper: Paper) -> dict[int, dict[tuple[str, str], int]]:
    return assign(sample_paper, 1000, seed=0)


def _render(paper: Paper, symbols: dict[tuple[str, str], int]) -> str:
    from examfp.cli import render_text

    return render_text(paper, symbols)


def test_split_chunks_on_blank_and_markers() -> None:
    text = "1. first line\nmore\n\n2) second\n\nQ3 third"
    chunks = split_chunks(text)
    assert len(chunks) == 3
    assert chunks[0].startswith("1. first")
    assert chunks[2].startswith("Q3 third")


def test_recovers_group_and_unit_and_option(sample_paper: Paper, book) -> None:  # type: ignore[no-untyped-def]
    text = _render(sample_paper, book[500])
    obs = read_leak(text, sample_paper)
    # Group numeric slot recovered to the true symbol.
    assert obs[("q1", "speed")][0] == book[500][("q1", "speed")]
    # Unit-form slot recovered.
    assert obs[("q1", "unit")][0] == book[500][("q1", "unit")]
    # Option-order slot recovered.
    assert obs[("q2", "opts")][0] == book[500][("q2", "opts")]


def test_all_recovered_symbols_match_truth(sample_paper: Paper, book) -> None:  # type: ignore[no-untyped-def]
    truth = book[321]
    obs = read_leak(_render(sample_paper, truth), sample_paper)
    assert obs  # something was recovered
    for position, (symbol, conf) in obs.items():
        assert symbol == truth[position]
        assert 0.0 < conf <= 1.0


def test_never_guesses_when_numbers_erased(sample_paper: Paper, book) -> None:  # type: ignore[no-untyped-def]
    # A chunk that matches q1 by words but with its group numbers removed:
    text = (
        "Rohan drives some distance in some hours.\n"
        "Calculate his average speed in km/h. Show your working."
    )
    obs = read_leak(text, sample_paper)
    # The group slot cannot be recovered and is simply absent (no fallback).
    assert ("q1", "speed") not in obs
    # Wording/units that are literally present may still be recovered.
    assert ("q1", "unit") in obs


def test_lorem_recovers_nothing(sample_paper: Paper) -> None:
    lorem = "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod."
    assert read_leak(lorem, sample_paper) == {}
