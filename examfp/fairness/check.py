"""The fairness checker: one :class:`FairnessReport` per variant, three channels never mixed.

Every candidate is compared with symbol 0 of the same slot (the reference),
every other slot held at symbol 0. The slot decides the channel (PLAN.md M6,
decision 1):

* **Wording** (unbanded text slots): the numbers in the two question texts
  must be identical; then NLI entailment both ways (:mod:`examfp.fairness.nli`);
  then readability (:mod:`examfp.fairness.readability`). In that order,
  stopping at the first failure, so a pair whose numbers differ never reaches
  the model. Never SymPy.
* **Unit form**: as wording, but the owner-approved unit table
  (:mod:`examfp.fairness.units`) replaces NLI (owner decision, 2026-10-17: the
  NLI tokenizer cannot read ² or ³). Never NLI, never SymPy.
* **Numeric** (banded groups): exact answer (:mod:`examfp.fairness.answers`,
  SymPy), digit counts and trivial operands (the frozen band validator), then
  the step rule of ADR 0004 (:mod:`examfp.fairness.bands`). Answer, digits and
  trivial always run; steps are compared only for a valid band member with the
  right answer. Never NLI.
* **Option order**: structural only, the same options with the same correct
  text. Neither NLI nor SymPy.

Each check is a ``(passed, reason)`` pair. A check that did not run is
recorded with ``ran=False`` and counts as not passed, so a report passes only
when every check ran and passed (fail closed).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from examfp.fairness import answers, bands, nli, readability, units
from examfp.fairness.nli import NliBackend
from examfp.fairness.readability import ReadabilityTolerance, Zipf
from examfp.models import (
    OptionOrderSlot,
    Paper,
    Question,
    Slot,
    TextSlot,
    UnitFormSlot,
    Variant,
)

# Any decimal digits (Unicode Nd, so Devanagari counts); superscripts are not Nd.
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_LETTERS = "ABCDEFGHIJ"


class Channel(StrEnum):
    WORDING = "wording"
    UNIT_FORM = "unit_form"
    NUMERIC = "numeric"
    OPTION_ORDER = "option_order"


@dataclass(frozen=True)
class CheckResult:
    """One rule's verdict. ``ran=False`` means an earlier check stopped the channel."""

    name: str
    passed: bool
    reason: str
    ran: bool = True


@dataclass(frozen=True)
class FairnessReport:
    """Per-check verdicts for one variant of one slot.

    Invariant: ``passed`` only when there is at least one check and every check
    ran and passed. ``nli_version`` is set exactly when the model was consulted.
    """

    question_id: str
    slot: str
    channel: Channel
    values: tuple[str, ...]
    checks: tuple[CheckResult, ...]
    nli_version: str | None = None

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(c.ran and c.passed for c in self.checks)

    @property
    def failed(self) -> frozenset[str]:
        """Names of the rules that ran and failed (skipped checks are not failures)."""
        return frozenset(c.name for c in self.checks if c.ran and not c.passed)


@dataclass(frozen=True)
class FairnessConfig:
    nli_threshold: float = nli.DEFAULT_THRESHOLD
    readability: ReadabilityTolerance = field(default_factory=ReadabilityTolerance)


def slot_channel(slot: Slot) -> Channel:
    """The fairness channel a slot's variants are judged in."""
    if isinstance(slot, OptionOrderSlot):
        return Channel.OPTION_ORDER
    if isinstance(slot, UnitFormSlot):
        return Channel.UNIT_FORM
    if slot.difficulty_band is not None:
        return Channel.NUMERIC
    return Channel.WORDING


def numbers(text: str) -> Counter[str]:
    """The multiset of numbers in ``text``, digits normalised to ASCII.

    Guarantees: superscripts (``cm²``) are not numbers; ``1,440`` is two numbers,
    never silently merged; spelled-out numbers are left to NLI.
    """
    found: Counter[str] = Counter()
    for match in _NUMBER.finditer(text):
        token = match.group()
        found["".join(str(unicodedata.decimal(c)) if c.isdigit() else c for c in token)] += 1
    return found


def reference_text(question: Question) -> str:
    """The question with every slot at symbol 0."""
    text, _letter = question.resolve({s.name: 0 for s in question.slots})
    return text


def _slot(question: Question, slot_name: str) -> Slot:
    for slot in question.slots:
        if slot.name == slot_name:
            return slot
    raise KeyError(f"question {question.id!r} has no slot {slot_name!r}")


def candidate_text(question: Question, slot_name: str, values: Sequence[str]) -> str:
    """The question with ``values`` in ``slot_name`` and every other slot at symbol 0.

    Raises :class:`ValueError` if ``values`` does not fill the slot's placeholders.
    """
    target = _slot(question, slot_name)
    if isinstance(target, OptionOrderSlot):
        raise ValueError("option-order slots are checked by symbol, not by values")
    if len(values) != len(target.fills):
        raise ValueError(f"slot {slot_name!r} fills {len(target.fills)} placeholder(s); "
                         f"got {len(values)} value(s)")
    variant = Variant(values=list(values))
    slots = [s.model_copy(update={"variants": [variant]}) if s.name == slot_name else s
             for s in question.slots]
    text, _letter = question.model_copy(update={"slots": slots}).resolve(
        {s.name: 0 for s in slots})
    return text


def option_order_structure(slot: OptionOrderSlot, shown: Sequence[str], letter: str) -> tuple[
        bool, str]:
    """Do the displayed options equal the slot's options, with ``letter`` on the correct one?"""
    if Counter(shown) != Counter(slot.options):
        return False, f"displayed options {list(shown)} differ from {slot.options}"
    index = _LETTERS.find(letter)
    correct = slot.options[slot.correct]
    if not 0 <= index < len(shown) or shown[index] != correct:
        return False, f"answer letter {letter!r} does not point at the correct option {correct!r}"
    return True, f"same {len(shown)} options; {letter} is {correct!r}"


def _skipped(name: str, because: str) -> CheckResult:
    return CheckResult(name, False, f"not run: {because}", ran=False)


class FairnessChecker:
    """Judges variants against their reference, one channel per slot kind.

    Invariant: wording pairs reach ``nli`` only when their numbers are identical;
    unit-form, numeric and option-order variants never reach it; wording and unit
    forms never reach SymPy or band arithmetic.
    """

    def __init__(self, nli_backend: NliBackend, zipf: Zipf,
                 config: FairnessConfig | None = None) -> None:
        self.nli = nli_backend
        self.zipf = zipf
        self.config = config or FairnessConfig()

    # --- wording and unit forms --------------------------------------------------------------
    def _textual(self, question: Question, slot: TextSlot | UnitFormSlot,
                 values: Sequence[str]) -> FairnessReport:
        """Numbers, then NLI (wording) or the unit table (unit form), then readability."""
        channel = slot_channel(slot)
        middle = "units" if channel is Channel.UNIT_FORM else "nli"
        reference = reference_text(question)
        candidate = candidate_text(question, slot.name, values)
        ref_numbers, cand_numbers = numbers(reference), numbers(candidate)
        same = ref_numbers == cand_numbers
        checks = [CheckResult(
            "numbers", same,
            "numbers identical to the reference" if same else
            f"numbers differ: {sorted(cand_numbers.elements())} vs the reference's "
            f"{sorted(ref_numbers.elements())}")]
        version: str | None = None
        if not same:
            checks += [_skipped(middle, "the numbers differ"),
                       _skipped("readability", "the numbers differ")]
        else:
            if channel is Channel.UNIT_FORM:
                passed, reason = units.check_unit_form(slot.variants[0].values[0], values[0])
            else:
                passed, reason = nli.check_entailment(
                    reference, candidate, self.nli, self.config.nli_threshold)
                version = self.nli.version
            checks.append(CheckResult(middle, passed, reason))
            if passed:
                passed, reason = readability.check_readability(
                    reference, candidate, self.zipf, self.config.readability)
                checks.append(CheckResult("readability", passed, reason))
            else:
                checks.append(_skipped("readability", f"{middle} rejected the variant"))
        return FairnessReport(question.id, slot.name, channel, tuple(values), tuple(checks),
                              version)

    # --- numeric -------------------------------------------------------------------------------
    def _numeric(self, question: Question, slot: TextSlot, values: Sequence[str]) -> FairnessReport:
        checks = [CheckResult("answer", *answers.check_answer(question, slot.name, values)),
                  CheckResult("digits", *bands.check_digits(slot, values)),
                  CheckResult("trivial", *bands.check_trivial(slot, values))]
        if all(c.passed for c in checks):
            checks.append(CheckResult("steps", *bands.check_steps(slot, values)))
        else:
            failed = ", ".join(c.name for c in checks if not c.passed)
            checks.append(_skipped("steps", f"not a valid band member ({failed} failed)"))
        return FairnessReport(question.id, slot.name, Channel.NUMERIC, tuple(values),
                              tuple(checks))

    # --- public --------------------------------------------------------------------------------
    def check_candidate(
        self, question: Question, slot_name: str, values: Sequence[str]
    ) -> FairnessReport:
        """Judge ``values`` as a variant of ``slot_name``, against the slot's symbol 0.

        Guarantees: the slot's channel alone decides which rules run; a value
        count that does not fit the slot fails a ``structure`` check, never raises.
        """
        slot = _slot(question, slot_name)
        if isinstance(slot, OptionOrderSlot):
            raise ValueError("option-order slots are checked with check_option_order")
        if len(values) != len(slot.fills):
            reason = f"{len(values)} value(s) for {len(slot.fills)} placeholder(s)"
            return FairnessReport(question.id, slot_name, slot_channel(slot), tuple(values),
                                  (CheckResult("structure", False, reason),))
        if isinstance(slot, TextSlot) and slot.difficulty_band is not None:
            return self._numeric(question, slot, values)
        return self._textual(question, slot, values)

    def check_option_order(self, question: Question, slot_name: str,
                           symbol: int) -> FairnessReport:
        """Judge one permutation of an option-order slot, structurally only."""
        slot = _slot(question, slot_name)
        if not isinstance(slot, OptionOrderSlot):
            raise ValueError(f"slot {slot_name!r} is not an option-order slot")
        fill = slot.fill(symbol)
        shown = [fill[name] for name in slot.fills]
        passed, reason = option_order_structure(slot, shown, slot.option_letter(symbol))
        return FairnessReport(question.id, slot_name, Channel.OPTION_ORDER, tuple(shown),
                              (CheckResult("options", passed, reason),))

    def check_paper(self, paper: Paper) -> list[FairnessReport]:
        """One report per variant of every slot, in paper order.

        Guarantees: covers every permutation of every option-order slot (judged
        against the slot's own options), every variant of every numeric group, the
        reference included (its answer and band are checked too), and every
        non-reference variant of every wording and unit-form slot.
        """
        reports: list[FairnessReport] = []
        for question in paper.questions:
            for slot in question.slots:
                if isinstance(slot, OptionOrderSlot):
                    reports += [self.check_option_order(question, slot.name, symbol)
                                for symbol in range(slot.alphabet)]
                    continue
                first = 0 if slot_channel(slot) is Channel.NUMERIC else 1
                reports += [self.check_candidate(question, slot.name, variant.values)
                            for variant in slot.variants[first:]]
        return reports
