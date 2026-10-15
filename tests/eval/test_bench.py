"""Tests for the robustness benchmark sweep."""

from __future__ import annotations

import csv
from dataclasses import fields
from pathlib import Path

import pytest

from eval.bench import BenchRow, format_table, run_bench, write_csv
from examfp.codebook.assign import assign
from examfp.models import Paper


def test_run_bench_shape_and_valid_rates(sample_paper: Paper) -> None:
    codebook = assign(sample_paper, 200, 0)
    rows = run_bench(sample_paper, codebook, k_values=range(1, 4), n_trials=10, seed=0)
    assert [r.k for r in rows] == [1, 2, 3]
    for r in rows:
        assert r.trials == 10
        for rate in (r.identified_rate, r.correct_rate, r.insufficient_rate, r.false_id_rate):
            assert 0.0 <= rate <= 1.0
        # An IDENTIFIED trial is either correct or a false id.
        assert r.identified_rate == pytest.approx(r.correct_rate + r.false_id_rate)
        assert r.mean_positions >= 0.0


def test_more_questions_recover_more_positions(sample_paper: Paper) -> None:
    codebook = assign(sample_paper, 200, 0)
    rows = run_bench(sample_paper, codebook, k_values=(1, 8), n_trials=20, seed=1)
    assert rows[1].mean_positions > rows[0].mean_positions


def test_write_csv_has_header_and_rows(sample_paper: Paper, tmp_path: Path) -> None:
    codebook = assign(sample_paper, 100, 0)
    rows = run_bench(sample_paper, codebook, k_values=range(1, 3), n_trials=5, seed=0)
    path = tmp_path / "out" / "results.csv"
    write_csv(rows, path)
    with path.open(encoding="utf-8") as fh:
        read = list(csv.reader(fh))
    assert read[0] == [f.name for f in fields(BenchRow)]
    assert len(read) == 1 + len(rows)


def test_format_table_renders(sample_paper: Paper) -> None:
    codebook = assign(sample_paper, 100, 0)
    rows = run_bench(sample_paper, codebook, k_values=(2,), n_trials=5, seed=0)
    table = format_table(rows)
    assert "false-id%" in table and "mean_pos" in table


# --- M5: accuracy by which questions leaked ----------------------------------------------------
def test_question_regions_split_into_thirds(sample_paper: Paper) -> None:
    from eval.bench import question_regions

    assert question_regions(sample_paper) == {
        "early": [1, 2, 3],
        "middle": [4, 5, 6],
        "late": [7, 8],
    }


def test_keep_questions_keeps_exactly_the_requested_blocks(sample_paper: Paper) -> None:
    from eval.bench import keep_questions
    from examfp.cli import render_text

    text = render_text(sample_paper, assign(sample_paper, 10, 0)[3])
    kept = keep_questions(text, [2, 7])
    blocks = [b for b in kept.split("\n\n") if b.strip()]
    assert [b.split(".", 1)[0] for b in blocks] == ["2", "7"]
    assert "A)" in blocks[0]  # MCQ options travel with their question


def test_run_region_bench_shape_and_valid_rates(sample_paper: Paper) -> None:
    from eval.bench import run_region_bench

    rows = run_region_bench(sample_paper, assign(sample_paper, 200, 0), n_trials=5, seed=0,
                            label="rs")
    cells = [(r.region, r.k) for r in rows]
    assert cells == [("early", 1), ("early", 2), ("early", 3), ("middle", 1), ("middle", 2),
                     ("middle", 3), ("late", 1), ("late", 2)]
    for r in rows:
        assert r.codebook == "rs" and r.trials == 5
        for rate in (r.identified_rate, r.correct_rate, r.insufficient_rate, r.false_id_rate):
            assert 0.0 <= rate <= 1.0
        assert r.identified_rate == pytest.approx(r.correct_rate + r.false_id_rate)


def test_region_csv_has_header(sample_paper: Paper, tmp_path: Path) -> None:
    from eval.bench import RegionRow, run_region_bench

    rows = run_region_bench(sample_paper, assign(sample_paper, 50, 0), n_trials=2, seed=0)
    path = tmp_path / "by_region.csv"
    write_csv(rows, path)
    with path.open(encoding="utf-8") as fh:
        read = list(csv.reader(fh))
    assert read[0] == [f.name for f in fields(RegionRow)]
    assert len(read) == 1 + len(rows)


# --- M5.5: calibration, read floor, collusion before/after ---------------------------------------
def test_measure_misreads_counts_disagreements_with_the_source(sample_paper: Paper) -> None:
    from eval.bench import measure_misreads

    report = measure_misreads(sample_paper, assign(sample_paper, 200, 0), n_trials=10, seed=0)
    assert report.reads > 0 and 0 <= report.misreads <= report.reads
    assert report.upper95 >= report.misreads / report.reads


def test_floor_sweep_rows_and_suggestion(sample_paper: Paper) -> None:
    from eval.bench import FloorRow, run_floor_sweep, suggest_floor

    rows = run_floor_sweep(sample_paper, assign(sample_paper, 200, 0), sizes=(1, 2),
                           k_values=(1, 4), n_trials=4, seed=0, misread_rate=0.0)
    assert rows == sorted(rows, key=lambda r: r.reads)
    for r in rows:
        assert r.trials == r.correct + r.false_identified + r.suspected + r.refused
    fake = [FloorRow(3, 5, 0, 1, 0, 0, 4), FloorRow(9, 5, 4, 0, 0, 0, 1),
            FloorRow(7, 5, 2, 2, 0, 0, 1)]
    assert suggest_floor(fake) == 8  # one above the most reads at which an innocent was named
    assert suggest_floor([FloorRow(5, 3, 3, 0, 0, 0, 0)]) == 1


def test_collusion_bench_before_and_after(sample_paper: Paper) -> None:
    from eval.bench import CollusionRow, run_collusion_bench

    rows = run_collusion_bench(sample_paper, assign(sample_paper, 200, 0), sizes=(1, 2),
                               n_trials=4, seed=0)
    assert [(r.rule, r.coalition) for r in rows] == [
        ("before", 1), ("after", 1), ("before", 2), ("after", 2)]
    for r in rows:
        assert isinstance(r, CollusionRow)
        assert r.trials == (r.identified_colluder + r.identified_innocent + r.suspected_exact
                            + r.suspected_partial + r.suspected_with_innocent + r.insufficient
                            + r.no_match)
        if r.rule == "before":
            assert r.suspected_exact == r.suspected_partial == r.suspected_with_innocent == 0
