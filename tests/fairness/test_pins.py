"""The NLI pins: commit SHAs, only the approved files, one cache directory each. No model."""

from __future__ import annotations

import re

import pytest

from examfp.fairness.pins import (
    NLI_MODEL_FILES,
    NLI_MODEL_ID,
    NLI_MODEL_REVISION,
    NLI_PIN,
    NLI_PINS,
    nli_model_subdir,
    nli_model_version,
    nli_pin,
)


def test_the_checker_uses_the_owner_approved_model() -> None:
    # Switching models is an owner decision (PLAN.md M6); it must change this test.
    assert NLI_PIN.version == (
        "cross-encoder/nli-deberta-v3-small@fa2804872c3b4bd748f38c0185cc85775361e735")
    assert NLI_PINS[NLI_PIN.key] == NLI_PIN
    assert (NLI_MODEL_ID, NLI_MODEL_REVISION, NLI_MODEL_FILES) == (
        NLI_PIN.model_id, NLI_PIN.revision, NLI_PIN.files)
    assert nli_model_version() == NLI_PIN.version
    assert nli_model_subdir() == NLI_PIN.subdir


@pytest.mark.parametrize("key", sorted(NLI_PINS))
def test_every_pin_is_a_commit_with_only_the_approved_files(key: str) -> None:
    pin = NLI_PINS[key]
    assert pin.key == key
    assert re.fullmatch(r"[0-9a-f]{40}", pin.revision), "a full commit SHA, never a branch"
    assert "model.safetensors" in pin.files and "config.json" in pin.files
    assert len(set(pin.files)) == len(pin.files)
    for name in pin.files:
        assert not name.endswith((".onnx", ".bin")) and "/" not in name, name


def test_pins_never_share_a_cache_directory() -> None:
    subdirs = [pin.subdir for pin in NLI_PINS.values()]
    assert len(set(subdirs)) == len(subdirs)
    for pin in NLI_PINS.values():
        assert pin.subdir.name == pin.revision
        assert pin.subdir.parent.name == pin.model_id.rsplit("/", 1)[-1]
        assert pin.version == f"{pin.model_id}@{pin.revision}"


def test_an_unpinned_model_is_refused() -> None:
    assert nli_pin(NLI_PIN.key) == NLI_PIN
    with pytest.raises(ValueError, match="no pinned NLI model"):
        nli_pin("large")
