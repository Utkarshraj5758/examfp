"""Score centres against recovered observations.

A centre earns ``+confidence`` for each observed position whose symbol matches
and ``-1.4 * confidence`` for each that disagrees, summed with numpy over the
whole centre matrix.  The result is only IDENTIFIED when the winner is unique
and clear; otherwise it refuses (INSUFFICIENT / NO_MATCH) — never a best guess.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

Observations = Mapping[tuple[str, str], tuple[int, float]]
Codebook = Mapping[int, Mapping[tuple[str, str], int]]

_MISMATCH_PENALTY = 1.4
_MARGIN_THRESHOLD = 0.5


class Outcome(StrEnum):
    IDENTIFIED = "IDENTIFIED"
    INSUFFICIENT = "INSUFFICIENT"
    NO_MATCH = "NO_MATCH"


@dataclass(frozen=True)
class ScoreResult:
    ranked: list[tuple[int, float]]
    margin: float
    positions_used: int
    outcome: Outcome


def score(observations: Observations, codebook: Codebook) -> ScoreResult:
    """Rank centres against ``observations`` and decide an :class:`Outcome`."""
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
