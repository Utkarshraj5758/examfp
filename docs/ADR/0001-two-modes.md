# ADR 0001 — Two modes: practical and provable

- **Status:** Accepted
- **Date:** 2026-10-15 (recorded in M4; the decision dates from Phase 0)
- **Supersedes:** none

## Context

TRACE names the source centre of a leaked paper. Two different kinds of
guarantee are available, and they come from different codebooks.

**Provable.** Tardos (2003) bounds the probability of accusing an innocent
centre when up to `c` centres collude, but needs
`m = ceil(100 * c^2 * ln(n/eps))` positions. A paper has far fewer
([NOTES F1](../../NOTES.md)): the sample paper has 31 positions, while
`n = 500, c = 3, eps = 1e-6` needs 18,028 bits — 354 papers per centre at 51
bits per paper. Even a 60-question paper supports `c_max = 0.34`. A single
paper cannot carry the code.

**Practical.** An exam board issues one paper per centre per sitting, and leaks
arrive cropped (erasures). That calls for a code that fits in one paper and
decodes from whichever positions survive. Reed–Solomon over GF(256) is MDS: any
`k` of its `n` symbols determine the codeword, tolerating up to `n − k`
erasures. It identifies a centre exactly from a clean read but offers **no
collusion bound**; its quality is whatever the evaluation harness measures.

## Decision

Run two modes with separate codebooks and separate claims.

| | `practical` | `provable` |
|---|---|---|
| Codebook | Reed–Solomon over GF(256) (`codebook/rs.py`, M5) | Tardos 2003 (`codebook/tardos.py`, built in M2) |
| Unit issued | one paper per centre | a multi-paper session per centre |
| Guarantee | empirically measured identification and false-identification rates | provable bound on accusing an innocent, for coalitions up to `c` |
| Allowed claim | "identified X% of k-question leaks, Y% false identification, N trials" | "resists `c` colluders at `eps`" — only for full-length sessions |

Rules:

1. **Never conflate the modes** in code, docs or claims. Practical-mode numbers
   are never presented as provable; the Tardos bound is never quoted for a
   single paper.
2. Each mode has its own codebook module. `assign.py` remains the practical
   entrypoint and keeps its public signature when M5 swaps in Reed–Solomon.
3. Every trace result records its mode alongside the model and codebook
   versions CLAUDE.md already requires.
4. Both modes share the decision rule: `IDENTIFIED` only above threshold,
   otherwise `INSUFFICIENT` or `NO_MATCH`; erasures are never guessed.
5. The empirical Tardos constant measured in M11 is labelled "measured, not
   proved". The literal constant 100 remains the only basis of a provable claim.

## Current state (M5)

Practical mode now runs on Reed–Solomon over GF(256) (M5), with slots packed
into symbols as recorded in [ADR 0002](0002-rs-slot-packing.md). The decision
rule gained a consistency gate and a read floor in M5.5
([ADR 0003](0003-decision-rule-under-collusion.md)), after collusion was found to
make the margin-only rule name innocent centres.

On the sample paper, single-source leaks of 4 or more questions are identified
100% of the time, with 0% false identification. Colluded leaks (2–5 centres)
are measured separately: after M5.5, 0 innocents identified in 800, though most
are refused. These are measured, practical-mode results, not proved bounds.

The PLAN.md baseline (91% at 6 leaked questions) was measured on the interim
mixed-radix codebook, which is kept only as a benchmark baseline in
`eval/baselines.py`.

## Consequences

- Claims stay honest: deployable today with measured numbers, plus a provable
  mode for settings that issue many papers per centre.
- Two codebook paths to maintain and test; trace records, reports and the
  dashboard must label the mode.
- Practical mode has no collusion guarantee. A leak blended from several centres
  is unbounded territory, so M11's collusion sweep (2–5 centres) must report the
  false-identification rate for every cell, and the decoder must prefer
  `INSUFFICIENT` over a wrong centre. *M5.5 confirmed the risk was real and added
  the consistency gate (ADR 0003).*

## Alternatives considered

- **Tardos only** — rejected: not deployable in one paper (NOTES F1).
- **Practical only** — rejected: discards the provable guarantee, which is
  already built and is what multi-paper settings need.
- **Shrink the Tardos constant until it fits a paper** — rejected: that swaps a
  proved bound for an unproved one while keeping the "provable" label. The
  measured constant is reported separately, labelled as measured.
