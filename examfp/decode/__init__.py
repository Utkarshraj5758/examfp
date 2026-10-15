"""Crude leak decoder: read symbols from a leaked paper and score centres.

rapidfuzz only — no embeddings, no ML.
"""

from examfp.decode.read import read_leak
from examfp.decode.score import Outcome, ScoreResult, score

__all__ = ["Outcome", "ScoreResult", "read_leak", "score"]
