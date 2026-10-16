# ADR 0002 — Packing paper slots into GF(256) symbols

- **Status:** Accepted
- **Date:** 2026-10-15 (M5)
- **Related:** [ADR 0001](0001-two-modes.md) (practical mode uses Reed–Solomon)

## Context

Practical mode encodes each centre as a Reed–Solomon codeword over GF(256)
(`examfp/codebook/rs.py`). A codeword symbol is a byte, and parity bytes take
**any** value 0..255. A paper slot, though, shows one of only 2..119 variants,
so no single slot can carry a symbol. Slots must be grouped, and the grouping
decides three things: whether the embedding is lossless, whether every slot
carries information, and how long the code is.

The scheme it replaces, mixed radix over the whole paper (NOTES.md F3), left 20
of the sample paper's 31 positions constant across 1,000 centres.

## Decision

Each GF(256) symbol is carried by a **group** of slots read as a mixed-radix
number (implemented in `examfp/codebook/assign.py`):

1. **Order.** Members are ordered most significant first: largest alphabet
   first, ties in paper order. Byte `b` is written as its mixed-radix digits.
2. **Injective.** Group capacity `prod(alphabets) >= 256`, so every byte has its
   own combination. Combinations above 255 are never produced; reading one back
   is an erasure, not a guess.
3. **Every slot varies.** The most significant member's place value,
   `capacity / max(alphabets)`, is at most 255. Then each member's digit takes at
   least two values over 0..255, so no position can be constant.
4. **Greedy grouping for a long code.** Anchor on the largest remaining slot; add
   the cheapest combination of remaining slots that reaches 256 (smallest product,
   then fewest slots). Once less than 256 of capacity remains, append the
   leftovers as low-order digits to the group where rule 3 stays tightest. If a
   leftover fits nowhere, raise rather than leave a constant slot.
5. **Order of symbols.** Groups are ordered by their earliest member; group `j`
   carries codeword symbol `j`. The code is systematic: the first `k` symbols
   are the message.
6. **Messages.** `k` is the fewest bytes that name every centre. Centres take
   distinct messages drawn without replacement from `256^k` by a generator seeded
   from `assign`'s `seed`, which spreads data and parity bytes over the whole
   range.

On the sample paper this yields **7 symbols** (n = 7). With 1,000 centres,
k = 2, so any 2 intact groups recover a centre and up to 5 can be lost:

| symbol | slots (alphabet) | capacity | top place value |
|---|---|---:|---:|
| 0 | q6.density(7), q7.cost(7), q1.intro/lead/closing(2 each) | 392 | 56 |
| 1 | q1.speed(7), q3.dims(7), q4.pctval(7) | 343 | 49 |
| 2 | q2.opts(119), q1.unit(3), q8.closing(2) | 714 | 6 |
| 3 | eight wording slots of q2–q5 | 256 | 128 |
| 4 | q5.opts(119), q3.unit(3) | 357 | 3 |
| 5 | eight wording/unit slots of q6–q8 | 256 | 128 |
| 6 | q8.opts(119), q6.unit(3) | 357 | 3 |

## Consequences

- No position is constant over 1,000 centres (tested for three seeds), and
  accuracy no longer depends on which questions leak (NOTES.md, M5).
- **Groups span questions.** Cropping one question can erase several symbols for
  *direct* RS decoding (`complete_symbols`), which needs `k` intact groups. The
  trace does not decode directly; it scores slots one by one against every
  centre, so a partly visible group still counts as evidence. Question-local
  grouping would favour direct decoding at the cost of fewer symbols; revisit if
  direct decoding enters the trace path.
- **Wasted capacity.** Each group covers 256 with some slack (59.5 bits of
  capacity, 56 bits used by 7 symbols), because parity forces whole bytes.
- `assign`'s public signature is unchanged, but its output now depends on the
  total number of centres (through `k` and the sampled messages). Anything that
  rebuilds one centre's symbols must use the same `n_centres` and `seed`.

## Alternatives considered

- **One symbol per question.** Rejected: most questions alone fall below 256
  (q1: 168, q4: 28), so this needs a smaller field, which the prompt rules out.
- **Mixed radix without the place-value rule.** Rejected: high-order members can
  stay at digit 0, which recreates the constant positions this ADR exists to
  remove.
- **Restricting symbols to the slots' joint alphabet.** Impossible for parity:
  RS parity takes every byte value.
