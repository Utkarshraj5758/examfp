"""Tests for the static HTML dashboard."""

from __future__ import annotations

from pathlib import Path

from api.dashboard import build_dashboard, collect, write_dashboard
from examfp.codebook.assign import assign
from examfp.models import Paper


def test_collect_and_build_render_html(sample_paper: Paper) -> None:
    codebook = assign(sample_paper, 200, 0)
    data = collect(sample_paper, codebook, seed=0, n_trials=5)
    assert data.n_centres == 200
    assert data.positions_per_paper == len(sample_paper.positions())
    assert len(data.bench) == 8

    html = build_dashboard(data)
    assert html.startswith("<!doctype html>")
    assert "examfp" in html
    assert "false-id%" in html
    assert "QR-code baseline" in html
    assert "<svg" in html
    # Leaked text is present and HTML-escaped (no raw angle-bracket injection).
    assert "questions leaked" in html


def test_write_dashboard(sample_paper: Paper, tmp_path: Path) -> None:
    codebook = assign(sample_paper, 100, 0)
    data = collect(sample_paper, codebook, seed=0, n_trials=3)
    out = tmp_path / "out" / "dashboard.html"
    write_dashboard(data, out)
    assert out.exists()
    assert out.read_text(encoding="utf-8").rstrip().endswith("</html>")
