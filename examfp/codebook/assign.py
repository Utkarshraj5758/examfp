"""Assign each centre a Reed-Solomon codeword, packed into the paper's slots.

Practical mode (ADR 0001): one paper per centre, codebook = Reed-Solomon over
GF(256) (:mod:`examfp.codebook.rs`).

Slot packing (ADR 0002)
-----------------------
An RS symbol is a byte, and parity bytes can take *any* value 0..255, but a slot
can only show one of its 2..119 variants. So each GF(256) symbol is carried by a
**group** of slots, read as a mixed-radix number:

* A group's members are ordered most-significant first, largest alphabet first
  (ties in paper order). Byte ``b`` maps to the digits of ``b`` in that mixed
  radix; slot ``i`` shows digit ``i``.
* **Capacity:** ``prod(alphabets) >= 256``, so every byte has its own
  combination (injective). Combinations above 255 are never produced; reading one
  back erases the symbol rather than guessing.
* **Every slot varies:** the most significant member's place value,
  ``capacity / max(alphabets)``, is at most 255, so every member's digit takes at
  least two values across 0..255. This is what removes the constant positions of
  the M3 mixed-radix codebook (NOTES.md, F3).
* **Grouping:** repeatedly anchor on the largest remaining slot and add the
  cheapest combination of remaining slots that reaches 256 (smallest product,
  then fewest slots). Slots left over once less than 256 of capacity remains are
  appended as low-order digits to the group where the place-value rule stays
  tightest. More groups means a longer code, so more erasure tolerance.
* Groups are ordered by their earliest member in the paper; group ``j`` carries
  codeword symbol ``j``. A group may span questions. The trace scores slots
  individually, so a partly visible group still counts as evidence; only direct
  RS decoding (:func:`complete_symbols`) treats a partly visible group as erased.

On the sample paper this gives 7 groups. With ``k = 2`` message bytes enough for
up to 65,536 centres, any 2 surviving groups recover the codeword, so up to 5 of
the 7 symbols can be lost.

Centres map to distinct messages drawn without replacement from ``256**k`` by a
generator seeded from ``seed``. That keeps data bytes, and hence parity bytes,
spread over the whole byte range.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping
from dataclasses import dataclass
from math import prod
from pathlib import Path

from examfp.codebook import rs
from examfp.models import Paper

Position = tuple[str, str]
Symbols = dict[Position, int]
Codebook = dict[int, Symbols]

_BYTE = 256
_KEY_SEP = "::"


@dataclass(frozen=True)
class SlotGroup:
    """The slots that jointly carry one GF(256) symbol, most significant first."""

    positions: tuple[Position, ...]
    alphabets: tuple[int, ...]

    @property
    def capacity(self) -> int:
        """Number of distinct slot combinations (at least 256)."""
        return prod(self.alphabets)


# --- grouping ----------------------------------------------------------------------------------
def _best_fill(
    anchor: int, pool: list[Position], alphabets: Mapping[Position, int]
) -> list[Position]:
    """Cheapest sub-multiset of ``pool`` lifting ``anchor`` to at least 256."""
    values = sorted({alphabets[p] for p in pool}, reverse=True)
    by_value = {v: [p for p in pool if alphabets[p] == v] for v in values}
    best: tuple[int, int, tuple[int, ...]] | None = None

    def search(i: int, product: int, counts: tuple[int, ...]) -> None:
        nonlocal best
        if product >= _BYTE:
            key = (product, sum(counts))
            if best is None or key < (best[0], best[1]):
                best = (product, sum(counts), counts)
            return
        if i == len(values):
            return
        value, running = values[i], product
        for count in range(len(by_value[value]) + 1):
            search(i + 1, running, (*counts, count))
            if running >= _BYTE:
                break
            running *= value

    search(0, anchor, ())
    if best is None:  # pragma: no cover - the caller guarantees enough capacity
        raise ValueError("pool cannot reach one GF(256) symbol")
    chosen: list[Position] = []
    for value, count in zip(values, best[2], strict=False):
        chosen.extend(by_value[value][:count])
    return chosen


def slot_groups(paper: Paper) -> list[SlotGroup]:
    """Partition the paper's positions into GF(256) symbol groups.

    Guarantees: every position is in exactly one group; each group has capacity
    >= 256 and a most-significant place value <= 255 (so every member varies);
    the result is deterministic. Raises :class:`ValueError` if the paper's
    positions cannot satisfy those rules.
    """
    alphabets = paper.alphabets()
    order = {pos: i for i, pos in enumerate(paper.positions())}

    def rank(p: Position) -> tuple[int, int]:
        return (-alphabets[p], order[p])

    pool = sorted(paper.positions(), key=rank)
    groups: list[list[Position]] = []
    while pool and prod(alphabets[p] for p in pool) >= _BYTE:
        anchor = pool.pop(0)
        fill = _best_fill(alphabets[anchor], pool, alphabets)
        for p in fill:
            pool.remove(p)
        groups.append([anchor, *fill])

    for leftover in pool:  # less than one byte of capacity remains
        best_index, best_place = -1, _BYTE
        for i, members in enumerate(groups):
            sizes = [alphabets[p] for p in members] + [alphabets[leftover]]
            place = prod(sizes) // max(sizes)
            if place < best_place:
                best_index, best_place = i, place
        if best_index < 0:
            raise ValueError(f"position {leftover} cannot join any GF(256) group and still vary")
        groups[best_index].append(leftover)

    result = []
    for members in groups:
        ordered = tuple(sorted(members, key=rank))
        result.append(SlotGroup(ordered, tuple(alphabets[p] for p in ordered)))
    result.sort(key=lambda g: min(order[p] for p in g.positions))
    return result


def byte_to_symbols(group: SlotGroup, value: int) -> Symbols:
    """Spread one byte over the group's slots (mixed radix, most significant first).

    Guarantees: injective over 0..255 and inverted by :func:`symbols_to_byte`.
    """
    if not 0 <= value < _BYTE:
        raise ValueError(f"{value} is not a byte")
    digits: list[int] = []
    for alphabet in reversed(group.alphabets):
        digits.append(value % alphabet)
        value //= alphabet
    digits.reverse()
    return dict(zip(group.positions, digits, strict=True))


def symbols_to_byte(group: SlotGroup, symbols: Mapping[Position, int]) -> int | None:
    """Read a group's byte back, or ``None`` if it cannot be read without guessing.

    Guarantees: returns ``None`` when any member is missing or out of range, or
    when the combination encodes a value above 255 (never produced by
    :func:`byte_to_symbols`).
    """
    value = 0
    for position, alphabet in zip(group.positions, group.alphabets, strict=True):
        symbol = symbols.get(position)
        if symbol is None or not 0 <= symbol < alphabet:
            return None
        value = value * alphabet + symbol
    return value if value < _BYTE else None


# --- the code ----------------------------------------------------------------------------------
def _message_length(n_centres: int) -> int:
    k = 1
    while _BYTE**k < n_centres:
        k += 1
    return k


def rs_shape(paper: Paper, n_centres: int) -> tuple[int, int]:
    """Return ``(n, k)``: GF(256) symbols the paper carries, and message symbols needed.

    Guarantees: ``n > k``, so at least one parity symbol exists; otherwise raises
    :class:`ValueError` (the paper is too small for that many centres).
    """
    n = len(slot_groups(paper))
    k = _message_length(n_centres)
    if n <= k:
        raise ValueError(
            f"paper carries {n} GF(256) symbols but {n_centres} centres need {k} "
            "message symbols plus at least one parity symbol"
        )
    return n, k


def _messages(n_centres: int, k: int, rng: random.Random) -> list[int]:
    """Distinct messages, one per centre, drawn without replacement."""
    return rng.sample(range(_BYTE**k), n_centres)


def assign(paper: Paper, n_centres: int, seed: int = 0) -> Codebook:
    """Return ``{centre_id: {(qid, slot): symbol}}`` for ``n_centres`` centres.

    Guarantees: each symbol is within its position's alphabet; distinct centres
    get distinct Reed-Solomon codewords, so the mapping is injective; any ``k`` of
    the paper's ``n`` symbol groups determine a centre's whole vector
    (:func:`complete_symbols`); symbols are listed in :meth:`Paper.positions`
    order. Deterministic for a given ``seed``.
    """
    groups = slot_groups(paper)
    n, k = rs_shape(paper, n_centres)
    rng = random.Random(seed)
    positions = paper.positions()

    book: Codebook = {}
    for centre, message in enumerate(_messages(n_centres, k, rng)):
        codeword = rs.encode(list(message.to_bytes(k, "big")), n - k)
        symbols: Symbols = {}
        for group, value in zip(groups, codeword, strict=True):
            symbols.update(byte_to_symbols(group, value))
        book[centre] = {pos: symbols[pos] for pos in positions}
    return book


def complete_symbols(
    paper: Paper, n_centres: int, observed: Mapping[Position, int]
) -> Symbols:
    """Recover a centre's full symbol vector from a partial observation.

    A group with any unread or unreadable member is an erasure. Guarantees: if at
    least ``k`` groups were read intact and consistently, returns the exact full
    vector (paper order). Otherwise raises :class:`~examfp.codebook.rs.RSDecodeError`
    - it never guesses.
    """
    groups = slot_groups(paper)
    n, k = rs_shape(paper, n_centres)
    received = [symbols_to_byte(g, observed) for g in groups]
    codeword = rs.decode_erasures(received, n - k)
    symbols: Symbols = {}
    for group, value in zip(groups, codeword, strict=True):
        symbols.update(byte_to_symbols(group, value))
    return {pos: symbols[pos] for pos in paper.positions()}


# --- serialisation ------------------------------------------------------------------------------
def dumps_codebook(codebook: Codebook) -> str:
    """Serialise to JSON text, inner keys as ``"qid::slot"`` (pure; no I/O)."""
    data = {
        str(centre): {f"{qid}{_KEY_SEP}{slot}": sym for (qid, slot), sym in symbols.items()}
        for centre, symbols in codebook.items()
    }
    return json.dumps(data, indent=2)


def loads_codebook(text: str) -> Codebook:
    """Inverse of :func:`dumps_codebook` (pure; no I/O)."""
    data: dict[str, dict[str, int]] = json.loads(text)
    book: Codebook = {}
    for centre, symbols in data.items():
        restored: Symbols = {}
        for key, sym in symbols.items():
            qid, slot = key.split(_KEY_SEP, 1)
            restored[(qid, slot)] = sym
        book[int(centre)] = restored
    return book


def save_codebook(codebook: Codebook, path: str | Path) -> None:
    """Write ``codebook`` to ``path`` as **plaintext** JSON.

    Prefer the encrypted path (the CLI default, :mod:`examfp.codebook.crypto`):
    codebooks are secrets (CLAUDE.md, security rules).
    """
    Path(path).write_text(dumps_codebook(codebook), encoding="utf-8")


def load_codebook(path: str | Path) -> Codebook:
    """Read a plaintext codebook written by :func:`save_codebook`."""
    return loads_codebook(Path(path).read_text(encoding="utf-8"))
