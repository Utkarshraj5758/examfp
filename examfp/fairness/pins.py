"""The pinned NLI model: which repository, which revision, which files.

Shared by the loader (:mod:`examfp.fairness.nli`, local files only) and the
download script (``ml/fetch_models.py``, the one place allowed to fetch). Only
the safetensors weights and the tokenizer and config files are pinned; the ONNX
copies and ``pytorch_model.bin`` are never fetched (PLAN.md M6, decision 5).
"""

from __future__ import annotations

from pathlib import PurePosixPath

NLI_MODEL_ID = "cross-encoder/nli-deberta-v3-small"
NLI_MODEL_REVISION = "fa2804872c3b4bd748f38c0185cc85775361e735"
NLI_MODEL_FILES = (
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "spm.model",
)


def nli_model_subdir() -> PurePosixPath:
    """Relative directory of the pinned model inside a model cache.

    Guarantees: names the revision, so two revisions never share a directory.
    """
    return PurePosixPath("nli-deberta-v3-small") / NLI_MODEL_REVISION


def nli_model_version() -> str:
    """The version string recorded beside every NLI-backed fairness result."""
    return f"{NLI_MODEL_ID}@{NLI_MODEL_REVISION}"
