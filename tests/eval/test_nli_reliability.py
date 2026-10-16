"""The held-out NLI reliability set is well formed, and its interval is exact. No model."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from eval.nli_reliability import clopper_pearson
from examfp.fairness.check import numbers

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
