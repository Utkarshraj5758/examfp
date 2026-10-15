# ADR 0003 — Decision rule under collusion: consistency gate, read floor, hypothesis

- **Status:** Accepted
- **Date:** 2026-10-16 (M5.5)
- **Related:** [ADR 0001](0001-two-modes.md) (practical mode has no proved collusion
  bound), [ADR 0002](0002-rs-slot-packing.md) (slot packing)

## Context

Until M5.5 the trace decided with a margin rule alone: score every centre over
the slots read (`+conf` per match, `-1.4 * conf` per mismatch) and name the top
centre if it led by more than 0.5. Every benchmark leak came from a single
centre, so the reported "0% false identification" never covered collusion.

**Finding: the score measures a different distance from the one Reed–Solomon
protects.** At the symbol level the practical code (n = 7, k = 2, d = 6)
satisfies the 2-traceability condition d > n(1 − 1/c²) = 5.25. A hybrid of two
whole codewords is therefore nearer, in symbols, to a colluder than to any
innocent. The trace, however, ranks by matching *slots*, and:

- colluders can mix single slots inside a symbol group, creating bytes neither
  of them holds;
- crops erase symbols, and the condition needs them observed;
- for 3 colluders the condition already fails (6 > 6.22 is false).

In both two-colluder failures we examined, the colluders were nearer the hybrid
in symbols (3–4 vs 6–7 for the innocent) while the innocent was nearer in slots
(9 vs 10–11; 10 vs 12). Over 1,000 centres the minimum symbol distance is 6 but
the minimum slot distance is only 8.

**Measured damage** (old rule, minority-strategy collusion, 6 questions, retype,
3% typos, 200 leaks each): an innocent centre was named in 5.5% of 2-centre
leaks and 47–55% of 3–5-centre leaks, with margins up to 12.0. Raising the
margin threshold cannot fix that.

## Decision

`score()` decides in this order (`examfp/decode/score.py`):

1. **Consistency gate.** A genuine single-source leak agrees with its source on
   every slot read, apart from reader misreads. Eliminate every centre with
   more than `tolerance` mismatching slots.
2. **Read floor.** No verdict naming any centre on fewer than `MIN_READ_SLOTS`
   read slots.
3. **Margin among survivors.** `IDENTIFIED` only if one survivor leads every
   other centre by more than 0.5. Tied survivors give `INSUFFICIENT`.
4. **Collusion hypothesis.** If no centre survives but exactly one smallest set
   of at most 5 centres jointly explains every read slot (marking assumption,
   same tolerance), the outcome is `COLLUSION_SUSPECTED` with that set. It is
   worded as a hypothesis for investigation, never an accusation. An ambiguous
   cover, or a search that exhausts its node budget, gives `INSUFFICIENT`.

**Calibrated parameters, never assumed:**

| parameter | value | how it was set |
|---|---|---|
| `MISREAD_RATE` | 2.88e-5 | 95% Clopper–Pearson upper bound: 0 misreads in 104,026 read slots |
| `FALSE_REJECTION_BUDGET` | 1e-3 | policy: at most 0.1% of genuine leaks refused because of misreads |
| tolerance | 0 (≤ 31 reads) | smallest `t` with `P(Bin(reads, rate) > t) <= budget` |
| `MIN_READ_SLOTS` | 11 | gate without a floor: innocents named at up to 10 reads, never from 11 up (0 in 5,804; 95% UB 0.052%) |

**Recalibration procedure** (required whenever the reader changes; OCR in M7
and paraphrase in M8–M10 will raise the misread rate):

1. Run `python -m eval.bench`. It reports misreads against the true source on
   6,000 single-source leaks and the 95% upper bound.
2. Set `MISREAD_RATE` to that bound. Keep the budget unless policy changes.
3. Read the floor table (gate at the new tolerance, no floor) and set
   `MIN_READ_SLOTS` to one above the most reads at which an innocent was
   identified. Confirm the boundary with a second seed.
4. Re-run the bench and accept only if the collusion rows show no innocent
   `IDENTIFIED`. A higher misread rate raises the tolerance, which gives hybrids
   more room, so the floor will move up.

## Consequences

- **Measured result** (same leaks, after the change): 0 innocents identified for
  every coalition size 1–5, and single-source leaks of 6 questions still
  identified 200/200.
- **Cost: thin leaks no longer name a centre.** Two questions carry at most 10
  slots, below the floor: single-source identification at 2 questions fell from
  91% to 0%, and at 3 questions from 99.5% to 82%. Four or more questions stay
  at 100%.
- **The collusion hypothesis is reliable only for pairs.** For 2 colluders it
  matched the exact pair 98 times in 200 and never named an outsider. For 3–5
  colluders it appeared 11 times in 600, and all 11 included a non-colluder: a
  smallest explanation is not necessarily the true coalition. The wording says so.
- **Empirical, not proved.** These are measured rates on the sample paper with
  1,000 centres. The only proved collusion bound remains the provable mode
  (Tardos, ADR 0001).
- The floor counts slots, but slots carry unequal information (a 2-variant
  wording slot vs a 119-variant option order). A floor in bits might recover some
  2–3-question leaks; measure before adopting it.

## Alternatives considered

- **Raise the margin threshold.** Rejected: false margins reached 12.0.
- **Symbol-level traceability decoding.** Guaranteed only for 2 colluders, with
  every symbol observed and colluders swapping whole symbols. Slot-level mixing
  and crops break each of those assumptions.
- **A fixed zero tolerance.** Rejected: it would silently break when OCR and
  paraphrase introduce misreads. The tolerance is derived, so it moves with the
  measured rate.
- **Report every minimal cover.** Rejected: it multiplies the centres named in
  a hypothesis; a unique cover or nothing.
