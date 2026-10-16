"""The held-out NLI reliability set, its exact interval, and the model comparison. No model."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

from eval import nli_reliability
from eval.nli_reliability import (
    Reliability,
    Scored,
    clopper_pearson,
    comparison_table,
    reliability,
)
from examfp.fairness.check import numbers
from examfp.fairness.pins import NLI_PIN, NliPin

PAIRS = Path(__file__).resolve().parents[2] / "eval" / "nli_reliability.json"


def _pairs() -> list[dict[str, object]]:
    pairs: list[dict[str, object]] = json.loads(PAIRS.read_text(encoding="utf-8"))["pairs"]
    return pairs


def test_set_is_balanced_and_covers_every_kind() -> None:
    pairs = _pairs()
    assert len(pairs) == 60 and len({p["id"] for p in pairs}) == 60
    assert Counter(bool(p["equivalent"]) for p in pairs) == {True: 30, False: 30}
    kinds = Counter(str(p["kind"]) for p in pairs if not p["equivalent"])
    assert set(kinds) == {"changed_quantity", "changed_units", "constraint",
                          "reversed_relationship"}
    assert all(p["kind"] == "equivalent" for p in pairs if p["equivalent"])


def test_every_pair_would_reach_the_model() -> None:
    # The checker sends a wording pair to NLI only when its numbers are identical.
    for pair in _pairs():
        assert numbers(str(pair["reference"])) == numbers(str(pair["candidate"])), pair["id"]


def test_clopper_pearson_known_values() -> None:
    low, high = clopper_pearson(0, 10)
    assert low == 0.0 and high == pytest.approx(1 - 0.025 ** (1 / 10), rel=1e-6)
    low, high = clopper_pearson(10, 10)
    assert high == 1.0 and low == pytest.approx(0.025 ** (1 / 10), rel=1e-6)
    # 55 / 60, the interval reported in NOTES.md (M6).
    low, high = clopper_pearson(55, 60)
    assert (round(100 * low, 1), round(100 * high, 1)) == (81.6, 97.2)


def _row(item: str, equivalent: bool, accepted: bool) -> Scored:
    return Scored("held-out", item, "equivalent" if equivalent else "constraint", equivalent,
                  0.9 if accepted else 0.1, 0.9 if accepted else 0.1, accepted)


def test_reliability_counts_both_error_kinds() -> None:
    rows = [_row("E1", True, True), _row("E2", True, False), _row("E3", True, False),
            _row("N1", False, True), _row("N2", False, False)]
    assert reliability(rows) == Reliability(correct=2, n=5, false_acceptances=1, different=2,
                                            false_rejections=2, equivalent=3)


def test_comparison_table_has_one_line_per_model() -> None:
    small = Reliability(55, 60, 2, 30, 3, 30)
    lines = comparison_table([("org/a@1", small), ("org/b@2", Reliability(60, 60, 0, 30, 0, 30))])
    assert len(lines) == 3
    assert "55/60 = 91.7%" in lines[1] and "81.6-97.2%" in lines[1]
    assert "2/30" in lines[1] and lines[1].endswith("3/30")
    assert "60/60 = 100.0%" in lines[2] and lines[2].endswith("0/30")


class _ConstantNli:
    """Stands in for the cross-encoder: accepts every pair, records its pin."""

    def __init__(self, model_dir: Path, pin: NliPin) -> None:
        self.pin = pin

    @property
    def version(self) -> str:
        return self.pin.version

    def entailment(self, premise: str, hypothesis: str) -> float:
        return 1.0


def test_held_out_only_never_scores_the_fixture(monkeypatch: pytest.MonkeyPatch,
                                                tmp_path: Path,
                                                capsys: pytest.CaptureFixture[str]) -> None:
    def refuse(*args: object, **kwargs: object) -> list[Scored]:
        raise AssertionError("the fixture was scored")

    monkeypatch.setattr(nli_reliability, "CrossEncoderNli", _ConstantNli)
    monkeypatch.setattr(nli_reliability, "score_fixture_wording", refuse)
    monkeypatch.setattr(nli_reliability, "_OUT_DIR", tmp_path)
    monkeypatch.setattr(sys, "argv", ["nli_reliability", "--held-out-only"])
    nli_reliability.main()
    out = capsys.readouterr().out
    # A model that accepts everything: every equivalent pair right, every other wrong.
    assert f"{NLI_PIN.version}" in out and "30/60 = 50.0%" in out
    assert (tmp_path / "nli_reliability.csv").is_file()


def test_a_candidate_pin_writes_its_own_csv(tmp_path: Path) -> None:
    other = NliPin("other", "org/other-nli", "0" * 40, ("config.json",))
    assert nli_reliability.csv_path(NLI_PIN).name == "nli_reliability.csv"
    assert nli_reliability.csv_path(other).name == "nli_reliability-other.csv"
