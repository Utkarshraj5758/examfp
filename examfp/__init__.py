"""examfp — per-centre fingerprinting of exam papers.

The package root re-exports the paper data model (:mod:`examfp.models`).
Subpackages: :mod:`examfp.codebook` (Reed-Solomon practical codebook, Tardos
provable code, envelope encryption), :mod:`examfp.decode` (leak reader and
decision rule) and :mod:`examfp.fairness` (the M6 fairness checker). Also
:mod:`examfp.render` (Typst PDF), :mod:`examfp.attacks` and :mod:`examfp.cli`.
"""

from examfp.models import (
    Answer,
    CapacityReport,
    DifficultyBand,
    OptionOrderSlot,
    Paper,
    Question,
    TextSlot,
    UnitFormSlot,
    Variant,
)

__all__ = [
    "Answer",
    "CapacityReport",
    "DifficultyBand",
    "OptionOrderSlot",
    "Paper",
    "Question",
    "TextSlot",
    "UnitFormSlot",
    "Variant",
]
