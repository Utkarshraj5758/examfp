"""Read symbols out of a leaked (possibly cropped/retyped) paper.

The reader is deliberately crude and conservative: it matches leak chunks to
questions by token and number overlap, then recovers each slot's symbol only
when the evidence is unambiguous.  An unrecoverable slot is simply omitted —
the reader never guesses and never falls back to a most-likely variant.
"""

from __future__ import annotations

import re
from itertools import permutations

from rapidfuzz import fuzz

from examfp.models import OptionOrderSlot, Paper, Question, TextSlot, UnitFormSlot

# A recovered observation: position -> (symbol, confidence).
Observations = dict[tuple[str, str], tuple[int, float]]

_WORD = re.compile(r"[a-zA-Z]+")
_NUM = re.compile(r"\d+")
_MARKS = re.compile(r"\[\s*\d+\s*marks?\s*\]", re.IGNORECASE)
_QMARK = re.compile(r"^\s*(?:Q\s*\d+|\d+\s*[.)])", re.IGNORECASE)
_OPTION_LINE = re.compile(r"^\s*([A-Za-z])\s*[).]\s*(.+?)\s*$")

_MATCH_THRESHOLD = 0.5
_FUZZ_THRESHOLD = 80.0


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text) if len(w) >= 2}


def _numbers(text: str) -> set[str]:
    return set(_NUM.findall(_MARKS.sub(" ", text)))


def split_chunks(text: str) -> list[str]:
    """Split a leak into chunks on blank lines or question-number markers."""
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                chunks.append("\n".join(current))
                current = []
            continue
        if _QMARK.match(line) and current:
            chunks.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


class _QuestionRef:
    """Precomputed matching material for one question."""

    def __init__(self, question: Question) -> None:
        self.question = question
        literal = re.sub(r"\{\{.*?\}\}", " ", question.template)
        words = _words(literal)
        numbers: set[str] = set()
        for slot in question.slots:
            if isinstance(slot, OptionOrderSlot):
                for opt in slot.options:
                    words |= _words(opt)
                    numbers |= _numbers(opt)
            else:
                for variant in slot.variants:
                    for value in variant.values:
                        words |= _words(value)
                        if value.isdigit():
                            numbers.add(value)
        self.words = words
        self.numbers = numbers

    def match_score(self, chunk: str) -> float:
        chunk_words = _words(chunk)
        if not chunk_words:
            return 0.0
        token = len(chunk_words & self.words) / len(chunk_words)
        chunk_numbers = _numbers(chunk)
        if chunk_numbers:
            number = len(chunk_numbers & self.numbers) / len(chunk_numbers)
            return 0.6 * token + 0.4 * number
        return token


def _perms(n: int) -> list[tuple[int, ...]]:
    identity = tuple(range(n))
    return [p for p in permutations(range(n)) if p != identity]


def _recover_group(slot: TextSlot, chunk: str) -> tuple[int, float] | None:
    present = _numbers(chunk)
    candidates = [
        i for i, v in enumerate(slot.variants) if all(val in present for val in v.values)
    ]
    if len(candidates) == 1:
        return candidates[0], 1.0
    return None  # zero or ambiguous -> do not guess


def _recover_text(slot: TextSlot | UnitFormSlot, chunk: str) -> tuple[int, float] | None:
    low = chunk.lower()
    exact = [i for i, v in enumerate(slot.variants) if v.values[0].lower() in low]
    if exact:
        # Prefer the most specific literal actually present (handles substrings).
        best = max(exact, key=lambda i: len(slot.variants[i].values[0]))
        return best, 1.0
    scored = [
        (i, fuzz.partial_ratio(v.values[0].lower(), low)) for i, v in enumerate(slot.variants)
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    if scored and scored[0][1] >= _FUZZ_THRESHOLD:
        if len(scored) == 1 or scored[0][1] > scored[1][1]:
            return scored[0][0], scored[0][1] / 100.0
    return None


def _recover_option(slot: OptionOrderSlot, chunk: str) -> tuple[int, float] | None:
    labelled: dict[str, str] = {}
    for line in chunk.splitlines():
        m = _OPTION_LINE.match(line)
        if m:
            labelled[m.group(1).upper()] = m.group(2)
    letters = sorted(labelled)
    if len(letters) != len(slot.options):
        return None

    order: list[int] = []
    confidences: list[float] = []
    for letter in letters:
        shown = labelled[letter].strip().lower()
        exact = [i for i, opt in enumerate(slot.options) if opt.lower() == shown]
        if len(exact) == 1:
            order.append(exact[0])
            confidences.append(1.0)
            continue
        scored = sorted(
            ((i, fuzz.partial_ratio(opt.lower(), shown)) for i, opt in enumerate(slot.options)),
            key=lambda t: t[1],
            reverse=True,
        )
        if scored[0][1] < _FUZZ_THRESHOLD or (len(scored) > 1 and scored[0][1] == scored[1][1]):
            return None
        order.append(scored[0][0])
        confidences.append(scored[0][1] / 100.0)

    if sorted(order) != list(range(len(slot.options))):
        return None  # not a clean permutation
    perms = _perms(len(slot.options))
    key = tuple(order)
    if key not in perms:
        return None  # natural order is excluded from the codebook
    return perms.index(key), min(confidences)


def _recover_slot(slot: object, chunk: str) -> tuple[int, float] | None:
    if isinstance(slot, OptionOrderSlot):
        return _recover_option(slot, chunk)
    if isinstance(slot, UnitFormSlot):
        return _recover_text(slot, chunk)
    if isinstance(slot, TextSlot):
        if slot.difficulty_band is not None:
            return _recover_group(slot, chunk)
        return _recover_text(slot, chunk)
    return None


def read_leak(text: str, paper: Paper) -> Observations:
    """Recover ``{(question_id, slot_name): (symbol, confidence)}`` from ``text``.

    Chunks are matched to questions (each question claimed at most once); for
    each match, every slot's symbol is recovered independently.  Only positions
    actually recovered are returned.
    """
    chunks = split_chunks(text)
    refs = {q.id: _QuestionRef(q) for q in paper.questions}

    pairs: list[tuple[float, int, str]] = []
    for ci, chunk in enumerate(chunks):
        for qid, ref in refs.items():
            s = ref.match_score(chunk)
            if s >= _MATCH_THRESHOLD:
                pairs.append((s, ci, qid))
    pairs.sort(key=lambda t: t[0], reverse=True)

    claimed_chunks: set[int] = set()
    claimed_questions: set[str] = set()
    matches: list[tuple[int, str]] = []
    for _s, ci, qid in pairs:
        if ci in claimed_chunks or qid in claimed_questions:
            continue
        claimed_chunks.add(ci)
        claimed_questions.add(qid)
        matches.append((ci, qid))

    observations: Observations = {}
    for ci, qid in matches:
        chunk = chunks[ci]
        question = refs[qid].question
        for slot in question.slots:
            recovered = _recover_slot(slot, chunk)
            if recovered is not None:
                observations[(qid, slot.name)] = recovered
    return observations
