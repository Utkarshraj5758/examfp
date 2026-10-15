"""Tests for leak-degradation attacks and end-to-end survivability."""

from __future__ import annotations

import random

from examfp.attacks import crop, retype, typos
from examfp.cli import render_text
from examfp.codebook.assign import assign
from examfp.decode.read import read_leak
from examfp.decode.score import Outcome, score
from examfp.models import Paper

_QNUM = __import__("re").compile(r"^\s*\d+\s*[.)]")


def _count_questions(text: str) -> int:
    blocks = [b for b in text.split("\n\n") if b.strip()]
    return sum(1 for b in blocks if _QNUM.match(b))


def test_crop_keeps_exactly_k_questions_intact(sample_paper: Paper) -> None:
    book = assign(sample_paper, 10, 0)
    full = render_text(sample_paper, book[3])
    rng = random.Random(1)
    cropped = crop(full, 3, rng)
    assert _count_questions(cropped) == 3
    # Each kept block is byte-identical to an original question block (intact).
    originals = [b for b in full.split("\n\n") if _QNUM.match(b.strip())]
    original_set = {b.strip() for b in originals}
    for block in cropped.split("\n\n"):
        assert block.strip() in original_set
    # An MCQ that is kept retains all five option lines.
    if "A)" in cropped:
        mcq = next(b for b in cropped.split("\n\n") if "A)" in b)
        assert sum(1 for ln in mcq.splitlines() if ln.strip()[:2] in
                   ("A)", "B)", "C)", "D)", "E)")) == 5


def test_typos_never_alter_digits(sample_paper: Paper) -> None:
    book = assign(sample_paper, 10, 0)
    full = render_text(sample_paper, book[7])
    rng = random.Random(2)
    noisy = typos(full, 0.5, rng)  # aggressive rate

    def digits(s: str) -> list[str]:
        return [c for c in s if c.isdigit()]

    assert digits(noisy) == digits(full)
    assert noisy != full  # something actually changed


def test_retype_strips_markers_and_lowercases(sample_paper: Paper) -> None:
    book = assign(sample_paper, 10, 0)
    full = render_text(sample_paper, book[1])
    typed = retype(full)
    assert typed == typed.lower()
    assert "marks]" not in typed and "mark]" not in typed
    # No leading "N." question markers remain.
    for line in typed.splitlines():
        assert not _QNUM.match(line)
    # Still separable into questions (blank lines preserved).
    assert typed.count("\n\n") >= 5


def test_six_question_retyped_leak_identification_rate(sample_paper: Paper) -> None:
    book = assign(sample_paper, 1000, 0)
    hits = 0
    trials = 100
    for seed in range(trials):  # full distribution, not a favourable window
        rng = random.Random(seed)
        centre = rng.randrange(1000)
        # A leaker retypes first, then makes typos while retyping.
        leak = typos(retype(crop(render_text(sample_paper, book[centre]), 6, rng)), 0.03, rng)
        result = score(read_leak(leak, sample_paper), book)
        if result.outcome is Outcome.IDENTIFIED and result.ranked[0][0] == centre:
            hits += 1
    assert hits >= 0.80 * trials, f"identification rate {hits}/{trials} below 80%"
