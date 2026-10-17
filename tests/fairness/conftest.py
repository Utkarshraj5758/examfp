"""Shared fixtures for the fairness tests: the approved fixture and the local model.

Tests marked ``local_model`` need the pinned NLI model (``.\\tasks.ps1
fetch-models``) and the ``fairness`` extra. Without them they skip, unless
``TRACE_REQUIRE_LOCAL_MODEL=1`` (set by ``.\\tasks.ps1 fairness``), which turns
the skip into a failure so the acceptance run can never pass vacuously.

``TRACE_NLI_MODEL=<key>`` runs them with another model pinned in
:data:`examfp.fairness.pins.NLI_PINS` (a candidate under evaluation); unset,
they use the checker's model, :data:`examfp.fairness.pins.NLI_PIN`.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any

import pytest

from examfp.fairness.nli import CrossEncoderNli, nli_model_dir
from examfp.fairness.pins import NLI_PIN, NliPin, nli_pin
from tests.fairness.support import ROOT, load_fixture

MODEL_CACHE = ROOT / "models"


@pytest.fixture(scope="session")
def fixture_entries() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = load_fixture()["variants"]
    return entries


def _selected_pin() -> NliPin:
    return nli_pin(os.environ.get("TRACE_NLI_MODEL") or NLI_PIN.key)


def _missing_local_model(pin: NliPin) -> str | None:
    for module in ("torch", "transformers", "wordfreq"):
        if importlib.util.find_spec(module) is None:
            return f"the fairness extra is not installed ({module} missing)"
    model = nli_model_dir(MODEL_CACHE, pin)
    absent = [name for name in pin.files if not (model / name).is_file()]
    if absent:
        return (f"pinned NLI model {pin.key} not fetched ({', '.join(absent)}); "
                f"run .\\tasks.ps1 fetch-models --model {pin.key}")
    return None


@pytest.fixture(scope="session")
def local_nli() -> CrossEncoderNli:
    """The selected pinned NLI model, loaded lazily on first use and shared by the session."""
    pin = _selected_pin()
    missing = _missing_local_model(pin)
    if missing is not None:
        if os.environ.get("TRACE_REQUIRE_LOCAL_MODEL") == "1":
            pytest.fail(missing)
        pytest.skip(missing)
    return CrossEncoderNli(nli_model_dir(MODEL_CACHE, pin), pin)
