"""Tests for the decision rule: consistency gate, read floor, collusion hypothesis."""

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
    # Just the first question: its 5 slots allow only 2*7*3*2*2 = 168 combinations,
    # so several of the 1,000 centres share any one of them -> ambiguous.
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


# --- M5.5: consistency gate ---------------------------------------------------------------------
# Ten positions. A colluded leak: p0-p4 from A (all 0), p5-p9 from B (all 1).
# INNOCENT matches 8 of the 10 read slots: the nearest single centre, yet it
# never sent anything. The ungated rule names INNOCENT with margin 7.2 (see
# tests/eval/test_baselines.py); the gate must not.
P = [("q", f"p{i}") for i in range(10)]
A, B, INNOCENT = 1, 2, 3
HYBRID = {p: (0 if i < 5 else 1, 1.0) for i, p in enumerate(P)}
TOY = {
    A: {p: 0 for p in P},
    B: {p: 1 for p in P},
    INNOCENT: {p: v for p, v in zip(P, [0, 0, 0, 0, 2, 1, 1, 1, 1, 2], strict=True)},
    **{c: {p: 9 for p in P} for c in range(10, 30)},  # unrelated centres
}
STRICT = {"misread_rate": 0.0, "min_read_slots": 5}


def test_gate_runs_before_margin_and_never_names_the_nearest_innocent() -> None:
    result = score(HYBRID, TOY, **STRICT)
    assert result.outcome is not Outcome.IDENTIFIED
    assert result.consistent == 0  # nobody explains all ten slots


def test_emptied_gate_above_the_floor_is_multi_source() -> None:
    result = score(HYBRID, TOY, **STRICT)
    assert result.outcome is Outcome.MULTI_SOURCE_SUSPECTED


def test_the_verdict_names_nobody() -> None:
    result = score(HYBRID, TOY, **STRICT)
    assert result.outcome is Outcome.MULTI_SOURCE_SUSPECTED
    assert not hasattr(result, "named_pair")  # the pair is not part of any verdict


def test_pair_hypothesis_is_opt_in_and_unique() -> None:
    from examfp.decode.score import unique_pair_hypothesis

    assert unique_pair_hypothesis(HYBRID, TOY, **STRICT) == (A, B)


def test_pair_hypothesis_none_when_ambiguous() -> None:
    from examfp.decode.score import unique_pair_hypothesis

    toy = dict(TOY)  # INNOCENT now explains p4 too: {A, B} and {INNOCENT, B} both cover
    toy[INNOCENT] = {**TOY[INNOCENT], P[4]: 0}
    assert score(HYBRID, toy, **STRICT).outcome is Outcome.MULTI_SOURCE_SUSPECTED
    assert unique_pair_hypothesis(HYBRID, toy, **STRICT) is None


def test_pair_hypothesis_never_names_three_or_more() -> None:
    from examfp.decode.score import unique_pair_hypothesis

    q = [("q", f"t{i}") for i in range(9)]
    toy = {
        1: {x: 0 for x in q},
        2: {x: 1 for x in q},
        3: {x: 2 for x in q},
        **{c: {x: 9 for x in q} for c in range(10, 30)},
    }
    hybrid = {x: (i // 3, 1.0) for i, x in enumerate(q)}  # only a triple explains it
    assert score(hybrid, toy, **STRICT).outcome is Outcome.MULTI_SOURCE_SUSPECTED
    assert unique_pair_hypothesis(hybrid, toy, **STRICT) is None


def test_pair_hypothesis_needs_an_emptied_gate_and_the_floor() -> None:
    from examfp.decode.score import unique_pair_hypothesis

    single = {p: (TOY[A][p], 1.0) for p in P}  # A explains it alone: not multi-source
    assert unique_pair_hypothesis(single, TOY, **STRICT) is None
    assert unique_pair_hypothesis(HYBRID, TOY, misread_rate=0.0, min_read_slots=11) is None


def test_multi_source_needs_the_read_floor() -> None:
    result = score(HYBRID, TOY, misread_rate=0.0, min_read_slots=11)
    assert result.outcome is Outcome.INSUFFICIENT


def test_exhausted_pair_search_names_nobody() -> None:
    from examfp.decode.score import unique_pair_hypothesis

    assert score(HYBRID, TOY, **STRICT, cover_node_budget=1).outcome is (
        Outcome.MULTI_SOURCE_SUSPECTED  # the signal does not need the search
    )
    assert unique_pair_hypothesis(HYBRID, TOY, **STRICT, cover_node_budget=1) is None


def test_single_source_leak_is_identified() -> None:
    leak = {p: (TOY[A][p], 1.0) for p in P}
    result = score(leak, TOY, **STRICT)
    assert result.outcome is Outcome.IDENTIFIED
    assert result.ranked[0][0] == A and result.consistent == 1


def test_read_floor_blocks_identification_on_thin_leaks() -> None:
    leak = {p: (TOY[B][p], 1.0) for p in P[:4]}
    assert score(leak, TOY, misread_rate=0.0, min_read_slots=4).outcome is Outcome.IDENTIFIED
    assert score(leak, TOY, misread_rate=0.0, min_read_slots=5).outcome is Outcome.INSUFFICIENT


def test_tolerance_comes_from_the_calibrated_misread_rate() -> None:
    from examfp.decode.calibrate import mismatch_tolerance

    leak = {p: (TOY[A][p], 1.0) for p in P}
    leak[P[3]] = (7, 1.0)  # one misread slot in a genuine leak from A
    strict = score(leak, TOY, misread_rate=0.0, min_read_slots=5)
    assert strict.tolerance == 0 and strict.outcome is not Outcome.IDENTIFIED
    lenient = score(leak, TOY, misread_rate=0.01, false_rejection_budget=1e-3, min_read_slots=5)
    assert lenient.tolerance == mismatch_tolerance(10, 0.01, 1e-3) >= 1
    assert lenient.outcome is Outcome.IDENTIFIED and lenient.ranked[0][0] == A


def test_tied_survivors_are_insufficient() -> None:
    twin = {**TOY, 99: dict(TOY[A])}  # a second centre identical on every read slot
    leak = {p: (TOY[A][p], 1.0) for p in P}
    result = score(leak, twin, **STRICT)
    assert result.consistent == 2 and result.outcome is Outcome.INSUFFICIENT


def test_consistent_centres_rank_first() -> None:
    leak = {p: (TOY[A][p], 1.0) for p in P}
    result = score(leak, TOY, **STRICT)
    assert [c for c, _ in result.ranked[: result.consistent]] == [A]


def test_calibrated_defaults_are_used_when_not_overridden() -> None:
    import importlib

    score_module = importlib.import_module("examfp.decode.score")

    leak = {p: (TOY[A][p], 1.0) for p in P}
    result = score(leak, TOY)
    assert result.tolerance == score_module.mismatch_tolerance(
        10, score_module.MISREAD_RATE, score_module.FALSE_REJECTION_BUDGET
    )
    assert score_module.MIN_READ_SLOTS >= 1


# --- end to end on the real codebook --------------------------------------------------------
def test_colluded_leaks_never_identify_an_innocent(sample_paper: Paper, book) -> None:  # type: ignore[no-untyped-def]
    import random

    from examfp.attacks import collude, crop, retype, typos

    rng = random.Random(2024)
    for _ in range(60):
        coalition = rng.sample(range(1000), rng.randint(2, 5))
        hybrid = collude([book[c] for c in coalition], rng, strategy="minority")
        text = _render(sample_paper, hybrid)
        leak = typos(retype(crop(text, rng.randint(2, 8), rng)), 0.03, rng)
        result = score(read_leak(leak, sample_paper), book)
        if result.outcome is Outcome.IDENTIFIED:
            assert result.ranked[0][0] in coalition, "an innocent centre was identified"
