"""Tests for the NLI channel that need no model: laziness, thresholds, the version record.

The real model runs only in ``test_acceptance.py`` (marked ``local_model``).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from examfp.fairness.nli import CrossEncoderNli, check_entailment, nli_model_dir
from examfp.fairness.pins import NLI_MODEL_REVISION, NliPin, nli_model_version


class FixedNli:
    """Fake backend: a fixed score per direction, keyed by (premise, hypothesis)."""

    version = "fake-nli@0"

    def __init__(self, scores: dict[tuple[str, str], float]) -> None:
        self.scores = scores

    def entailment(self, premise: str, hypothesis: str) -> float:
        return self.scores[(premise, hypothesis)]


def test_entailment_must_hold_in_both_directions() -> None:
    both = FixedNli({("a", "b"): 0.9, ("b", "a"): 0.8})
    passed, reason = check_entailment("a", "b", both, threshold=0.5)
    assert passed
    assert "0.900" in reason and "0.800" in reason

    one_way = FixedNli({("a", "b"): 0.95, ("b", "a"): 0.2})
    passed, reason = check_entailment("a", "b", one_way, threshold=0.5)
    assert not passed and "0.200" in reason


def test_threshold_is_inclusive_and_configurable() -> None:
    backend = FixedNli({("a", "b"): 0.7, ("b", "a"): 0.7})
    assert check_entailment("a", "b", backend, threshold=0.7)[0]
    assert not check_entailment("a", "b", backend, threshold=0.71)[0]


def test_threshold_out_of_range_is_refused() -> None:
    backend = FixedNli({})
    with pytest.raises(ValueError):
        check_entailment("a", "b", backend, threshold=1.5)


def test_construction_does_not_load_the_model(tmp_path: Path) -> None:
    backend = CrossEncoderNli(tmp_path / "absent")
    assert not backend.loaded
    assert backend.version == nli_model_version()


def test_missing_model_files_raise_with_the_fetch_command(tmp_path: Path) -> None:
    backend = CrossEncoderNli(tmp_path / "absent")
    with pytest.raises(FileNotFoundError, match="fetch-models"):
        backend.entailment("a", "b")
    assert not backend.loaded


def test_model_dir_names_the_pinned_revision(tmp_path: Path) -> None:
    path = nli_model_dir(tmp_path)
    assert path.parent.parent == tmp_path
    assert path.name == NLI_MODEL_REVISION


def test_another_pin_records_its_own_version_and_directory(tmp_path: Path) -> None:
    other = NliPin("other", "org/other-nli", "0" * 40, ("config.json", "model.safetensors"))
    backend = CrossEncoderNli(nli_model_dir(tmp_path, other), other)
    assert backend.model_dir == tmp_path / "other-nli" / ("0" * 40)
    assert backend.version == "org/other-nli@" + "0" * 40 != nli_model_version()
    with pytest.raises(FileNotFoundError, match="fetch-models --model other"):
        backend.entailment("a", "b")
    assert not backend.loaded


def test_importing_the_nli_module_does_not_import_torch_or_transformers() -> None:
    code = (
        "import sys, examfp.fairness.nli, examfp.fairness.readability; "
        "assert 'torch' not in sys.modules and 'transformers' not in sys.modules, "
        "sorted(m for m in sys.modules if m.startswith(('torch', 'transformers')))"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
