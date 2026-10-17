"""Variant separation: the reader must be able to tell a slot's variants apart.

A fingerprint symbol is only as good as the reader's ability to recover it. The
fuzzy reader (:mod:`examfp.decode.read`) lowercases the leak, takes the longest
variant found verbatim, and otherwise the variant with the strictly best fuzzy
partial match. Two variants that are too alike are confused when a typo lands
in the one shown. M6 found this in the sample paper: "Show your work." beside
"Show your working." was misread 6 times in 104,048 reads.

Two rules, applied to every pair of variants of a text-read slot (wording,
instruction and unit-form slots):

* **No containment.** Neither variant, normalised (lowercase, collapsed
  whitespace, trailing punctuation dropped), may contain the other: no prefix,
  suffix or infix. ``eval/separation.py`` measured such pairs misreading at
  0.3-4.9% (prefix) and 0.5-9.0% (suffix, infix) per read, because the reader
  takes the longest variant found verbatim and a typo in the longer one leaves
  the shorter one intact (owner, 2026-10-17: extended from prefix only).
* **Minimum edit distance.** Their case-insensitive Levenshtein distance must be
  at least :data:`MIN_EDIT_DISTANCE`. The sweep's pre-declared rule measured
  :data:`MEASURED_MIN_EDIT_DISTANCE` = 11; it is **recorded, not adopted**
  (owner, 2026-10-17): at 11, 17 of the sample paper's 29 text-variant pairs
  fail, and the confusion beyond distance 6 comes from a short variant nearly
  embedded in a long one, which edit distance does not measure (ADR 0004).

Pure string arithmetic: no model, no randomness.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from rapidfuzz.distance import Levenshtein

Check = tuple[bool, str]

# Measured 2026-10-17 by eval/separation.py (1.7M reads, seed 0): the smallest
# distance with no misread at or above it whose pooled reads bound the rate at or
# below MISREAD_RATE (ADR 0004, "Variant separation").
MEASURED_MIN_EDIT_DISTANCE = 11
# Deployed minimum. Not the measured value (owner decision, 2026-10-17): 1 turns
# the distance rule off, since distinct texts are always at least 1 apart.
MIN_EDIT_DISTANCE = 1

_SPACE = re.compile(r"\s+")
_TRAILING = ".,;:!? "


def normalise(text: str) -> str:
    """Lowercase, collapse whitespace, and drop trailing punctuation."""
    return _SPACE.sub(" ", text.lower()).strip().rstrip(_TRAILING)


def edit_distance(a: str, b: str) -> int:
    """Case-insensitive Levenshtein distance, as the lowercasing reader sees the texts."""
    return int(Levenshtein.distance(a.lower(), b.lower()))


def is_prefix_pair(a: str, b: str) -> bool:
    """Is one normalised text a proper prefix of the other? (Identical texts are not.)"""
    x, y = normalise(a), normalise(b)
    return x != y and (x.startswith(y) or y.startswith(x))


def is_contained_pair(a: str, b: str) -> bool:
    """Does one normalised text contain the other (prefix, suffix or infix)?

    Identical texts are the same variant, not a contained pair.
    """
    x, y = normalise(a), normalise(b)
    return x != y and (x in y or y in x)


def check_separation(
    candidate: str, others: Sequence[str], min_distance: int = MIN_EDIT_DISTANCE
) -> Check:
    """Is ``candidate`` separable from every other variant of its slot?

    Guarantees: fails if any other variant contains it or is contained in it
    (normalised), or lies closer than ``min_distance``; a variant identical to
    ``candidate`` is the same variant and is skipped.
    """
    closest: tuple[int, str] | None = None
    for other in others:
        if other == candidate:
            continue
        if is_contained_pair(candidate, other):
            return False, (f"one of {candidate!r} and {other!r} contains the other; the "
                           "reader confuses such pairs (ADR 0004)")
        distance = edit_distance(candidate, other)
        if closest is None or distance < closest[0]:
            closest = (distance, other)
    if closest is None:
        return True, "no other variant to separate from"
    distance, other = closest
    if distance < min_distance:
        return False, (f"edit distance {distance} to {other!r}, below the minimum "
                       f"{min_distance} (ADR 0004)")
    return True, f"closest variant {other!r} at edit distance {distance} (minimum {min_distance})"
