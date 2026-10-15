"""Superseded codebooks, kept only so benchmarks can report before/after.

Not used by the library or the CLI. ``mixed_radix_assign`` is the crude M3
assignment, preserved verbatim: it is position-dependent (NOTES.md, F3), which
is the weakness M5's Reed-Solomon codebook removes.
"""

from __future__ import annotations

from math import prod

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
