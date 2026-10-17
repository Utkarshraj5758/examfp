# ADR 0003 — Decision rule under collusion: consistency gate, read floor, multi-source signal

- **Status:** Accepted
- **Date:** 2026-10-16 (M5.5; step 4 revised twice the same day after review)
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
4. **Multi-source signal.** If the gate eliminates every centre and the floor
   is cleared, the outcome is `MULTI_SOURCE_SUSPECTED`. **It names nobody.** The
   verdict states that no single centre in this codebook explains the observed
   slots and lists three possible causes: the leak combines papers from more
   than one centre, misreads exceed the gate tolerance, or the leak comes from a
   paper outside this codebook.

**Pair hypothesis: opt-in, never part of a verdict.** `unique_pair_hypothesis()`
looks for a pair of centres that jointly explains every read slot (marking
assumption, same tolerance). It runs only under `trace --hypotheses`. It reports
a pair only when exactly one pair covers the reads; sets of three or more are
never reported, and an ambiguous cover or an exhausted node budget reports
nobody. Any pair is printed together with its measured accuracy (98 correct of
109 on the M5.5 bench, 117 of 126 after M6 revised the sample paper; every wrong
one from a leak involving 3 or more centres).
The output also states that the system cannot distinguish a two-centre leak from
a larger one.

**Display follows the verdict.** A ranked list of centres, and the margin, is
shown only beside an `IDENTIFIED` verdict, where the named centre already is the
verdict. For any other outcome it appears only under `--hypotheses`, labelled
"not a verdict". Otherwise rank 1 would do at the display layer what the gate
forbids in the rule (`show_ranking()`, used by the CLI and the dashboard).

*History.* The first M5.5 version, `COLLUSION_SUSPECTED`, named any unique
minimal set of up to 5 centres. The first review restricted the named set to a
unique pair attached to the verdict. The second review demoted the pair to the
opt-in hypothesis above, for the reason given under Consequences.

**Calibrated parameters, never assumed:**

| parameter | value | how it was set |
|---|---|---|
| `MISREAD_RATE` | 2.88e-5 | 95% Clopper–Pearson upper bound: 0 misreads in 104,026 read slots |
| `FALSE_REJECTION_BUDGET` | 1e-3 | policy: at most 0.1% of genuine leaks refused because of misreads |
| tolerance | 0 (≤ 31 reads) | smallest `t` with `P(Bin(reads, rate) > t) <= budget` |
| `MIN_READ_SLOTS` | 11 | gate without a floor: innocents named at up to 10 reads, never from 11 up (0 in 5,804; 95% UB 0.052%) |

**Re-measured 2026-10-17 (M6), after the fairness fixes changed the sample
paper:** 0 misreads in 104,098 read slots (same bound, tolerance 0); innocents
again identified at up to 10 reads and never from 11 up on seeds 1 and 7 (0 in
5,812 leaks), so `MIN_READ_SLOTS` stays 11; 0 innocents identified for coalitions
of 1–5. Only the pair accuracy moved (117 of 126). The first M6 draft of the
paper used a wording variant that is nearly a prefix of its reference ("Show
your work." beside "Show your working."). It produced 6 misreads, which would
have raised the tolerance to 1 and the floor to 16, and cut 3-question leaks to
0% and 4-question leaks to 47.5%. The paper was changed instead (NOTES.md, M6).

**Recalibration procedure** (required whenever the reader or the paper changes;
OCR in M7 and paraphrase in M8–M10 will raise the misread rate):

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
- **The multi-source signal is reliable; the pair is not, so it was demoted.**
  The signal fired on 800/800 leaks from 2–5 centres and on 0/200 single-source
  leaks. For 2 colluders the unique pair was the exact coalition 98 times and
  never included an outsider. All 11 wrong pairs came from leaks involving 3–5
  centres (8, 1 and 2), and all 11 were *pairs*. Refusing to name sets of 3 or
  more therefore removed none of them. A pair is wrong exactly when more centres
  were involved, and the observation cannot tell that case from a genuine
  two-centre leak. The risk cannot be filtered out, only disclosed. Hence:
  verdicts name nobody, and the pair appears only on request, with its error
  rate.
- **The signal depends on calibration.** Misreads beyond the tolerance, or a
  leak from outside the codebook, also empty the gate. That is why the verdict
  lists three causes rather than asserting collusion. Recalibrating on every
  reader change (M7) is part of the rule. The enum name still suggests the first
  cause only; NOTES.md proposes renaming it in M7.
- **Empirical, not proved.** These are measured rates on the sample paper with
  1,000 centres. The only proved collusion bound remains the provable mode
  (Tardos, ADR 0001).
- The floor counts slots, but slots carry unequal information (a 2-variant
  wording slot vs a 119-variant option order). A bits floor was measured but not
  adopted: its threshold moved between seeds (16.29 vs 18.59 bits), and at 18.59
  it would lift 3-question leaks from about 80% to about 91%. *On the M6 paper*
  seeds 1 and 7 give 17.79 and 16.29 bits, and at 17.79 3-question leaks would go
  from 82–84% to 98–99%. M11 revisits it with more trials.
- **2-question leaks are a capacity bound.** The most informative question pair
  carries 17.79 bits, but excluding the observed false identifications needed at
  least 18.59 on the pre-M6 paper. On the M6 paper seed 1 produced a false
  identification at exactly 17.79 bits, so the requirement is at least 17.79, and
  a bits floor identifies only strictly above it. More data can only raise that
  requirement. So no entropy-based
  floor can recover 2-question leaks: the information needed to rule out a
  hybrid is not in the observation (sample paper, 1,000 centres).

## Alternatives considered

- **Raise the margin threshold.** Rejected: false margins reached 12.0.
- **Symbol-level traceability decoding.** Guaranteed only for 2 colluders, with
  every symbol observed and colluders swapping whole symbols. Slot-level mixing
  and crops break each of those assumptions.
- **A fixed zero tolerance.** Rejected: it would silently break when OCR and
  paraphrase introduce misreads. The tolerance is derived, so it moves with the
  measured rate.
- **Report every minimal cover.** Rejected: it multiplies the centres named in
  a hypothesis; a unique pair or nobody.
- **Name unique minimal sets of 3–5 centres.** Rejected in review: in M5.5 no
  such set was ever the unique minimal explanation, and naming larger sets
  multiplies the chance of implicating an outsider.
- **Attach the unique pair to the verdict.** Rejected in the second review: 11
  of 109 such pairs implicated an outsider, all from leaks of 3 or more
  centres, and nothing observable separates those from genuine two-centre
  leaks. Kept only as the opt-in `--hypotheses` output, which prints the error
  rate.
