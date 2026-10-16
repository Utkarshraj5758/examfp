"""Reed-Solomon codes over GF(256): systematic encoding, Forney erasure decoding.

A faithful implementation of the textbook construction, with the parameters
used by QR codes (ISO/IEC 18004), so published QR vectors double as test oracles:

* field GF(2^8) with primitive polynomial ``x^8 + x^4 + x^3 + x^2 + 1`` (0x11D)
  and primitive element ``alpha = 2``;
* generator polynomial ``g(x) = prod_{i=0}^{nsym-1} (x - alpha^i)`` (first
  consecutive root ``alpha^0``);
* systematic encoding: codeword = message followed by the ``nsym`` remainder
  symbols of ``m(x) * x^nsym mod g(x)``;
* erasure decoding: syndromes, erasure locator, error evaluator, then Forney's
  formula for each erased magnitude.

The resulting ``[n, k]`` code is MDS: any ``k`` of the ``n`` symbols determine
the codeword, so up to ``n - k`` erasures are always recoverable.

Conventions: codewords are lists with the highest-degree coefficient first
(``codeword[0]`` is the first message symbol); an erased symbol is ``None``.
Pure functions only; no dependency beyond the standard library.
"""

from __future__ import annotations

from collections.abc import Sequence

PRIMITIVE_POLY = 0x11D
GENERATOR = 2
MAX_LENGTH = 255  # n <= 2^8 - 1


class RSDecodeError(ValueError):
    """Raised when a received word cannot be decoded without guessing."""


def _build_tables() -> tuple[tuple[int, ...], tuple[int, ...]]:
    exp = [0] * 512
    log = [0] * 256
    x = 1
    for i in range(255):
        exp[i] = x
        log[x] = i
        x <<= 1  # multiply by alpha = 2
        if x & 0x100:
            x ^= PRIMITIVE_POLY
    for i in range(255, 512):  # doubled so EXP[LOG[a] + LOG[b]] needs no modulo
        exp[i] = exp[i - 255]
    return tuple(exp), tuple(log)


EXP, LOG = _build_tables()
"""Antilog (``EXP[i] = alpha^i``, length 512) and log tables (``LOG[0]`` unused)."""


# --- field arithmetic (addition and subtraction are XOR) -------------------------------
def gf_mul(a: int, b: int) -> int:
    """Product in GF(256). Guarantees a result in ``0..255``."""
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def gf_div(a: int, b: int) -> int:
    """Quotient ``a / b`` in GF(256); raises :class:`ZeroDivisionError` if ``b == 0``."""
    if b == 0:
        raise ZeroDivisionError("division by zero in GF(256)")
    if a == 0:
        return 0
    return EXP[(LOG[a] - LOG[b]) % 255]


def gf_pow(a: int, power: int) -> int:
    """``a ** power`` in GF(256) (``0 ** 0 == 1``)."""
    if power == 0:
        return 1
    if a == 0:
        return 0
    return EXP[(LOG[a] * power) % 255]


def gf_inv(a: int) -> int:
    """Multiplicative inverse; raises :class:`ZeroDivisionError` for ``0``."""
    return gf_div(1, a)


# --- polynomials -------------------------------------------------------------------------
def _poly_mul(p: Sequence[int], q: Sequence[int]) -> list[int]:
    """Product of two polynomials (same coefficient order in and out)."""
    out = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a == 0:
            continue
        for j, b in enumerate(q):
            out[i + j] ^= gf_mul(a, b)
    return out


def _eval_high_first(poly: Sequence[int], x: int) -> int:
    acc = 0
    for coef in poly:
        acc = gf_mul(acc, x) ^ coef
    return acc


def _eval_low_first(poly: Sequence[int], x: int) -> int:
    acc = 0
    for coef in reversed(poly):
        acc = gf_mul(acc, x) ^ coef
    return acc


def generator_poly(nsym: int) -> list[int]:
    """``g(x) = prod_{i<nsym} (x - alpha^i)``, monic, highest degree first.

    Guarantees: degree ``nsym`` with roots exactly ``alpha^0 .. alpha^(nsym-1)``.
    """
    g = [1]
    for i in range(nsym):
        g = _poly_mul(g, [1, EXP[i]])
    return g


# --- validation --------------------------------------------------------------------------
def _check_symbols(symbols: Sequence[int | None]) -> None:
    for s in symbols:
        if s is not None and not 0 <= s <= 255:
            raise ValueError(f"{s!r} is not a GF(256) symbol (0..255)")


def _check_shape(n: int, nsym: int) -> None:
    if nsym < 1:
        raise ValueError("nsym must be >= 1")
    if n - nsym < 1:
        raise ValueError(f"no message symbols: n={n}, nsym={nsym}")
    if n > MAX_LENGTH:
        raise ValueError(f"codeword length {n} exceeds {MAX_LENGTH} for GF(256)")


# --- encode ------------------------------------------------------------------------------
def encode(message: Sequence[int], nsym: int) -> list[int]:
    """Systematically encode ``message`` with ``nsym`` parity symbols.

    Guarantees: the result is ``list(message) + parity`` and every syndrome of
    it is zero, i.e. it is a codeword of the ``[len(message) + nsym, len(message)]``
    RS code.
    """
    _check_symbols(message)
    _check_shape(len(message) + nsym, nsym)
    gen = generator_poly(nsym)
    work = list(message) + [0] * nsym
    for i in range(len(message)):  # synthetic division by the monic g(x)
        coef = work[i]
        if coef:
            for j in range(1, len(gen)):
                work[i + j] ^= gf_mul(gen[j], coef)
    return list(message) + work[len(message):]


def syndromes(codeword: Sequence[int], nsym: int) -> list[int]:
    """``S_i = c(alpha^i)`` for ``i < nsym``; all zero iff ``codeword`` is a codeword."""
    return [_eval_high_first(codeword, EXP[i]) for i in range(nsym)]


# --- erasure decoding --------------------------------------------------------------------
def decode_erasures(received: Sequence[int | None], nsym: int) -> list[int]:
    """Fill every ``None`` in ``received`` and return the full codeword.

    Guarantees: if at most ``nsym`` symbols are erased and the surviving ones are
    untouched, the original codeword is returned exactly. Otherwise raises
    :class:`RSDecodeError` - more than ``nsym`` erasures, or survivors that are
    inconsistent with every codeword. It never guesses.
    """
    _check_symbols(received)
    n = len(received)
    _check_shape(n, nsym)
    erased = [i for i, s in enumerate(received) if s is None]
    if len(erased) > nsym:
        raise RSDecodeError(f"{len(erased)} erasures exceed the {nsym} this code can fill")

    word = [0 if s is None else s for s in received]
    synd = syndromes(word, nsym)  # S(x), lowest degree first
    if erased and any(synd):
        # Erasure locator Lambda(x) = prod (1 + X_j x), X_j = alpha^degree.
        locators = [EXP[n - 1 - i] for i in erased]
        lam = [1]
        for x_j in locators:
            lam = _poly_mul(lam, [1, x_j])
        omega = _poly_mul(synd, lam)[:nsym]  # Omega(x) = S(x) Lambda(x) mod x^nsym
        # Formal derivative in characteristic 2: only odd-degree terms survive.
        lam_prime = [lam[d] if d % 2 == 1 else 0 for d in range(1, len(lam))]
        for i, x_j in zip(erased, locators, strict=True):
            x_inv = gf_inv(x_j)
            denominator = _eval_low_first(lam_prime, x_inv)
            if denominator == 0:
                raise RSDecodeError("degenerate erasure locator")
            # Forney with first root alpha^0: e_j = X_j * Omega(X_j^-1) / Lambda'(X_j^-1).
            word[i] ^= gf_div(gf_mul(x_j, _eval_low_first(omega, x_inv)), denominator)

    if any(syndromes(word, nsym)):
        raise RSDecodeError("surviving symbols are inconsistent with every codeword")
    return word
