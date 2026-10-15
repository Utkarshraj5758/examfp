"""Robustness sweeps: how well a degraded leak is traced, and whether *which* leaks matters.

1. **k sweep.** For ``k`` in 1..8: random centre -> crop to ``k`` random questions
   -> retype -> 3% typos -> trace.
2. **Region sweep (M5).** Leaks drawn only from the early, middle or late third
   of the paper, for every ``k`` up to the size of that third. A codebook whose
   accuracy depends on position shows up here at once.

Both sweeps run for the current Reed-Solomon codebook (``rs``) and the
superseded mixed-radix one (``mixed-radix``, :mod:`eval.baselines`), so the
before/after sits in one table. All randomness flows from seeded generators.

``python -m eval.bench`` (or ``.\\tasks.ps1 bench``) prints both tables and writes
``eval/out/results.csv`` and ``eval/out/results_by_region.csv``. No plots.
"""

from __future__ import annotations

import csv
import random
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import astuple, dataclass, fields
from pathlib import Path

from eval.baselines import mixed_radix_assign
from examfp.attacks import crop, retype, typos
from examfp.cli import render_text
from examfp.codebook.assign import assign
from examfp.decode.read import read_leak
from examfp.decode.score import Outcome, score
from examfp.models import Paper

_SAMPLE = Path(__file__).resolve().parents[1] / "data" / "papers" / "sample.json"
_OUT = Path(__file__).resolve().parent / "out" / "results.csv"
_OUT_REGION = Path(__file__).resolve().parent / "out" / "results_by_region.csv"
_TYPO_RATE = 0.03
_QUESTION = re.compile(r"^\s*(\d+)\s*[.)]")

Codebook = Mapping[int, Mapping[tuple[str, str], int]]
CODEBOOKS: dict[str, Callable[[Paper, int, int], dict[int, dict[tuple[str, str], int]]]] = {
    "rs": assign,
    "mixed-radix": mixed_radix_assign,
}


@dataclass(frozen=True)
class BenchRow:
    k: int
    trials: int
    identified_rate: float
    correct_rate: float
    insufficient_rate: float
    false_id_rate: float
    mean_positions: float
    codebook: str = "rs"


@dataclass(frozen=True)
class RegionRow:
    codebook: str
    region: str
    k: int
    trials: int
    identified_rate: float
    correct_rate: float
    insufficient_rate: float
    false_id_rate: float
    mean_positions: float


@dataclass
class _Tally:
    identified: int = 0
    correct: int = 0
    insufficient: int = 0
    false_id: int = 0
    positions: int = 0

    def add(self, paper: Paper, codebook: Codebook, centre: int, leak: str) -> None:
        result = score(read_leak(leak, paper), codebook)
        self.positions += result.positions_used
        if result.outcome is Outcome.IDENTIFIED:
            self.identified += 1
            if result.ranked[0][0] == centre:
                self.correct += 1
            else:
                self.false_id += 1
        elif result.outcome is Outcome.INSUFFICIENT:
            self.insufficient += 1

    def rates(self, n: int) -> tuple[float, float, float, float, float]:
        return (
            self.identified / n,
            self.correct / n,
            self.insufficient / n,
            self.false_id / n,
            self.positions / n,
        )


# --- k sweep -----------------------------------------------------------------------------------
def run_bench(
    paper: Paper,
    codebook: Codebook,
    k_values: Iterable[int] = range(1, 9),
    n_trials: int = 200,
    seed: int = 0,
    label: str = "rs",
) -> list[BenchRow]:
    """Crop to ``k`` random questions; all randomness flows from ``seed``."""
    centres = list(codebook)
    rng = random.Random(seed)
    rows: list[BenchRow] = []
    for k in k_values:
        tally = _Tally()
        for _ in range(n_trials):
            centre = rng.choice(centres)
            text = render_text(paper, codebook[centre])
            tally.add(paper, codebook, centre, typos(retype(crop(text, k, rng)), _TYPO_RATE, rng))
        rows.append(BenchRow(k, n_trials, *tally.rates(n_trials), codebook=label))
    return rows


# --- region sweep ------------------------------------------------------------------------------
def question_regions(paper: Paper) -> dict[str, list[int]]:
    """Split question numbers (1-based) into contiguous early/middle/late thirds.

    Guarantees: every question in exactly one region, in paper order; sizes differ
    by at most one, earlier regions taking the extra questions.
    """
    base, extra = divmod(len(paper.questions), 3)
    regions: dict[str, list[int]] = {}
    start = 1
    for i, name in enumerate(("early", "middle", "late")):
        size = base + (1 if i < extra else 0)
        regions[name] = list(range(start, start + size))
        start += size
    return regions


def keep_questions(text: str, numbers: Iterable[int]) -> str:
    """Keep only the rendered question blocks with these numbers (options included)."""
    wanted = set(numbers)
    blocks = [b for b in text.split("\n\n") if b.strip()]
    kept = []
    for block in blocks:
        match = _QUESTION.match(block)
        if match and int(match.group(1)) in wanted:
            kept.append(block)
    return "\n\n".join(kept)


def run_region_bench(
    paper: Paper,
    codebook: Codebook,
    n_trials: int = 200,
    seed: int = 0,
    label: str = "rs",
) -> list[RegionRow]:
    """Leak ``k`` random questions from one region at a time; seeded throughout."""
    centres = list(codebook)
    rng = random.Random(seed)
    rows: list[RegionRow] = []
    for region, numbers in question_regions(paper).items():
        for k in range(1, len(numbers) + 1):
            tally = _Tally()
            for _ in range(n_trials):
                centre = rng.choice(centres)
                text = keep_questions(render_text(paper, codebook[centre]), rng.sample(numbers, k))
                tally.add(paper, codebook, centre, typos(retype(text), _TYPO_RATE, rng))
            rows.append(RegionRow(label, region, k, n_trials, *tally.rates(n_trials)))
    return rows


# --- output ------------------------------------------------------------------------------------
def format_table(rows: Sequence[BenchRow]) -> str:
    header = (
        f"{'codebook':<12} {'k':>2}  {'trials':>6}  {'ident%':>7}  {'correct%':>8}  "
        f"{'insuff%':>7}  {'false-id%':>9}  {'mean_pos':>8}"
    )
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r.codebook:<12} {r.k:>2}  {r.trials:>6}  {100 * r.identified_rate:>7.1f}  "
            f"{100 * r.correct_rate:>8.1f}  {100 * r.insufficient_rate:>7.1f}  "
            f"{100 * r.false_id_rate:>9.1f}  {r.mean_positions:>8.1f}"
        )
    return "\n".join(lines)


def format_region_table(rows: Sequence[RegionRow]) -> str:
    header = (
        f"{'codebook':<12} {'region':<7} {'k':>2}  {'correct%':>8}  {'insuff%':>7}  "
        f"{'false-id%':>9}  {'mean_pos':>8}"
    )
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r.codebook:<12} {r.region:<7} {r.k:>2}  {100 * r.correct_rate:>8.1f}  "
            f"{100 * r.insufficient_rate:>7.1f}  {100 * r.false_id_rate:>9.1f}  "
            f"{r.mean_positions:>8.1f}"
        )
    return "\n".join(lines)


def write_csv(rows: Sequence[BenchRow] | Sequence[RegionRow], path: Path) -> None:
    """Write dataclass rows to CSV, header taken from the row type."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if rows:
            writer.writerow([f.name for f in fields(rows[0])])
        for row in rows:
            writer.writerow(astuple(row))


def main() -> None:
    paper = Paper.model_validate_json(_SAMPLE.read_text(encoding="utf-8"))
    k_rows: list[BenchRow] = []
    region_rows: list[RegionRow] = []
    for label, build in CODEBOOKS.items():
        book = build(paper, 1000, 0)
        k_rows += run_bench(paper, book, range(1, 9), n_trials=200, seed=0, label=label)
        region_rows += run_region_bench(paper, book, n_trials=200, seed=0, label=label)
    print(format_table(k_rows))
    print()
    print(format_region_table(region_rows))
    write_csv(k_rows, _OUT)
    write_csv(region_rows, _OUT_REGION)
    print(f"\nwrote {_OUT}\nwrote {_OUT_REGION}")


if __name__ == "__main__":
    main()
