"""Calibration helpers for the decision rule in :mod:`examfp.decode.score`.

The consistency gate lets a centre survive with up to ``t`` mismatching slots,
because a *genuine* leak can still disagree with its source where the reader
misread a slot. ``t`` must therefore come from the reader's measured misread
rate, not be fixed at zero:

1. **Measure** misreads: on leaks with known sources, count read slots whose
   symbol differs from the source's (:func:`misread_upper_bound` turns the count
   into a conservative rate; ``eval/bench.py`` prints it).
2. **Choose the false-rejection budget** ``alpha``: the probability that a genuine
   leak is refused because of misreads alone.
3. **Tolerance** for a leak with ``r`` reads is the smallest ``t`` with
   ``P(Binomial(r, rate) > t) <= alpha`` (:func:`mismatch_tolerance`).

A larger tolerance also gives hybrids of several centres more room to pass
the gate, so every recalibration must be re-checked against the collusion rows
of the benchmark. Pure functions, standard library only.
"""

from __future__ import annotations

from math import exp, lgamma, log, pow


def _log_pmf(n: int, p: float, i: int) -> float:
    return (
        lgamma(n + 1) - lgamma(i + 1) - lgamma(n - i + 1) + i * log(p) + (n - i) * log(1.0 - p)
    )


def _cdf(n: int, p: float, k: int) -> float:
    """P(X <= k) for X ~ Binomial(n, p), with 0 < p < 1."""
    return min(1.0, sum(exp(_log_pmf(n, p, i)) for i in range(k + 1)))


def binomial_tail(n: int, p: float, t: int) -> float:
    """``P(X > t)`` for ``X ~ Binomial(n, p)``.

    Guarantees: summed directly over ``i > t`` (no ``1 - cdf`` cancellation), so
    tiny tails stay accurate.
    """
    if t < 0:
        return 1.0
    if t >= n or p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    return min(1.0, sum(exp(_log_pmf(n, p, i)) for i in range(t + 1, n + 1)))


def mismatch_tolerance(reads: int, misread_rate: float, budget: float) -> int:
    """Smallest ``t`` such that a genuine leak exceeds ``t`` misreads with prob <= ``budget``.

    Guarantees: monotone non-decreasing in ``misread_rate``; ``0`` when the rate is 0.
    """
    for t in range(reads + 1):
        if binomial_tail(reads, misread_rate, t) <= budget:
            return t
    return reads


def misread_upper_bound(misreads: int, reads: int, confidence: float = 0.95) -> float:
    """One-sided Clopper-Pearson upper bound on a misread rate.

    Guarantees: the true rate lies below the returned value with probability at
    least ``confidence``; with zero misreads it equals ``1 - (1 - confidence)^(1/reads)``.
    Raises :class:`ValueError` when ``reads <= 0``.
    """
    if reads <= 0:
        raise ValueError("need at least one read slot to estimate a misread rate")
    if misreads >= reads:
        return 1.0
    alpha = 1.0 - confidence
    if misreads == 0:
        return 1.0 - pow(alpha, 1.0 / reads)
    lo, hi = misreads / reads, 1.0
    for _ in range(200):  # bisection on the decreasing function p -> P(X <= misreads)
        mid = (lo + hi) / 2.0
        if _cdf(reads, mid, misreads) > alpha:
            lo = mid
        else:
            hi = mid
    return hi
