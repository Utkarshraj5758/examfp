"""Leak decoder: read symbols from a leaked paper, then decide.

``read_leak`` recovers slot symbols (rapidfuzz only, no ML; unreadable slots are
absent, never guessed). ``score`` decides: consistency gate, read floor, margin,
and a collusion hypothesis (ADR 0003).
"""

from examfp.decode.read import read_leak
from examfp.decode.score import Outcome, ScoreResult, score

__all__ = ["Outcome", "ScoreResult", "read_leak", "score"]
