"""Tests for the Typst renderer, layout invariance, and capacity report."""

from __future__ import annotations

import io
import os
import random
import tempfile

import pytest
import typst
from hypothesis import given, settings
from hypothesis import strategies as st
from pypdf import PdfReader

from examfp.models import Paper
from examfp.render import (
    build_typst_source,
    escape_typst,
    query_layout,
    render_pdf,
)


def _pdf_pages_and_text(pdf: bytes) -> tuple[int, str]:
    reader = PdfReader(io.BytesIO(pdf))
    text = "".join(page.extract_text() for page in reader.pages)
    return len(reader.pages), " ".join(text.split())


def _norm(text: str) -> str:
    return " ".join(text.split())


def _zeros(paper: Paper) -> dict[tuple[str, str], int]:
    return {k: 0 for k in paper.alphabets()}


def _extremes_and_random(paper: Paper, n: int, seed: int) -> list[dict[tuple[str, str], int]]:
    alph = paper.alphabets()
    rng = random.Random(seed)
    centres = [
        {k: 0 for k in alph},
        {k: v - 1 for k, v in alph.items()},
        {k: min(1, v - 1) for k, v in alph.items()},  # long unit forms
    ]
    centres += [{k: rng.randrange(v) for k, v in alph.items()} for _ in range(n)]
    return centres


# --- escaper property --------------------------------------------------------
def _pdf_text_of(markup: str) -> str:
    source = "#set page(width: 600pt, height: 200pt)\n" + markup
    handle, path = tempfile.mkstemp(suffix=".typ")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(source)
        pdf: bytes = typst.compile(path)
    finally:
        os.unlink(path)
    _, text = _pdf_pages_and_text(pdf)
    return text


_escaper_text = st.text(
    alphabet=st.characters(
        min_codepoint=0x20,
        max_codepoint=0x2FF,
        blacklist_categories=("Cc", "Cf", "Zl", "Zp", "Zs", "Cs"),
    ),
    min_size=1,
    max_size=60,
)


@settings(max_examples=120, deadline=None)
@given(raw=_escaper_text)
def test_escaper_property_round_trip(raw: str) -> None:
    # Character fidelity is the escaper's job; PDF text extraction inserts/drops
    # spaces from kerning (e.g. "AV" -> "A V"), so compare whitespace-insensitively.
    def squash(s: str) -> str:
        return "".join(s.split())

    extracted = _pdf_text_of(f'#"{escape_typst(raw)}"')
    assert squash(extracted) == squash(raw)


# --- basic render ------------------------------------------------------------
def test_render_pdf_valid(sample_paper: Paper) -> None:
    assert render_pdf(sample_paper, _zeros(sample_paper)).startswith(b"%PDF")


def test_build_source_differs_per_centre(sample_paper: Paper) -> None:
    alph = sample_paper.alphabets()
    a = build_typst_source(sample_paper, {k: 0 for k in alph})
    b = build_typst_source(sample_paper, {k: v - 1 for k, v in alph.items()})
    assert a != b
    assert "{{" not in a and "{{" not in b


def test_build_source_bad_symbols_raise(sample_paper: Paper) -> None:
    with pytest.raises(ValueError):
        build_typst_source(sample_paper, {("q1", "intro"): 0})  # wrong key set
    syms = _zeros(sample_paper)
    syms[("q2", "opts")] = sample_paper.alphabets()[("q2", "opts")]
    with pytest.raises(IndexError):
        build_typst_source(sample_paper, syms)


# --- acceptance: text differs, canonical identical, letters vary -------------
def test_acceptance_text_differs_canonical_identical(sample_paper: Paper) -> None:
    alph = sample_paper.alphabets()
    zeros = {k: 0 for k in alph}
    ones = {k: min(1, v - 1) for k, v in alph.items()}
    maxes = {k: v - 1 for k, v in alph.items()}
    texts = [_pdf_pages_and_text(render_pdf(sample_paper, c))[1] for c in (zeros, ones, maxes)]
    assert texts[0] != texts[1] != texts[2] and texts[0] != texts[2]

    keys = [sample_paper.answer_key(c) for c in (zeros, ones, maxes)]
    canon = [{q: a.canonical for q, a in k.items()} for k in keys]
    assert canon[0] == canon[1] == canon[2]


# --- layout invariance via Typst layout query -------------------------------
def test_layout_invariance_via_query(sample_paper: Paper) -> None:
    centres = _extremes_and_random(sample_paper, n=8, seed=11)

    def layout(sym: dict[tuple[str, str], int]) -> dict[str, dict[str, tuple[int, float]]]:
        marks = query_layout(sample_paper, sym)
        out: dict[str, dict[str, tuple[int, float]]] = {}
        for m in marks:
            out.setdefault(str(m["id"]), {})[str(m["role"])] = (
                int(str(m["page"])),
                round(float(str(m["y"])), 1),
            )
        return out

    layouts = [layout(c) for c in centres]

    # Same page count across centres.
    pages = {max(p for roles in lay.values() for p, _ in roles.values()) for lay in layouts}
    assert len(pages) == 1

    ref = layouts[0]
    for lay in layouts[1:]:
        # Identical per-question start/end (page, y): nothing wrapped differently.
        assert lay == ref
    # No question spans a page break.
    for q in sample_paper.questions:
        assert ref[q.id]["start"][0] == ref[q.id]["end"][0]


def test_render_page_count_equal_across_centres(sample_paper: Paper) -> None:
    centres = _extremes_and_random(sample_paper, n=6, seed=99)
    page_counts = {_pdf_pages_and_text(render_pdf(sample_paper, c))[0] for c in centres}
    assert page_counts == {1}


# --- capacity report ---------------------------------------------------------
def test_capacity_report_durable_fraction_and_shortfall(sample_paper: Paper) -> None:
    from math import log

    rep = sample_paper.capacity_report(n_centres=500, c=3, eps=1e-6)
    assert rep.positions == 31
    assert rep.durable_fraction >= 0.60  # target met
    # Literal Tardos constant kept exactly; huge requirement -> shortfall.
    assert rep.tardos_required == pytest.approx(100 * 9 * log(500 / 1e-6))
    assert rep.positions < rep.tardos_required
    text = str(rep)
    assert "k = <unset>" in text  # empirical constant placeholder
    assert "eps=1e-2" in text and "eps=1e-6" in text  # feasibility grid
    assert "multi-paper" in text
    assert rep.projected_positions_60 > rep.positions


def test_capacity_feasibility_matches_formula(sample_paper: Paper) -> None:
    from math import log

    rep = sample_paper.capacity_report(n_centres=500, c=3, eps=1e-3)
    assert rep.feasibility[(5, 1e-6)] == pytest.approx(100 * 25 * log(500 / 1e-6))
