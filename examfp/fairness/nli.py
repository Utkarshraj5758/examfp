"""Wording channel, step 2: bidirectional entailment with a pinned NLI model.

A wording variant asks the same question as its reference only if each text
entails the other. :func:`check_entailment` scores both directions with an
:class:`NliBackend` and requires both to reach a configurable threshold.

:class:`CrossEncoderNli` wraps ``cross-encoder/nli-deberta-v3-small`` at the
revision pinned in :mod:`examfp.fairness.pins`. It loads lazily, on the first
pair it scores, from local files only (CLAUDE.md, non-negotiable 8), and keeps
the loaded model on the instance: no module-level cache, no global state.
Importing this module imports neither torch nor transformers.

Numeric variants never reach this module (PLAN.md M6, decision 1): the checker
routes them to SymPy and band arithmetic, and sends a wording pair here only
when its numbers are identical.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from examfp.fairness.pins import NLI_MODEL_FILES, nli_model_subdir, nli_model_version

Check = tuple[bool, str]

DEFAULT_THRESHOLD = 0.5


class NliBackend(Protocol):
    """Scores how strongly ``premise`` entails ``hypothesis``, in [0, 1]."""

    @property
    def version(self) -> str: ...

    def entailment(self, premise: str, hypothesis: str) -> float: ...


def nli_model_dir(cache: Path) -> Path:
    """Directory of the pinned model inside the local model ``cache``."""
    return cache.joinpath(*nli_model_subdir().parts)


class CrossEncoderNli:
    """The pinned cross-encoder, loaded lazily from local files and kept on the instance.

    Invariant: constructing it touches neither the disk nor torch; the first call
    to :meth:`entailment` loads the model, and every later call reuses it.
    """

    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir
        self._model: Any = None
        self._tokenizer: Any = None
        self._entailment_index = -1

    @property
    def version(self) -> str:
        return nli_model_version()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _load(self) -> None:
        missing = [name for name in NLI_MODEL_FILES if not (self.model_dir / name).is_file()]
        if missing:
            raise FileNotFoundError(
                f"NLI model files missing from {self.model_dir}: {', '.join(missing)}. "
                "Fetch the pinned revision with `.\\tasks.ps1 fetch-models`."
            )
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(str(self.model_dir), local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(
            str(self.model_dir), local_files_only=True
        )
        model.eval()
        labels = {str(label).lower(): int(i) for i, label in model.config.id2label.items()}
        if "entailment" not in labels:
            raise ValueError(f"model at {self.model_dir} has no entailment label: {labels}")
        self._tokenizer, self._model = tokenizer, model
        self._entailment_index = labels["entailment"]

    def entailment(self, premise: str, hypothesis: str) -> float:
        """Probability that ``premise`` entails ``hypothesis`` (softmax over the labels).

        Guarantees: deterministic for a given input (inference mode, no sampling).
        """
        if self._model is None:
            self._load()
        import torch

        inputs = self._tokenizer(premise, hypothesis, return_tensors="pt", truncation=True)
        with torch.inference_mode():
            logits = self._model(**inputs).logits[0]
        return float(torch.softmax(logits, dim=-1)[self._entailment_index])


def check_entailment(
    reference: str, candidate: str, backend: NliBackend, threshold: float = DEFAULT_THRESHOLD
) -> Check:
    """Does each text entail the other with probability at least ``threshold``?

    Guarantees: both directions are scored, and both must reach the threshold.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(f"threshold {threshold} is not a probability")
    forward = backend.entailment(reference, candidate)
    backward = backend.entailment(candidate, reference)
    passed = forward >= threshold and backward >= threshold
    reason = (f"entailment {forward:.3f} reference->candidate, {backward:.3f} "
              f"candidate->reference; threshold {threshold:.2f} both ways")
    return passed, reason
