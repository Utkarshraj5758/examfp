"""Pydantic data model for fingerprintable exam papers.

The fingerprint works by wording, numbers, option order and unit rendering —
never by the answer.  A :class:`Question` carries a fixed ``template`` with
named ``{{placeholder}}`` slots; each slot fills one or more placeholders with
an *answer-preserving* variant.  One symbol per slot selects the variant, and
the dict of symbols across the paper (keyed by ``(question_id, slot_name)``) is
what distinguishes one centre from another.

Slot kinds and their fingerprint *channel*:

* :class:`TextSlot` without a band -> ``wording`` (fragile: a leaker paraphrases).
* :class:`TextSlot` with a :class:`DifficultyBand` -> ``group`` (durable): fills
  a numeric group whose operands vary while the answer and the difficulty band
  (digit counts, operation, step count, non-trivial operands) stay fixed.
* :class:`UnitFormSlot` -> ``units`` (durable): equivalent renderings of one
  unit (``km/h`` vs ``kilometres per hour``); a leaker copies them literally.
* :class:`OptionOrderSlot` -> ``option`` (durable): permutations of an MCQ's
  options (all of them except the identity, so no centre gets natural order).

All functions here are pure: they read the model and return values.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from itertools import permutations
from math import factorial, log, log2, prod
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_LETTERS = "ABCDEFGHIJ"

# Durable channels carry payload a leaker reproduces literally; wording is fragile.
DURABLE_CHANNELS = frozenset({"group", "units", "option"})
_BASE_TRIVIAL = frozenset({1, 2, 10, 100})
_PERCENT_TRIVIAL = frozenset({50, 100})


def template_slot_names(template: str) -> list[str]:
    """Placeholder names referenced by ``template``, in first-appearance order."""
    return [m.group(1) for m in _PLACEHOLDER.finditer(template)]


class Answer(BaseModel):
    """A question's answer for one centre.

    Invariant: ``canonical`` is identical for every centre (the paper is
    answer-preserving); ``option_letter`` is the auto-generated per-centre label
    of the correct MCQ option, or ``None`` for non-MCQ questions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical: str
    option_letter: str | None = None


class Variant(BaseModel):
    """One approved fill: one value per placeholder the slot fills.

    Accepts a bare string (``"Calculate"``) as sugar for a single value.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: list[str] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _coerce(cls, data: object) -> object:
        if isinstance(data, str):
            return {"values": [data]}
        if isinstance(data, dict) and "text" in data and "values" not in data:
            return {"values": [data["text"]]}
        return data


class DifficultyBand(BaseModel):
    """The difficulty a numeric group must hold constant across its variants.

    Invariant: every variant uses ``operation`` with the declared per-operand
    digit counts and excludes trivial operands, so varying the numbers changes
    surface detail only — not how hard the question is.
    """

    model_config = ConfigDict(extra="forbid")

    operation: Literal["divide", "multiply", "percent", "add", "subtract"]
    operand_digits: list[int] = Field(min_length=1)
    exclude_trivial: bool = True

    @property
    def trivial(self) -> frozenset[int]:
        extra = _PERCENT_TRIVIAL if self.operation == "percent" else frozenset()
        return _BASE_TRIVIAL | extra


class _SlotBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    fills: list[str] = Field(default_factory=list)

    def _default_fills(self) -> None:
        if not self.fills:
            self.fills = [self.name]


class TextSlot(_SlotBase):
    """Wording slot (fragile) or numeric group (durable, when banded)."""

    kind: Literal["text"] = "text"
    variants: list[Variant] = Field(min_length=1)
    difficulty_band: DifficultyBand | None = None

    @model_validator(mode="after")
    def _check(self) -> TextSlot:
        self._default_fills()
        for v in self.variants:
            if len(v.values) != len(self.fills):
                raise ValueError(
                    f"slot {self.name!r}: variant {v.values} supplies "
                    f"{len(v.values)} value(s) but fills {len(self.fills)} placeholder(s)"
                )
        if self.difficulty_band is not None:
            self._check_band(self.difficulty_band)
        return self

    def _check_band(self, band: DifficultyBand) -> None:
        if len(band.operand_digits) != len(self.fills):
            raise ValueError(
                f"slot {self.name!r}: operand_digits {band.operand_digits} does not "
                f"match {len(self.fills)} filled placeholder(s)"
            )
        for v in self.variants:
            for value, digits in zip(v.values, band.operand_digits, strict=True):
                if not value.isdigit() or len(value) != digits:
                    raise ValueError(
                        f"slot {self.name!r}: operand {value!r} is not a "
                        f"{digits}-digit number (difficulty band violated)"
                    )
                if band.exclude_trivial and int(value) in band.trivial:
                    raise ValueError(
                        f"slot {self.name!r}: operand {value!r} is trivial for a "
                        f"{band.operation} band (excluded: {sorted(band.trivial)})"
                    )

    @property
    def channel(self) -> str:
        return "group" if self.difficulty_band is not None else "wording"

    @property
    def alphabet(self) -> int:
        return len(self.variants)

    def fill(self, symbol: int) -> dict[str, str]:
        _check_range(symbol, self.alphabet, self.name)
        return dict(zip(self.fills, self.variants[symbol].values, strict=True))


class UnitFormSlot(_SlotBase):
    """Durable unit slot: equivalent renderings of one unit."""

    kind: Literal["unit_form"] = "unit_form"
    variants: list[Variant] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> UnitFormSlot:
        self._default_fills()
        if len(self.fills) != 1:
            raise ValueError(f"unit_form slot {self.name!r} must fill exactly one placeholder")
        for v in self.variants:
            if len(v.values) != 1:
                raise ValueError(f"unit_form slot {self.name!r}: variant must be a single value")
        return self

    @property
    def channel(self) -> str:
        return "units"

    @property
    def alphabet(self) -> int:
        return len(self.variants)

    def fill(self, symbol: int) -> dict[str, str]:
        _check_range(symbol, self.alphabet, self.name)
        return {self.fills[0]: self.variants[symbol].values[0]}


class OptionOrderSlot(_SlotBase):
    """Durable MCQ slot: permutations of the options, identity excluded.

    Invariant: distractor texts never vary (they are radicals); only the order
    varies.  Alphabet is ``n! - 1`` for ``n`` options.
    """

    kind: Literal["option_order"] = "option_order"
    fills: list[str] = Field(min_length=2)
    options: list[str] = Field(min_length=2)
    correct: int = Field(ge=0)

    @model_validator(mode="after")
    def _check(self) -> OptionOrderSlot:
        if len(self.fills) != len(self.options):
            raise ValueError(
                f"option_order slot {self.name!r}: {len(self.fills)} fills but "
                f"{len(self.options)} options"
            )
        if self.correct >= len(self.options):
            raise ValueError(
                f"option_order slot {self.name!r}: correct index {self.correct} "
                f"out of range for {len(self.options)} options"
            )
        return self

    @property
    def _perms(self) -> list[tuple[int, ...]]:
        identity = tuple(range(len(self.options)))
        return [p for p in permutations(range(len(self.options))) if p != identity]

    @property
    def channel(self) -> str:
        return "option"

    @property
    def alphabet(self) -> int:
        return factorial(len(self.options)) - 1

    def fill(self, symbol: int) -> dict[str, str]:
        _check_range(symbol, self.alphabet, self.name)
        order = self._perms[symbol]
        return {self.fills[i]: self.options[order[i]] for i in range(len(order))}

    def option_letter(self, symbol: int) -> str:
        _check_range(symbol, self.alphabet, self.name)
        return _LETTERS[self._perms[symbol].index(self.correct)]


def _check_range(symbol: int, alphabet: int, name: str) -> None:
    if not 0 <= symbol < alphabet:
        raise IndexError(
            f"symbol {symbol} out of range for slot {name!r} (alphabet {alphabet})"
        )


Slot = Annotated[
    TextSlot | UnitFormSlot | OptionOrderSlot, Field(discriminator="kind")
]


class Question(BaseModel):
    """A single exam question: template plus slots plus a canonical answer.

    Invariant: every ``{{placeholder}}`` is filled by exactly one slot (across
    all slots' ``fills``), slot names are unique, and ``answer`` is the canonical
    answer independent of any symbol choice.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    template: str = Field(min_length=1)
    slots: list[Slot] = Field(default_factory=list)
    answer: str = Field(min_length=1)
    marks: int = Field(default=1, ge=0)

    @model_validator(mode="before")
    @classmethod
    def _default_kind(cls, data: object) -> object:
        if isinstance(data, dict) and isinstance(data.get("slots"), list):
            for slot in data["slots"]:
                if isinstance(slot, dict) and "kind" not in slot:
                    slot["kind"] = "text"
        return data

    @model_validator(mode="after")
    def _check(self) -> Question:
        names = [s.name for s in self.slots]
        dupes = [n for n, c in Counter(names).items() if c > 1]
        if dupes:
            raise ValueError(f"duplicate slot name(s) in question {self.id!r}: {dupes}")

        placeholders = set(template_slot_names(self.template))
        fills = [f for s in self.slots for f in s.fills]
        fill_dupes = [f for f, c in Counter(fills).items() if c > 1]
        if fill_dupes:
            raise ValueError(
                f"question {self.id!r}: placeholder(s) filled more than once: {fill_dupes}"
            )
        missing = placeholders - set(fills)
        if missing:
            raise ValueError(f"question {self.id!r}: unfilled placeholder(s): {sorted(missing)}")
        extra = set(fills) - placeholders
        if extra:
            raise ValueError(f"question {self.id!r}: fills with no placeholder: {sorted(extra)}")
        return self

    def resolve(self, symbols: Mapping[str, int]) -> tuple[str, str | None]:
        """Return ``(text, option_letter)`` for this question's symbols.

        ``symbols`` maps each slot name to its variant index.  Raises
        :class:`KeyError` for a missing slot and :class:`IndexError` for an
        out-of-range symbol.
        """
        fillmap: dict[str, str] = {}
        letter: str | None = None
        for slot in self.slots:
            symbol = symbols[slot.name]
            fillmap.update(slot.fill(symbol))
            if isinstance(slot, OptionOrderSlot):
                letter = slot.option_letter(symbol)
        text = _PLACEHOLDER.sub(lambda m: fillmap[m.group(1)], self.template)
        return text, letter

    def answer_for(self, symbols: Mapping[str, int]) -> Answer:
        _, letter = self.resolve(symbols)
        return Answer(canonical=self.answer, option_letter=letter)


class CapacityReport(BaseModel):
    """The result of :meth:`Paper.capacity_report` (printable via ``str``)."""

    model_config = ConfigDict(frozen=True)

    n_centres: int
    c: int
    eps: float
    positions: int
    questions: int
    payload_bits: float
    durable_bits: float
    fragile_bits: float
    bits_by_channel: dict[str, float]
    positions_by_channel: dict[str, int]
    tardos_required: float
    feasibility: dict[tuple[int, float], float]
    projected_positions_60: float

    @property
    def durable_fraction(self) -> float:
        total = self.durable_bits + self.fragile_bits
        return self.durable_bits / total if total else 0.0

    def __str__(self) -> str:
        lines = [
            "============ capacity_report ============",
            f"positions available (sample) : {self.positions}   "
            f"payload bits : {self.payload_bits:.1f}",
            f"durable fraction (headline)  : {100 * self.durable_fraction:.1f}%  "
            f"[durable {self.durable_bits:.1f} / fragile {self.fragile_bits:.1f} bits]",
            "  by channel: "
            + ", ".join(
                f"{ch}={self.bits_by_channel.get(ch, 0.0):.1f}b/"
                f"{self.positions_by_channel.get(ch, 0)}p"
                for ch in ("group", "option", "units", "wording")
            ),
            "",
            "[1] theoretical Tardos (literal constant): m = 100*c^2*ln(n/eps)",
            f"    at c={self.c}, eps={self.eps:g}, n={self.n_centres}: "
            f"m = {self.tardos_required:,.0f} positions",
            "[2] empirical Tardos: m = k*c^2*ln(n/eps)   k = <unset>  "
            "(measured, not proved; pending M6)",
            "[3] feasibility (positions available="
            f"{self.positions} vs required):",
            f"        {'eps=1e-2':>12} {'eps=1e-3':>12} {'eps=1e-6':>12}",
        ]
        for cc in (2, 3, 5):
            cells = []
            for e in (1e-2, 1e-3, 1e-6):
                req = self.feasibility[(cc, e)]
                cells.append(f"{req:>10,.0f}{'*' if self.positions >= req else ' '}")
            lines.append(f"  c={cc}  " + " ".join(cells))
        lines.append(f"    (* = sample's {self.positions} positions suffice; blank = shortfall)")
        perq = self.positions / self.questions
        lines.append(
            f"[4] projection: {perq:.2f} positions/question -> "
            f"60-question paper ~ {self.projected_positions_60:.0f} positions"
        )
        lines.append(
            "    multi-paper note: codewords spanning several papers in one exam session"
        )
        lines.append(
            "    would multiply available positions (future work, not implemented)."
        )
        return "\n".join(lines)


class Paper(BaseModel):
    """A whole exam paper: ordered questions plus identity metadata."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    questions: list[Question] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Paper:
        ids = [q.id for q in self.questions]
        dupes = [i for i, c in Counter(ids).items() if c > 1]
        if dupes:
            raise ValueError(f"duplicate question id(s) in paper {self.id!r}: {dupes}")
        return self

    def positions(self) -> list[tuple[str, str]]:
        """Fingerprint positions ``(question_id, slot_name)`` in a deterministic
        order: questions in paper order, slots in listed order.

        Because symbol vectors are keyed by this tuple, inserting a question
        leaves the keys of existing positions unchanged.
        """
        return [(q.id, s.name) for q in self.questions for s in q.slots]

    def alphabets(self) -> dict[tuple[str, str], int]:
        """Alphabet size at each position, keyed by ``(question_id, slot_name)``."""
        return {(q.id, s.name): s.alphabet for q in self.questions for s in q.slots}

    def _slot(self, qid: str, name: str) -> Slot:
        for q in self.questions:
            if q.id == qid:
                for s in q.slots:
                    if s.name == name:
                        return s
        raise KeyError((qid, name))

    def answer_key(self, symbols: Mapping[tuple[str, str], int]) -> dict[str, Answer]:
        """Return ``{question_id: Answer}`` for a symbol vector.

        Guarantees: ``canonical`` is identical for every valid symbol vector;
        ``option_letter`` varies with option-order symbols.  Validates the vector.
        """
        validate_symbols(self, symbols)
        out: dict[str, Answer] = {}
        for q in self.questions:
            q_syms = {s.name: symbols[(q.id, s.name)] for s in q.slots}
            out[q.id] = q.answer_for(q_syms)
        return out

    def capacity_report(
        self, n_centres: int, c: int, eps: float
    ) -> CapacityReport:
        """Compute the capacity report (arithmetic only; no Tardos code)."""
        bits_by_channel: dict[str, float] = {}
        positions_by_channel: dict[str, int] = {}
        for q in self.questions:
            for s in q.slots:
                bits_by_channel[s.channel] = bits_by_channel.get(s.channel, 0.0) + log2(
                    s.alphabet
                )
                positions_by_channel[s.channel] = positions_by_channel.get(s.channel, 0) + 1
        durable = sum(b for ch, b in bits_by_channel.items() if ch in DURABLE_CHANNELS)
        fragile = sum(b for ch, b in bits_by_channel.items() if ch not in DURABLE_CHANNELS)
        n_pos = len(self.positions())
        feasibility = {
            (cc, e): 100 * cc * cc * log(n_centres / e)
            for cc in (2, 3, 5)
            for e in (1e-2, 1e-3, 1e-6)
        }
        return CapacityReport(
            n_centres=n_centres,
            c=c,
            eps=eps,
            positions=n_pos,
            questions=len(self.questions),
            payload_bits=durable + fragile,
            durable_bits=durable,
            fragile_bits=fragile,
            bits_by_channel=bits_by_channel,
            positions_by_channel=positions_by_channel,
            tardos_required=100 * c * c * log(n_centres / eps),
            feasibility=feasibility,
            projected_positions_60=(n_pos / len(self.questions)) * 60,
        )

    def codebook_size(self) -> int:
        """Total number of distinct centres the paper can encode."""
        return prod(self.alphabets().values())


def validate_symbols(
    paper: Paper, symbols: Mapping[tuple[str, str], int]
) -> None:
    """Validate a symbol vector against the paper's positions and alphabets.

    Raises :class:`ValueError` if the key set differs from :meth:`Paper.positions`
    and :class:`IndexError` if any symbol is out of range for its alphabet.
    """
    alphabets = paper.alphabets()
    expected = set(alphabets)
    got = set(symbols)
    if got != expected:
        missing = expected - got
        extra = got - expected
        raise ValueError(
            f"symbol vector key mismatch for paper {paper.id!r}: "
            f"missing={sorted(missing)} extra={sorted(extra)}"
        )
    for key, symbol in symbols.items():
        _check_range(symbol, alphabets[key], f"{key[0]}/{key[1]}")
