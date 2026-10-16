"""Shared fixtures for the fairness tests: the approved fixture and the local model.

Tests marked ``local_model`` need the pinned NLI model (``.\\tasks.ps1
fetch-models``) and the ``fairness`` extra. Without them they skip, unless
``TRACE_REQUIRE_LOCAL_MODEL=1`` (set by ``.\\tasks.ps1 fairness``), which turns
the skip into a failure so the acceptance run can never pass vacuously.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

import pytest

from examfp.fairness.nli import CrossEncoderNli, nli_model_dir
from examfp.fairness.pins import NLI_MODEL_FILES
from tests.fairness.support import ROOT, load_fixture

MODEL_CACHE = ROOT / "models"


@pytest.fixture(scope="session")
def fixture_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = load_fixture()["variants"]
    return entries


def _missing_local_model() -> str | None:
    for module in ("torch", "transformers", "wordfreq"):
        if importlib.util.find_spec(module) is None:
            return f"the fairness extra is not installed ({module} missing)"
    model = nli_model_dir(MODEL_CACHE)
    absent = [name for name in NLI_MODEL_FILES if not (model / name).is_file()]
    if absent:
        return f"pinned NLI model not fetched ({', '.join(absent)}); run .\\tasks.ps1 fetch-models"
    return None


@pytest.fixture(scope="session")
def local_nli() -> CrossEncoderNli:
    """The pinned NLI model, loaded lazily on first use and shared by the session."""
    missing = _missing_local_model()
    if missing is not None:
        if os.environ.get("TRACE_REQUIRE_LOCAL_MODEL") == "1":
            pytest.fail(missing)
        pytest.skip(missing)
    return CrossEncoderNli(nli_model_dir(MODEL_CACHE))
