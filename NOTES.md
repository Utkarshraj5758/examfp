# TRACE — engineering notes

Findings and design decisions, newest milestone last. Every number here was
measured on the sample paper (`data/papers/sample.json`: 8 questions,
31 fingerprint positions) unless stated otherwise.

---

## Phase 0 findings (M1–M3, Sept 2026)

### F1 — Capacity: one paper cannot carry a provable code

Tardos (2003) needs code length `m = 100 * c^2 * k` with
`k = ceil(ln(n/eps))` (Tardos's `k = ceil(ln(1/eps_1))`, union bound
`eps_1 = eps/n`), constants kept literally. The sample paper offers **31
positions** (59.5 payload bits before M6, 58.5 after; 51 Tardos bits after taking
`floor(log2(alphabet))` per position).

*Corrected 2026-10-17:* until then the code and this table used the unrounded
`ln(n/eps)` in place of `k`. That gave `m` and `Z` smaller than the proof
requires, the unsafe direction. The table also mixed rounding (nearest integer
here, ceiling in the text). Every figure below now uses the ceiling.

Required positions, `n = 500` centres (`k` = 11, 14, 21 for the three `eps`):

| c | eps = 1e-2 | eps = 1e-3 | eps = 1e-6 |
|---|-----------:|-----------:|-----------:|
| 2 | 4,400 | 5,600 | 8,400 |
| 3 | 9,900 | 12,600 | 18,900 |
| 5 | 27,500 | 35,000 | 52,500 |

No cell is reachable. At `eps = 1e-6` the sample supports `c_max = 0.12`; a
realistic 60-question paper (~3.9 positions/question, ~232 positions) reaches
only `c_max = 0.33` (0.34 under the unrounded form) — not even one colluder.
Multi-paper layering makes the length representable: at
`n = 500, c = 3, eps = 1e-6` a centre's codeword is 18,900 bits = **371 papers
per session** at 51 bits/paper (354 under the unrounded form). In a
coin-strategy collusion demo the accuser caught all three colluders and accused
no innocent, both before and after the correction (CLI defaults n = 100, c = 3,
eps = 0.01: m = 9,000, Z = 600).

*Still unrounded:* `Paper.capacity_report` in the frozen `models.py` prints
`m = 100*c^2*ln(n/eps)` for its theoretical line and feasibility grid. Changing
it needs explicit instruction; until then its figures are slightly low.

**Consequence:** two modes that must never be conflated — see
[ADR 0001](docs/ADR/0001-two-modes.md). The empirical constant `k` is still
`<unset>`; PLAN.md assigns its measurement to M11.

### F2 — Channel durability: what a leaker copies vs. what they rewrite

Fingerprint channels split by whether a leaker reproduces them verbatim:

| channel | durable? | positions | bits |
|---|---|---:|---:|
| numeric groups | yes — numbers are copied exactly | 5 | 14.0 |
| MCQ option order | yes — order is copied exactly | 3 | 20.7 |
| unit forms (`km/h` vs `kilometres per hour`) | yes — copied literally | 4 | 5.8 |
| wording (`Calculate` vs `Work out`) | **no** — paraphrase destroys it | 19 | 19.0 |

Durable fraction **68.1%** (target ≥ 60%). It got there by widening numeric
groups to 6–7 variants *inside* their difficulty bands, using 5-option MCQs
(5! − 1 = 119 permutations, identity excluded) and making wording binary.

- Difficulty bands cap numeric alphabets (a 1-digit non-trivial divisor allows at
  most 7 variants), so durable capacity grows mainly through option order.
- Positions and bits are different budgets: Tardos length is counted in
  positions, codebook size in bits. 19 of 31 positions are fragile wording.
- `attacks.typos` only swaps adjacent letters, so the numeric payload survives
  typos verbatim; `retype` keeps digits, option lines and units.
- Implication for M8–M10: under paraphrase, wording positions become erasures.
  The neural decoder must be judged on durable-channel recovery first.

### F3 — Mixed-radix assignment is position-dependent

The crude `assign` expands `x = (c*617 + 37 + seed) mod prod(alphabets)` in mixed
radix with the **last** position least significant. For 1,000 centres
`x < ~617,000`, far below `prod(alphabets) ~ 8e17`, so the high-order positions
never change. Measured: **20 of 31 positions — all of q1–q5 and 2 of q6's 5 —
hold the same symbol for every one of the 1,000 centres.** Only 11 positions
(the rest of q6, plus q7 and q8) discriminate, so **identification depends on
which questions leak**: a q1-only leak ties all 1,000 centres (`INSUFFICIENT`).

Crop → retype → 3% typos, 200 trials per `k` (`eval/out/results.csv`, seed 0):

| k leaked | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| correct % | 0.0 | 9.5 | 27.5 | 53.5 | 71.0 | 91.0 | 100 | 100 |
| false-id % (single-source) | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Over seeds 0–99 the 6-question rate is 88/100; the misses are crops that drop
the late questions, and they come back `INSUFFICIENT`, never a wrong centre.
*Correction (M5.5): every leak here came from one centre. Under collusion the
same margin-only rule did name innocent centres; see M5.5.*
Recovery averages ~3.8 positions per leaked question.

**Fix (M5):** Reed–Solomon over GF(256) is MDS — any `k` symbols determine the
codeword — so every position carries information and accuracy should stop
depending on which questions leak. M5 must report accuracy by leaked-question
position, before vs after.

**Status: fixed in M5.** No position is constant any more, and early, middle and
late leaks perform alike — see the M5 section below.

### Smaller Phase 0 notes

- PDF text extraction inserts or drops spaces around kerned pairs (`AV` → `A V`);
  any test that round-trips text through a PDF must compare whitespace-insensitively.
- Question text is emitted as Typst string literals (`#"..."`), which disables
  smart quotes and `--` dash substitution; only `\` and `"` need escaping.

---

## M4 — repo hardening (2026-10-15)

- **numpy pin.** numpy 2.5 requires Python ≥ 3.12, so the 3.11 contract pins
  **numpy 2.4.6**. The whole pinned set, all extras together, was resolved with
  wheels only for Python 3.11 and 3.12 on Windows (74 / 73 packages).
- **Packaging bug fixed.** `packages = ["examfp"]` shipped only the top-level
  package; `examfp.codebook` and `examfp.decode` were missing from built wheels
  (editable installs hid it, and so does a stale `build/` directory — verify
  with a clean build). Now discovered with `packages.find`; guarded by
  `tests/test_repo_hygiene.py`. The wheel now holds exactly `examfp`,
  `examfp.codebook`, `examfp.decode`, `ml`, `service`.
- **Line endings.** Git for Windows sets `core.autocrlf=true` in its system
  gitconfig, so Windows clones — CI included — get CRLF files. The suite is
  green on a CRLF clone. Git-for-Windows `grep` strips CR, so check endings with
  `git ls-files --eol`, not grep.
- **Acceptance record.** Clean clone → fresh `.venv` → `pip install -e ".[dev]"`
  → `.\tasks.ps1 lint` clean and `.\tasks.ps1 test` 110 passed, on Python
  3.12.10 (clean export) and 3.11.17 (real `git clone`, CRLF).
  `pre-commit run --all-files` green. CI has not run yet: the project is not a
  git repository and has no remote.
- **Execution policy.** Windows 11 defaults to `Restricted`, which blocks
  `.\tasks.ps1`. Allow local scripts once with
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or run one task with
  `powershell -ExecutionPolicy Bypass -File .\tasks.ps1 test`.
- **`ml/` and `service/`** exist as empty packages so the contract's
  `mypy --strict examfp service ml` runs exactly as written.
- **Pre-commit hooks are local** (`language: system`): they run the pinned
  ruff/mypy from the active environment. Isolated hook environments would drift
  from the pins and lack the dependencies mypy needs.

### Open items found during M4 (not fixed — out of scope)

- **Plaintext codebook on disk.** `generate`, `demo` and `dashboard` write
  `out/codebook.json` unencrypted, violating security rule 5. `.gitignore`
  keeps it out of git, but the real fix is envelope encryption (M12).
  *M5: partly resolved — `--encrypt` writes only an AES-GCM envelope. Plaintext
  is still the default so the demo runs with zero setup.* *2026-10-17: sealing
  is now the default for `generate`, `demo` and the dashboard; `--plaintext`
  opts out with a warning (M5 open items below).*
- **Layout drift.** `api/dashboard.py` and `eval/` predate the CLAUDE.md layout
  (`service/`, `web/`). `examfp/cli.py`'s `dashboard` command imports
  `api.dashboard`, so the core library reaches into repo tooling — against
  "the core library is pure". Resolve when M12/M13 replace the dashboard.
  *M5: dependency inverted — the command moved to `python -m api.dashboard` and
  a hygiene test forbids `examfp/` importing repo tooling. `api/` and `eval/`
  still predate the layout.*
- **Stale placeholder text.** `Paper.capacity_report` prints
  `k = <unset> (... pending M6)`, but PLAN.md now assigns measuring `k` to M11.
  `models.py` is frozen; correct it in M11 under explicit instruction.
  *M5: fixed on explicit instruction (one string in `models.py`).*

### Deferred dependency choices

Pinned only what CLAUDE.md / PLAN.md name unambiguously. Chosen later, in the
milestone that needs them: worker framework (Celery vs RQ, M12), JWT library
(M12), ~~AES-GCM library and whether it lives in core or service~~ (decided in
M5: `cryptography` in core, as CLAUDE.md places `crypto.py` there), SymPy
(M6), DeBERTa tokenizer extras such as `sentencepiece`/`protobuf` (M6/M9), OCR
engines (M7), plotting for figures (M10/M11), and a transitive lock file.

---

## M5 — Reed–Solomon codebook (2026-10-15)

**Codec.** `examfp/codebook/rs.py`: RS over GF(256), QR-code parameters
(primitive polynomial 0x11D, alpha = 2, first root alpha^0), systematic
encoding, Forney erasure decoding, standard library only. It reproduces three
published vectors (ISO/IEC 18004 "HELLO WORLD" and "01234567" 1-M, Wikiversity
"RS codes for coders"), each cross-checked against the independent `reedsolo`.
Hypothesis: any `k` surviving symbols recover the codeword; a corrupted survivor
is refused, never absorbed.

**Packing** ([ADR 0002](docs/ADR/0002-rs-slot-packing.md)). Each GF(256) symbol is
a group of slots read in mixed radix, with capacity >= 256 (injective) and a
most-significant place value <= 255 (every slot varies). The sample paper gives
**n = 7** symbols; 1,000 centres need **k = 2**, so up to 5 symbols may be lost.
`assign` keeps its signature. No position is constant over 1,000 centres
(previously 20 of 31).

### Before / after (sample paper, 1,000 centres, retype + 3% typos, 200 trials per cell)

Random crop of `k` questions — correct identification:

| k | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| mixed-radix (before) | 0.0 | 9.5 | 27.5 | 53.5 | 71.0 | 91.0 | 100 | 100 |
| Reed–Solomon (after) | 1.5 | 91.0 | 99.5 | 100 | 100 | 100 | 100 | 100 |

Leaks drawn only from one third of the paper — correct identification:

| region (questions) | k | mixed-radix | Reed–Solomon |
|---|--:|--:|--:|
| early (q1–q3) | 1 / 2 / 3 | 0 / 0 / 0 | 1.0 / 94.5 / 100 |
| middle (q4–q6) | 1 / 2 / 3 | 0 / 0 / 0 | 2.0 / 90.0 / 100 |
| late (q7–q8) | 1 / 2 | 0 / 100 | 1.0 / 99.0 |

False identification is **0% in every cell, for both codebooks — for
single-source leaks**, the only kind this sweep contained. Every miss is
`INSUFFICIENT`. *Correction (M5.5): colluded leaks were not tested here, and the
margin-only rule named innocents for them; see M5.5.* The mixed-radix k-sweep
reproduces the Phase 0 numbers exactly,
confirming the baseline was preserved verbatim. Raw data: `eval/out/results.csv`,
`eval/out/results_by_region.csv` (`.\tasks.ps1 bench`, ~30 s).

**Findings.**
- Position dependence is gone: before, early or middle leaks were worthless at
  any size; now every third performs alike.
- **One question is still not enough, by arithmetic, not by code.** A question
  offers at most a few hundred slot combinations (q1: 168, q2: 476) for 1,000
  centres, so several centres share any one of them. Two questions reach about
  90%; three, 100%. *Superseded by the M5.5 read floor (11 slots): two questions
  carry at most 10 slots and no longer name a centre; three reach 82%; four or
  more, 100%.*
- The trace still scores slots against every centre (`score.py`) rather than
  decoding RS directly. RS supplies the spread and distance; direct erasure
  decoding (`complete_symbols`) needs `k` *intact* groups, and groups span
  questions (ADR 0002).

### Decisions

- **Crypto randomness.** Data keys and nonces come from `os.urandom`, the one
  deliberate exception to the seeded-RNG rule: seeded keys would be predictable.
  The source is injectable so tests stay deterministic.
- **Envelope design.** Fresh AES-256-GCM data key per envelope, wrapped by the
  vault's KEK (also AES-256-GCM). Associated data binds format, KEK id and
  purpose. `EnvVault` is the dev stub (`TRACE_KEK`, base64 of 32 bytes); M12 adds
  a real vault behind the same `Vault` protocol. Generate a dev key with
  `python -c "import base64,secrets;print(base64.b64encode(secrets.token_bytes(32)).decode())"`.
- **`cryptography==50.0.2`** pinned in core, resolved with wheels for Python 3.11
  and 3.12 on Windows alongside every other pin. No cipher is implemented here.

### Bugs the new codebook exposed (fixed)

- `leak` rebuilt one centre as `assign(paper, centre + 1)[centre]`. That was
  only valid for the per-centre mixed-radix code; RS codewords depend on the
  total centre count. `leak` now takes `--centres` (default 1000, as `generate`).
- `demo`/`dashboard` reused any codebook already in `out/`, including a pre-M5
  one, and reported the old behaviour. They now refuse a codebook that is not the
  current demo codebook and say to delete `out/`; they never overwrite it.
- `tasks.ps1` was an advanced script (because of `[Parameter()]` attributes),
  so forwarded arguments starting `--out` collided with `-OutVariable` /
  `-OutBuffer`. It now uses a plain `param()` and passes `$args` through.

### Open items

- **Codebook versioning.** Codebook files carry no scheme or version metadata,
  so staleness is detected only by comparing with the demo codebook. CLAUDE.md
  requires every trace to record the codebook version: add a versioned header
  (M12).
- **Rendered papers are codebook-equivalent.** Each `out/centre_*.txt` reveals
  that centre's codeword, so the full set reveals the codebook even when it is
  encrypted. Treat rendered papers as secrets: delete after printing, and
  encrypt or keep them in the service in M12.
- **Plaintext by default.** `--encrypt` is opt-in; flip the default once a
  vault is part of normal setup (M12).
  *Fixed for `generate` (2026-10-17, brought forward from M12):* the audit
  found rule 5 violated in practice (`out/` held a plaintext codebook and 1,000
  codebook-equivalent papers; that directory was sent to the Recycle Bin).
  `generate` now seals by default, refuses to run without `TRACE_KEK`, and
  `--plaintext` opts out with a warning naming the file. `demo` and
  `python -m api.dashboard` now follow the same rule for their demo codebook in
  `out/` (`--encrypt` is gone; their `--plaintext` warns, naming the file and
  whether it was written or reused). *Still open:* every entry point writes the
  rendered papers (`out/centre_*.txt`) in clear, and each is
  codebook-equivalent (open item above).

---

## M5.5 — consistency gate: a live safety bug (2026-10-16)

*Revised twice after review: the collusion outcome is `MULTI_SOURCE_SUSPECTED`
(formerly `COLLUSION_SUSPECTED`), raised whenever the gate eliminates every
centre above the floor. It names nobody. The pair hypothesis has been demoted to
an opt-in `trace --hypotheses` (see "Named pair demoted" below).*

**The bug.** The margin-only rule (M3–M5) named innocent centres under
collusion, and the "0% false identification" reported until now covered
single-source leaks only. RS decoding was never in the trace path, so nothing
"fell back": the slot score was the only decision, and it measures a different
distance from the one RS protects ([ADR 0003](docs/ADR/0003-decision-rule-under-collusion.md)).
Over 1,000 centres the minimum symbol distance is 6 but the minimum slot
distance is 8, and colluders can mix slots inside a symbol.

### Before / after (minority-strategy collusion, 6 questions, retype, 3% typos, 200 leaks per row)

| centres in leak | innocent identified, before | innocent identified, after | after: `MULTI_SOURCE_SUSPECTED` | `--hypotheses` pair = exact coalition | `--hypotheses` pair incl. an outsider |
|---|--:|--:|--:|--:|--:|
| 1 (single source) | 0 | 0 — all 200 identified | **0** | – | – |
| 2 | 11 (5.5%) | **0** | **200** | 98 | 0 |
| 3 | 94 (47%) | **0** | **200** | 0 | 8 |
| 4 | 110 (55%) | **0** | **200** | 0 | 1 |
| 5 | 100 (50%) | **0** | **200** | 0 | 2 |

The multi-source signal fired on every colluded leak (800/800) and on no
single-source leak (0/200). No verdict names a centre. The two pair columns
describe only the opt-in hypothesis: all 98 correct pairs were the unique
minimal pair, and the other 102 2-centre leaks have no unique pair, so
`--hypotheses` prints none for them.

Before the change, false margins reached 12.0 (random-mixing probe: 5–6% of
2-centre and 21–38% of 3–5-centre leaks named an innocent). Raw data:
`eval/out/results_collusion.csv`.

### Calibration (procedure in ADR 0003; rerun on every reader change)

- **Misread rate:** 0 misreads in 104,026 read slots, so the 95% upper bound is
  2.88e-5 and the tolerance is 0 at budget 1e-3. With only 6,969 reads the bound
  was 4.3e-4, giving tolerance 1 and a floor of 18. More evidence earned the
  tighter value.
- **Read floor:** with the gate and no floor, innocents were identified at up to
  10 slots read (seeds 1 and 7) and never from 11 up: 0 in 5,804 leaks, 95% upper
  bound 0.052%. `MIN_READ_SLOTS = 11`. Raw data: `eval/out/results_floor.csv`.

### Costs and limits (honest accounting)

- **Thin leaks no longer name a centre.** Single-source identification: 2
  questions 91% → 0% (they carry at most 10 slots), 3 questions 99.5% → 82%, 4+
  still 100%. For 2 questions this is a capacity bound, not a tuning shortfall
  (see below).
- **Measured, not proved.** Sample paper, 1,000 centres, one reader. The only
  proved collusion bound remains the provable mode (Tardos).
- The existing 12-line-leak tests pass at exactly 11 slots read, right on the
  floor.

### Named pair demoted to an opt-in hypothesis (review, 2026-10-16)

The second revision of M5.5 attached the unique minimal pair to the
`MULTI_SOURCE_SUSPECTED` verdict. That pair is now **out of the verdict**, and
the outcome names nobody. The computation survives as `unique_pair_hypothesis()`
in `examfp/decode/score.py`, and only `trace --hypotheses` runs it. When it finds
a pair, the trace prints the pair with its measured accuracy (98 correct of 109,
every wrong one from a leak involving 3 or more centres). It also states that
the system cannot distinguish a two-centre leak from a larger one, so either
named centre may have taken no part.

**Why it was demoted.** All 11 wrong pairs came from leaks involving 3–5
centres (8, 1 and 2 respectively), and every one of them was a *pair*. Refusing
to name sets of 3 or more therefore removed none of them. A unique pair is wrong
exactly when the leak involved more centres than the pair, and nothing in the
observation separates that case from a genuine two-centre leak. No rule can
filter that risk out; the output can only disclose it. So the pair is shown only
on request, and always with the measured error.

The printed 98/109 lives in `PAIR_HYPOTHESIS_CORRECT` and `PAIR_HYPOTHESIS_NAMED`.
`tests/eval/test_bench.py::test_printed_pair_accuracy_matches_the_benchmark`
reruns the benchmark (seed 2) and fails if the measured counts drift from the
printed ones.

**Verdict text.** `MULTI_SOURCE_SUSPECTED` used to read as an assertion of
collusion. It now says that no single centre in this codebook explains the
observed slots. It lists three possible causes: (1) the leak combines papers from
more than one centre; (2) misreads beyond the gate tolerance; (3) the leak comes
from a paper outside this codebook. It ends with "No centre is named."

### 2-question leaks: a capacity bound, not a shortfall

Slots carry unequal information, so the natural refinement of the slot floor is
a floor on bits read (Σ log2 alphabet over the read slots). Bits per question on
the sample paper are: q1 7.39, q2 8.89, q3 6.39, q4 4.81, q5 8.89, q6 7.39,
q7 6.81, q8 8.89.

- **The required level is at least 18.59 bits.** Seed 7 produced a false
  identification at 18.59 bits read (gate on, no floor). A bits floor identifies
  only strictly above its value, so to exclude that case it must be at least
  18.59 (`suggest_bits_floor`). The required level is a maximum over the false
  identifications observed, so more trials can only raise it.
- **No two questions reach it.** The most informative pair, q2 + q5 (the MCQs),
  carries **17.79 bits**. That value is exact, not sampled.
- **So no entropy-based floor can recover 2-question leaks.** The information is
  not present in the observation. In raw capacity, two questions exceed the
  log2 1000 ≈ 9.97 bits needed to index 1,000 centres. What they lack is enough
  information to rule out a hybrid of other centres. Better tuning cannot change
  that; only a paper that carries more information per question could.
- **Scope:** the sample paper, 1,000 centres, and the current fuzzy reader. A
  different paper design or codebook size needs this rechecked.

### Open items

- **Bits-based floor for 3+ questions — measured, not deployed (M11).** Seed 1
  suggests identifying above 16.29 bits, but seed 7 shows 3 false IDs above that
  line in 3,056 leaks. The threshold is unstable; seed 7 alone needs 18.59.
  Predicted gain at 18.59 bits: single-source 3-question leaks 80–81% → 90–92%;
  2-question leaks stay at 0% (bound above). `MIN_READ_SLOTS` stays 11. M11 must
  stabilise the threshold with far more trials before any adoption.
- **Pair accuracy above 24 slots — retracted (2026-10-17).** On the pre-M6
  paper, seed 1's floor sweep showed `--hypotheses` pairs that included an
  outsider only at 11–23 slots read (75 among 2,315 multi-source results at ≥ 11
  reads). This note read that as a hint the pair might be reliable on larger
  leaks. **The same sweep on the M6 paper contradicts it:** seed 1 (4,000 leaks,
  crops 1–8, gate with no floor) has outsider pairs at **24 and at 25 reads**,
  one each. That is 2 among the 921 multi-source results at ≥ 24 reads, and 73
  among 2,310 at ≥ 11 (`eval/out/results_floor.csv`). There is no read count
  above which the pair can be trusted. It stays an opt-in hypothesis printed with
  its measured error.
- **Rename `MULTI_SOURCE_SUSPECTED` in M7 (proposal).** The outcome means "no
  single centre in this codebook explains the observed slots", and it has three
  causes. The name asserts only the first. M7's OCR recalibration will make cause
  (2), misreads beyond the tolerance, more likely, and M7 touches this code
  anyway. Rename then, e.g. to `NO_CONSISTENT_SOURCE`. Kept as-is for now to
  avoid churn across the enum, CLI, bench CSV and CLAUDE.md rule 4.
- **Contract wording on pairs.** *Fixed:* CLAUDE.md rule 4 now matches the code.
  A verdict names at most one centre, and only on `IDENTIFIED`. A multi-source
  verdict names nobody. A ranking is shown only beside `IDENTIFIED` or on
  request. Pair hypotheses are opt-in and always carry their measured accuracy.
  `tests/test_repo_hygiene.py` checks that the rule lists exactly the `Outcome`
  values, so the M7 rename cannot leave the contract behind.
- **Ranked list on non-identifying outcomes.** *Fixed.* The trace, the demo and
  the dashboard printed the top 5 centres with scores for every outcome, which
  defeated the gate at the display layer: on a two-centre full-paper leak, the
  default `MULTI_SOURCE_SUSPECTED` output listed both colluders at ranks 1–2 and
  three innocent centres below them. A reader would take rank 1 as the verdict.
  Now `show_ranking()` in `examfp/cli.py` allows a ranking (and the margin) only
  beside an `IDENTIFIED` verdict, or under `trace --hypotheses`, where it is
  labelled "not a verdict". The dashboard uses the same rule. Tests assert that no
  centre identifier appears in the default output of a `MULTI_SOURCE_SUSPECTED`,
  `NO_MATCH` or `INSUFFICIENT` trace.
- **Contract.** *Fixed:* CLAUDE.md now promises a measured false-identification
  rate (practical mode) or a provable collusion bound (provable mode).

---

## M6 — Fairness checker (2026-10-17)

**Built.** `examfp/fairness/`: `answers.py` (SymPy, exact `Rational`),
`bands.py` (the frozen band validator, wrapped, plus the step rule of
[ADR 0004](docs/ADR/0004-step-count-rule.md)), `nli.py` (the pinned
cross-encoder, lazy, local files only), `units.py` (unit table),
`readability.py`, `check.py` (`FairnessChecker`; one `FairnessReport` per
variant with per-check pass/fail and reason), `pins.py` (model id, revision,
files). `.\tasks.ps1 fetch-models` is the only download; `.\tasks.ps1 fairness`
runs the local acceptance and `eval/nli_reliability.py`.

**Dependencies.** SymPy 1.14.0 is a base dependency; the `fairness` extra holds
torch 2.14.1, transformers 5.19.0, tokenizers 0.23.3, sentencepiece 0.2.2 and
wordfreq 3.1.1. The whole pinned set, all extras together, resolves with wheels
only for Python 3.11 and 3.12 on Windows (83 packages each; 74 / 73 at M4). The
revision ships `tokenizer.json`, so no protobuf is needed. A `.[dev]`-only venv
(CI's profile: SymPy present, no torch, transformers or wordfreq) is lint-clean
and passes 371 tests with `local_model` deselected.

| slot | channel | checks, in order |
|---|---|---|
| unbanded text | wording | numbers identical → NLI both ways → readability (stop at first failure) |
| unit form | unit form | numbers identical → unit table → readability |
| banded group | numeric | SymPy answer, digits, trivial; then steps, only for a valid band member with the right answer |
| option order | option order | same options, answer letter on the correct text |

A check that did not run is recorded as not run and counts as not passed. The
separation is proved in CI: a raising NLI backend for every numeric and
unit-form variant and for U11; a spy showing every pair the model saw has
identical numbers and reference numeric groups; SymPy and the band rules
patched to raise during wording checks.

### Owner rulings in this session

- **Step rule** (ADR 0004): equal positional operations AND equal carries,
  borrows or non-zero remainders in the canonical written method; per-operation
  definitions, addition/subtraction included. Every carry counts (the leftmost
  column's and those in the addition of partial products); the multiplier is
  the second operand in fill order.
- **After the first acceptance run:** keep the model and threshold 0.5, record
  the failure, and fix the paper; judge unit forms with a deterministic unit
  table instead of NLI.

### Acceptance — not met (recorded on the owner's decision)

`cross-encoder/nli-deberta-v3-small@fa2804872c3b4bd748f38c0185cc85775361e735`,
threshold 0.5 both ways, CPU (AMD64 family 25, 6 torch threads), 2026-10-17:

| criterion | target | result |
|---|---|---|
| false acceptances, 11 unfair entries | 0 | **0**, each failing exactly its labelled rule |
| false rejections, 29 fair entries | ≤ 2 | **3** (F11, F13, F14): **not met**. 5 before the unit table (also F21, F22) |
| lazy load | yes | yes: construction touches neither disk nor torch |
| one pair scored on CPU | < 300 ms | median 76 ms, max 95 ms (21 pairs); first call 20 s cold (imports + load) |
| sample paper passes every check | yes | yes, 414 reports |

All three rejections come from NLI, and no threshold rescues them:

| entry | candidate (reference) | ref → cand | cand → ref |
|---|---|--:|--:|
| F11 | "Show all your steps." ("Show your working.") | 0.009 | 0.881 |
| F13 | "Show each step of your working." | 0.003 | 0.972 |
| F14 | "Tick the correct box." ("Choose one option only.") | 0.524 | 0.034 |
| U09, unfair | "Give your answer in square metres." | 0.000 | 0.803 |
| U10, unfair | "Identify a value other than" | 0.008 | 0.827 |

The fair rejections share the unfair entries' one-way pattern: F13's weaker
direction (0.003) is below U10's (0.008). Entailment is stricter than "asks the
same question": a more specific instruction entails the general one, not the
reverse. F14 is the hard case the fixture anticipated. Nothing was tuned on the
fixture and no label was revised (now a CLAUDE.md rule). The pinned set
{F11, F13, F14} is a test, and the budget is a strict xfail that fails loudly
once it passes.

**Unit forms.** The DeBERTa tokenizer maps ² and ³ to `[UNK]`, so the model
cannot see cm² or g/cm³; it rejected both of q3's alternatives ("sq cm"
0.002 / 0.005). `units.py` holds exactly the forms the paper and the fixture
use; matching is exact; an unlisted form fails closed.

### Model reliability (decision 7; M9's baseline)

- **Held-out set** (`eval/nli_reliability.json`, 60 pairs, labelled and
  committed before any scoring): **55/60 = 91.7% (95% CI 81.6–97.2%)**.
  Equivalent 27/30 (E03, E09, E25 rejected); changed units 7/7; constraint 8/8;
  reversed relationship 7/7; changed quantity **6/8**.
- **Two false acceptances**: N06 circumference → area (0.834 / 0.625) and N08
  factors → multiples (0.991 / 0.989). The NLI gate can pass a wording variant
  that asks for a different quantity. The sample's wording slots (lead verbs,
  closings, intros) sit away from the quantity asked, so the exposure is small
  here, but NLI alone is not safe for a slot that names the quantity.
- **Fixture agreement**, on the 20 wording entries the checker sends to the
  model: 17/20 (85.0%, CI 62.1–96.8%). Unit forms, shown for reference only:
  3/5.
- **Context sensitivity:** "Show your method." passes in q3 (F12: 0.647 / 0.857)
  but fails in q1, q6 and q7.

### Sample paper changes (decisions 3 and 4)

| slot | change | alphabet |
|---|---|---|
| q3 dims | removed 20 × 72 (1 carry) and 32 × 45 (4 carries) | 7 → 5 |
| q7 cost | removed 72 × 20 and 45 × 32 | 7 → 5 |
| q4 pctval | 20% of 300 and 25% of 240 (one step) → 12% of 500, 48% of 125 | 7 |
| q1, q6, q7 intro | place-name swaps → same-place paraphrases (F16–F18) | 2 |
| closings of q1, q3, q4, q6, q7 | "Show all your steps." → "Include your working." | 2 |
| closings of q2, q5, q8 | "Tick the correct box." → "Select only one option." | 2 |

- **Why 5 for q3 and q7:** exactly five operand sets of 1440 tie with 16 × 90
  under the step rule ({16, 90}, {18, 80}, {24, 60}, {30, 48}, {36, 40}), and the
  reader identifies a group by its *set* of numbers, so the swapped F28 and F29
  (fair, and passing) cannot be added beside their originals.
- **Replacement wording:** candidate lists were fixed before scoring, and the
  first candidate passing in every question that uses the closing was taken:
  "Show your method." failed q1, q6, q7; "Show your work." passed;
  "Select only one option." passed.
- **Finding: a near-prefix variant breaks the reader.** "Show your work." is
  nearly a prefix of "Show your working."; under typos the fuzzy reader took
  the reference for it 6 times in 104,048 reads (all six misreads were this).
  Following ADR 0003 for that paper would have set tolerance 1 and floor 16
  (seed 7), cutting 3-question leaks to 0%, 4-question leaks to 47.5%, and the
  pair hypothesis to 6/125. A second list fixed in advance ("Show your
  calculations.", "Include your working.", "Show how you worked it out.") gave
  "Include your working.", which passes all five (≥ 0.99 both ways) and reads
  with 0 misreads. **This choice was made after measuring both papers**, so the
  numbers below come from a paper picked partly on the bench. Authoring rule
  from now on: no variant may be a near-substring of another in the same slot.
- **Fixture `approved` flags:** F11 and F14 → false; F15–F18, F26, F27 → true.
  No label changed.

### Published numbers that moved (`.\tasks.ps1 bench`)

| measure | before M6 | after M6 |
|---|---|---|
| payload / group bits | 59.5 / 14.04 | 58.5 / 13.07 |
| durable fraction | 68.1% | 67.5% |
| q3 / q7 bits | 6.39 / 6.81 | 5.91 / 6.32 |
| RS shape | n = 7, k = 2 | n = 7, k = 2; every group's membership changed (ADR 0002) |
| RS, 3 questions identified | 82.0% | 80.0% |
| RS, 4–8 questions | 100% | 100% |
| RS, early / middle thirds, 3 questions | 99.0 / 98.0% | 99.5 / 97.0% |
| false identification, single source | 0% | 0% in every cell |
| misreads (6,000 leaks) | 0 / 104,026 | 0 / 104,098; bound 2.88e-5, tolerance 0, unchanged |
| `MIN_READ_SLOTS` | 11 | 11: false IDs up to 10 reads (seeds 1 and 7), 0 in 5,812 leaks at ≥ 11 |
| innocents identified, coalitions 1–5 | 0 | 0 |
| pair hypothesis (`--hypotheses`) | 98 / 109 | 117 / 126; all 9 wrong from 3- or 4-centre leaks |
| old margin-only rule, 2-centre leaks naming an innocent | 5.5% | 11.5% |
| bits floor (not deployed) | seed 1 16.29, seed 7 18.59 | seed 1 17.79, seed 7 16.29 |
| mixed-radix baseline: constant positions / 6 questions | 20 / 91.0% | 19 / 87.0% |

- **The 2-question capacity bound still holds, now with equality.** Seed 1
  produced a false identification at 17.79 bits, exactly what q2 + q5 carry;
  a bits floor identifies only strictly above, so 2-question leaks stay at 0%.
- A bits floor at 17.79 would lift single-source 3-question leaks from 82–84%
  to 98–99% (seeds 1 and 7). Still M11's open item, not deployed.
- `out/` from earlier milestones holds a pre-M6 codebook; `demo` refuses it and
  says to delete `out/`.

### A stronger model, chosen on held-out data (2026-10-17)

**Approved by the owner before any download:**
`cross-encoder/nli-deberta-v3-base@6c749ce3425cd33b46d187e45b92bbf96ee12ec7`,
the same seven files as the small pin (`model.safetensors`, 737.7 MB; config
and tokenizer files only; no ONNX, no `pytorch_model.bin`). Its tokenizer files
are byte-identical to the small model's, so ² and ³ are still `[UNK]` and unit
forms stay with the unit table. Pinned as `NLI_BASE` beside `NLI_PIN`, which is
unchanged; `.\tasks.ps1 fetch-models --model base` fetches it.

**Choice rule, fixed by the owner before any scoring.** The rule uses the
60-pair held-out set only (`python -m eval.nli_reliability --model small
--model base --held-out-only`), at threshold 0.5 both ways. Base is chosen only
if it has **false acceptances ≤ 2 and accuracy ≥ 55/60, with at least one of the
two strictly better**. A tie on both, or a trade-off, keeps small. The fixture
is then run once (`.\tasks.ps1 fairness`) with the chosen model. Nothing on the
fixture feeds back into the choice or the threshold.

**Result: base is not chosen; small stays; M6 stays open.** Held-out set,
threshold 0.5 both ways, CPU, 2026-10-17:

| model | accuracy | 95% CI | false acc. | false rej. | wrong |
|---|---|---|--:|--:|---|
| small `@fa2804872c3b4bd748f38c0185cc85775361e735` | **55/60 = 91.7%** | 81.6–97.2% | 2/30 | 3/30 | E03, E09, E25; N06, N08 |
| base `@6c749ce3425cd33b46d187e45b92bbf96ee12ec7` | 54/60 = 90.0% | 79.5–96.2% | 2/30 | 4/30 | E03, E09, **E18**, E25; N08, **N29** |

Base ties on false acceptances and is one pair worse on accuracy, so it fails
"accuracy ≥ 55/60". Small reproduced its recorded numbers exactly.

- **Base rejects the same one-way pairs, plus one more.** In E09, E18 and E25
  the candidate entails the reference (0.94–0.998) but not the reverse
  (0.004–0.179). E18 is "Round 4.678 to two decimal places." vs "Give 4.678
  correct to two decimal places." A bigger NLI model is no more lenient about
  specificity, which is the pattern behind F11 and F13.
- **Base accepts a reversed division.** N29 is "Divide 84 by 12." vs "Divide 12
  by 84." (0.943 / 0.991). Both use the same numbers, so the numbers rule passes
  it and NLI is the only guard. Small rejects it. Base fixes N06 (circumference
  → area), and both accept N08 (factors → multiples).
- **The set cannot separate the two.** One pair apart, with intervals that
  almost coincide. The rule's tie-break keeps the incumbent, which is the
  smaller and faster model.
- **Latency was not the obstacle.** One pair on CPU (AMD64 family 25, 6 torch
  threads, 21 calls): small median 74 ms (max 93), base median 152 ms (max 198).
  Both are under 300 ms.

**The one fixture run, with the chosen model (small),** `.\tasks.ps1 fairness`:
unchanged. 0 false acceptances, each unfair entry failing exactly its labelled
rule. False rejections {F11, F13, F14}: **3 against a budget of 2**, still the
strict xfail. Lazy load and the 300 ms test pass, the sample paper passes every
check, and fixture agreement is 17/20. **Base was not run on the fixture.** The
protocol runs it only with the chosen model, and its fixture result would invite
choosing on the fixture.

### Closing M6: three structural rules (2026-10-17)

The owner asked for three changes, tests first: variant separation, a structural
guard on the quantity asked, and instruction phrasing moved to a curated table.
Then: mark M6 done if the acceptance passes, otherwise stop and report without
tuning anything. **It does not pass: 9 false rejections against a budget of 2.**
Details and basis are in [ADR 0004](docs/ADR/0004-step-count-rule.md),
parts 2–4.

**1. Variant separation** (`separation.py`, the `separation` check on every
text-read slot). Sweep `eval/separation.py`: 1,602,000 reads (seed 0). The 23
text-read slots were paired with synthetic competitors at exact edit distances
1–12, plus prefix and containment shapes, and read under the bench's attack.

- Edit family misread rate by distance: 0.57%, 0.18%, 0.07%, 0.02%, 0.03%,
  0.004% for d = 1–6; 0 at d = 7–8; 1 and 14 misreads (of 69,000 reads each) at
  d = 9 and 10; 0 at d = 11–12.
- Prefix pairs misread at 0.34–4.95% (d ≤ 8; 6.6% for the single pair at
  d = 9), containment pairs at 0.54–9.0% (by edit distance).
- The rule fixed before the run gives **11**: 0 in 138,000 reads at d ≥ 11, 95%
  bound 2.17e-5 ≤ `MISREAD_RATE`.
- The tail at d = 9–10 is a short variant nearly embedded in a long one ("cm²"
  in "xklbccwm²xfjc"; one typo makes it verbatim), which edit distance does not
  measure.
- **Owner decision:** extend the structural rule from *prefix* to *any
  containment* (adopted). Record 11 but **do not adopt** it (deployed minimum 1,
  the distance rule off): at 11, 17 of the paper's 29 text-variant pairs fail
  (all leads at d = 7–8, all working closings at d = 7, four short unit pairs),
  and fixture false rejections would go from 9 to 16.
- The paper's own pairs read clean except q4 "Show your working." / "Include
  your working." (d = 7, no containment): **1 misread in 4,000**. The M6 pair
  "Show your work." misread 2 in 4,000.

**2. The ask is a radical** (`ask.py`, the `ask` check on NLI-judged wording).
The ask region runs from the first sentence that opens the ask (a table command,
a literal command, or "?") to the end of the question. A wording slot must sit
before it, in the stem, or the model is not consulted; with no locatable ask,
the check fails closed. Held-out N06 and N08 rebuilt as slots are rejected
before NLI. The sample's only NLI-judged slots, its three intros, sit in the
stem. **Limit:** relationships and data in the stem ("Asha is 4 years older
than Ravi") are radicals the rule does not cover; NLI and the numbers rule
still guard them.

**3. Instruction phrasing** (`instructions.py`, the `instruction` channel).
The category is the command, working instructions and option-choice phrasing
that neither name nor constrain the quantity asked. The table is exactly the
sample paper's instruction vocabulary, four classes and eight phrasings, and a
test pins it to the paper: nothing came from the fixture. An unlisted phrasing
fails closed, so NLI is never consulted for instruction slots.

- **Held-out set on open question prose alone** (E09, the one instruction-only
  pair, removed by a rule fixed in code before scoring): **55/59 = 93.2% (95% CI
  83.5–98.1%)** against 55/60 = 91.7%. The same 55 correct; the pair removed
  was one of the model's errors. **This is not an improvement in model quality:
  the table added coverage, not model quality.** False acceptances stay 2/30
  (N06, N08); part 2's ask rule, not the model, now keeps those out of a slot.

**Acceptance** (`.\tasks.ps1 fairness`, nli-deberta-v3-small@fa28048, threshold
0.5, CPU, 2026-10-17):

| criterion | result |
|---|---|
| false acceptances, 11 unfair | **0**; each caught by its labelled rule (U10 and U11 also fail `separation`) |
| false rejections, 29 fair | **9**: F01, F03, F04, F07, F09 (command synonyms the paper does not use), F11, F12, F13, F14 (closings it does not use), all by the instruction table; was 3 |
| lazy load, < 300 ms per pair | pass |
| sample paper passes every check | pass |
| fixture entries decided without the model | 37 of 40; only the three stem intros (F16–F18) reach NLI, which accepts all three |

Every rejection is now a fail-closed table miss, not a model error. The budget
can be met only by listing more phrasings, an owner decision about coverage.
Adding the rejected fixture phrasings themselves would be tuning on the
fixture. **M6 stays `[~]`.** No fixture label was touched, and no `approved`
flag changed (the paper did not change).

*Correction to the closing session's question:* I first reported that 22 of the
paper's 29 pairs fall below 11; the count is 17, now pinned by
`tests/eval/test_separation_sweep.py`.

### Fairness is now part of authoring (2026-10-17)

The audit found the checker outside the authoring path: `generate` never called
it, so a paper that failed it could still be generated and printed. `generate`
now runs `FairnessChecker.check_paper` after the vault check and before writing
anything. Any failing variant, or a checker that cannot run (model not fetched,
extra not installed), stops it with each failure listed. `--skip-fairness` is
the explicit opt-out, and it prints every skipped check by channel with variant
counts. The checks per channel live in `examfp.fairness.check.CHECKS`, which a
test keeps equal to what the checker runs. On the sample paper, with the real
model: all 414 variants pass, about 35 s with a cold model load.

### Finding: the sample paper carries fingerprints on features CBSE papers do not have (2026-10-17)

Building the instruction table from a domain source (consolidation session, step
4) turned up a finding larger than the table. **Real CBSE board papers contain
no per-question working instruction, and their MCQs have four options with
section-level choice wording.** So **8 of the sample paper's 31 positions** (five
"Show your working." closings and three option-choice closings) sit on a textual
feature that does not exist in the deployment target. Its three five-option MCQs
(alphabet 5! − 1 = 119) do not match the target either (4! − 1 = 23). These
are **invented carriers, not unlisted variants**. Not fixed here: the next
session rebuilds the paper.

**Source.** CBSE Class X main examination 2025, downloaded 2026-10-17 with owner
approval from `www.cbse.gov.in/cbsenew/question-paper/2025/X/`:

| archive | bytes | SHA-256 |
|---|--:|---|
| `041_Mathematics_Standard.zip` | 54,529,382 | `438fc0ef5e02bbf513d0da090c7846e64bd631d595f48eb919e1ba3dcfd69ebf` |
| `086_Science.zip` | 43,732,463 | `5e288459ad2558db9b6ee2fa652c123e1842047daaa0452133d6d365d2dc426d` |

- **What was read:** 18 papers with a text layer (Mathematics 30/1–30/3 and
  Science 31/1–31/3, three sets each). Sets 4–6 and the visually-impaired
  versions are scanned images and were not read (no OCR). Only the English text
  was read; the Hindi text layer does not decode.
- **What could not be used:** `cbseacademic.nic.in`'s sample papers, because
  its TLS certificate expired on 2026-10-17. No official state-board site
  exposed papers, so the source is CBSE alone.
- **Method:** text extracted with pypdf. Sentence openers were counted first,
  with no word list, to find the commands the papers use. Each command was then
  counted wherever it opens a clause (sentence start, after punctuation, or
  after "then", "hence", "and", "also", "so").
- **Reproducibility:** the extraction scripts were scratch tools run from
  `%TEMP%` and are not committed. The counts reproduce from the two archives by
  the method above; the rebuild session should commit the extraction tool with
  the new table.

**Command frequencies** (clause-initial occurrences; papers containing it, of 18):

| command | count | papers | | command | count | papers |
|---|--:|--:|---|---|--:|--:|
| Find | 116 | 13 | | Justify | 16 | 9 |
| Write | 58 | 9 | | Determine | 12 | 10 |
| Name | 35 | 9 | | Identify | 12 | 7 |
| State | 34 | 9 | | Show | 11 | 9 |
| Prove | 34 | 9 | | List | 10 | 6 |
| Give | 33 | 10 | | Mark | 8 | 6 |
| Select | 32 | 18 | | Mention | 4 | 4 |
| Draw | 29 | 9 | | Define, Illustrate, Observe, Match, Choose | 3 each | 3 each |
| Explain | 23 | 9 | | Differentiate, Describe | 1 each | 1 each |
| Calculate | 17 | 10 | | | | |

**Zero counts — evidence, not gaps.**

- **"Work out": 0. "Write down": 0.** Also 0: Evaluate, Compute, Solve,
  Verify, Suggest, Predict, Complete, Fill, Express, Obtain, Construct, Tick.
- The sample paper's lead variant "Work out" (five questions) and the fixture's
  fair "Write down" (F09) are absent from the target.
- **No per-question working instruction occurs in any of the 18 papers.** No
  sentence asks for working. "steps" and "method" appear only as subject
  content ("Write the main steps to culture yeast", "State in brief the method
  of preparation of …").
- **Option choice is section-level and four-option only.** "Select and write
  the most appropriate option out of the four options given for each of the
  questions …" appears at the head of Section A in 9 papers. The
  assertion–reason instruction "Select the correct answer to these questions
  from the codes (A), (B), (C) and (D) as given below." appears in all 18.
  There is no per-question closing such as "Choose one option only."

**What a CBSE-sourced table would do** (simulated in memory, not adopted). The
table: compute = Find / Calculate / Determine; state a fact = State / Name /
Identify / Give / Write / Mention; the two section-level choice sentences.

- **Fixture:** 8 false rejections (F02 and F05 "Work out", F09 "Write down",
  and F11–F15, whose closing slots would fall to the ask rule) and 0 false
  acceptances. U09 would then be caught only by the ask rule.
- **Sample paper:** it would fail 13 of its own variants, so `generate` would
  refuse it.
- **Held-out set:** unaffected (55/60; 55/59 on open prose).
- The instruction table in `examfp/fairness/instructions.py` is unchanged.

**Next session: rebuild the paper on CBSE structure.** That means four-option
MCQs with section-level choice wording, no per-question working closings, CBSE
command phrasings, and the instruction table rebuilt from CBSE vocabulary.
**Every capacity, identification and calibration number will then be
re-measured against the rebuilt paper.** That covers capacity and RS packing,
the k-sweep and region sweep, the ADR 0003 misread rate and floor, collusion and
pair accuracy, the separation sweep and the fairness acceptance. Committing the
benchmark output with run cards (consolidation step 7) waits for that, so it
does not freeze numbers about to go stale.

**Predictions to test on the rebuilt paper (not claims):**

1. *Dropping the wording closings raises the durable fraction above the current
   67.5%*, since wording is the fragile channel. On the current structure,
   removing the 8 closing slots and moving to four-option MCQs gives
   32.39 / 43.39 = **74.6%** by arithmetic.
2. *Four-option MCQs cut each option slot from log₂(119) = 6.89 to
   log₂(23) = 4.52 bits, so total payload should land near 38–42 bits rather
   than 58.51* (owner's estimate). Arithmetic on the current structure (−8.00
   bits for the closings, −7.11 for the three option slots) gives **43.39 bits**,
   slightly above that range. Landing in 38–42 needs about 1.4–5.4 more bits
   removed elsewhere in the rebuild.
   - Fewer symbols may also change the RS shape (n = 7 today; 1,000 centres
     need k = 2), so `rs_shape` must be re-checked.

### Open items

- **M6 acceptance is open:** 9 false rejections against a budget of 2, all
  fail-closed misses of the instruction table. Superseded in substance by the
  CBSE finding above: the paper is rebuilt first, then the table, then the
  acceptance is re-run. Closing needs an owner decision
  on the table's coverage, from a source other than the fixture (for example a
  published command-word glossary), or on the budget itself.
- **Separation by distance is open:** edit distance does not see near-embedding.
  A measure that does, such as the reader's partial ratio after a simulated
  typo, needs a design fixed before a fresh sweep. Typo-created variants
  elsewhere in the question ("₹" vs "cs") are a further mechanism, not covered.
- **The unit table's provenance:** it lists "km per hour" (F20), a fixture form
  the paper does not use, so it was not built from the paper alone as the
  instruction table is. Owner decision whether to drop it (F20 would become a
  false rejection).
- **Stem radicals** (data, relationships) are guarded only by NLI and the
  numbers rule.
- **NLI false acceptances** on held-out data (2/30, both "changed quantity"),
  now kept out of slots by the ask rule.
- **Readability tolerances** (words and syllables within 20%, rare words within
  1, Zipf < 3.0) were set before scoring and have not been calibrated; no
  fixture entry exercises readability as the deciding rule.
