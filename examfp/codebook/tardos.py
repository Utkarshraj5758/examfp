"""M2: the Tardos coding layer (replaces the crude affine :mod:`assign`).

This is a faithful reproduction of Tardos's probabilistic fingerprinting code
(G. Tardos, "Optimal Probabilistic Fingerprint Codes", STOC 2003) — not a new
construction:

* ``k = ceil(ln(n / eps))`` (Tardos's ``k = ceil(ln(1/eps_1))`` with the union
  bound ``eps_1 = eps / n``), code length ``m = 100 * c^2 * k`` (literal constant),
* per-position bias ``p_i = sin^2(r_i)`` with ``r_i`` uniform on
  ``[t', pi/2 - t']``, ``t' = arcsin(sqrt(t))`` and cutoff ``t = 1/(300 c)``
  (the arcsine distribution on ``[t, 1-t]``),
* codeword bit ``X_{j,i} = 1`` with probability ``p_i``,
* one-sided accusation score ``S_j = sum_{i: y_i=1} g(X_{j,i}, p_i)`` with
  ``g(1,p)=sqrt((1-p)/p)``, ``g(0,p)=-sqrt(p/(1-p))``; accuse when ``S_j > Z``,
  ``Z = 20 * c * k``.

Until 2026-10-17 the code used the unrounded ``ln(n / eps)`` in place of ``k``,
which made ``m`` and ``Z`` smaller than the proof requires (NOTES.md, F1).

Adapting the binary code to our q-ary channel: each fingerprint position of a
paper carries ``floor(log2(alphabet))`` codeword bits, packed MSB-first into the
slot symbol.  Because one paper holds only ~50 bits while ``m`` is thousands, a
centre's codeword is spread across ``k = ceil(m / bits_per_paper)`` papers in an
exam *session* (multi-paper layering).

Security/determinism (per project conventions): the bias vector ``p`` and the
codeword matrix ``X`` are secrets held only in memory — never written to disk or
logged.  All randomness comes from an explicitly seeded numpy generator.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import ceil, floor, log, log2

import numpy as np

from examfp.models import Paper

Symbols = dict[tuple[str, str], int]
Position = tuple[str, str]


def position_bit_widths(paper: Paper) -> list[tuple[Position, int]]:
    """Return ``(position, bit_width)`` where ``width = floor(log2(alphabet))``."""
    alphabets = paper.alphabets()
    return [(pos, floor(log2(alphabets[pos]))) for pos in paper.positions()]


def bits_per_paper(paper: Paper) -> int:
    """Total codeword bits one rendered paper can carry."""
    return sum(width for _, width in position_bit_widths(paper))


@dataclass
class TardosCode:
    """A built Tardos code for ``n_centres`` over a paper's bit layout.

    ``biases`` and ``codewords`` are secrets: do not serialise or log them.
    """

    paper: Paper
    n_centres: int
    c: int
    eps: float
    seed: int
    m: int
    k: int
    t: float
    threshold: float
    layout: list[tuple[Position, int]] = field(repr=False)
    biases: np.ndarray = field(repr=False)  # secret p, shape (m,)
    codewords: np.ndarray = field(repr=False)  # secret X, shape (n_centres, m) bool

    # -- construction ---------------------------------------------------------
    @classmethod
    def build(
        cls, paper: Paper, n_centres: int, c: int, eps: float, seed: int
    ) -> TardosCode:
        """Build the code (biases + codewords) from a seeded RNG."""
        if n_centres < 1 or c < 1 or not 0.0 < eps < 1.0:
            raise ValueError("require n_centres>=1, c>=1, 0<eps<1")
        # Tardos's k = ceil(ln(1/eps_1)); the union bound over n centres gives
        # eps_1 = eps / n. The ceiling comes before the multiplication: without it m
        # and Z fall short of what the proof requires.
        log_factor = ceil(log(n_centres / eps))
        m = 100 * c * c * log_factor
        t = 1.0 / (300 * c)
        threshold = float(20 * c * log_factor)
        layout = position_bit_widths(paper)
        bpp = sum(w for _, w in layout)
        if bpp < 1:
            raise ValueError("paper carries no codeword bits")
        k = ceil(m / bpp)

        rng = np.random.default_rng(seed)
        t_prime = np.arcsin(np.sqrt(t))
        r = rng.uniform(t_prime, np.pi / 2.0 - t_prime, size=m)
        biases = np.sin(r) ** 2  # arcsine-distributed on [t, 1-t]
        # Codeword matrix: X_{j,i} = 1 with probability p_i (independent stream).
        draws = rng.random((n_centres, m))
        codewords = draws < biases  # broadcast p over rows

        return cls(
            paper=paper,
            n_centres=n_centres,
            c=c,
            eps=eps,
            seed=seed,
            m=m,
            k=k,
            t=t,
            threshold=threshold,
            layout=layout,
            biases=biases,
            codewords=codewords,
        )

    # -- encoding (replaces assign) ------------------------------------------
    def session_symbols(self, centre: int) -> list[Symbols]:
        """Return the ``k`` per-paper symbol dicts for one centre's session.

        Bit ``0..m-1`` of the centre's codeword is laid across the session's
        papers in order; bit-slots past ``m`` are padded with 0.  Every packed
        symbol is ``< 2**width <= alphabet``, so each dict is a valid render
        vector for :func:`examfp.render.render_pdf`.
        """
        bits = self.codewords[centre]
        session: list[Symbols] = []
        idx = 0
        for _ in range(self.k):
            symbols: Symbols = {}
            for pos, width in self.layout:
                value = 0
                for _b in range(width):
                    bit = int(bits[idx]) if idx < self.m else 0
                    value = (value << 1) | bit
                    idx += 1
                symbols[pos] = value
            session.append(symbols)
        return session

    def assign(self) -> dict[int, list[Symbols]]:
        """Return ``{centre: [per-paper symbols, ...]}`` for every centre."""
        return {c: self.session_symbols(c) for c in range(self.n_centres)}

    # -- accusation -----------------------------------------------------------
    def observed_to_bits(
        self, paper_index: int, observations: Mapping[Position, tuple[int, float]]
    ) -> dict[int, int]:
        """Map decoded symbols from session paper ``paper_index`` to codeword bits.

        ``observations`` is the output of :func:`examfp.decode.read.read_leak`
        for one leaked paper; erased positions are simply absent.
        """
        bpp = sum(w for _, w in self.layout)
        base = paper_index * bpp
        bits: dict[int, int] = {}
        within = 0
        for pos, width in self.layout:
            if pos in observations:
                symbol = observations[pos][0]
                for b in range(width):
                    gi = base + within + b
                    if gi < self.m:
                        bits[gi] = (symbol >> (width - 1 - b)) & 1
            within += width
        return bits

    def scores(self, pirate_bits: Mapping[int, int]) -> np.ndarray:
        """Per-centre one-sided Tardos accusation scores over observed 1-bits."""
        ones = np.array(
            sorted(i for i, b in pirate_bits.items() if b == 1 and 0 <= i < self.m),
            dtype=np.int64,
        )
        if ones.size == 0:
            return np.zeros(self.n_centres, dtype=np.float64)
        p = self.biases[ones]
        g_one = np.sqrt((1.0 - p) / p)
        g_zero = -np.sqrt(p / (1.0 - p))
        sub = self.codewords[:, ones]  # (n_centres, |ones|)
        contrib = np.where(sub, g_one, g_zero)
        return contrib.sum(axis=1)

    def accuse(self, pirate_bits: Mapping[int, int]) -> list[int]:
        """Return centres whose accusation score exceeds the threshold ``Z``."""
        scores = self.scores(pirate_bits)
        return [c for c in range(self.n_centres) if scores[c] > self.threshold]


def simulate_pirate(
    code: TardosCode,
    coalition: list[int],
    seed: int,
    strategy: str = "coin",
) -> dict[int, int]:
    """Forge a pirate codeword from a coalition under the marking assumption.

    Where all colluders share a bit, that bit is forced; where they differ, the
    adversary picks per ``strategy`` (``"coin"`` random, ``"majority"``).
    Returns a fully observed bit dict over all ``m`` positions.
    """
    rng = np.random.default_rng(seed)
    rows = code.codewords[coalition]  # (|coalition|, m)
    ones = rows.sum(axis=0)
    size = len(coalition)
    forced_one = ones == size
    forced_zero = ones == 0
    if strategy == "majority":
        chosen = ones * 2 >= size
    else:  # coin
        chosen = rng.random(code.m) < 0.5
    result = np.where(forced_one, 1, np.where(forced_zero, 0, chosen.astype(int)))
    return {i: int(result[i]) for i in range(code.m)}
