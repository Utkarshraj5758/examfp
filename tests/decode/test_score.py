"""Tests for scoring and the three acceptance outcomes."""

from __future__ import annotations

import pytest

from examfp.codebook.assign import assign
from examfp.decode.read import read_leak
from examfp.decode.score import Outcome, score
from examfp.models import Paper


@pytest.fixture
def book(sample_paper: Paper) -> dict[int, dict[tuple[str, str], int]]:
    return assign(sample_paper, 1000, seed=0)


def _render(paper: Paper, symbols: dict[tuple[str, str], int]) -> str:
    from examfp.cli import render_text

    return render_text(paper, symbols)


def test_clean_12_line_leak_identifies_centre(sample_paper: Paper, book) -> None:  # type: ignore[no-untyped-def]
    target = 500
    leak = "\n".join(_render(sample_paper, book[target]).splitlines()[-12:])
    assert len(leak.splitlines()) == 12
    result = score(read_leak(leak, sample_paper), book)
    assert result.outcome is Outcome.IDENTIFIED
    assert result.ranked[0][0] == target
    assert result.margin > 0.5


def test_lorem_yields_no_match(sample_paper: Paper, book) -> None:  # type: ignore[no-untyped-def]
    lorem = (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."
    )
    result = score(read_leak(lorem, sample_paper), book)
    assert result.outcome is Outcome.NO_MATCH
    assert result.positions_used == 0
    assert result.ranked == []


def test_one_question_leak_is_insufficient_not_wrong(sample_paper: Paper, book) -> None:  # type: ignore[no-untyped-def]
    target = 500
    # Just the first question (near-constant across centres -> ambiguous).
    q1 = "\n".join(_render(sample_paper, book[target]).splitlines()[3:5])
    result = score(read_leak(q1, sample_paper), book)
    assert result.outcome is Outcome.INSUFFICIENT
    assert result.positions_used > 0


def test_score_rewards_matches_penalises_mismatches(sample_paper: Paper) -> None:
    # Two centres differing at one position; an observation of centre A's symbol
    # should rank A above B by 1.0 + 1.4 = 2.4 (match reward + avoided penalty).
    codebook = {
        1: {("q1", "lead"): 0, ("q2", "opts"): 5},
        2: {("q1", "lead"): 1, ("q2", "opts"): 5},
    }
    obs = {("q1", "lead"): (0, 1.0)}
    result = score(obs, codebook)
    a = dict(result.ranked)
    assert a[1] == pytest.approx(1.0)
    assert a[2] == pytest.approx(-1.4)


def test_tie_at_top_is_insufficient() -> None:
    codebook = {1: {("q1", "lead"): 0}, 2: {("q1", "lead"): 0}}
    result = score({("q1", "lead"): (0, 1.0)}, codebook)
    assert result.outcome is Outcome.INSUFFICIENT
    assert result.margin == pytest.approx(0.0)
