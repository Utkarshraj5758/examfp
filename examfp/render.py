"""Render a fingerprinted paper to PDF via Typst.

Given a :class:`~examfp.models.Paper` and a symbol vector keyed by
``(question_id, slot_name)``, this builds a Typst source document (pure) and
compiles it to PDF.  The mapping from a *centre* to its symbol vector belongs to
the coding-theory module and is fed in as ``symbols``.

Question text is emitted as Typst string literals (``#"..."``) so arbitrary
content — numbers, units, ₹, permuted options — renders verbatim, and each
question is an unbreakable block so it never spans a page break.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping

import typst

from examfp.models import Paper, validate_symbols

_Symbols = Mapping[tuple[str, str], int]


def escape_typst(text: str) -> str:
    """Escape ``text`` for a Typst string literal (``#"..."``)."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _question_symbols(paper: Paper, symbols: _Symbols) -> dict[str, dict[str, int]]:
    validate_symbols(paper, symbols)
    grouped: dict[str, dict[str, int]] = {}
    for q in paper.questions:
        grouped[q.id] = {s.name: symbols[(q.id, s.name)] for s in q.slots}
    return grouped


def _question_block(qid: str, body_lines: list[str], marks: int, mark_positions: bool) -> str:
    label = "mark" if marks == 1 else "marks"
    first = f'#"{escape_typst(body_lines[0])}" #h(1fr) _({marks} {label})_'
    rest = [f'#"{escape_typst(ln)}"' for ln in body_lines[1:]]
    body = " #linebreak() ".join([first, *rest])
    block = f"#block(breakable: false)[+ {body}]"
    if not mark_positions:
        return block
    start = (
        f'#context [#metadata((id: "{qid}", role: "start", '
        f"page: here().page(), y: here().position().y.pt()))<qmark>]"
    )
    end = (
        f'#context [#metadata((id: "{qid}", role: "end", '
        f"page: here().page(), y: here().position().y.pt()))<qmark>]"
    )
    return f"{start}\n{block}\n{end}"


def build_typst_source(
    paper: Paper, symbols: _Symbols, *, mark_positions: bool = False
) -> str:
    """Build the Typst source for ``paper`` at ``symbols`` (pure).

    With ``mark_positions`` each question is bracketed by queryable
    ``<qmark>`` metadata (page + y), used by the layout-invariance test.
    Raises :class:`ValueError`/:class:`IndexError` for an invalid symbol vector.
    """
    grouped = _question_symbols(paper, symbols)
    lines: list[str] = [
        '#set page(paper: "a4", margin: 2.5cm)',
        "#set text(size: 11pt)",
        '#set enum(numbering: "1.")',
        f'#align(center)[= #"{escape_typst(paper.title)}"]',
        "",
    ]
    for q in paper.questions:
        text, _ = q.resolve(grouped[q.id])
        body_lines = text.split("\n")
        lines.append(_question_block(q.id, body_lines, q.marks, mark_positions))
    return "\n".join(lines) + "\n"


def render_pdf(paper: Paper, symbols: _Symbols) -> bytes:
    """Compile ``paper`` at ``symbols`` to PDF bytes (valid ``%PDF`` output)."""
    source = build_typst_source(paper, symbols)
    handle, path = tempfile.mkstemp(suffix=".typ")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(source)
        pdf: bytes = typst.compile(path)
        return pdf
    finally:
        os.unlink(path)


def query_layout(paper: Paper, symbols: _Symbols) -> list[dict[str, object]]:
    """Return the ``<qmark>`` metadata (id, role, page, y) via Typst layout query.

    Used to verify layout invariance: each question's start/end position and
    page across centres.
    """
    source = build_typst_source(paper, symbols, mark_positions=True)
    handle, path = tempfile.mkstemp(suffix=".typ")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(source)
        import json

        raw: str = typst.query(path, "<qmark>", field="value")
        result: list[dict[str, object]] = json.loads(raw)
        return result
    finally:
        os.unlink(path)
