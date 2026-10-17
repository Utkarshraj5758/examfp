"""The ask rule: the quantity asked is a radical and never sits in a wording slot.

Item-generation theory separates a question's **radicals**, the elements that
decide what is measured and how hard it is, from its **incidentals**, surface
features that can vary without changing either. A fingerprint may vary
incidentals only. The quantity asked is the first radical: "its circumference"
and "its area" are different questions over the same data. So are the units,
precision and format the answer must take, and the options of a multiple-choice
question.

The held-out NLI set showed the model can pass such a change (circumference ->
area, factors -> multiples). The fix is structural, so that NLI is never the
only guard against a changed ask:

* The **ask region** runs from the start of the first template sentence that
  opens the ask to the end of the question. A sentence opens the ask when it
  holds a command: a slot whose reference is a command phrasing in the
  instruction table, the same phrasing written literally (case-insensitive,
  whole words), or a sentence ending in a question mark.
* Every **NLI-judged wording slot** must lie wholly before the ask region, in
  the stem that sets out the situation. Instruction slots, unit forms, numeric
  groups and option orders may sit in the ask region, because their own tables
  and rules keep the ask identical.
* No locatable ask means the rule **fails closed** for every wording slot of
  the question.

The region deliberately covers more than the clause that names the quantity: a
sentence after the command constrains the answer and is part of the ask too.
Sentences are split on ``.``, ``?`` or ``!`` followed by whitespace or the end,
and on line breaks; placeholders count as text, so the split depends only on
the template.
"""

from __future__ import annotations

import re

from examfp.fairness.instructions import COMMAND, command_phrases, instruction_class
from examfp.models import Question, Slot, TextSlot

Check = tuple[bool, str]

# The placeholder syntax of examfp.models (frozen), repeated here to locate slots.
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_BOUNDARY = re.compile(r"[.?!](?=\s|$)|\n")


def sentences(template: str) -> list[tuple[int, int]]:
    """Character spans of the template's sentences, in order, covering the whole template."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _BOUNDARY.finditer(template):
        end = match.end()
        if template[start:end].strip():
            spans.append((start, end))
        start = end
    if template[start:].strip():
        spans.append((start, len(template)))
    return spans


def _opens_ask(question: Question, span: tuple[int, int]) -> bool:
    text = question.template[span[0]:span[1]]
    for match in _PLACEHOLDER.finditer(text):
        slot = next((s for s in question.slots if match.group(1) in s.fills), None)
        if isinstance(slot, TextSlot) and slot.difficulty_band is None:
            found = instruction_class(slot.variants[0].values[0])
            if found is not None and found.role == COMMAND:
                return True
    literal = _PLACEHOLDER.sub(" ", text)
    for phrase in command_phrases():
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", literal, re.IGNORECASE):
            return True
    return literal.rstrip().endswith("?")


def ask_region_start(question: Question) -> int | None:
    """Template offset where the ask region begins, or ``None`` if no sentence opens it."""
    for span in sentences(question.template):
        if _opens_ask(question, span):
            return span[0]
    return None


def check_ask(question: Question, slot: Slot) -> Check:
    """Does wording slot ``slot`` stay out of the ask region, in the stem?

    Guarantees: fails when any of the slot's placeholders lies in the ask region,
    and fails closed when the question has no locatable ask.
    """
    start = ask_region_start(question)
    if start is None:
        return False, ("cannot locate the clause that names the target quantity (no command "
                       "or question mark), so a wording slot cannot be shown to stay out of it")
    positions = [m.start() for m in _PLACEHOLDER.finditer(question.template)
                 if m.group(1) in slot.fills]
    if not positions:
        return False, f"slot {slot.name!r} has no placeholder in the template"
    if max(positions) >= start:
        sentence = next(question.template[a:b].strip() for a, b in sentences(question.template)
                        if a <= max(positions) < b)
        return False, (f"wording slot {slot.name!r} sits in the ask ({sentence!r}): the "
                       "quantity asked and how to answer are radicals and may not vary")
    return True, f"wording slot {slot.name!r} sits in the stem, before the ask"
