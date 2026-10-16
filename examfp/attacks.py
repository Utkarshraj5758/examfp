"""Leak-degradation attacks: crop, typos, retype.

These model how a leaked paper reaches an investigator in the wild — a photo of
a few questions, a hurried retype, fat-finger errors.  The fingerprint must
survive them; a visible mark (QR code, watermark) generally does not.

All randomness comes from an explicitly-passed :class:`random.Random`.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from collections.abc import Hashable, Mapping, Sequence
from typing import TypeVar

_P = TypeVar("_P", bound=Hashable)

_MARKS = re.compile(r"\[\s*\d+\s*marks?\s*\]", re.IGNORECASE)
_QNUM_LEAD = re.compile(r"^\s*(?:Q\s*\d+|\d+)\s*[.)]\s*", re.IGNORECASE)
_QNUM_BLOCK = re.compile(r"^\s*(?:Q\s*\d+|\d+)\s*[.)]", re.IGNORECASE)


def _split_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.split("\n"):
        if not line.strip():
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def crop(text: str, k: int, rng: random.Random) -> str:
    """Keep ``k`` whole question blocks (with their option lines) intact.

    Guarantees: exactly ``k`` question blocks are returned, in original order,
    each byte-identical to the source (nothing within a kept question is
    altered).  Raises :class:`ValueError` if fewer than ``k`` questions exist.
    """
    questions = [b for b in _split_blocks(text) if _QNUM_BLOCK.match(b)]
    if k > len(questions):
        raise ValueError(f"cannot keep {k} questions; only {len(questions)} present")
    chosen = sorted(rng.sample(range(len(questions)), k))
    return "\n\n".join(questions[i] for i in chosen)


def typos(text: str, rate: float, rng: random.Random) -> str:
    """Swap adjacent alphabetic characters with probability ``rate`` each.

    Guarantees: digits are never touched and never moved — a swap happens only
    when both neighbours are ASCII letters, so the numeric fingerprint payload
    is preserved verbatim.
    """
    chars = list(text)
    i = 0
    n = len(chars)
    while i < n - 1:
        if chars[i].isalpha() and chars[i + 1].isalpha() and rng.random() < rate:
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
            i += 2  # don't re-touch the just-swapped pair
        else:
            i += 1
    return "".join(chars)


def retype(text: str) -> str:
    """Lowercase, collapse whitespace, strip question markers and marks tags.

    Line and paragraph breaks are preserved (blank lines collapse to one) so the
    text is still separable into questions; only intra-line runs of spaces are
    collapsed.  Models a candidate re-keying the paper from memory/screen.
    """
    out_lines: list[str] = []
    for raw in text.split("\n"):
        line = raw.lower()
        line = _MARKS.sub("", line)
        line = _QNUM_LEAD.sub("", line)
        line = re.sub(r"[ \t]+", " ", line).strip()
        out_lines.append(line)

    collapsed: list[str] = []
    prev_blank = False
    for line in out_lines:
        if not line:
            if collapsed and not prev_blank:
                collapsed.append("")
            prev_blank = True
        else:
            collapsed.append(line)
            prev_blank = False
    while collapsed and collapsed[-1] == "":
        collapsed.pop()
    return "\n".join(collapsed)


_COLLUSION_STRATEGIES = ("minority", "random")


def collude(
    symbols: Sequence[Mapping[_P, int]], rng: random.Random, strategy: str = "minority"
) -> dict[_P, int]:
    """Forge one paper from several centres' papers (marking assumption).

    Colluders compare their papers slot by slot. Where they all agree the slot
    is undetectable and must be copied; where they differ they choose:

    * ``"minority"``: a value held by the fewest colluders (ties broken by
      ``rng``) - the classic attack on accusation scores, since the rare value
      points away from the majority of the coalition;
    * ``"random"``: the value of a uniformly chosen colluder.

    Guarantees: every output symbol is held by at least one colluder, agreed
    positions are copied unchanged, and the result is in the first paper's
    position order. Raises :class:`ValueError` for fewer than two papers,
    mismatched positions or an unknown strategy. The caller renders the result.
    """
    if strategy not in _COLLUSION_STRATEGIES:
        raise ValueError(f"unknown collusion strategy {strategy!r}")
    if len(symbols) < 2:
        raise ValueError("a coalition needs at least two centres")
    positions = list(symbols[0])
    if any(set(s) != set(positions) for s in symbols[1:]):
        raise ValueError("colluders' papers must cover the same positions")

    hybrid: dict[_P, int] = {}
    for pos in positions:
        held = [s[pos] for s in symbols]
        counts = Counter(held)
        if len(counts) == 1:
            hybrid[pos] = held[0]
        elif strategy == "minority":
            rarest = min(counts.values())
            hybrid[pos] = rng.choice(sorted(v for v, n in counts.items() if n == rarest))
        else:
            hybrid[pos] = rng.choice(held)
    return hybrid
