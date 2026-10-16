"""M6 acceptance with the pinned NLI model (local only; CI deselects ``local_model``).

Acceptance (PLAN.md M6): at most 2 false rejections on the 29 fair entries,
zero false acceptances on the 11 unfair; the model loads lazily and scores a
pair in under 300 ms on CPU; the sample paper passes every check.

**Status (owner decision, 2026-10-17): the false-rejection budget is not met**
with ``cross-encoder/nli-deberta-v3-small@fa28048`` at threshold 0.5. Three fair
entries are rejected (F11, F13, F14), all by NLI, and no threshold separates
them from the unfair U09 and U10. The owner kept the model and threshold; the
failure is recorded in NOTES.md (M6) and the budget test is a strict xfail, so
it fails loudly the day it starts passing. The measured rejection set is pinned,
so any drift (model, threshold or code) shows up as a failure here.
"""

from __future__ import annotations

import time
from statistics import median
from typing import Any

import pytest

from examfp.fairness.check import FairnessChecker, FairnessReport
from examfp.fairness.nli import CrossEncoderNli
from examfp.fairness.readability import wordfreq_zipf
from examfp.models import Paper
from tests.fairness.support import ROOT, VIOLATION_CHECKS

pytestmark = pytest.mark.local_model

SAMPLE = ROOT / "data" / "papers" / "sample.json"
FALSE_REJECTION_BUDGET = 2
# Measured 2026-10-17, nli-deberta-v3-small@fa28048, threshold 0.5 (NOTES.md, M6).
RECORDED_FALSE_REJECTIONS = frozenset({"F11", "F13", "F14"})


@pytest.fixture(scope="module")
def fixture_reports(
    fixture_entries: list[dict[str, Any]], local_nli: CrossEncoderNli
) -> list[tuple[dict[str, Any], FairnessReport]]:
    sample_paper = Paper.model_validate_json(SAMPLE.read_text(encoding="utf-8"))
    checker = FairnessChecker(local_nli, wordfreq_zipf())
    out = []
    for entry in fixture_entries:
        question = next(q for q in sample_paper.questions if q.id == entry["question"])
        out.append((entry, checker.check_candidate(question, entry["slot"], entry["values"])))
    return out


def _false_rejections(reports: list[tuple[dict[str, Any], FairnessReport]]) -> set[str]:
    return {e["id"] for e, r in reports if e["fair"] and not r.passed}


def test_no_false_acceptances(fixture_reports: list[tuple[dict[str, Any], FairnessReport]],
                              local_nli: CrossEncoderNli) -> None:
    for entry, report in fixture_reports:
        if not entry["fair"]:
            assert not report.passed, entry["id"]
            # Each unfair entry fails exactly the rule on its label.
            assert report.failed <= VIOLATION_CHECKS[entry["violation"]], (entry["id"], report)
        if report.nli_version is not None:
            assert report.nli_version == local_nli.version


def test_false_rejections_are_the_recorded_ones(
    fixture_reports: list[tuple[dict[str, Any], FairnessReport]]
) -> None:
    assert _false_rejections(fixture_reports) == RECORDED_FALSE_REJECTIONS
    for entry, report in fixture_reports:
        if entry["id"] in RECORDED_FALSE_REJECTIONS:
            assert report.failed == frozenset({"nli"}), entry["id"]


@pytest.mark.xfail(strict=True, reason="M6 acceptance open: 3 false rejections (F11, F13, F14) "
                   "vs a budget of 2 with the pinned model; NOTES.md, M6")
def test_false_rejections_within_budget(
    fixture_reports: list[tuple[dict[str, Any], FairnessReport]]
) -> None:
    assert len(_false_rejections(fixture_reports)) <= FALSE_REJECTION_BUDGET


def test_model_loads_lazily_and_scores_a_pair_under_300_ms(local_nli: CrossEncoderNli) -> None:
    fresh = CrossEncoderNli(local_nli.model_dir, local_nli.pin)
    assert not fresh.loaded
    premise = "A school has 400 students.\nCalculate 15% of them. Show your working."
    hypothesis = "A school has 400 students.\nFind 15% of them. Show your working."
    fresh.entailment(premise, hypothesis)  # first call loads the model
    assert fresh.loaded
    timings = []
    for _ in range(7):
        start = time.perf_counter()
        fresh.entailment(premise, hypothesis)
        timings.append(time.perf_counter() - start)
    assert median(timings) < 0.300, timings


def test_sample_paper_passes_every_check(
    sample_paper: Paper, local_nli: CrossEncoderNli
) -> None:
    reports = FairnessChecker(local_nli, wordfreq_zipf()).check_paper(sample_paper)
    failing = [(r.question_id, r.slot, r.values, sorted(r.failed)) for r in reports
               if not r.passed]
    assert failing == []
