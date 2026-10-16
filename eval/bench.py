"""Robustness sweeps: how well a degraded leak is traced, and whether *which* leaks matters.

1. **k sweep.** For ``k`` in 1..8: random centre -> crop to ``k`` random questions
   -> retype -> 3% typos -> trace.
2. **Region sweep (M5).** Leaks drawn only from the early, middle or late third
   of the paper, for every ``k`` up to the size of that third. A codebook whose
   accuracy depends on position shows up here at once.

Both sweeps run for the current Reed-Solomon codebook (``rs``) and the
superseded mixed-radix one (``mixed-radix``, :mod:`eval.baselines`), so the
before/after sits in one table.

3. **Calibration (M5.5).** The reader's misread rate on single-source leaks
   (95% upper bound), and a sweep of the consistency gate *without* a read floor
   over every crop size, single-source and colluded: the floor must sit above the
   most slots at which an innocent centre was ever named.
4. **Collusion (M5.5).** 2-5 centres, minority strategy, outcome distribution
   per coalition size for the old margin-only rule (``before``) and the gated
   rule with the deployed constants (``after``).

All randomness flows from seeded generators. The k-sweep and region
``false-id%`` columns cover single-source leaks only; colluded leaks are
reported separately in the collusion table.

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

from eval.baselines import mixed_radix_assign, score_ungated
from examfp.attacks import collude, crop, retype, typos
from examfp.cli import render_text
from examfp.codebook.assign import assign
from examfp.decode.calibrate import mismatch_tolerance, misread_upper_bound
from examfp.decode.read import read_leak
from examfp.decode.score import (
    FALSE_REJECTION_BUDGET,
    MIN_READ_SLOTS,
    MISREAD_RATE,
    Outcome,
    ScoreResult,
    score,
)
from examfp.models import Paper

_SAMPLE = Path(__file__).resolve().parents[1] / "data" / "papers" / "sample.json"
_OUT = Path(__file__).resolve().parent / "out" / "results.csv"
_OUT_REGION = Path(__file__).resolve().parent / "out" / "results_by_region.csv"
_OUT_FLOOR = Path(__file__).resolve().parent / "out" / "results_floor.csv"
_OUT_COLLUSION = Path(__file__).resolve().parent / "out" / "results_collusion.csv"
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


def write_csv(
    rows: Sequence[BenchRow] | Sequence[RegionRow] | Sequence[FloorRow] | Sequence[CollusionRow],
    path: Path,
) -> None:
    """Write dataclass rows to CSV, header taken from the row type."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if rows:
            writer.writerow([f.name for f in fields(rows[0])])
        for row in rows:
            writer.writerow(astuple(row))


# --- M5.5: calibration -------------------------------------------------------------------------
@dataclass(frozen=True)
class MisreadReport:
    reads: int
    misreads: int
    upper95: float

    @property
    def point(self) -> float:
        return self.misreads / self.reads if self.reads else 0.0


def _leak(
    paper: Paper, codebook: Codebook, sources: list[int], k: int, rng: random.Random
) -> str:
    """Single-source (one id) or colluded (2+ ids, minority) leak: crop, retype, typos."""
    if len(sources) == 1:
        symbols = dict(codebook[sources[0]])
    else:
        symbols = collude([codebook[c] for c in sources], rng, strategy="minority")
    return typos(retype(crop(render_text(paper, symbols), k, rng)), _TYPO_RATE, rng)


def measure_misreads(
    paper: Paper, codebook: Codebook, n_trials: int = 400, seed: int = 0
) -> MisreadReport:
    """Count read slots that disagree with the true source (single-source leaks)."""
    rng = random.Random(seed)
    centres = list(codebook)
    reads = misreads = 0
    for i in range(n_trials):
        source = rng.choice(centres)
        observed = read_leak(_leak(paper, codebook, [source], 1 + i % 8, rng), paper)
        reads += len(observed)
        misreads += sum(codebook[source][p] != s for p, (s, _c) in observed.items())
    upper = misread_upper_bound(misreads, reads) if reads else 1.0
    return MisreadReport(reads, misreads, upper)


@dataclass(frozen=True)
class FloorRow:
    reads: int
    trials: int
    correct: int
    false_identified: int
    multi_source: int
    pair_with_innocent: int  # multi-source results whose named pair includes a non-source
    refused: int


def run_floor_sweep(
    paper: Paper,
    codebook: Codebook,
    sizes: Iterable[int] = (1, 2, 3, 4, 5),
    k_values: Iterable[int] = range(1, 9),
    n_trials: int = 100,
    seed: int = 0,
    misread_rate: float = MISREAD_RATE,
) -> list[FloorRow]:
    """Gated rule with NO read floor, tallied by slots read (the floor's evidence)."""
    rng = random.Random(seed)
    centres = list(codebook)
    tally: dict[int, list[int]] = {}
    for size in sizes:
        for k in k_values:
            for _ in range(n_trials):
                sources = rng.sample(centres, size)
                observed = read_leak(_leak(paper, codebook, sources, k, rng), paper)
                result = score(observed, codebook, misread_rate=misread_rate, min_read_slots=0)
                cell = tally.setdefault(result.positions_used, [0, 0, 0, 0, 0, 0])
                cell[0] += 1
                if result.outcome is Outcome.IDENTIFIED:
                    cell[1 if result.ranked[0][0] in sources else 2] += 1
                elif result.outcome is Outcome.MULTI_SOURCE_SUSPECTED:
                    cell[3] += 1
                    cell[4] += any(c not in sources for c in result.named_pair)
                else:
                    cell[5] += 1
    return [FloorRow(r, *cell) for r, cell in sorted(tally.items())]


def suggest_floor(rows: Sequence[FloorRow]) -> int:
    """One more than the most slots read at which an innocent centre was identified."""
    worst = [r.reads for r in rows if r.false_identified]
    return max(worst) + 1 if worst else 1


@dataclass(frozen=True)
class CollusionRow:
    rule: str
    coalition: int
    trials: int
    identified_colluder: int
    identified_innocent: int
    pair_exact: int  # multi-source, named pair == the coalition
    pair_partial: int  # multi-source, named pair inside the coalition
    pair_with_innocent: int  # multi-source, named pair includes a non-colluder
    multi_source_unnamed: int  # multi-source, nobody named
    insufficient: int
    no_match: int
    mean_reads: float


def _classify(result: ScoreResult, sources: list[int]) -> str:
    if result.outcome is Outcome.IDENTIFIED:
        return "identified_colluder" if result.ranked[0][0] in sources else "identified_innocent"
    if result.outcome is Outcome.MULTI_SOURCE_SUSPECTED:
        named = set(result.named_pair)
        if not named:
            return "multi_source_unnamed"
        if not named <= set(sources):
            return "pair_with_innocent"
        return "pair_exact" if named == set(sources) else "pair_partial"
    return "insufficient" if result.outcome is Outcome.INSUFFICIENT else "no_match"


def run_collusion_bench(
    paper: Paper,
    codebook: Codebook,
    sizes: Iterable[int] = (1, 2, 3, 4, 5),
    n_trials: int = 200,
    seed: int = 0,
    k_questions: int = 6,
) -> list[CollusionRow]:
    """The same leaks through the old margin-only rule and the gated rule."""
    rng = random.Random(seed)
    centres = list(codebook)
    rows: list[CollusionRow] = []
    rules: tuple[tuple[str, Callable[..., ScoreResult]], ...] = (
        ("before", score_ungated),
        ("after", score),
    )
    for size in sizes:
        counts: dict[str, dict[str, int]] = {"before": {}, "after": {}}
        reads = 0
        for _ in range(n_trials):
            sources = rng.sample(centres, size)
            observed = read_leak(_leak(paper, codebook, sources, k_questions, rng), paper)
            reads += len(observed)
            for rule, decide in rules:
                kind = _classify(decide(observed, codebook), sources)
                counts[rule][kind] = counts[rule].get(kind, 0) + 1
        for rule, _decide in rules:
            c = counts[rule]
            rows.append(CollusionRow(
                rule, size, n_trials, c.get("identified_colluder", 0),
                c.get("identified_innocent", 0), c.get("pair_exact", 0),
                c.get("pair_partial", 0), c.get("pair_with_innocent", 0),
                c.get("multi_source_unnamed", 0), c.get("insufficient", 0),
                c.get("no_match", 0), reads / n_trials,
            ))
    return rows


def format_floor_table(rows: Sequence[FloorRow]) -> str:
    header = (f"{'reads':>5} {'trials':>6} {'correct':>7} {'FALSE-ID':>8} "
              f"{'multi-src':>9} {'pair+innocent':>13} {'refused':>7}")
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(f"{r.reads:>5} {r.trials:>6} {r.correct:>7} {r.false_identified:>8} "
                     f"{r.multi_source:>9} {r.pair_with_innocent:>13} {r.refused:>7}")
    return "\n".join(lines)


def format_collusion_table(rows: Sequence[CollusionRow]) -> str:
    header = (f"{'rule':<6} {'c':>2} {'trials':>6} {'id-colluder':>11} {'ID-INNOCENT':>11} "
              f"{'pair=coal':>9} {'pair<coal':>9} {'pair+inn':>8} {'unnamed':>7} "
              f"{'insuff':>6} {'nomatch':>7}")
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r.rule:<6} {r.coalition:>2} {r.trials:>6} {r.identified_colluder:>11} "
            f"{r.identified_innocent:>11} {r.pair_exact:>9} {r.pair_partial:>9} "
            f"{r.pair_with_innocent:>8} {r.multi_source_unnamed:>7} {r.insufficient:>6} "
            f"{r.no_match:>7}"
        )
    return "\n".join(lines)


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

    book = assign(paper, 1000, 0)
    misreads = measure_misreads(paper, book, n_trials=6000, seed=0)
    print("\n=== calibration: single-source leaks, crops 1-8, retype, 3% typos ===")
    print(f"misreads {misreads.misreads} / {misreads.reads} read slots; point "
          f"{misreads.point:.2e}, 95% upper bound {misreads.upper95:.2e}")
    print(f"deployed MISREAD_RATE = {MISREAD_RATE:.2e} -> tolerance at 31 reads: "
          f"{mismatch_tolerance(31, MISREAD_RATE, FALSE_REJECTION_BUDGET)}")
    floor_rows = run_floor_sweep(paper, book, n_trials=100, seed=1,
                                 misread_rate=misreads.upper95)
    print("\n=== read floor: gated rule with NO floor, by slots read (100 trials per cell) ===")
    print(format_floor_table(floor_rows))
    print(f"suggested MIN_READ_SLOTS = {suggest_floor(floor_rows)}; deployed = {MIN_READ_SLOTS}")
    collusion_rows = run_collusion_bench(paper, book, n_trials=200, seed=2)
    print("\n=== collusion: minority strategy, 6 questions, retype, 3% typos (200 per row) ===")
    print(format_collusion_table(collusion_rows))
    write_csv(floor_rows, _OUT_FLOOR)
    write_csv(collusion_rows, _OUT_COLLUSION)
    for path in (_OUT, _OUT_REGION, _OUT_FLOOR, _OUT_COLLUSION):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
