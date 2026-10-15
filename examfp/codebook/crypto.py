"""Envelope encryption for secrets at rest: AES-256-GCM with a vault-wrapped key.

Reproduces the standard envelope-encryption pattern (as used by cloud KMS
services) with a single published primitive, AES-256-GCM (NIST SP 800-38D),
provided by the ``cryptography`` package. Nothing here implements a cipher.

1. A fresh 256-bit **data key** encrypts the payload.
2. The **vault** wraps the data key under its key-encryption key (KEK), also
   with AES-256-GCM, so the KEK never leaves the vault.
3. Only the ciphertext, its nonce and the wrapped data key are stored.

The associated data binds the envelope format, the KEK id and the purpose (for
example ``"codebook"``), so a relabelled or repurposed envelope fails
authentication instead of decrypting.

Randomness: data keys and nonces come from the OS CSPRNG (``os.urandom``). This
is the one deliberate exception to the project's seeded-RNG rule - a seeded
generator would make keys predictable. The entropy source is injectable so tests
can be deterministic; production code must keep the default.

Pure: no environment, filesystem or logging access. Callers pass the
environment mapping to :meth:`EnvVault.from_environ` and do the file I/O.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from collections.abc import Callable, Mapping
from typing import Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

FORMAT = "trace-envelope/v1"
KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12  # 96-bit GCM nonce

Urandom = Callable[[int], bytes]


class VaultError(Exception):
    """The vault cannot provide a usable key. Messages never include key material."""


class DecryptionError(Exception):
    """An envelope failed to open: tampered, wrong key, wrong purpose or malformed."""


class Vault(Protocol):
    """Wraps and unwraps data keys under a KEK the caller never sees."""

    @property
    def kek_id(self) -> str: ...

    def wrap(self, dek: bytes, aad: bytes) -> bytes: ...

    def unwrap(self, wrapped: bytes, aad: bytes) -> bytes: ...


class EnvVault:
    """Development vault stub: the KEK is base64 in ``TRACE_KEK`` (id in ``TRACE_KEK_ID``).

    Generate a key with::

        python -c "import base64,secrets;print(base64.b64encode(secrets.token_bytes(32)).decode())"

    A production vault (M12) implements the same :class:`Vault` protocol.
    """

    ENV_KEY = "TRACE_KEK"
    ENV_KEY_ID = "TRACE_KEK_ID"

    def __init__(self, kek: bytes, kek_id: str = "env", urandom: Urandom = os.urandom) -> None:
        if len(kek) != KEY_BYTES:
            raise VaultError(f"KEK must be {KEY_BYTES} bytes (AES-256)")
        self._aead = AESGCM(kek)
        self._kek_id = kek_id
        self._urandom = urandom

    def __repr__(self) -> str:
        return f"EnvVault(kek_id={self._kek_id!r})"  # never the key

    @property
    def kek_id(self) -> str:
        return self._kek_id

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> EnvVault:
        """Build the stub from an explicit environment mapping.

        Guarantees: raises :class:`VaultError` - naming the variable, never echoing
        its value - when the key is missing, not base64, or not 32 bytes.
        """
        raw = environ.get(cls.ENV_KEY)
        if not raw:
            raise VaultError(f"{cls.ENV_KEY} is not set; it must hold a base64 32-byte key")
        try:
            kek = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError):
            raise VaultError(f"{cls.ENV_KEY} is not valid base64") from None
        if len(kek) != KEY_BYTES:
            raise VaultError(f"{cls.ENV_KEY} must decode to {KEY_BYTES} bytes (AES-256)")
        return cls(kek, environ.get(cls.ENV_KEY_ID) or "env")

    def wrap(self, dek: bytes, aad: bytes) -> bytes:
        """Return ``nonce || AES-GCM(KEK, dek)``."""
        nonce = self._urandom(NONCE_BYTES)
        return nonce + self._aead.encrypt(nonce, dek, aad)

    def unwrap(self, wrapped: bytes, aad: bytes) -> bytes:
        """Inverse of :meth:`wrap`; raises :class:`DecryptionError` on any mismatch."""
        try:
            return self._aead.decrypt(wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:], aad)
        except (InvalidTag, ValueError):
            raise DecryptionError("data key failed authentication: wrong KEK or tampered") from None


def _aad(kek_id: str, purpose: str) -> bytes:
    return f"{FORMAT}|{kek_id}|{purpose}".encode()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def seal(plaintext: bytes, vault: Vault, *, purpose: str, urandom: Urandom = os.urandom) -> bytes:
    """Encrypt ``plaintext`` into a JSON envelope.

    Guarantees: the envelope contains no plaintext and no unwrapped key; each call
    uses a fresh data key and nonce; it opens only with the same vault KEK and the
    same ``purpose``.
    """
    aad = _aad(vault.kek_id, purpose)
    dek = urandom(KEY_BYTES)
    nonce = urandom(NONCE_BYTES)
    envelope = {
        "format": FORMAT,
        "kek_id": vault.kek_id,
        "purpose": purpose,
        "wrapped_key": _b64(vault.wrap(dek, aad)),
        "nonce": _b64(nonce),
        "ciphertext": _b64(AESGCM(dek).encrypt(nonce, plaintext, aad)),
    }
    return json.dumps(envelope, sort_keys=True).encode("ascii")


def is_sealed(data: bytes) -> bool:
    """True if ``data`` is a TRACE envelope (checks the header, not the contents)."""
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return False
    return isinstance(parsed, dict) and parsed.get("format") == FORMAT


def open_sealed(envelope: bytes, vault: Vault, *, purpose: str) -> bytes:
    """Decrypt an envelope in memory and return the plaintext.

    Guarantees: raises :class:`DecryptionError` - never returns partial or
    unauthenticated data - when the envelope is malformed, tampered with, sealed
    under another KEK, or meant for another purpose.
    """
    try:
        data = json.loads(envelope)
        fields = (data["format"], data["kek_id"], data["purpose"])
        wrapped = base64.b64decode(data["wrapped_key"], validate=True)
        nonce = base64.b64decode(data["nonce"], validate=True)
        ciphertext = base64.b64decode(data["ciphertext"], validate=True)
    except (ValueError, KeyError, TypeError, UnicodeDecodeError, binascii.Error):
        raise DecryptionError("not a well-formed TRACE envelope") from None
    fmt, kek_id, sealed_purpose = fields
    if fmt != FORMAT:
        raise DecryptionError(f"unsupported envelope format {fmt!r}")
    if sealed_purpose != purpose:
        raise DecryptionError(f"envelope was sealed for {sealed_purpose!r}, not {purpose!r}")
    if kek_id != vault.kek_id:
        raise DecryptionError(f"envelope was sealed under KEK {kek_id!r}, not {vault.kek_id!r}")
    aad = _aad(kek_id, purpose)
    dek = vault.unwrap(wrapped, aad)
    try:
        return AESGCM(dek).decrypt(nonce, ciphertext, aad)
    except (InvalidTag, ValueError):
        raise DecryptionError("ciphertext failed authentication (tampered)") from None
