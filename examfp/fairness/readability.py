"""Wording channel, step 3: readability within tolerance.

A wording variant must read about as easily as its reference. Three counts
are compared on the whole question text, reference against candidate:

* **words**: runs of letters (digits, symbols and superscripts are not words);
* **syllables**: a fixed heuristic, vowel groups with a silent final *e*, and a
  vowel-less abbreviation (``km``, ``kmph``) read letter by letter;
* **rare words**: words whose Zipf frequency is below ``rare_zipf`` (3.0 means
  fewer than one occurrence per million words), from ``wordfreq``.

The tolerance is symmetric: an easier variant is as unfair to the other
centres as a harder one. Word and syllable counts may differ by at most a
fraction of the reference's count; rare words by an absolute number. The
syllable heuristic is deterministic, not linguistically exact; only the
difference between two texts matters.

The word-frequency source is injected (``zipf``), so tests run without
wordfreq; :func:`wordfreq_zipf` imports it lazily. Never SymPy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

Check = tuple[bool, str]
Zipf = Callable[[str], float]

_VOWELS = frozenset("aeiouy")
_APOSTROPHES = frozenset("'’")


@dataclass(frozen=True)
class ReadabilityTolerance:
    """How far a candidate's counts may move from the reference's (both directions)."""

    words: float = 0.20  # fraction of the reference's word count
    syllables: float = 0.20  # fraction of the reference's syllable count
    rare_words: int = 1  # absolute
    rare_zipf: float = 3.0


DEFAULT_TOLERANCE = ReadabilityTolerance()


@dataclass(frozen=True)
class ReadabilityCounts:
    words: int
    syllables: int
    rare_words: int


def words(text: str) -> list[str]:
    """Runs of letters, with apostrophes allowed between letters (``don't``)."""
    found: list[str] = []
    current: list[str] = []
    for i, ch in enumerate(text):
        joins = (ch in _APOSTROPHES and bool(current) and i + 1 < len(text)
                 and text[i + 1].isalpha())
        if ch.isalpha() or joins:
            current.append(ch)
        elif current:
            found.append("".join(current))
            current = []
    if current:
        found.append("".join(current))
    return found


def count_syllables(word: str) -> int:
    """Heuristic syllables of one word; at least 1.

    Guarantees: deterministic; a word with no vowel is an abbreviation, read
    letter by letter (``km`` is 2).
    """
    letters = [c for c in word.lower() if c.isalpha()]
    if not letters:
        return 0
    if not any(c in _VOWELS for c in letters):
        return len(letters)
    groups = 0
    previous_vowel = False
    for c in letters:
        vowel = c in _VOWELS
        groups += vowel and not previous_vowel
        previous_vowel = vowel
    if letters[-1] == "e" and letters[-2:] != ["l", "e"] and groups > 1:
        groups -= 1  # silent final e: make, here, calculate
    return max(1, groups)


def readability_counts(
    text: str, zipf: Zipf, rare_zipf: float = ReadabilityTolerance.rare_zipf
) -> ReadabilityCounts:
    """Word, syllable and rare-word counts of ``text``."""
    found = words(text)
    return ReadabilityCounts(
        words=len(found),
        syllables=sum(count_syllables(w) for w in found),
        rare_words=sum(zipf(w) < rare_zipf for w in found),
    )


def check_readability(
    reference: str,
    candidate: str,
    zipf: Zipf,
    tolerance: ReadabilityTolerance = DEFAULT_TOLERANCE,
) -> Check:
    """Are the candidate's counts within ``tolerance`` of the reference's, both ways?

    Guarantees: every count is compared; the reason lists all three.
    """
    ref = readability_counts(reference, zipf, tolerance.rare_zipf)
    cand = readability_counts(candidate, zipf, tolerance.rare_zipf)
    limits = (
        ("words", ref.words, cand.words, tolerance.words * ref.words),
        ("syllables", ref.syllables, cand.syllables, tolerance.syllables * ref.syllables),
        ("rare words", ref.rare_words, cand.rare_words, float(tolerance.rare_words)),
    )
    parts = []
    passed = True
    for name, mine, theirs, allowed in limits:
        within = abs(theirs - mine) <= allowed
        passed &= within
        parts.append(f"{name} {mine} vs {theirs} (allowed ±{allowed:g})"
                     + ("" if within else " OUTSIDE"))
    return passed, "; ".join(parts)


def wordfreq_zipf() -> Zipf:
    """English Zipf frequencies from wordfreq (the ``fairness`` extra), imported lazily."""
    from wordfreq import zipf_frequency

    def zipf(word: str) -> float:
        return float(zipf_frequency(word, "en"))

    return zipf
