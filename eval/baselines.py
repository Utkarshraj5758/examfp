"""Superseded codebooks and decision rules, kept only for before/after benchmarks.

Not used by the library or the CLI.

* ``mixed_radix_assign`` is the crude M3 assignment, preserved verbatim: it is
  position-dependent (NOTES.md, F3), which M5's Reed-Solomon codebook removes.
* ``score_ungated`` is the M3-M5 decision rule, preserved verbatim: margin-only,
  so under collusion it can name an innocent centre with a large margin
  (NOTES.md, M5.5), which the consistency gate removes.
"""

from __future__ import annotations

from collections.abc import Mapping
from math import prod

import numpy as np

from examfp.decode.score import Outcome, ScoreResult
from examfp.models import Paper

Symbols = dict[tuple[str, str], int]
Codebook = dict[int, Symbols]


def mixed_radix_assign(paper: Paper, n_centres: int, seed: int = 0) -> Codebook:
    """The M3 crude assignment: affine scramble, then mixed radix over positions.

    Guarantees: each symbol is within its position's alphabet and the mapping is
    injective while ``n_centres`` stays below ``prod(paper.alphabets())``. It does
    NOT spread information: high-order positions are constant for small
    ``n_centres``.
    """
    positions = paper.positions()
    alphabets = paper.alphabets()
    radices = [alphabets[pos] for pos in positions]
    modulus = prod(radices)

    book: Codebook = {}
    for c in range(n_centres):
        x = (c * 617 + 37 + seed) % modulus
        digits: Symbols = {}
        for pos, radix in zip(reversed(positions), reversed(radices), strict=True):
            digits[pos] = x % radix
            x //= radix
        book[c] = {pos: digits[pos] for pos in positions}  # restore position order
    return book


_MISMATCH_PENALTY = 1.4
_MARGIN_THRESHOLD = 0.5


def score_ungated(
    observations: Mapping[tuple[str, str], tuple[int, float]],
    codebook: Mapping[int, Mapping[tuple[str, str], int]],
) -> ScoreResult:
    """The M3-M5 decision rule: margin over all centres, no consistency gate.

    Guarantees nothing under collusion; kept to show the before/after.
    """
    positions = list(observations)
    if not positions or not codebook:
        return ScoreResult(ranked=[], margin=0.0, positions_used=0, outcome=Outcome.NO_MATCH)

    centres = list(codebook)
    obs_symbols = np.array([observations[p][0] for p in positions], dtype=np.int64)
    obs_conf = np.array([observations[p][1] for p in positions], dtype=np.float64)
    matrix = np.array(
        [[codebook[c].get(p, -1) for p in positions] for c in centres], dtype=np.int64
    )

    match = matrix == obs_symbols  # (n_centres, n_positions)
    contrib = np.where(match, obs_conf, -_MISMATCH_PENALTY * obs_conf)
    scores = contrib.sum(axis=1)

    order = np.argsort(-scores, kind="stable")
    ranked = [(centres[i], float(scores[i])) for i in order]

    top = scores[order[0]]
    n_top = int(np.count_nonzero(scores == top))
    second = float(scores[order[1]]) if len(order) > 1 else float("-inf")
    margin = float(top) - second

    if n_top > 1:
        outcome = Outcome.INSUFFICIENT
    elif margin > _MARGIN_THRESHOLD:
        outcome = Outcome.IDENTIFIED
    else:
        outcome = Outcome.INSUFFICIENT

    return ScoreResult(
        ranked=ranked,
        margin=margin,
        positions_used=len(positions),
        outcome=outcome,
    )
