"""Tests for the M2 Tardos coding layer."""

from __future__ import annotations

from math import ceil, log

import pytest

from examfp.codebook.tardos import (
    TardosCode,
    bits_per_paper,
    position_bit_widths,
    simulate_pirate,
)
from examfp.models import Paper, validate_symbols


def test_bit_widths_are_floor_log2_alphabet(sample_paper: Paper) -> None:
    widths = dict(position_bit_widths(sample_paper))
    assert widths[("q2", "opts")] == 6  # alphabet 119 -> floor(log2)=6
    assert widths[("q1", "speed")] == 2  # alphabet 7 -> 2
    assert widths[("q1", "lead")] == 1  # alphabet 2 -> 1
    assert bits_per_paper(sample_paper) == sum(widths.values())


def test_parameters_follow_tardos_2003(sample_paper: Paper) -> None:
    # Tardos: k = ceil(ln(1/eps_1)), m = 100 c^2 k, Z = 20 c k, t = 1/(300 c). The union
    # bound over n centres gives eps_1 = eps / n, so k = ceil(ln(n / eps)).
    code = TardosCode.build(sample_paper, n_centres=500, c=3, eps=1e-6, seed=0)
    log_factor = ceil(log(500 / 1e-6))
    assert log_factor == 21  # ln(5e8) = 20.03: the ceiling is not a rounding detail
    assert code.m == 100 * 3 * 3 * log_factor == 18_900
    assert code.threshold == 20 * 3 * log_factor == 1_260
    assert code.t == pytest.approx(1 / (300 * 3))
    assert code.k == ceil(code.m / bits_per_paper(sample_paper))  # papers per session


def test_the_ceiling_never_shortens_the_code(sample_paper: Paper) -> None:
    # The unrounded form gave a shorter code and a lower threshold: the unsafe direction.
    for n, c, eps in ((100, 3, 0.01), (500, 2, 1e-3), (1000, 5, 1e-6)):
        code = TardosCode.build(sample_paper, n_centres=n, c=c, eps=eps, seed=0)
        assert code.m >= ceil(100 * c * c * log(n / eps))
        assert code.threshold >= 20 * c * log(n / eps)
        assert code.m == 100 * c * c * ceil(log(n / eps))


def test_build_is_deterministic(sample_paper: Paper) -> None:
    a = TardosCode.build(sample_paper, 20, 2, 0.1, seed=5)
    b = TardosCode.build(sample_paper, 20, 2, 0.1, seed=5)
    assert (a.codewords == b.codewords).all()
    assert (a.biases == b.biases).all()
    assert a.assign() == b.assign()


def test_session_symbols_are_valid_render_vectors(sample_paper: Paper) -> None:
    code = TardosCode.build(sample_paper, 5, 2, 0.5, seed=1)
    session = code.session_symbols(0)
    assert len(session) == code.k
    for per_paper in session:
        validate_symbols(sample_paper, per_paper)  # keys + ranges all valid


def test_observed_to_bits_round_trips_a_paper_slice(sample_paper: Paper) -> None:
    code = TardosCode.build(sample_paper, 5, 2, 0.5, seed=2)
    session = code.session_symbols(0)
    bpp = bits_per_paper(sample_paper)
    for paper_index, per_paper in enumerate(session):
        observations = {pos: (sym, 1.0) for pos, sym in per_paper.items()}
        bits = code.observed_to_bits(paper_index, observations)
        # Every recovered global bit matches the centre's codeword.
        for gi, bit in bits.items():
            assert bit == int(code.codewords[0][gi])
        # Bits only within [base, base+bpp) and below m.
        base = paper_index * bpp
        assert all(base <= gi < min(base + bpp, code.m) for gi in bits)


def test_accuser_catches_colluders_clears_innocents(sample_paper: Paper) -> None:
    code = TardosCode.build(sample_paper, n_centres=100, c=3, eps=0.01, seed=7)
    coalition = [0, 1, 2]
    pirate = simulate_pirate(code, coalition, seed=1, strategy="coin")
    accused = code.accuse(pirate)
    assert accused, "expected at least one accusation"
    assert set(accused) & set(coalition), "a colluder must be caught"
    assert set(accused) <= set(coalition), "no innocent may be accused"


def test_random_bits_accuse_nobody(sample_paper: Paper) -> None:
    import numpy as np

    code = TardosCode.build(sample_paper, 50, 2, 0.05, seed=3)
    rng = np.random.default_rng(99)
    pirate = {i: int(b) for i, b in enumerate(rng.integers(0, 2, size=code.m))}
    assert code.accuse(pirate) == []  # noise correlates with no codeword


def test_single_centre_pirate_accuses_that_centre(sample_paper: Paper) -> None:
    code = TardosCode.build(sample_paper, 50, 2, 0.05, seed=4)
    pirate = {i: int(b) for i, b in enumerate(code.codewords[17])}
    assert code.accuse(pirate) == [17]  # exact copy of centre 17
