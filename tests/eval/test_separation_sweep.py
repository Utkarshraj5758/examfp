"""The variant-separation sweep: its generators, its rule for the minimum, and the record."""

from __future__ import annotations

import random
from itertools import combinations

import pytest

from eval.separation import (
    DistanceRow,
    by_distance,
    contained_competitor,
    edit_competitor,
    measure_pair,
    prefix_competitor,
    suggest_min_distance,
    text_slots,
)
from examfp.fairness.check import Channel, slot_channel
from examfp.fairness.separation import (
    MEASURED_MIN_EDIT_DISTANCE,
    edit_distance,
    is_contained_pair,
    is_prefix_pair,
)
from examfp.models import Paper


def test_text_slots_are_the_23_slots_the_reader_matches_as_text(sample_paper: Paper) -> None:
    slots = text_slots(sample_paper)
    assert len(slots) == 23
    assert ("q1", "closing", "Show your working.") in slots
    assert all(name not in ("speed", "dims", "opts") for _q, name, _r in slots)


@pytest.mark.parametrize("reference", ["Show your working.", "₹", "km/h", "Calculate"])
@pytest.mark.parametrize("distance", [1, 4, 12])
def test_edit_competitors_hit_the_distance_with_no_containment(reference: str,
                                                               distance: int) -> None:
    competitor = edit_competitor(reference, distance, random.Random(f"{reference}{distance}"))
    assert competitor is not None
    assert edit_distance(reference, competitor) == distance
    assert not is_contained_pair(reference, competitor)


def test_shape_competitors_have_the_shape_of_their_family() -> None:
    rng = random.Random(0)
    assert prefix_competitor("Show your working.", 3, False, rng) == "Show your work."
    extended = prefix_competitor("Show your working.", 2, True, rng)
    assert extended is not None and is_prefix_pair("Show your working.", extended)
    for extend in (False, True):
        contained = contained_competitor("Show your working.", 2, extend, rng)
        assert contained is not None
        assert is_contained_pair("Show your working.", contained)
        assert not is_prefix_pair("Show your working.", contained)


def _rows(misreads: dict[int, int], reads: int = 69_000) -> list[DistanceRow]:
    return [DistanceRow(d, 69, reads, m, 0) for d, m in sorted(misreads.items())]


def test_the_minimum_is_the_start_of_the_zero_tail_with_enough_reads() -> None:
    assert suggest_min_distance(_rows({1: 9, 2: 3, 3: 0, 4: 0})) == 3
    # A misread further out moves it past that point.
    assert suggest_min_distance(_rows({1: 9, 2: 0, 3: 1, 4: 0, 5: 0})) == 4
    # Too few pooled reads to bound the rate at the calibrated MISREAD_RATE.
    assert suggest_min_distance(_rows({1: 9, 2: 0}, reads=1_000)) is None
    assert suggest_min_distance(_rows({1: 9, 2: 3})) is None


def test_the_recorded_sweep_result() -> None:
    # The measured edit-family tallies (eval/out/separation.csv, 2026-10-17, seed 0).
    recorded = {1: 391, 2: 125, 3: 47, 4: 14, 5: 18, 6: 3, 7: 0, 8: 0, 9: 1, 10: 14, 11: 0,
                12: 0}
    assert suggest_min_distance(_rows(recorded)) == MEASURED_MIN_EDIT_DISTANCE == 11


def test_seventeen_of_the_papers_29_text_pairs_fall_below_the_measured_minimum(
    sample_paper: Paper
) -> None:
    pairs = [(a.values[0], b.values[0])
             for q in sample_paper.questions for s in q.slots
             if slot_channel(s) in (Channel.WORDING, Channel.INSTRUCTION, Channel.UNIT_FORM)
             for a, b in combinations(s.variants, 2)]  # type: ignore[union-attr]
    assert len(pairs) == 29
    assert sum(edit_distance(a, b) < MEASURED_MIN_EDIT_DISTANCE for a, b in pairs) == 17


def test_the_m6_pair_is_confused_and_tallied(sample_paper: Paper) -> None:
    result = measure_pair(sample_paper, "q1", "closing", "Show your working.",
                          "Show your work.", 4000, random.Random(0), "m6")
    assert result.distance == 3 and result.prefix and result.contained
    assert result.misreads >= 1  # deterministic for this seed
    rows = by_distance([result], "m6")
    assert rows == [DistanceRow(3, 1, 4000, result.misreads, result.erasures)]
