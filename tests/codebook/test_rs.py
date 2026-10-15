"""Tests for Reed-Solomon over GF(256): field tables, known vectors, erasures."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from examfp.codebook.rs import (
    EXP,
    LOG,
    RSDecodeError,
    decode_erasures,
    encode,
    generator_poly,
    gf_div,
    gf_inv,
    gf_mul,
    gf_pow,
    syndromes,
)

nonzero = st.integers(min_value=1, max_value=255)
element = st.integers(min_value=0, max_value=255)


# --- GF(256) with primitive polynomial 0x11D, alpha = 2 --------------------------------
def test_antilog_table_is_a_primitive_cycle() -> None:
    assert EXP[0] == 1 and EXP[1] == 2
    assert EXP[8] == 0x1D  # x^8 = x^4 + x^3 + x^2 + 1 (mod 0x11D)
    assert EXP[255] == 1  # alpha has order 255
    assert sorted(EXP[:255]) == list(range(1, 256))  # every nonzero element exactly once


def test_log_inverts_antilog() -> None:
    for i in range(255):
        assert LOG[EXP[i]] == i


def test_known_products() -> None:
    assert gf_mul(0x80, 2) == 0x1D  # reduction by 0x11D
    assert gf_mul(0, 77) == 0 and gf_mul(77, 1) == 77
    assert gf_pow(2, 255) == 1 and gf_pow(2, 8) == 0x1D


@given(a=element, b=element, c=element)
def test_field_axioms(a: int, b: int, c: int) -> None:
    assert gf_mul(a, b) == gf_mul(b, a)
    assert gf_mul(a, gf_mul(b, c)) == gf_mul(gf_mul(a, b), c)
    assert gf_mul(a, b ^ c) == gf_mul(a, b) ^ gf_mul(a, c)  # addition is XOR


@given(a=nonzero, b=nonzero)
def test_division_and_inverse(a: int, b: int) -> None:
    assert gf_mul(a, gf_inv(a)) == 1
    assert gf_mul(gf_div(a, b), b) == a


def test_division_by_zero_raises() -> None:
    with pytest.raises(ZeroDivisionError):
        gf_div(5, 0)


# --- generator polynomial ---------------------------------------------------------------
@pytest.mark.parametrize("nsym", [1, 2, 5, 10, 32])
def test_generator_has_consecutive_roots_from_alpha0(nsym: int) -> None:
    g = generator_poly(nsym)
    assert len(g) == nsym + 1 and g[0] == 1  # monic, degree nsym
    for i in range(nsym):
        x, acc = EXP[i], 0
        for coef in g:  # Horner, highest degree first
            acc = gf_mul(acc, x) ^ coef
        assert acc == 0


# --- published known vectors (QR code RS: GF(256)/0x11D, alpha=2, first root alpha^0) --
# Cross-checked against the independent `reedsolo` implementation during M5.
KNOWN_VECTORS = {
    # ISO/IEC 18004 / thonky.com QR tutorial: "HELLO WORLD", version 1-M.
    "qr-hello-world-1M": (
        [32, 91, 11, 120, 209, 114, 220, 77, 67, 64, 236, 17, 236, 17, 236, 17],
        [196, 35, 39, 119, 235, 215, 231, 226, 93, 23],
    ),
    # ISO/IEC 18004 Annex I worked example: "01234567", version 1-M.
    "iso18004-01234567-1M": (
        [16, 32, 12, 86, 97, 128, 236, 17, 236, 17, 236, 17, 236, 17, 236, 17],
        [165, 36, 212, 193, 237, 54, 199, 135, 44, 85],
    ),
    # Wikiversity, "Reed-Solomon codes for coders": rs_encode_msg(msg_in, 10).
    "wikiversity-rs-for-coders": (
        [0x40, 0xD2, 0x75, 0x47, 0x76, 0x17, 0x32, 0x06,
         0x27, 0x26, 0x96, 0xC6, 0xC6, 0x96, 0x70, 0xEC],
        [0xBC, 0x2A, 0x90, 0x13, 0x6B, 0xAF, 0xEF, 0xFD, 0x4B, 0xE0],
    ),
}


@pytest.mark.parametrize("name", sorted(KNOWN_VECTORS))
def test_systematic_encoding_matches_known_vector(name: str) -> None:
    data, parity = KNOWN_VECTORS[name]
    codeword = encode(data, nsym=len(parity))
    assert codeword[: len(data)] == data  # systematic: message first, unchanged
    assert codeword[len(data):] == parity
    assert syndromes(codeword, len(parity)) == [0] * len(parity)


@pytest.mark.parametrize("name", sorted(KNOWN_VECTORS))
def test_known_vector_survives_maximum_erasures(name: str) -> None:
    data, parity = KNOWN_VECTORS[name]
    codeword = data + parity
    received: list[int | None] = list(codeword)
    for i in range(0, 2 * len(parity), 2):  # erase n-k symbols, spread out
        received[i] = None
    assert decode_erasures(received, nsym=len(parity)) == codeword


# --- erasure decoding (Forney) ----------------------------------------------------------
@st.composite
def code_and_erasures(
    draw: st.DrawFn, exact: bool = False
) -> tuple[list[int], int, list[int]]:
    k = draw(st.integers(min_value=1, max_value=40))
    nsym = draw(st.integers(min_value=1, max_value=40))
    message = draw(st.lists(element, min_size=k, max_size=k))
    n = k + nsym
    count = nsym if exact else draw(st.integers(min_value=0, max_value=nsym))
    erased = draw(st.lists(st.integers(0, n - 1), min_size=count, max_size=count, unique=True))
    return message, nsym, erased


@settings(max_examples=300, deadline=None)
@given(case=code_and_erasures())
def test_up_to_n_minus_k_erasures_recover_the_codeword(
    case: tuple[list[int], int, list[int]],
) -> None:
    message, nsym, erased = case
    codeword = encode(message, nsym)
    received: list[int | None] = [None if i in erased else s for i, s in enumerate(codeword)]
    assert decode_erasures(received, nsym) == codeword


@settings(max_examples=200, deadline=None)
@given(case=code_and_erasures(exact=True))
def test_any_k_surviving_symbols_recover_the_codeword(
    case: tuple[list[int], int, list[int]],
) -> None:
    message, nsym, erased = case  # exactly n-k erased: only k symbols survive
    codeword = encode(message, nsym)
    received: list[int | None] = [None if i in erased else s for i, s in enumerate(codeword)]
    assert decode_erasures(received, nsym)[: len(message)] == message


def test_more_than_n_minus_k_erasures_is_refused() -> None:
    codeword = encode([1, 2, 3], nsym=4)
    received: list[int | None] = [None] * 5 + codeword[5:]
    with pytest.raises(RSDecodeError):
        decode_erasures(received, nsym=4)


@settings(max_examples=200, deadline=None)
@given(case=code_and_erasures(), data=st.data())
def test_a_corrupted_symbol_is_detected_not_absorbed(
    case: tuple[list[int], int, list[int]], data: st.DataObject
) -> None:
    message, nsym, erased = case
    if len(erased) == nsym:  # need spare redundancy (distance argument)
        erased = erased[:-1]
    codeword = encode(message, nsym)
    survivors = [i for i in range(len(codeword)) if i not in erased]
    bad = data.draw(st.sampled_from(survivors))
    flip = data.draw(nonzero)
    received: list[int | None] = [None if i in erased else s for i, s in enumerate(codeword)]
    received[bad] = codeword[bad] ^ flip
    with pytest.raises(RSDecodeError):
        decode_erasures(received, nsym)


def test_input_validation() -> None:
    with pytest.raises(ValueError):
        encode([256], nsym=2)  # not a GF(256) symbol
    with pytest.raises(ValueError):
        encode([0] * 250, nsym=10)  # n = 260 > 255
    with pytest.raises(ValueError):
        decode_erasures([1, 2, 3], nsym=3)  # no message symbol left
