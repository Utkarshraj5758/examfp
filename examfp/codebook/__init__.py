"""Codebooks: map centres to symbol vectors.

:mod:`~examfp.codebook.assign` is the practical mode (Reed-Solomon over GF(256),
:mod:`~examfp.codebook.rs`); :mod:`~examfp.codebook.tardos` is the provable mode;
:mod:`~examfp.codebook.crypto` seals codebooks at rest (ADR 0001, ADR 0002).
"""

from examfp.codebook.assign import assign, load_codebook, save_codebook

__all__ = ["assign", "load_codebook", "save_codebook"]
