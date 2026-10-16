"""The pinned NLI models: which repository, which revision, which files.

Shared by the loader (:mod:`examfp.fairness.nli`, local files only) and the
download script (``ml/fetch_models.py``, the one place allowed to fetch). Only
the safetensors weights and the tokenizer and config files are pinned; the ONNX
copies and ``pytorch_model.bin`` are never fetched (PLAN.md M6, decision 5).

:data:`NLI_PIN` is the model the fairness checker uses. :data:`NLI_PINS` also
holds candidates pinned for comparison on the held-out set
(``eval/nli_reliability.py``); a candidate is never used by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class NliPin:
    """One NLI cross-encoder, pinned to a commit, with the only files ever fetched."""

    key: str  # short name used on the command line: "small", "base"
    model_id: str
    revision: str  # full commit SHA, never a branch name
    files: tuple[str, ...]

    @property
    def subdir(self) -> PurePosixPath:
        """Relative directory of this model inside a model cache.

        Guarantees: names the repository and the revision, so two models or two
        revisions never share a directory.
        """
        return PurePosixPath(self.model_id.rsplit("/", 1)[-1]) / self.revision

    @property
    def version(self) -> str:
        """The version string recorded beside every result this model produced."""
        return f"{self.model_id}@{self.revision}"


_DEBERTA_V3_FILES = (
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "spm.model",
)

NLI_SMALL = NliPin(
    key="small",
    model_id="cross-encoder/nli-deberta-v3-small",
    revision="fa2804872c3b4bd748f38c0185cc85775361e735",
    files=_DEBERTA_V3_FILES,
)

# Candidate, approved by the owner on 2026-10-17 for comparison on the held-out
# set only (PLAN.md M6, "To close M6"). Same tokenizer files as the small model.
# Not chosen: 54/60 on the held-out set against small's 55/60 (NOTES.md, M6).
NLI_BASE = NliPin(
    key="base",
    model_id="cross-encoder/nli-deberta-v3-base",
    revision="6c749ce3425cd33b46d187e45b92bbf96ee12ec7",
    files=_DEBERTA_V3_FILES,
)

NLI_PIN = NLI_SMALL
NLI_PINS: dict[str, NliPin] = {pin.key: pin for pin in (NLI_SMALL, NLI_BASE)}

# The checker's model, under the names the loader and the tests have always used.
NLI_MODEL_ID = NLI_PIN.model_id
NLI_MODEL_REVISION = NLI_PIN.revision
NLI_MODEL_FILES = NLI_PIN.files


def nli_pin(key: str) -> NliPin:
    """The pinned model named ``key``; refuses a name that is not pinned."""
    try:
        return NLI_PINS[key]
    except KeyError:
        raise ValueError(f"no pinned NLI model {key!r}; pinned: {', '.join(NLI_PINS)}") from None


def nli_model_subdir(pin: NliPin = NLI_PIN) -> PurePosixPath:
    """Relative directory of ``pin`` (default: the checker's model) inside a model cache.

    Guarantees: names the revision, so two revisions never share a directory.
    """
    return pin.subdir


def nli_model_version(pin: NliPin = NLI_PIN) -> str:
    """The version string recorded beside every NLI-backed fairness result."""
    return pin.version
