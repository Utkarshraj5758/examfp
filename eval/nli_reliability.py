"""NLI model reliability (PLAN.md M6, decision 7): M9's baseline.

Scores two sets exactly as the fairness checker scores a wording candidate,
entailment in both directions at the configured threshold:

1. ``eval/nli_reliability.json``: 60 hand-labelled pairs outside the fixture,
   half equivalent, half not (changed quantity, changed units, added or removed
   constraint, reversed relationship). Accuracy with a 95% Clopper-Pearson
   interval, overall and by kind.
2. The fixture's wording subset (``tests/fixtures/variants.json``): agreement of
   the model's decision with the hand labels, on the entries the checker sends
   to the model (wording slots with identical numbers; U11 is decided by the
   numbers rule). Unit forms are judged by the unit table, not the model (owner
   decision, 2026-10-17); the model's view of them is printed for reference.

Needs the ``fairness`` extra and the pinned model (``.\\tasks.ps1 fetch-models``).
``python -m eval.nli_reliability`` prints both tables and writes
``eval/out/nli_reliability.csv``. Deterministic: no sampling anywhere.
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import astuple, dataclass, fields
from pathlib import Path

from examfp.decode.calibrate import misread_upper_bound
from examfp.fairness.check import candidate_text, numbers, reference_text
from examfp.fairness.nli import DEFAULT_THRESHOLD, CrossEncoderNli, NliBackend, nli_model_dir
from examfp.models import Paper, UnitFormSlot

_ROOT = Path(__file__).resolve().parents[1]
_PAIRS = Path(__file__).resolve().parent / "nli_reliability.json"
_FIXTURE = _ROOT / "tests" / "fixtures" / "variants.json"
_SAMPLE = _ROOT / "data" / "papers" / "sample.json"
_OUT = Path(__file__).resolve().parent / "out" / "nli_reliability.csv"


@dataclass(frozen=True)
class Scored:
    set: str
    id: str
    kind: str
    label_equivalent: bool
    forward: float  # reference -> candidate
    backward: float  # candidate -> reference
    accepted: bool

    @property
    def correct(self) -> bool:
        return self.accepted == self.label_equivalent


def clopper_pearson(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Two-sided exact interval for a proportion (each tail (1 - confidence) / 2)."""
    one_sided = 1.0 - (1.0 - confidence) / 2.0
    upper = misread_upper_bound(successes, n, one_sided)
    lower = 1.0 - misread_upper_bound(n - successes, n, one_sided)
    return max(0.0, lower), min(1.0, upper)


def _score(backend: NliBackend, set_name: str, item_id: str, kind: str, equivalent: bool,
           reference: str, candidate: str, threshold: float) -> Scored:
    forward = backend.entailment(reference, candidate)
    backward = backend.entailment(candidate, reference)
    accepted = forward >= threshold and backward >= threshold
    return Scored(set_name, item_id, kind, equivalent, forward, backward, accepted)


def score_reliability_set(backend: NliBackend, threshold: float = DEFAULT_THRESHOLD
                          ) -> list[Scored]:
    """Score every pair of the held-out set; refuses a pair whose numbers differ."""
    pairs = json.loads(_PAIRS.read_text(encoding="utf-8"))["pairs"]
    scored = []
    for pair in pairs:
        if numbers(pair["reference"]) != numbers(pair["candidate"]):
            raise ValueError(f"{pair['id']}: numbers differ; the checker never sends it to NLI")
        scored.append(_score(backend, "held-out", pair["id"], pair["kind"], pair["equivalent"],
                             pair["reference"], pair["candidate"], threshold))
    return scored


def score_fixture_wording(backend: NliBackend, threshold: float = DEFAULT_THRESHOLD
                          ) -> list[Scored]:
    """Score the fixture's wording entries that the checker would send to the model."""
    paper = Paper.model_validate_json(_SAMPLE.read_text(encoding="utf-8"))
    entries = json.loads(_FIXTURE.read_text(encoding="utf-8"))["variants"]
    scored = []
    for entry in entries:
        if entry["channel"] != "wording":
            continue
        question = next(q for q in paper.questions if q.id == entry["question"])
        slot = next(s for s in question.slots if s.name == entry["slot"])
        set_name = "fixture-units" if isinstance(slot, UnitFormSlot) else "fixture"
        reference = reference_text(question)
        candidate = candidate_text(question, entry["slot"], entry["values"])
        if numbers(reference) != numbers(candidate):
            continue
        scored.append(_score(backend, set_name, entry["id"], entry["violation"] or "fair",
                             entry["fair"], reference, candidate, threshold))
    return scored


def summarise(rows: list[Scored]) -> list[str]:
    """Accuracy with its interval, by kind, and the misjudged items."""
    correct = sum(r.correct for r in rows)
    low, high = clopper_pearson(correct, len(rows))
    lines = [f"accuracy {correct}/{len(rows)} = {100 * correct / len(rows):.1f}% "
             f"(95% CI {100 * low:.1f}-{100 * high:.1f}%)"]
    by_kind: dict[str, list[Scored]] = defaultdict(list)
    for r in rows:
        by_kind[r.kind].append(r)
    for kind, items in sorted(by_kind.items()):
        lines.append(f"  {kind:<22} {sum(i.correct for i in items):>2}/{len(items)}")
    equivalent = [r for r in rows if r.label_equivalent]
    different = [r for r in rows if not r.label_equivalent]
    lines.append(f"  false rejections {sum(not r.accepted for r in equivalent)}/{len(equivalent)}"
                 f", false acceptances {sum(r.accepted for r in different)}/{len(different)}")
    for r in rows:
        if not r.correct:
            lines.append(f"  wrong: {r.id} ({r.kind}) forward {r.forward:.3f} "
                         f"backward {r.backward:.3f}")
    return lines


def write_csv(rows: list[Scored], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([f.name for f in fields(Scored)])
        for row in rows:
            writer.writerow(astuple(row))


def main() -> None:
    backend = CrossEncoderNli(nli_model_dir(_ROOT / "models"))
    held_out = score_reliability_set(backend)
    fixture = score_fixture_wording(backend)
    print(f"model {backend.version}, threshold {DEFAULT_THRESHOLD} both ways")
    print("\n=== held-out wording set (eval/nli_reliability.json) ===")
    print("\n".join(summarise(held_out)))
    sent = [r for r in fixture if r.set == "fixture"]
    units = [r for r in fixture if r.set == "fixture-units"]
    print("\n=== fixture wording entries the checker sends to the model: agreement ===")
    print("\n".join(summarise(sent)))
    print("\n=== fixture unit forms (judged by the unit table; model shown for reference) ===")
    print("\n".join(summarise(units)))
    write_csv(held_out + fixture, _OUT)
    print(f"\nwrote {_OUT}")


if __name__ == "__main__":
    main()
