"""Tests for envelope encryption of codebooks (AES-256-GCM, vault-wrapped data key)."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

import pytest

from examfp.codebook.crypto import (
    KEY_BYTES,
    DecryptionError,
    EnvVault,
    VaultError,
    is_sealed,
    open_sealed,
    seal,
)

KEK = bytes(range(32))
OTHER_KEK = bytes(range(1, 33))
PLAINTEXT = b'{"0": {"q1::intro": 1, "q2::opts": 87}}'


def _counter_urandom() -> Callable[[int], bytes]:
    state = {"n": 0}

    def urandom(size: int) -> bytes:
        state["n"] += 1
        return bytes((state["n"] + i) % 256 for i in range(size))

    return urandom


def test_round_trip() -> None:
    vault = EnvVault(KEK)
    envelope = seal(PLAINTEXT, vault, purpose="codebook")
    assert is_sealed(envelope)
    assert open_sealed(envelope, vault, purpose="codebook") == PLAINTEXT


def test_envelope_holds_no_plaintext_and_no_raw_key() -> None:
    vault = EnvVault(KEK)
    envelope = seal(PLAINTEXT, vault, purpose="codebook")
    assert b"q1::intro" not in envelope
    assert KEK not in envelope and base64.b64encode(KEK) not in envelope
    fields = json.loads(envelope)
    assert set(fields) == {"format", "kek_id", "purpose", "wrapped_key", "nonce", "ciphertext"}


def test_fresh_key_and_nonce_every_time() -> None:
    vault = EnvVault(KEK)
    a = seal(PLAINTEXT, vault, purpose="codebook")
    b = seal(PLAINTEXT, vault, purpose="codebook")
    assert a != b  # CSPRNG data key and nonce per envelope


def test_entropy_source_is_injectable_for_tests() -> None:
    a = seal(PLAINTEXT, EnvVault(KEK, urandom=_counter_urandom()), purpose="codebook",
             urandom=_counter_urandom())
    b = seal(PLAINTEXT, EnvVault(KEK, urandom=_counter_urandom()), purpose="codebook",
             urandom=_counter_urandom())
    assert a == b


def _tamper(envelope: bytes, field: str) -> bytes:
    data = json.loads(envelope)
    raw = bytearray(base64.b64decode(data[field]))
    raw[-1] ^= 0x01
    data[field] = base64.b64encode(bytes(raw)).decode()
    return json.dumps(data).encode()


@pytest.mark.parametrize("field", ["ciphertext", "wrapped_key", "nonce"])
def test_tampering_is_detected(field: str) -> None:
    vault = EnvVault(KEK)
    envelope = _tamper(seal(PLAINTEXT, vault, purpose="codebook"), field)
    with pytest.raises(DecryptionError):
        open_sealed(envelope, vault, purpose="codebook")


def test_wrong_kek_is_rejected() -> None:
    envelope = seal(PLAINTEXT, EnvVault(KEK), purpose="codebook")
    with pytest.raises(DecryptionError):
        open_sealed(envelope, EnvVault(OTHER_KEK), purpose="codebook")


def test_purpose_and_kek_id_are_bound() -> None:
    envelope = seal(PLAINTEXT, EnvVault(KEK), purpose="codebook")
    with pytest.raises(DecryptionError):
        open_sealed(envelope, EnvVault(KEK), purpose="leak-upload")
    relabelled = json.loads(envelope)
    relabelled["kek_id"] = "other"
    with pytest.raises(DecryptionError):
        open_sealed(json.dumps(relabelled).encode(), EnvVault(KEK, kek_id="other"),
                    purpose="codebook")


def test_plaintext_is_not_sealed() -> None:
    assert not is_sealed(PLAINTEXT)
    assert not is_sealed(b"\x00\xff not json")


def test_env_vault_reads_base64_key() -> None:
    environ = {"TRACE_KEK": base64.b64encode(KEK).decode(), "TRACE_KEK_ID": "dev-1"}
    vault = EnvVault.from_environ(environ)
    assert vault.kek_id == "dev-1"
    assert open_sealed(seal(PLAINTEXT, vault, purpose="codebook"), EnvVault(KEK, kek_id="dev-1"),
                       purpose="codebook") == PLAINTEXT


def test_env_vault_errors_never_echo_the_key() -> None:
    with pytest.raises(VaultError, match="TRACE_KEK"):
        EnvVault.from_environ({})
    short = base64.b64encode(b"x" * 16).decode()
    with pytest.raises(VaultError) as excinfo:
        EnvVault.from_environ({"TRACE_KEK": short})
    assert short not in str(excinfo.value)
    with pytest.raises(VaultError):
        EnvVault.from_environ({"TRACE_KEK": "not base64!!"})


def test_key_size_is_256_bits() -> None:
    assert KEY_BYTES == 32
    with pytest.raises(VaultError):
        EnvVault(b"too short")
