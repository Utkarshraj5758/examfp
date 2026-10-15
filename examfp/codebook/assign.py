"""Assign each centre a symbol vector — deliberately crude.

No Tardos, no Reed-Solomon, no encryption, no ML.  Each centre id ``c`` is
scrambled by a fixed affine map and expanded in mixed radix over the paper's
positions (:meth:`Paper.positions`) and their alphabets.  Mixed-radix expansion
is a bijection on ``[0, prod(alphabets))``, so distinct scrambled ids give
distinct symbol vectors — injective for any centre count below the codebook
size.
"""

from __future__ import annotations

import json
from math import prod
from pathlib import Path

from examfp.models import Paper

Symbols = dict[tuple[str, str], int]
Codebook = dict[int, Symbols]

_KEY_SEP = "::"


def assign(paper: Paper, n_centres: int, seed: int = 0) -> Codebook:
    """Return ``{centre_id: {(qid, slot): symbol}}`` for ``n_centres`` centres.

    Guarantees: each symbol is within its position's alphabet; the mapping is
    injective while ``n_centres`` stays below ``prod(paper.alphabets())``.
    ``seed`` shifts the affine scramble (``seed=0`` gives the plain ``c*617+37``).
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


def save_codebook(codebook: Codebook, path: str | Path) -> None:
    """Write ``codebook`` to JSON, inner keys as ``"qid::slot"``."""
    data = {
        str(centre): {f"{qid}{_KEY_SEP}{slot}": sym for (qid, slot), sym in symbols.items()}
        for centre, symbols in codebook.items()
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_codebook(path: str | Path) -> Codebook:
    """Read a codebook written by :func:`save_codebook`."""
    data: dict[str, dict[str, int]] = json.loads(Path(path).read_text(encoding="utf-8"))
    book: Codebook = {}
    for centre, symbols in data.items():
        restored: Symbols = {}
        for key, sym in symbols.items():
            qid, slot = key.split(_KEY_SEP, 1)
            restored[(qid, slot)] = sym
        book[int(centre)] = restored
    return book
