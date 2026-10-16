"""Decide whether a leak names a centre: consistency gate, read floor, then margin.

Each centre is scored over the slots actually read: ``+confidence`` per
matching slot, ``-1.4 * confidence`` per mismatch (numpy over the whole centre
matrix). The score ranks; it does not decide. The decision runs in this order:

1. **Consistency gate.** A genuine single-source leak agrees with its source on
   every slot read, apart from reader misreads, so a centre with more than
   ``tolerance`` mismatching slots cannot be the sole source and is eliminated.
   ``tolerance`` comes from the reader's calibrated misread rate
   (:func:`examfp.decode.calibrate.mismatch_tolerance`).
2. **Read floor.** No verdict naming any centre is given on fewer than
   ``min_read_slots`` read slots; thin leaks match innocents by chance.
3. **Margin among survivors.** ``IDENTIFIED`` only when one surviving centre
   is ahead of every other centre by more than ``MARGIN_THRESHOLD``.
4. **Multi-source signal.** If the gate eliminates every centre and the read
   floor is cleared, the outcome is ``MULTI_SOURCE_SUSPECTED``: no single
   centre is consistent with the leak. It names nobody, except that when exactly
   one *pair* of centres jointly explains every read slot (marking assumption)
   the pair is attached as **a hypothesis for investigation, never an
   accusation**. Sets of three or more are never named: in M5.5 every such set
   observed (11 of 11) implicated an uninvolved centre.

   The signal assumes ``tolerance`` matches the reader. Misreads beyond it, or a
   leak from outside this codebook, also empty the gate - hence recalibration on
   every reader change (ADR 0003).

Why the gate exists: the slot score measures a different distance from the one
Reed-Solomon protects (symbols). Under collusion, a hybrid leak can sit nearer
an innocent centre in slots than either colluder (ADR 0003). Without the gate
the old rule named innocents with margins up to 12.

Guarantees are empirical, not proved: see NOTES.md (M5.5) for the measured
false-identification rates, single-source and colluded. A provable collusion
bound is the provable mode's job (Tardos, ADR 0001).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from examfp.decode.calibrate import mismatch_tolerance

Observations = Mapping[tuple[str, str], tuple[int, float]]
Codebook = Mapping[int, Mapping[tuple[str, str], int]]

MISMATCH_PENALTY = 1.4
MARGIN_THRESHOLD = 0.5

# --- calibrated parameters (procedure: NOTES.md, M5.5; ADR 0003) -----------------------------
# Upper 95% bound on the reader's per-slot misread rate. Measured 2026-10-16:
# 0 misreads in 104,026 read slots (fuzzy reader; crops 1-8, retype, 3% typos).
# Re-measure whenever the reader changes (OCR in M7, paraphrase in M8-M10):
# `python -m eval.bench` prints it; then re-check the floor and collusion rows.
MISREAD_RATE = 2.88e-5
# Accepted probability that a genuine leak is refused because of misreads alone.
# With the rate above this gives a mismatch tolerance of 0 up to 31 reads.
FALSE_REJECTION_BUDGET = 1e-3
# Fewest read slots for any verdict naming centres. Measured 2026-10-16 with the
# gate at the tolerance above and no floor: innocents were identified at up to 10
# slots read (seeds 1 and 7) and never from 11 up - 0 in 5,804 leaks, 95% upper
# bound 0.052%. Sample paper, 1,000 centres; re-measure for other operating points.
MIN_READ_SLOTS = 11
# A multi-source result may name a pair, never a larger set (M5.5: every set of
# 3+ observed implicated an uninvolved centre). Budget for the pair search; an
# exhausted search names nobody.
NAMED_SET_SIZE = 2
COVER_NODE_BUDGET = 20_000


class Outcome(StrEnum):
    IDENTIFIED = "IDENTIFIED"
    MULTI_SOURCE_SUSPECTED = "MULTI_SOURCE_SUSPECTED"  # names nobody but a hypothesis pair
    INSUFFICIENT = "INSUFFICIENT"
    NO_MATCH = "NO_MATCH"


@dataclass(frozen=True)
class ScoreResult:
    """A decision plus the evidence behind it.

    ``ranked`` lists the consistent centres first (by score), then the rest; when
    the outcome is ``IDENTIFIED`` the named centre is ``ranked[0][0]``.
    ``named_pair`` holds exactly two centre ids, and only for
    ``MULTI_SOURCE_SUSPECTED`` when one pair uniquely explains the reads;
    otherwise it is empty. It is a hypothesis, never an accusation.
    """

    ranked: list[tuple[int, float]]
    margin: float
    positions_used: int
    outcome: Outcome
    consistent: int = 0
    tolerance: int = 0
    named_pair: tuple[int, ...] = ()


class _Stop(Exception):
    """Ends the covering-set search early (ambiguous or over budget)."""


def _minimal_covers(
    match: np.ndarray, tolerance: int, max_size: int, node_budget: int
) -> list[frozenset[int]] | None:
    """Smallest sets of centres that jointly explain all but ``tolerance`` read slots.

    Returns up to two distinct minimal covers (two means ambiguous), ``[]`` if no
    set of at most ``max_size`` centres explains the slots, or ``None`` if the
    search ran out of budget. Exact branch and bound: some member must hold the
    most constrained unexplained slot, unless that slot is a tolerated misread.
    """
    n_centres, reads = match.shape
    words = -(-reads // 64)
    packed = np.zeros((n_centres, words), dtype=np.uint64)
    masks = [0] * n_centres
    holders: list[list[int]] = []
    for j in range(reads):
        rows = np.flatnonzero(match[:, j])
        packed[rows, j // 64] |= np.uint64(1 << (j % 64))
        holders.append([int(c) for c in rows])
        for c in rows:
            masks[int(c)] |= 1 << j

    def coverage(uncovered: int) -> np.ndarray:
        u = np.array([(uncovered >> (64 * w)) & ((1 << 64) - 1) for w in range(words)],
                     dtype=np.uint64)
        return np.bitwise_count(packed & u).sum(axis=1)

    nodes = 0

    def search(
        uncovered: int, chosen: tuple[int, ...], left: int, skips: int, found: set[frozenset[int]]
    ) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > node_budget:
            raise _Stop
        remaining = uncovered.bit_count()
        if remaining <= skips:
            found.add(frozenset(chosen))
            if len(found) > 1:
                raise _Stop
            return
        if left == 0:
            return
        cov = coverage(uncovered)
        if left * int(cov.max()) < remaining - skips:
            return  # no `left` centres can explain what remains
        if left == 1:
            for c in np.flatnonzero(remaining - cov <= skips):
                if int(c) not in chosen:
                    found.add(frozenset((*chosen, int(c))))
                    if len(found) > 1:
                        raise _Stop
            return
        bits = [j for j in range(reads) if uncovered >> j & 1]
        j = min(bits, key=lambda b: len(holders[b]))
        for c in holders[j]:
            if c not in chosen:
                search(uncovered & ~masks[c], (*chosen, c), left - 1, skips, found)
        if skips:
            search(uncovered & ~(1 << j), chosen, left, skips - 1, found)

    for size in range(2, max_size + 1):
        found: set[frozenset[int]] = set()
        try:
            search((1 << reads) - 1, (), size, tolerance, found)
        except _Stop:
            return None if nodes > node_budget else list(found)
        if found:
            return list(found)
    return []


def score(
    observations: Observations,
    codebook: Codebook,
    *,
    misread_rate: float = MISREAD_RATE,
    false_rejection_budget: float = FALSE_REJECTION_BUDGET,
    min_read_slots: int = MIN_READ_SLOTS,
    cover_node_budget: int = COVER_NODE_BUDGET,
) -> ScoreResult:
    """Rank centres against ``observations`` and decide an :class:`Outcome`.

    Guarantees: ``IDENTIFIED`` only for a centre that passes the consistency gate,
    on at least ``min_read_slots`` reads, ahead of every other centre by more than
    ``MARGIN_THRESHOLD``; ``MULTI_SOURCE_SUSPECTED`` whenever no centre passes
    the gate and the floor is met, with ``named_pair`` set only when exactly one
    pair explains the reads; otherwise ``INSUFFICIENT`` (or ``NO_MATCH`` with no
    reads). Never a best guess, never a named set of three or more. Keyword
    arguments exist for calibration and tests; production uses the defaults.
    """
    positions = list(observations)
    if not positions or not codebook:
        return ScoreResult(ranked=[], margin=0.0, positions_used=0, outcome=Outcome.NO_MATCH)

    centres = list(codebook)
    reads = len(positions)
    obs_symbols = np.array([observations[p][0] for p in positions], dtype=np.int64)
    obs_conf = np.array([observations[p][1] for p in positions], dtype=np.float64)
    matrix = np.array(
        [[codebook[c].get(p, -1) for p in positions] for c in centres], dtype=np.int64
    )
    match = matrix == obs_symbols  # (n_centres, n_reads)
    scores = np.where(match, obs_conf, -MISMATCH_PENALTY * obs_conf).sum(axis=1)

    tolerance = mismatch_tolerance(reads, misread_rate, false_rejection_budget)
    consistent = (~match).sum(axis=1) <= tolerance
    order = np.lexsort((-scores, ~consistent))  # consistent first, then by score
    ranked = [(centres[i], float(scores[i])) for i in order]
    n_consistent = int(consistent.sum())
    floor_met = reads >= min_read_slots

    if n_consistent == 0:
        if not floor_met:
            return ScoreResult(ranked, 0.0, reads, Outcome.INSUFFICIENT, 0, tolerance)
        pair: tuple[int, ...] = ()
        pairs = _minimal_covers(match, tolerance, NAMED_SET_SIZE, cover_node_budget)
        if pairs is not None and len(pairs) == 1 and len(pairs[0]) == NAMED_SET_SIZE:
            pair = tuple(sorted(centres[i] for i in pairs[0]))
        return ScoreResult(ranked, 0.0, reads, Outcome.MULTI_SOURCE_SUSPECTED, 0, tolerance, pair)

    top = float(scores[order[0]])
    runner_up = float(scores[order[1]]) if len(order) > 1 else float("-inf")
    margin = top - runner_up
    tied = n_consistent > 1 and runner_up == top
    named = floor_met and not tied and margin > MARGIN_THRESHOLD
    outcome = Outcome.IDENTIFIED if named else Outcome.INSUFFICIENT
    return ScoreResult(ranked, margin, reads, outcome, n_consistent, tolerance)
