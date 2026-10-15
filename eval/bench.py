"""Robustness sweep: how well a k-question retyped, typo'd leak is traced.

For each crop size ``k`` we run many trials of
``random centre -> crop to k -> retype -> 3% typos -> trace`` and record how
often the trace lands on the right centre (and how often it goes wrong).

Run with ``python -m eval.bench`` (or ``make bench``); writes
``eval/out/results.csv`` and prints a table.  No plots.
"""

from __future__ import annotations

import csv
import random
from collections.abc import Iterable, Mapping
from dataclasses import astuple, dataclass, fields
from pathlib import Path

from examfp.attacks import crop, retype, typos
from examfp.cli import render_text
from examfp.codebook.assign import assign
from examfp.decode.read import read_leak
from examfp.decode.score import Outcome, score
from examfp.models import Paper

_SAMPLE = Path(__file__).resolve().parents[1] / "data" / "papers" / "sample.json"
_OUT = Path(__file__).resolve().parent / "out" / "results.csv"
_TYPO_RATE = 0.03

Codebook = Mapping[int, Mapping[tuple[str, str], int]]


@dataclass(frozen=True)
class BenchRow:
    k: int
    trials: int
    identified_rate: float
    correct_rate: float
    insufficient_rate: float
    false_id_rate: float
    mean_positions: float


def _one_trial(
    paper: Paper, codebook: Codebook, centres: list[int], rng: random.Random, k: int
) -> tuple[str, bool, int]:
    """Return ``(outcome, correct, positions_recovered)`` for one leak."""
    centre = rng.choice(centres)
    text = render_text(paper, codebook[centre])
    leak = typos(retype(crop(text, k, rng)), _TYPO_RATE, rng)  # retype, then typos
    result = score(read_leak(leak, paper), codebook)
    correct = bool(result.ranked) and result.ranked[0][0] == centre
    return result.outcome.value, correct, result.positions_used


def run_bench(
    paper: Paper,
    codebook: Codebook,
    k_values: Iterable[int] = range(1, 9),
    n_trials: int = 200,
    seed: int = 0,
) -> list[BenchRow]:
    """Run the sweep; all randomness flows from the seeded generator."""
    centres = list(codebook)
    rng = random.Random(seed)
    rows: list[BenchRow] = []
    for k in k_values:
        identified = correct = insufficient = false_id = 0
        positions_total = 0
        for _ in range(n_trials):
            outcome, is_correct, positions = _one_trial(paper, codebook, centres, rng, k)
            positions_total += positions
            if outcome == Outcome.IDENTIFIED.value:
                identified += 1
                if is_correct:
                    correct += 1
                else:
                    false_id += 1
            elif outcome == Outcome.INSUFFICIENT.value:
                insufficient += 1
        rows.append(
            BenchRow(
                k=k,
                trials=n_trials,
                identified_rate=identified / n_trials,
                correct_rate=correct / n_trials,
                insufficient_rate=insufficient / n_trials,
                false_id_rate=false_id / n_trials,
                mean_positions=positions_total / n_trials,
            )
        )
    return rows


def format_table(rows: list[BenchRow]) -> str:
    header = (
        f"{'k':>2}  {'trials':>6}  {'ident%':>7}  {'correct%':>8}  "
        f"{'insuff%':>7}  {'false-id%':>9}  {'mean_pos':>8}"
    )
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r.k:>2}  {r.trials:>6}  {100 * r.identified_rate:>7.1f}  "
            f"{100 * r.correct_rate:>8.1f}  {100 * r.insufficient_rate:>7.1f}  "
            f"{100 * r.false_id_rate:>9.1f}  {r.mean_positions:>8.1f}"
        )
    return "\n".join(lines)


def write_csv(rows: list[BenchRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [f.name for f in fields(BenchRow)]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(columns)
        for row in rows:
            writer.writerow(astuple(row))


def main() -> None:
    paper = Paper.model_validate_json(_SAMPLE.read_text(encoding="utf-8"))
    codebook = assign(paper, 1000, seed=0)
    rows = run_bench(paper, codebook, k_values=range(1, 9), n_trials=200, seed=0)
    print(format_table(rows))
    write_csv(rows, _OUT)
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    main()
