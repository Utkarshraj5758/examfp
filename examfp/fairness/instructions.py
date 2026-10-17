"""Instruction channel: instruction and option-choice phrasing, from a curated table.

Owner decision (2026-10-17, M6): instruction boilerplate is judged like unit
forms, by a closed table of equivalent phrasings, not by NLI. The category:

* **instruction phrasing** - the command that says what to do with the question
  ("Calculate", "State") and instructions about the working ("Show your
  working."), provided it neither names nor constrains the quantity asked;
* **option-choice phrasing** - how to answer a multiple-choice question
  ("Choose one option only.").

Anything that names units, precision or the quantity ("Give your answer in
square metres.") is not boilerplate: it is part of the ask, a radical
(:mod:`examfp.fairness.ask`).

The table holds exactly the sample paper's complete instruction vocabulary,
grouped by what each phrasing asks the candidate to do. It was not built from
the fixture: the fixture's rejected entries (F11, F13, F14) are not in it, and a
test pins the table to the paper's vocabulary. Matching is exact; an unlisted
phrasing fails closed, so a fair synonym the paper does not use is rejected
until the owner adds it. Adding a phrasing or a class is an owner decision:
review it like a change to a frozen file.
"""

from __future__ import annotations

from dataclasses import dataclass

Check = tuple[bool, str]

COMMAND = "command"
WORKING = "working"
OPTION_CHOICE = "option_choice"


@dataclass(frozen=True)
class InstructionClass:
    """Phrasings that ask the candidate to do exactly the same thing."""

    role: str  # COMMAND, WORKING or OPTION_CHOICE
    meaning: str
    phrases: frozenset[str]


INSTRUCTION_TABLE: tuple[InstructionClass, ...] = (
    InstructionClass(COMMAND, "compute the result, with working",
                     frozenset({"Calculate", "Work out"})),
    InstructionClass(COMMAND, "give a fact or a choice, without working",
                     frozenset({"State", "Identify"})),
    InstructionClass(WORKING, "show the method used", frozenset({"Show your working.",
                                                                 "Include your working."})),
    InstructionClass(OPTION_CHOICE, "choose exactly one option",
                     frozenset({"Choose one option only.", "Select only one option."})),
)


def instruction_class(phrase: str,
                      table: tuple[InstructionClass, ...] = INSTRUCTION_TABLE
                      ) -> InstructionClass | None:
    """The class ``phrase`` belongs to, or ``None`` if the table does not list it exactly."""
    for entry in table:
        if phrase in entry.phrases:
            return entry
    return None


def command_phrases(table: tuple[InstructionClass, ...] = INSTRUCTION_TABLE) -> frozenset[str]:
    """Every phrasing whose role is a command (it opens the ask)."""
    return frozenset(p for entry in table if entry.role == COMMAND for p in entry.phrases)


def check_instruction(
    reference: str, candidate: str, table: tuple[InstructionClass, ...] = INSTRUCTION_TABLE
) -> Check:
    """Do ``reference`` and ``candidate`` ask for the same thing, per the table?

    Guarantees: passes only when both are listed in the same class; an unlisted
    phrasing fails closed, even if unchanged.
    """
    ref_class = instruction_class(reference, table)
    cand_class = instruction_class(candidate, table)
    for phrase, found in ((reference, ref_class), (candidate, cand_class)):
        if found is None:
            return False, f"{phrase!r} is not in the instruction table"
    assert ref_class is not None and cand_class is not None
    if ref_class != cand_class:
        return False, (f"{candidate!r} is a different instruction ({cand_class.meaning}) "
                       f"from the reference {reference!r} ({ref_class.meaning})")
    return True, f"{candidate!r} and {reference!r} both ask the candidate to {ref_class.meaning}"
