"""Tests for the robustness benchmark sweep."""

from __future__ import annotations

import csv
from dataclasses import fields
from pathlib import Path

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
        assert r.identified_rate == r.correct_rate + r.false_id_rate
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
