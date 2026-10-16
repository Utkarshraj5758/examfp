# ADR 0004 — Step count: equal steps in the canonical written method

- **Status:** Accepted
- **Date:** 2026-10-17 (M6)
- **Decided by:** the owner, in the planning session (PLAN.md M6, decision 2) and at
  the M6 kickoff. This ADR records the rule; it does not adapt it.
- **Implemented in:** `examfp/fairness/bands.py` (`step_count`, `check_steps`)

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
