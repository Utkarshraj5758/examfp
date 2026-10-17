"""Variant separation sweep: how alike can two variants be before the reader confuses them?

The M6 finding: "Show your work." beside "Show your working." (edit distance 3,
a near-prefix) was misread 6 times in 104,048 reads. This sweep measures the
reader's confusion as a function of the distance between two variants, so the
minimum in :data:`examfp.fairness.separation.MIN_EDIT_DISTANCE` is measured, not
guessed (ADR 0004).

For every text-read slot of the sample paper (wording, instruction and unit-form
slots; 23 in all), the slot's reference variant is paired with synthetic
competitors, and each pair is read under the benchmark's attack: render the
question, retype, 3% adjacent-letter typos, ``read_leak`` against the whole
paper. The variant shown alternates. A read returning the other variant is a
misread; an unread slot is an erasure (never a guess).

Families of competitors (all deterministic, seeded per pair):

* ``edit``: random letter substitutions, insertions and deletions until the
  Levenshtein distance is exactly ``d`` (1..12), excluding any pair in a prefix
  or containment relation. Three competitors per slot and distance.
* ``prefix``: the reference truncated or extended by ``k`` letters before its
  final punctuation (1..8): the shape of the M6 finding.
* ``contained``: ``k`` leading letters dropped or prepended (1..8), so one text
  contains the other without being its prefix.
* ``paper``: the paper's own variant pairs, plus the M6 pair itself.

**The rule for the minimum, fixed before the sweep ran:** the smallest ``d``
such that the ``edit`` family shows no misread at ``d`` or any larger distance,
and the reads pooled from ``d`` upwards bound the misread rate at or below the
calibrated ``MISREAD_RATE`` (95% Clopper-Pearson), so separation keeps the
decision rule's calibration valid (ADR 0003).

``python -m eval.separation`` prints the tables and writes
``eval/out/separation.csv``.
"""

from __future__ import annotations

import csv
import functools
import random
import string
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import astuple, dataclass, fields
from pathlib import Path

from examfp.attacks import retype, typos
from examfp.cli import render_text
from examfp.decode.calibrate import misread_upper_bound
from examfp.decode.read import read_leak
from examfp.decode.score import MISREAD_RATE
from examfp.fairness.separation import edit_distance, is_prefix_pair
from examfp.fairness.separation import is_contained_pair as contains_pair
from examfp.models import OptionOrderSlot, Paper, Question, TextSlot, Variant

_SAMPLE = Path(__file__).resolve().parents[1] / "data" / "papers" / "sample.json"
_OUT = Path(__file__).resolve().parent / "out" / "separation.csv"
_TYPO_RATE = 0.03
_TRAILING = ".,;:!? "
M6_PAIR = ("q1", "closing", "Show your working.", "Show your work.")


@dataclass(frozen=True)
class PairResult:
    family: str
    question: str
    slot: str
    reference: str
    competitor: str
    distance: int
    prefix: bool
    contained: bool
    reads: int
    misreads: int
    erasures: int


def text_slots(paper: Paper) -> list[tuple[str, str, str]]:
    """``(question, slot, reference)`` for every slot the reader matches as text."""
    out = []
    for question in paper.questions:
        for slot in question.slots:
            if isinstance(slot, OptionOrderSlot):
                continue
            if isinstance(slot, TextSlot) and slot.difficulty_band is not None:
                continue
            out.append((question.id, slot.name, slot.variants[0].values[0]))
    return out


def _split(text: str) -> tuple[str, str]:
    core = text.rstrip(_TRAILING)
    return core, text[len(core):]


def edit_competitor(reference: str, distance: int, rng: random.Random,
                    attempts: int = 5000) -> str | None:
    """A text at exactly ``distance`` from ``reference``, in no prefix or containment relation."""
    editable = [i for i, c in enumerate(reference) if not c.isdigit()]
    for _ in range(attempts):
        # Substitutions and deletions at distinct original positions, insertions for
        # the rest, so the edits rarely cancel and long distances stay reachable on
        # short references.
        touched = rng.randint(0, min(distance, len(editable)))
        spots = set(rng.sample(editable, touched))
        out: list[str] = []
        for i, c in enumerate(reference):
            if i in spots:
                if rng.random() < 0.5 or len(spots) == len(reference):  # never delete it all
                    out.append(rng.choice([x for x in string.ascii_lowercase if x != c.lower()]))
            else:
                out.append(c)
        for _ in range(distance - touched):
            out.insert(rng.randint(0, len(out)), rng.choice(string.ascii_lowercase))
        candidate = "".join(out)
        if (candidate.strip() and edit_distance(reference, candidate) == distance
                and not contains_pair(reference, candidate)):
            return candidate
    return None


def prefix_competitor(reference: str, k: int, extend: bool, rng: random.Random) -> str | None:
    """The reference cut or extended by ``k`` letters before its final punctuation."""
    core, tail = _split(reference)
    if extend:
        candidate = core + "".join(rng.choice(string.ascii_lowercase) for _ in range(k)) + tail
    else:
        if len(core) - k < 1:
            return None
        candidate = core[:-k].rstrip() + tail
    return candidate if is_prefix_pair(reference, candidate) else None


def contained_competitor(reference: str, k: int, extend: bool, rng: random.Random) -> str | None:
    """``k`` leading letters prepended or dropped: containment that is not a prefix."""
    if extend:
        candidate = "".join(rng.choice(string.ascii_lowercase) for _ in range(k)) + reference
    else:
        if len(reference) - k < 1:
            return None
        candidate = reference[k:].lstrip()
    ok = contains_pair(reference, candidate) and not is_prefix_pair(reference, candidate)
    return candidate if ok else None


def _with_variants(paper: Paper, qid: str, slot_name: str, texts: Sequence[str]) -> Paper:
    questions: list[Question] = []
    for question in paper.questions:
        if question.id == qid:
            slots = [s.model_copy(update={"variants": [Variant(values=[t]) for t in texts]})
                     if s.name == slot_name else s for s in question.slots]
            question = question.model_copy(update={"slots": slots})
        questions.append(question)
    return paper.model_copy(update={"questions": questions})


def measure_pair(paper: Paper, qid: str, slot_name: str, reference: str, competitor: str,
                 reads: int, rng: random.Random, family: str = "edit") -> PairResult:
    """Read a two-variant slot ``reads`` times under the benchmark attack, alternating."""
    full = _with_variants(paper, qid, slot_name, [reference, competitor])
    question = next(q for q in full.questions if q.id == qid)
    alone = full.model_copy(update={"questions": [question]})
    misreads = erasures = 0
    for i in range(reads):
        shown = i % 2
        symbols = {(qid, s.name): (shown if s.name == slot_name else 0) for s in question.slots}
        leak = typos(retype(render_text(alone, symbols)), _TYPO_RATE, rng)
        got = read_leak(leak, full).get((qid, slot_name))
        if got is None:
            erasures += 1
        elif got[0] != shown:
            misreads += 1
    return PairResult(family, qid, slot_name, reference, competitor,
                      edit_distance(reference, competitor), is_prefix_pair(reference, competitor),
                      contains_pair(reference, competitor), reads, misreads, erasures)


def _run_pair(results: list[PairResult], paper: Paper, seed: int, qid: str, slot_name: str,
              reference: str, family: str, competitor: str | None, tag: str,
              n: int) -> None:
    """Measure one pair, if the generator produced a competitor, with its own seed."""
    if competitor is None:
        return
    rng = random.Random(f"{seed}|read|{family}|{qid}|{slot_name}|{tag}")
    results.append(measure_pair(paper, qid, slot_name, reference, competitor, n, rng, family))


def sweep(paper: Paper, reads: int = 1000, distances: Iterable[int] = range(1, 13),
          per_distance: int = 3, ks: Iterable[int] = range(1, 9), seed: int = 0
          ) -> list[PairResult]:
    """Every family over every text-read slot; each pair seeded from its own identity."""
    distances, ks = list(distances), list(ks)
    results: list[PairResult] = []
    for qid, slot_name, reference in text_slots(paper):
        run = functools.partial(_run_pair, results, paper, seed, qid, slot_name, reference)
        for d in distances:
            for j in range(per_distance):
                rng = random.Random(f"{seed}|edit|{qid}|{slot_name}|{d}|{j}")
                run("edit", edit_competitor(reference, d, rng), f"{d}|{j}", n=reads)
        for k in ks:
            for extend in (False, True):
                rng = random.Random(f"{seed}|shape|{qid}|{slot_name}|{k}|{extend}")
                run("prefix", prefix_competitor(reference, k, extend, rng), f"p{k}{extend}",
                    n=reads)
                run("contained", contained_competitor(reference, k, extend, rng),
                    f"c{k}{extend}", n=reads)
        slot = next(s for q in paper.questions if q.id == qid for s in q.slots
                    if s.name == slot_name)
        assert not isinstance(slot, OptionOrderSlot)
        for variant in slot.variants[1:]:
            run("paper", variant.values[0], f"paper|{variant.values[0]}", n=4 * reads)
    qid, slot_name, reference, competitor = M6_PAIR
    rng = random.Random(f"{seed}|read|m6")
    results.append(measure_pair(paper, qid, slot_name, reference, competitor, 4 * reads, rng,
                                "m6"))
    return results


@dataclass(frozen=True)
class DistanceRow:
    distance: int
    pairs: int
    reads: int
    misreads: int
    erasures: int


def by_distance(results: Sequence[PairResult], family: str = "edit") -> list[DistanceRow]:
    """Tally one family by edit distance."""
    cells: dict[int, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for r in results:
        if r.family == family:
            cell = cells[r.distance]
            cell[0] += 1
            cell[1] += r.reads
            cell[2] += r.misreads
            cell[3] += r.erasures
    return [DistanceRow(d, *cell) for d, cell in sorted(cells.items())]


def suggest_min_distance(rows: Sequence[DistanceRow], misread_rate: float = MISREAD_RATE
                         ) -> int | None:
    """The smallest distance with no misread at or above it whose pooled reads bound the rate.

    Returns ``None`` when no distance in the sweep qualifies (sweep too small or
    confusion at the largest distance tested).
    """
    for i, row in enumerate(rows):
        tail = rows[i:]
        if any(r.misreads for r in tail):
            continue
        pooled = sum(r.reads for r in tail)
        if pooled and misread_upper_bound(0, pooled) <= misread_rate:
            return row.distance
        return None
    return None


def format_rows(rows: Sequence[DistanceRow], label: str) -> str:
    lines = [f"{label:<10} {'d':>3} {'pairs':>5} {'reads':>8} {'misreads':>8} {'erasures':>8}"]
    for r in rows:
        lines.append(f"{'':<10} {r.distance:>3} {r.pairs:>5} {r.reads:>8} {r.misreads:>8} "
                     f"{r.erasures:>8}")
    return "\n".join(lines)


def write_csv(results: Sequence[PairResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([f.name for f in fields(PairResult)])
        for r in results:
            writer.writerow(astuple(r))


def main() -> None:
    paper = Paper.model_validate_json(_SAMPLE.read_text(encoding="utf-8"))
    results = sweep(paper)
    edit = by_distance(results, "edit")
    print(format_rows(edit, "edit"))
    print(format_rows(by_distance(results, "prefix"), "prefix"))
    print(format_rows(by_distance(results, "contained"), "contained"))
    for r in results:
        if r.family in ("paper", "m6"):
            print(f"{r.family:<6} {r.question}.{r.slot:<8} d={r.distance:>2} "
                  f"{r.reference!r} / {r.competitor!r}: {r.misreads}/{r.reads} misreads, "
                  f"{r.erasures} erasures")
    confused = [r for r in results if r.family == "edit" and r.misreads]
    for r in sorted(confused, key=lambda r: -r.distance)[:10]:
        print(f"confused (edit) d={r.distance}: {r.reference!r} / {r.competitor!r} "
              f"{r.misreads}/{r.reads}")
    suggestion = suggest_min_distance(edit)
    print(f"suggested MIN_EDIT_DISTANCE = {suggestion} (pooled bound <= MISREAD_RATE "
          f"{MISREAD_RATE:.2e})")
    write_csv(results, _OUT)
    print(f"wrote {_OUT}")


if __name__ == "__main__":
    main()
