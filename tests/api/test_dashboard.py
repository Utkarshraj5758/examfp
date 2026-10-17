"""Tests for the static HTML dashboard."""

from __future__ import annotations

from pathlib import Path

from api.dashboard import build_dashboard, collect, write_dashboard
from examfp.codebook.assign import assign
from examfp.models import Paper

KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="  # base64 of bytes 0..31 (test only)


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
    assert "single-source" in html  # the 0% figure covers single-source leaks only
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


def test_dashboard_entrypoint_lives_in_api(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from typer.testing import CliRunner

    from api.dashboard import app

    sample = Path(__file__).resolve().parents[2] / "data" / "papers" / "sample.json"
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out" / "dashboard.html"
    result = CliRunner().invoke(app, [str(sample), "--out", str(out), "--trials", "2"],
                                env={"TRACE_KEK": KEY})
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert (tmp_path / "out" / "codebook.json.enc").exists()  # sealed by default
    assert not (tmp_path / "out" / "codebook.json").exists()


def test_dashboard_shows_a_ranking_only_for_an_identified_verdict(sample_paper: Paper) -> None:
    from dataclasses import replace

    data = collect(sample_paper, assign(sample_paper, 100, 0), seed=0, n_trials=2)
    assert data.demo.outcome == "IDENTIFIED"
    assert "<th>score</th>" in build_dashboard(data)  # the named centre is the verdict

    ranked = [(777_001, 9.5, False), (777_002, 8.0, False), (777_003, 1.0, True)]
    multi = replace(data, demo=replace(data.demo, outcome="MULTI_SOURCE_SUSPECTED",
                                       top5=ranked, verdict=["verdict: MULTI_SOURCE_SUSPECTED"]))
    page = build_dashboard(multi)
    assert not [cid for cid, _, _ in ranked if str(cid) in page]
    assert "<th>score</th>" not in page and "&middot; margin" not in page  # not CSS margin
    assert "No ranking shown" in page


def test_dashboard_without_a_key_refuses_and_names_the_opt_out(
    tmp_path: Path, monkeypatch  # type: ignore[no-untyped-def]
) -> None:
    from typer.testing import CliRunner

    from api.dashboard import app

    sample = Path(__file__).resolve().parents[2] / "data" / "papers" / "sample.json"
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, [str(sample), "--trials", "2"], env={"TRACE_KEK": None})
    assert result.exit_code != 0
    assert "TRACE_KEK" in result.output and "--plaintext" in result.output
    assert not (tmp_path / "out").exists()


def test_dashboard_plaintext_warns_and_names_the_file(
    tmp_path: Path, monkeypatch  # type: ignore[no-untyped-def]
) -> None:
    from typer.testing import CliRunner

    from api.dashboard import app

    sample = Path(__file__).resolve().parents[2] / "data" / "papers" / "sample.json"
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, [str(sample), "--trials", "2", "--plaintext"],
                                env={"TRACE_KEK": None})
    assert result.exit_code == 0, result.output
    warning = next(line for line in result.output.splitlines() if "warning" in line)
    assert "PLAINTEXT" in warning and str(Path("out") / "codebook.json") in warning
