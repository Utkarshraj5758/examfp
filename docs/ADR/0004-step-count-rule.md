# ADR 0004 — Fairness rules: equal steps, variant separation, and the ask

- **Status:** Accepted
- **Date:** 2026-10-17 (M6). Parts 2–4 added the same day, to close M6.
- **Decided by:** the owner, in the planning session (PLAN.md M6, decision 2), at
  the M6 kickoff, and in the closing session. This ADR records the rules; it does
  not adapt them.
- **Implemented in:** `examfp/fairness/bands.py` (part 1, `step_count`,
  `check_steps`), `separation.py` (part 2), `ask.py` (part 3),
  `instructions.py` (part 4)

*Part 1 is the step count. Part 2 is variant separation; part 3, the ask as a
radical; part 4, instruction phrasing. All are structural: none uses a model.*

# Part 1 — Step count

## Context

Every centre's paper must be identical in answers and difficulty. For a numeric
group, the difficulty band in `models.py` (frozen) already fixes the operation,
the digit count of each operand, and excludes trivial operands. It does not fix
how much *work* the numbers need. The sample paper's q3 offered 16 × 90 and
32 × 45 as equal: same answer (1440), same digit counts, no trivial operand. Yet
the first needs one carry-free partial product (16 × 0) and one with two carries
(16 × 9), and the second needs two partial products with three carries and an
addition with one more. A centre that drew 32 × 45 sat a harder question.

The fairness checker needs a step count that a machine can compare and a person
can check by hand.

## Decision

**General principle.** Two variants are equal in steps when, in the canonical
written method, they require the same number of **positional operations** AND
the same number of **carries, borrows or non-zero remainders**. A candidate is
compared with its slot's reference variant (symbol 0).

| operation | canonical method | positional operations | events counted |
|---|---|---|---|
| multiply | long multiplication; the multiplier is the **second operand in fill order** | one per digit of the multiplier, zeros included | carries: every column whose result is 10 or more, in every partial-product row **and** in the addition of the rows, **the leftmost column included** |
| divide | short / long division, dividend first | one per digit of the **dividend**, not of the answer (a dropped leading zero would undercount) | non-zero remainders, one per step, the first partial dividend included |
| add | column addition | one per digit column | carries, the leftmost column included |
| subtract | column subtraction, minuend first | one per digit column | borrows |
| percent | percentage first, then the whole | **one** if 100 / p is a whole number, **two** otherwise | none: the rule counts operations only |

**Why percentages work this way.** A unit fraction of 100 needs one division
(20% of 300 = 300 ÷ 5). Anything else needs a division and a multiplication
(15% of 400 = 400 ÷ 100 × 15). So 20% and 25% are one step; 15%, 40% and 75%
are two.

**Addition and subtraction** are defined although the sample paper has no such
bands, so the checker has no hole: an unrecognised case can never pass by
default.

**Operand order is fill order.** The checker never reorders operands. Divide:
(dividend, divisor). Multiply: (multiplicand, multiplier). Percent:
(percentage, whole). Subtract: (minuend, subtrahend). Add: addends. The author
controls which multiplicand the method writes on top through `fills`.

**Scope of the comparison.** Steps are compared only for a candidate that is a
valid band member (right digit counts, no trivial operand) with the right answer.
Otherwise the band or answer rule is the one that fails, and the step check is
recorded as not run.

**Fail closed.** No canonical method means no step count, and the check fails:
three or more factors, a zero divisor, a zero percentage, a negative difference,
a non-whole operand, an unknown operation.

### Worked examples (all in `tests/fairness/test_bands.py`)

| group | operations | events | note |
|---|--:|--:|---|
| 16 × 90 | 2 | 2 carries | 16×0 = 0; 16×9: 6×9 = 54 (carry), 1×9+5 = 14 (carry); 0 + 1440 none |
| 90 × 16 | 2 | 2 carries | 90×6: 9×6 = 54 (carry); 90×1 none; 540 + 900: 5+9 = 14 (carry) |
| 32 × 45 | 2 | 4 carries | rejected against 16 × 90 |
| 20 × 72 | 2 | 1 carry | rejected against 16 × 90 |
| 18 × 25 / 25 × 18 | 2 / 2 | 3 / 2 carries | operand order matters in general |
| 180 ÷ 3 | 3 | 1 remainder | 1 r1, 18 r0, 0 r0 |
| 200 ÷ 3 | 3 | 3 remainders | (and the wrong answer) |
| 15% / 12% / 48% | 2 / 2 / 2 | — | |
| 20% / 25% | 1 / 1 | — | rejected against 15% |

### Owner rulings on the details (2026-10-17)

- **Which carries count:** every carry, including the leftmost column's (whose
  tens digit is written rather than carried) and those in the addition of the
  partial products. The alternatives would have made 90 × 16 and 16 × 90 differ
  (the fixture labels both fair).
- **Which operand is the multiplier:** the second in fill order. Under the
  every-carry reading the choice changes nothing on the current paper, but it
  does in general (18 × 25 vs 25 × 18).

## Consequences

- **The sample paper changed** (PLAN.md M6, decision 3). q3 lost 20 × 72 and
  32 × 45, and q7 lost 72 × 20 and 45 × 32. Each now has 5 variants: exactly 5
  distinct operand sets of 1440 tie with the reference under this rule, and the
  reader identifies a group by its *set* of numbers, so a swapped pair (90 × 16
  beside 16 × 90) could not be told apart. q4 replaced 20% and 25% with 12% of
  500 and 48% of 125 and kept 7 variants. Divisions q1 and q6 were already
  uniform (3 / 2 operations, 1 non-zero remainder each).
- Durable capacity fell from 14.04 to 13.07 group bits, which changes the RS
  slot packing (ADR 0002) and calls for the recalibration check of ADR 0003.
  The measured consequences are in NOTES.md, M6.
- A band's alphabet is now bounded by the step rule as well as by the digit
  counts: an author must find variants that tie with the reference in both
  counts, which can be few.

## Limitation

**This counts steps in one canonical method, and students may solve by others.**
A student may compute 16 × 90 as 16 × 9 × 10, 25% as "divide by 4", 48% of 125
as 48 ÷ 8 × 10, or 90 × 16 with the 90 written underneath. Two variants equal
under this rule can differ in effort under another method, and vice versa. The
rule is a reproducible proxy for equal difficulty, chosen because it can be
checked by hand and by machine; it is not a measurement of how hard students
find a question. The percentage rule counts operations only, so it ignores
carries inside the division and multiplication it implies.

## Alternatives considered

- **Count non-zero partial products only** (the planning draft: 16 × 90 is one
  partial product). Superseded by the owner's positional-operation rule, which
  counts every multiplier digit.
- **Internal carries only** (the leftmost column's tens digit is not a carry).
  Rejected by the owner: it makes 90 × 16 (0 carries) differ from 16 × 90 (1).
- **Carries in the partial-product rows only.** Rejected: it ignores the addition
  of the rows, which is part of the written method.
- **Quotient digits for division.** Rejected: 180 ÷ 3 = 60 has two quotient
  digits, but the method works through three dividend digits; a dropped leading
  zero undercounts.
- **Multiplier = the operand with fewer digits, or both orders must match.**
  Rejected in favour of fill order, which the author controls.

---

# Part 2 — Variant separation

## Context

A fingerprint symbol is only as good as the reader's ability to recover it. The
fuzzy reader (`examfp/decode/read.py`) lowercases the leak, takes the longest
variant found verbatim, and otherwise the variant with the strictly best fuzzy
partial match (at least 80). In M6 the sample paper's first replacement closing,
"Show your work.", sat beside "Show your working.". A typo in the longer text
let the shorter one win: 6 misreads in 104,048 reads, and under ADR 0003 that
would have raised the gate tolerance to 1 and the read floor to 16. Choosing a
different variant fixed it, but only case by case. The rule has to be
structural.

## Measurement (`eval/separation.py`, 2026-10-17, seed 0)

Every one of the sample paper's 23 text-read slots (wording, instruction, unit
form) was paired with synthetic competitors, and each pair was read 1,000 times
under the benchmark's attack (render, retype, 3% adjacent-letter typos,
`read_leak` against the whole paper), alternating which variant was shown. That
makes 1,602,000 reads in all. The paper's own reference–variant pairs were read
4,000 times each.

| family | what the competitor is | misreads per read |
|---|---|---|
| edit, d = 1 / 2 / 3 / 4 / 5 / 6 | random letter edits at exact Levenshtein distance d, no prefix or containment | 0.57% / 0.18% / 0.07% / 0.02% / 0.03% / 0.004% |
| edit, d = 7 / 8 / 9 / 10 / 11 / 12 | (69,000 reads each) | 0 / 0 / 1 misread / 14 misreads / 0 / 0 |
| prefix, by edit distance d = 1 … 9 | the reference truncated or extended by k = 1 … 8 letters before the final punctuation | 0.34% at d = 1, up to 4.95% at d = 7 (4.85% at d = 8); the single pair at d = 9: 6.6% |
| containment, by edit distance d = 1 … 8 | k = 1 … 8 leading letters dropped or prepended (suffix, infix) | 0.54% at d = 1, rising to 9.0% at d = 8 |
| the paper's 26 reference–variant pairs (of its 29 pairs; the 3 between two non-reference variants were not read) | as written | 0, except q4 "Show your working." / "Include your working." (d = 7): 1 in 4,000 |
| the M6 pair | "Show your working." / "Show your work." (d = 3) | 2 in 4,000 |

**The rule for the minimum, fixed before the sweep ran:** the smallest distance
`d` such that the edit family shows no misread at `d` or above, and the reads
pooled from `d` upwards bound the misread rate at or below the calibrated
`MISREAD_RATE` (2.88e-5, ADR 0003) at 95%. **It gives 11**: 0 misreads in
138,000 reads at d ≥ 11, upper bound 2.17e-5.

**Why so far out.** The misreads at d = 9 and 10 are not near-duplicates. They
are short references nearly embedded in long competitors: "cm²" inside
"xklbccwm²xfjc", where one adjacent-letter typo makes "cm²" appear verbatim.
Edit distance counts the padding, but the reader only aligns the best
substring, so the two measures disagree. Containment of any kind is the
dominant hazard: prefix pairs, and suffix or infix pairs even more so, misread
at rates two orders of magnitude above the calibrated rate.

## Decision (owner, 2026-10-17)

1. **No containment.** No variant of a text-read slot may contain another
   (normalised: lowercase, collapsed whitespace, trailing punctuation dropped):
   no prefix, suffix or infix. This extends the requested prefix rule, because
   the containment family misread even more than the prefix family. It catches
   the M6 pair.
2. **The edit-distance minimum is recorded, not adopted.**
   `MEASURED_MIN_EDIT_DISTANCE = 11` is kept beside the deployed
   `MIN_EDIT_DISTANCE = 1`, which turns the distance rule off. At 11, 17 of the paper's 29 text-variant pairs
   would fail: every lead pair (d = 7–8), every working closing (d = 7) and four
   short unit pairs (d = 1–5). Fixture false rejections would rise from 9 to
   16. The bench reads those 17 pairs with no misreads (except the one q4
   misread above), so the cost would buy little.

## Consequences

- The M6 near-prefix case, and any containment, is now rejected structurally
  (`separation` check on every text-read slot). U11 also fails it: it contains
  its reference "On the way to Nashik,".
- **The distance rule is open.** Edit distance is the wrong measure for this
  reader. A measure that sees near-embedding, such as the reader's own partial
  ratio after a simulated typo, needs a new design fixed before a fresh sweep.
  The current pair at d = 7 that misread once in 4,000 shows that the residual
  risk is not zero.
- Two further mechanisms were seen and are not covered: a typo elsewhere in the
  question can create a short variant verbatim ("₹" vs "cs": "cost" became
  "csot"), and a variant may occur verbatim in the question's other text.

---

# Part 3 — The ask is a radical

## Context

Item-generation theory separates a question's **radicals**, the elements that
decide what is measured and how hard it is, from its **incidentals**, surface
features that can vary without changing either. A fingerprint may vary
incidentals only.

The quantity asked is the first radical: "its circumference" and "its area"
over the same circle are different questions. The units, precision and format
the answer must take are radicals too, and so are the options of a
multiple-choice question. Until now only NLI guarded a wording slot against a
changed ask. The held-out set showed that is not enough: the model passed
circumference → area (0.834 / 0.625) and factors → multiples (0.991 / 0.989).
**NLI must never be the only guard against a changed ask.**

## Decision

- The **ask region** runs from the start of the first template sentence that
  opens the ask to the end of the question. A sentence opens the ask when it
  holds a command: a slot whose reference is a command phrasing in the
  instruction table (part 4), the same phrasing written literally (whole words,
  case-insensitive), or a sentence ending in "?". Sentences split on `.`, `?` or
  `!` before whitespace or the end, and on line breaks, in the template itself.
- An **NLI-judged wording slot** must lie wholly before the ask region, in the
  stem that sets out the situation. Otherwise the `ask` check fails, and the
  model is not consulted.
- Instruction slots, unit forms, numeric groups and option orders may sit in the
  ask region, because their tables and rules keep the ask identical.
- **No locatable ask fails closed** for every wording slot of the question. An
  earlier false anchor (a context sentence that happens to contain "state") only
  widens the region, so it errs strict.

The region is deliberately wider than "the clause that names the target
quantity". Whatever follows the command constrains the answer and is part of
the ask.

## Consequences

- Held-out N06 and N08, rebuilt as slots, are rejected by `ask` before any model
  call (`tests/fairness/test_check.py`, `tests/fairness/test_ask.py`).
- The sample paper is unaffected: its only NLI-judged slots are the three intros,
  all in the stem. No fixture entry changed verdict.
- **Limit:** the stem holds radicals too, the data and the relationships ("Asha
  is 4 years older than Ravi"). A wording slot that reverses a relationship in
  the stem is still guarded only by NLI and the numbers rule. On the held-out set
  the pinned model caught 7 of 7 reversed relationships; base, the candidate,
  passed one (N29).

---

# Part 4 — Instruction phrasing (owner decision, 2026-10-17)

**Category.** *Instruction phrasing* is the command that says what to do with
the question ("Calculate", "State"), and instructions about the working ("Show
your working."). *Option-choice phrasing* says how to answer a multiple-choice
question ("Choose one option only."). Both qualify only if they neither name nor
constrain the quantity asked: "Give your answer in square metres." is part of
the ask, not boilerplate.

**Rule.** A slot whose reference phrasing is in the instruction table is judged
by the table, like unit forms: the candidate must be listed in the same class.
An unlisted phrasing fails closed. NLI is never consulted.

**The table is the paper's complete instruction vocabulary**, every variant of
every instruction slot in the sample paper, grouped by what it asks for:
compute ("Calculate", "Work out"), recall ("State", "Identify"), show working
("Show your working.", "Include your working."), choose one option ("Choose one
option only.", "Select only one option."). It was not built from the fixture,
and a test pins it to the paper's vocabulary.

**Consequence.** Every fair instruction phrasing the paper does not use is now
rejected. That covers the five command synonyms (F01 "Find", F03 "Determine",
F04 "Find", F07 "Name", F09 "Write down"), which NLI used to pass, and the four
closings (F11, F12, F13, F14). Fixture false rejections go from 3 to 9. The
model's quality is unchanged: on open question prose alone (the held-out set
less its one instruction-only pair, E09), it scores 55/59 = 93.2% (CI
83.5–98.1%) against 55/60 = 91.7%. These are the same 55 correct answers; the
pair removed was one of its errors. The table added coverage, not model
quality.
